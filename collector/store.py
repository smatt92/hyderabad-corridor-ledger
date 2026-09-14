"""Database access for the collector: Supabase REST with the service key.

The only collector module that reads or writes the database. It runs in
GitHub Actions and nowhere else; the service key never reaches Vercel.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime

PAGE_SIZE = 1000  # PostgREST's max-rows on Supabase
OUTCOME_TABLES = ("samples", "failed_samples")


class DatabaseError(RuntimeError):
    """A request to the database failed. Never contains the key."""


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


class Database:
    def __init__(self, url: str, key: str, timeout: float = 30.0):
        self.url = url.rstrip("/")
        self.key = key
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "Database":
        url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise DatabaseError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        return cls(url, key)

    def headers(self, content_type: str = "application/json") -> dict:
        headers = {"apikey": self.key, "Content-Type": content_type}
        if self.key.startswith("eyJ"):  # legacy JWT keys also go in Authorization
            headers["Authorization"] = f"Bearer {self.key}"
        return headers

    def raw(self, method: str, path: str, data: bytes | None = None,
            headers: dict | None = None) -> tuple[dict, bytes]:
        """Any request under the project URL. (lowercased response headers, body)."""
        req = urllib.request.Request(f"{self.url}/{path}", data=data, method=method,
                                     headers={**self.headers(), **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return {k.lower(): v for k, v in resp.headers.items()}, resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:500].decode(errors="replace")
            raise DatabaseError(f"{method} {path}: HTTP {exc.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise DatabaseError(f"{method} {path}: {exc}") from None

    def request(self, method: str, path: str, params=(), body=None, prefer: str | None = None):
        """A REST call. (response headers, parsed JSON body or None)."""
        query = "?" + urllib.parse.urlencode(list(params)) if params else ""
        headers = {"Accept": "application/json", **({"Prefer": prefer} if prefer else {})}
        data = None if body is None else json.dumps(body).encode()
        response_headers, payload = self.raw(method, f"rest/v1/{path}{query}", data, headers)
        return response_headers, json.loads(payload) if payload else None

    def select_all(self, table: str, params, order: str = "seq.asc") -> list[dict]:
        rows: list[dict] = []
        while True:
            _, page = self.request("GET", table, [*params, ("order", order),
                                                  ("limit", str(PAGE_SIZE)),
                                                  ("offset", str(len(rows)))])
            rows.extend(page or [])
            if len(page or []) < PAGE_SIZE:
                return rows


class Ledger:
    """What a collector run needs from the database."""

    def __init__(self, db: Database):
        self.db = db

    def count(self, table: str) -> int:
        column = "seq" if table in OUTCOME_TABLES else "id"
        headers, _ = self.db.request("GET", table, [("select", column), ("limit", "1")],
                                     prefer="count=exact")
        return int(headers.get("content-range", "*/0").rsplit("/", 1)[-1])

    def recorded_corridors(self, slot: datetime, corridor_ids: list[str]) -> set[str]:
        """Which of these corridors already have an outcome, sample or failure, for
        this slot. Naming the corridors lets the (corridor_id, scheduled_slot) index
        answer instead of a scan."""
        found: set[str] = set()
        for table in OUTCOME_TABLES:
            _, rows = self.db.request("GET", table, [
                ("select", "corridor_id"), ("corridor_id", f"in.({','.join(corridor_ids)})"),
                ("scheduled_slot", f"eq.{iso(slot)}"),
            ])
            found.update(row["corridor_id"] for row in rows or [])
        return found

    def attempts_between(self, start: datetime, end: datetime) -> int:
        """HTTP attempts spent in [start, end): the budget used.

        Each run counts the larger of two records, because each misses attempts the
        other keeps. Outcome rows miss the attempts behind an outcome that was never
        inserted (a duplicate slot, a failed insert). The run row misses a run killed
        before it finished, which never wrote its count."""
        by_run: dict[str | None, int] = defaultdict(int)
        for table in OUTCOME_TABLES:
            for row in self.db.select_all(table, [
                ("select", "collector_run,attempts"), ("requested_at", f"gte.{iso(start)}"),
                ("requested_at", f"lt.{iso(end)}"),
            ]):
                by_run[row["collector_run"]] += row["attempts"]
        for row in self.db.select_all("corridor_route_checks", [
            ("select", "collector_run,attempts"), ("checked_at", f"gte.{iso(start)}"),
            ("checked_at", f"lt.{iso(end)}"),
        ], order="id.asc"):
            by_run[row["collector_run"]] += row["attempts"]
        # probe mode: one row per attempt, made outside any collector run
        by_run[None] += len(self.db.select_all("probe_calls", [
            ("select", "id"), ("requested_at", f"gte.{iso(start)}"),
            ("requested_at", f"lt.{iso(end)}"),
        ], order="id.asc"))
        for run in self.db.select_all("collector_runs", [
            ("select", "id,attempts"), ("started_at", f"gte.{iso(start)}"),
            ("started_at", f"lt.{iso(end)}"),
        ], order="id.asc"):
            by_run[run["id"]] = max(by_run[run["id"]], run["attempts"])
        return sum(by_run.values())

    def quota_refused_since(self, start: datetime) -> bool:
        """Whether TomTom refused a call for quota at or after `start`, sample or road."""
        for table, key, moment in (("failed_samples", "seq", "requested_at"),
                                   ("corridor_route_checks", "id", "checked_at")):
            _, rows = self.db.request("GET", table, [
                ("select", key), ("error_class", "eq.quota_exhausted"),
                (moment, f"gte.{iso(start)}"), ("limit", "1"),
            ])
            if rows:
                return True
        return False

    def insert_responses(self, rows: list[dict]) -> None:
        """TomTom response headers worth keeping: see migration 0011."""
        if rows:
            self.db.request("POST", "tomtom_responses", body=rows, prefer="return=minimal")

    def route_state(self, corridor_ids: list[str],
                    since: datetime) -> tuple[dict[str, int | None], list[dict]]:
        """({id: route_polyline_length_m} for these corridors where the database holds them
        as verified, route checks since `since`). The polylines themselves are not read."""
        ids = f"in.({','.join(corridor_ids)})"
        _, rows = self.db.request("GET", "corridors", [
            ("select", "id,route_polyline_length_m"), ("id", ids), ("verified", "eq.true"),
        ])
        checks = self.db.select_all("corridor_route_checks", [
            ("select", "corridor_id,checked_at,error_class"), ("corridor_id", ids),
            ("checked_at", f"gte.{iso(since)}"),
        ], order="id.asc")
        return {r["id"]: r["route_polyline_length_m"] for r in rows or []}, checks

    def stored_route(self, corridor_id: str) -> dict:
        """The simplified stored road and its length, for comparing a refetch."""
        _, rows = self.db.request("GET", "corridors", [
            ("select", "route_polyline_simplified,route_polyline_length_m"),
            ("id", f"eq.{corridor_id}"),
        ])
        return rows[0]

    def probed_since(self, start: datetime, corridor_ids: list[str]) -> set[str]:
        """Probe mode: which of these corridors have an attempt at or after `start`."""
        _, rows = self.db.request("GET", "probe_calls", [
            ("select", "corridor_id"), ("corridor_id", f"in.({','.join(corridor_ids)})"),
            ("requested_at", f"gte.{iso(start)}"),
        ])
        return {r["corridor_id"] for r in rows or []}

    def probe_retries_and_refusals(self, start: datetime) -> list[dict]:
        """Probe attempts since `start` that were a 429 or a retry: enough to tell a 429
        that ended its slot from one that was retried."""
        return self.db.select_all("probe_calls", [
            ("select", "corridor_id,requested_at,attempt,http_status"),
            ("requested_at", f"gte.{iso(start)}"), ("or", "(http_status.eq.429,attempt.gt.1)"),
        ], order="id.asc")

    def insert_probe_calls(self, rows: list[dict]) -> None:
        if rows:
            self.db.request("POST", "probe_calls", body=rows, prefer="return=minimal")

    def probe_rows(self, start: datetime, end: datetime) -> list[dict]:
        return self.db.select_all("probe_calls", [
            ("select", "corridor_id,requested_at,attempt,http_status,latency_ms"),
            ("requested_at", f"gte.{iso(start)}"), ("requested_at", f"lt.{iso(end)}"),
        ], order="id.asc")

    def insert_route_check(self, row: dict) -> None:
        self.db.request("POST", "corridor_route_checks", body=row, prefer="return=minimal")

    def store_route_polyline(self, corridor_id: str, values: dict) -> bool:
        """False when the row already holds a road or is gone. A stored road is never
        written over; 0012's corridors_guard refuses it as well."""
        _, rows = self.db.request("PATCH", "corridors", [
            ("id", f"eq.{corridor_id}"), ("route_polyline", "is.null"), ("select", "id"),
        ], body=values, prefer="return=representation")
        return bool(rows)

    def start_run(self, run_id: str, sha: str | None) -> None:
        self.db.request("POST", "collector_runs", body={"id": run_id, "collector_sha": sha},
                        prefer="return=minimal")

    def finish_run(self, run_id: str, values: dict) -> None:
        self.db.request("PATCH", "collector_runs", [("id", f"eq.{run_id}")],
                        body={**values, "finished_at": iso(datetime.now(UTC))},
                        prefer="return=minimal")

    def _insert_once(self, table: str, row: dict) -> bool:
        _, inserted = self.db.request(
            "POST", table, [("on_conflict", "corridor_id,scheduled_slot")], body=row,
            prefer="resolution=ignore-duplicates,return=representation",
        )
        return bool(inserted)

    def insert_sample(self, row: dict) -> bool:
        """False when the slot already has a sample: a retry never makes a second row."""
        return self._insert_once("samples", row)

    def insert_failure(self, row: dict) -> bool:
        return self._insert_once("failed_samples", row)
