"""Row access for the read API.

Only tables in READABLE can be selected. samples is deliberately absent: the
read path serves precomputed rows and never touches raw measurements.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

READABLE = frozenset({
    "corridors", "interventions", "dataset_stats", "corridor_stats", "corridor_rankings",
    "metrics_daily", "metrics_day", "profile_hourly", "heatmap_weekly", "network_hourly",
    "pair_advantage_hourly", "intervention_audit", "chain_verifications", "export_manifest",
})
PAGE_SIZE = 1000  # PostgREST's row cap per request on Supabase

Filter = tuple[str, str, Any]  # (column, op, value); op: eq, gte, lte, notnull
Order = tuple[str, str]        # (column, "asc" | "desc")
Row = dict[str, Any]


class StoreError(RuntimeError):
    """The database could not be read."""


class Store(Protocol):
    sample: bool

    def select(
        self, table: str, filters: Sequence[Filter] = (), order: Sequence[Order] = (),
        limit: int | None = None,
    ) -> list[Row]: ...


def check_readable(table: str) -> None:
    if table not in READABLE:
        raise ValueError(f"table {table!r} is not readable by the API")


def postgrest_params(
    filters: Sequence[Filter], order: Sequence[Order], limit: int | None, offset: int = 0
) -> list[tuple[str, str]]:
    params = [("select", "*")]
    for column, op, value in filters:
        if op == "notnull":
            params.append((column, "not.is.null"))
        elif op in ("eq", "gte", "lte"):
            params.append((column, f"{op}.{value}"))
        else:
            raise ValueError(f"unsupported filter {op!r}")
    if order:
        params.append(("order", ",".join(f"{c}.{d}" for c, d in order)))
    if limit is not None:
        params.append(("limit", str(limit)))
    if offset:
        params.append(("offset", str(offset)))
    return params


class PostgrestStore:
    sample = False

    def __init__(self, url: str, key: str, timeout: float = 8.0):
        self.base = url.rstrip("/") + "/rest/v1/"
        self.key = key
        self.timeout = timeout

    def _get(self, table: str, params: list[tuple[str, str]]) -> list[Row]:
        request = urllib.request.Request(
            self.base + table + "?" + urllib.parse.urlencode(params),
            headers={"apikey": self.key, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise StoreError(f"could not read {table}") from exc

    def select(self, table, filters=(), order=(), limit=None):
        check_readable(table)
        if limit is not None:
            return self._get(table, postgrest_params(filters, order, limit))
        rows: list[Row] = []
        while True:
            page = self._get(table, postgrest_params(filters, order, PAGE_SIZE, len(rows)))
            rows.extend(page)
            if len(page) < PAGE_SIZE:
                return rows


def _matches(value: Any, op: str, target: Any) -> bool:
    if op == "notnull":
        return value is not None
    if value is None:
        return False
    return {"eq": value == target, "gte": value >= target, "lte": value <= target}[op]


class MemoryStore:
    """In-memory rows with the same filter semantics. Tests, and local fixture
    previews built from the real pipeline. Never used on a deployment."""

    def __init__(self, tables: dict[str, list[Row]], sample: bool = False):
        self.tables = tables
        self.sample = sample
        self.queried: list[str] = []

    @classmethod
    def from_dir(cls, directory: Path, sample: bool) -> "MemoryStore":
        tables = {p.stem: json.loads(p.read_text()) for p in sorted(directory.glob("*.json"))}
        return cls(tables, sample=sample)

    def select(self, table, filters=(), order=(), limit=None):
        check_readable(table)
        self.queried.append(table)
        rows = [r for r in self.tables.get(table, [])
                if all(_matches(r.get(c), op, v) for c, op, v in filters)]
        for column, direction in reversed(order):
            present = sorted((r for r in rows if r.get(column) is not None),
                             key=lambda r: r[column], reverse=direction == "desc")
            absent = [r for r in rows if r.get(column) is None]
            rows = present + absent
        return rows[:limit] if limit is not None else rows


def store_from_env() -> Store:
    if os.environ.get("SUPABASE_SERVICE_KEY"):
        raise RuntimeError(
            "SUPABASE_SERVICE_KEY is set: the read API must never hold the service key"
        )
    fixtures = os.environ.get("LEDGER_FIXTURE_DIR")
    if fixtures:
        if os.environ.get("VERCEL"):
            raise RuntimeError("fixture data can never be served from a deployment")
        return MemoryStore.from_dir(Path(fixtures), sample=True)
    return PostgrestStore(os.environ["SUPABASE_URL"], os.environ["SUPABASE_PUBLISHABLE_KEY"])
