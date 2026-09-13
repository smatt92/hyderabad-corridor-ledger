"""Monthly archive of the hot tables.

    python collector/archive.py run             archive and prune what has aged out
    python collector/archive.py download DIR    fetch every archive into DIR/<table>/

The archive bucket is the permanent record; samples and failed_samples keep
the last 90 days. For each table, while its oldest rows were requested before
the hot window, `run`:

  1. reads the next contiguous block of rows, stopping at the first row inside
     the window and never taking the newest row, which holds the chain head;
  2. checks the block's hash chain, linked to the previous archive's last row;
  3. writes Parquet, uploads it, downloads it back, and checks the returned
     bytes' sha256 and the chain again from the downloaded copy;
  4. records the archive in sample_archives, then calls prune_archived(), which
     re-checks the row count and boundary hash in the database before deleting.

Any mismatch stops the run before a row is deleted.
"""

import hashlib
import io
import sys
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from chain import as_bytes, as_utc, breaks
from store import PAGE_SIZE, Database, iso

HOT_DAYS = 90
ROWS_PER_FILE = 20_000  # about 1 KB a row: far under the bucket's 50 MB file limit
BUCKET = "archive"
TABLES = ("samples", "failed_samples")

# Every column of each table, in table order. A column the table gains and
# this format lacks stops the archive: nothing is dropped on the way out.
SCHEMAS = {
    "samples": (
        ("seq", "int64"), ("corridor_id", "string"), ("scheduled_slot", "timestamp"),
        ("requested_at", "timestamp"), ("attempts", "int16"), ("http_status", "int16"),
        ("length_m", "int32"), ("travel_time_s", "int32"), ("traffic_delay_s", "int32"),
        ("no_traffic_travel_time_s", "int32"), ("historic_travel_time_s", "int32"),
        ("raw_gz", "binary"), ("raw_gz_sha256", "binary"), ("collector_run", "string"),
        ("collector_sha", "string"), ("inserted_at", "timestamp"), ("prev_hash", "binary"),
        ("row_hash", "binary"),
    ),
    "failed_samples": (
        ("seq", "int64"), ("corridor_id", "string"), ("scheduled_slot", "timestamp"),
        ("requested_at", "timestamp"), ("attempts", "int16"), ("error_class", "string"),
        ("http_status", "int16"), ("detail_gz", "binary"), ("detail_gz_sha256", "binary"),
        ("collector_run", "string"), ("collector_sha", "string"), ("inserted_at", "timestamp"),
        ("prev_hash", "binary"), ("row_hash", "binary"),
    ),
}


def _arrow_type(kind: str):
    import pyarrow as pa

    return {"int64": pa.int64(), "int32": pa.int32(), "int16": pa.int16(),
            "string": pa.string(), "binary": pa.binary(),
            "timestamp": pa.timestamp("us", tz="UTC")}[kind]


def _value(kind: str, value):
    if value is None:
        return None
    if kind == "binary":
        return as_bytes(value)
    if kind == "timestamp":
        return as_utc(value)
    return value


def to_parquet(table: str, rows: list[dict]) -> bytes:
    import pyarrow as pa
    import pyarrow.parquet as pq

    names = {name for name, _ in SCHEMAS[table]}
    unknown = sorted(set().union(*rows) - names) if rows else []
    if unknown:
        raise RuntimeError(f"{table} has columns the archive format lacks: {unknown}")
    fields = [pa.field(name, _arrow_type(kind)) for name, kind in SCHEMAS[table]]
    arrays = [pa.array([_value(kind, row[name]) for row in rows], type=_arrow_type(kind))
              for name, kind in SCHEMAS[table]]
    buffer = io.BytesIO()
    pq.write_table(pa.Table.from_arrays(arrays, schema=pa.schema(fields)), buffer,
                   compression="zstd")
    return buffer.getvalue()


def from_parquet(payload: bytes) -> list[dict]:
    import pyarrow.parquet as pq

    return pq.read_table(io.BytesIO(payload)).to_pylist()


def object_path(table: str, first_seq: int, last_seq: int) -> str:
    return f"{table.replace('_', '-')}/{first_seq:012d}-{last_seq:012d}.parquet"


def cutoff(now: datetime) -> datetime:
    """Rows requested before this instant have left the 90-day hot window."""
    return datetime.combine((now - timedelta(days=HOT_DAYS)).date(), time.min, UTC)


def take_block(rows: list[dict], newest_seq: int, before: datetime,
               limit: int = ROWS_PER_FILE) -> list[dict]:
    """The archivable prefix of rows given in seq order."""
    block = []
    for row in rows:
        if (len(block) == limit or row["seq"] >= newest_seq
                or as_utc(row["requested_at"]) >= before):
            break
        block.append(row)
    return block


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class Archiver:
    def __init__(self, db: Database):
        self.db = db

    def get(self, table: str, params) -> list[dict]:
        _, rows = self.db.request("GET", table, params)
        return rows or []

    def prune(self, archive: dict) -> None:
        _, deleted = self.db.request("POST", "rpc/prune_archived",
                                     body={"archive_id": archive["id"]})
        if deleted != archive["row_count"]:
            raise RuntimeError(f"archive {archive['id']}: pruned {deleted} rows, "
                               f"expected {archive['row_count']}")

    def finish_unpruned(self, table: str) -> None:
        """An archive recorded by a run that stopped before pruning."""
        for archive in self.get("sample_archives", [
            ("select", "id,row_count"), ("table_name", f"eq.{table}"),
            ("pruned_at", "is.null"), ("order", "first_seq.asc"),
        ]):
            self.prune(archive)

    def candidates(self, table: str, after_seq: int, newest_seq: int,
                   before: datetime) -> list[dict]:
        rows: list[dict] = []
        while len(rows) < ROWS_PER_FILE:
            page = self.get(table, [
                ("select", "*"), ("seq", f"gt.{after_seq}"), ("seq", f"lt.{newest_seq}"),
                ("order", "seq.asc"), ("limit", str(min(PAGE_SIZE, ROWS_PER_FILE - len(rows)))),
            ])
            rows.extend(page)
            if not page or as_utc(page[-1]["requested_at"]) >= before:
                break
            after_seq = page[-1]["seq"]
        return rows

    def archive_next(self, table: str, before: datetime) -> int:
        """Archive and prune one block. Returns its row count, 0 when nothing is due."""
        head = self.get(table, [("select", "seq"), ("order", "seq.desc"), ("limit", "1")])
        if not head:
            return 0
        previous = self.get("sample_archives", [
            ("select", "last_seq,last_row_hash"), ("table_name", f"eq.{table}"),
            ("order", "last_seq.desc"), ("limit", "1"),
        ])
        start = previous[0]["last_seq"] + 1 if previous else 1
        link = bytes.fromhex(previous[0]["last_row_hash"]) if previous else None
        newest = head[0]["seq"]
        rows = take_block(self.candidates(table, start - 1, newest, before), newest, before)
        if not rows:
            return 0
        if rows[0]["seq"] != start:
            raise RuntimeError(f"{table}: oldest retained row is seq {rows[0]['seq']}, "
                               f"but the archive ends at {start - 1}")
        if problems := breaks(table, rows, before=link):
            seq, problem = problems[0]
            raise RuntimeError(f"{table}: chain break at seq {seq}: {problem}. Nothing archived.")

        payload = to_parquet(table, rows)
        path = object_path(table, rows[0]["seq"], rows[-1]["seq"])
        # Overwriting is safe: a path is a seq range, and a range is archived once.
        self.db.raw("POST", f"storage/v1/object/{BUCKET}/{path}", payload,
                    {"Content-Type": "application/vnd.apache.parquet", "x-upsert": "true"})
        _, stored = self.db.raw("GET", f"storage/v1/object/{BUCKET}/{path}")
        back = from_parquet(stored)
        if (sha256_hex(stored) != sha256_hex(payload) or len(back) != len(rows)
                or breaks(table, back, before=link)
                or back[-1]["row_hash"] != as_bytes(rows[-1]["row_hash"])):
            raise RuntimeError(f"{path}: the uploaded archive does not read back intact. "
                               "Nothing pruned.")

        _, created = self.db.request("POST", "sample_archives", body={
            "table_name": table, "first_seq": rows[0]["seq"], "last_seq": rows[-1]["seq"],
            "row_count": len(rows), "requested_before": iso(before), "object_path": path,
            "n_bytes": len(payload), "sha256": sha256_hex(payload),
            "last_row_hash": as_bytes(rows[-1]["row_hash"]).hex(),
            "verified_at": iso(datetime.now(UTC)),
        }, prefer="return=representation")
        self.prune(created[0])
        return len(rows)


def run(db: Database, now: datetime | None = None) -> int:
    before = cutoff(now or datetime.now(UTC))
    archiver = Archiver(db)
    total = 0
    for table in TABLES:
        archiver.finish_unpruned(table)
        while n := archiver.archive_next(table, before):
            print(f"{table}: archived and pruned {n} rows")
            total += n
    print(f"archive: {total} rows moved to the {BUCKET} bucket; the hot tables keep rows "
          f"requested from {before:%Y-%m-%d} UTC")
    return 0


def download(db: Database, directory: Path) -> int:
    _, archives = db.request("GET", "sample_archives", [
        ("select", "table_name,object_path,sha256"), ("order", "table_name.asc,first_seq.asc"),
    ])
    for archive in archives or []:
        _, payload = db.raw("GET", f"storage/v1/object/{BUCKET}/{archive['object_path']}")
        if sha256_hex(payload) != archive["sha256"]:
            raise RuntimeError(f"{archive['object_path']}: sha256 does not match sample_archives")
        target = directory / archive["table_name"] / Path(archive["object_path"]).name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    print(f"downloaded {len(archives or [])} archives into {directory}")
    return 0


def main(argv: list[str]) -> int:
    if argv[1:] == ["run"]:
        return run(Database.from_env())
    if len(argv) == 3 and argv[1] == "download":
        return download(Database.from_env(), Path(argv[2]))
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
