"""Reading raw records and writing derived tables.

This is the only module in metrics/ that touches the network or the disk.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from metrics.exports import OBJECTS, csv_gz, manifest_row, open_dataset, parquet
from metrics.params import METHOD_VERSION
from metrics.raw import SOURCE_COLUMNS

PAGE_SIZE = 1000  # PostgREST's max rows per request on Supabase
WRITE_BATCH = 500
DATE_COLUMNS = {
    "day", "as_of", "window_start", "window_end", "detected_at", "segment_start",
    "effective_day", "pre_start", "pre_end", "post_start", "post_end",
}
CORRIDOR_METADATA = [
    "id", "code", "name", "pair_id", "role", "origin_name", "origin_lat", "origin_lon",
    "destination_name", "dest_lat", "dest_lon",
]


class Supabase:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.base = self.url + "/rest/v1/"
        self.key = key

    @classmethod
    def from_env(cls, read_only: bool) -> "Supabase":
        """Writes need the service key and run only in GitHub Actions. A read-only
        run can use the publishable key: every source table is public read."""
        key = os.environ.get("SUPABASE_SERVICE_KEY")
        if read_only:
            key = key or os.environ["SUPABASE_PUBLISHABLE_KEY"]
        elif not key:
            raise RuntimeError("SUPABASE_SERVICE_KEY is required to write derived tables")
        return cls(os.environ["SUPABASE_URL"], key)

    def headers(self) -> dict[str, str]:
        headers = {"apikey": self.key}
        if self.key.startswith("eyJ"):  # legacy JWT keys also go in Authorization
            headers["Authorization"] = f"Bearer {self.key}"
        return headers

    def request(self, method: str, path: str, body=None, prefer: str | None = None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method)
        for name, value in self.headers().items():
            req.add_header(name, value)
        req.add_header("Content-Type", "application/json")
        if prefer:
            req.add_header("Prefer", prefer)
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = resp.read()
        return json.loads(payload) if payload else None

    def get(self, table: str, params: dict) -> list[dict]:
        return self.request("GET", f"{table}?{urllib.parse.urlencode(params)}")

    def upload(self, bucket: str, path: str, payload: bytes, content_type: str) -> None:
        req = urllib.request.Request(
            f"{self.url}/storage/v1/object/{bucket}/{path}", data=payload, method="POST"
        )
        for name, value in self.headers().items():
            req.add_header(name, value)
        req.add_header("Content-Type", content_type)
        req.add_header("x-upsert", "true")
        with urllib.request.urlopen(req, timeout=300) as resp:
            resp.read()


def _bytea(value: str) -> bytes:
    """PostgREST returns bytea as a '\\x'-prefixed hex string."""
    if not value.startswith("\\x"):
        raise ValueError("unexpected bytea encoding from PostgREST")
    return bytes.fromhex(value[2:])


def load_hot_samples(db: Supabase) -> pd.DataFrame:
    rows, last = [], 0
    while True:
        page = db.get(
            "samples",
            {"select": ",".join(SOURCE_COLUMNS), "seq": f"gt.{last}", "order": "seq.asc",
             "limit": PAGE_SIZE},
        )
        if not page:
            break
        rows.extend(page)
        last = page[-1]["seq"]
    frame = pd.DataFrame(rows, columns=SOURCE_COLUMNS)
    frame["raw_gz"] = frame["raw_gz"].map(_bytea)
    return frame


def load_archive(directory: Path) -> pd.DataFrame:
    """Archive layout: *.parquet files whose columns include those of
    public.samples, with raw_gz stored as binary, exactly as in the table."""
    files = sorted(Path(directory).glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no .parquet files in {directory}")
    return pd.concat([pd.read_parquet(f, columns=SOURCE_COLUMNS) for f in files], ignore_index=True)


def load_corridors(db: Supabase) -> pd.DataFrame:
    columns = ["id", "cadence_s", "pair_id", "role"]
    rows = db.get("corridors", {"select": ",".join(columns), "order": "id.asc"})
    return pd.DataFrame(rows, columns=columns).rename(columns={"id": "corridor_id"})


def load_corridor_metadata(db: Supabase) -> pd.DataFrame:
    rows = db.get("corridors", {"select": ",".join(CORRIDOR_METADATA), "order": "id.asc"})
    return pd.DataFrame(rows, columns=CORRIDOR_METADATA).rename(columns={"id": "corridor_id"})


def load_interventions(db: Supabase) -> pd.DataFrame:
    rows = db.get("interventions", {"select": "id,corridor_id,effective_at", "order": "id.asc"})
    return pd.DataFrame(rows, columns=["id", "corridor_id", "effective_at"])


def to_records(frame: pd.DataFrame) -> list[dict]:
    out = frame.copy()
    for col in out.columns:
        if col in DATE_COLUMNS:
            out[col] = pd.to_datetime(out[col]).dt.strftime("%Y-%m-%d")
    return json.loads(out.to_json(orient="records", date_format="iso", date_unit="us"))


def replace_table(db: Supabase, table: str, frame: pd.DataFrame) -> None:
    """Delete every row, then insert the recomputed ones. Not atomic: a failed run
    leaves a partial table, which the next run replaces. Derived data only."""
    db.request("DELETE", f"{table}?method_version=not.is.null", prefer="return=minimal")
    records = to_records(frame)
    for start in range(0, len(records), WRITE_BATCH):
        db.request("POST", table, body=records[start:start + WRITE_BATCH], prefer="return=minimal")


def export_payloads(tables: dict[str, pd.DataFrame], corridors: pd.DataFrame):
    """(format, payload, content type, manifest row) for each open-dataset file."""
    frame = open_dataset(tables["metrics_daily"], corridors, tables["corridor_stats"])
    for fmt, payload, content_type in (
        ("csv", csv_gz(frame), "application/gzip"),
        ("parquet", parquet(frame), "application/vnd.apache.parquet"),
    ):
        yield fmt, payload, content_type, manifest_row(
            fmt, payload, frame, tables["dataset_stats"], METHOD_VERSION
        )


def publish_exports(db: Supabase, tables: dict[str, pd.DataFrame], corridors: pd.DataFrame) -> None:
    """Upload each file, then record it in export_manifest. A failed upload leaves
    the previous manifest row, which still describes the previous file."""
    for fmt, payload, content_type, row in export_payloads(tables, corridors):
        db.upload("exports", OBJECTS[fmt], payload, content_type)
        db.request("POST", "export_manifest", body=to_records(pd.DataFrame([row])),
                   prefer="resolution=merge-duplicates,return=minimal")
        print(f"export {fmt}: {row['n_rows']} rows, {row['n_bytes']} bytes, sha256 {row['sha256']}")


def record_chain_verification(db: Supabase) -> dict:
    result = db.request("POST", "rpc/record_chain_verification", body={})
    return result[0] if isinstance(result, list) else result


def exit_on_broken_chain(result: dict) -> int:
    summary = (f"chain walk: {result['rows_checked']} rows, head seq {result['head_seq']}, "
               f"{result['breaks']} breaks")
    if result["ok"]:
        print(summary)
        return 0
    print(f"{summary}; first break at seq {result['first_break_seq']}", file=sys.stderr)
    return 1
