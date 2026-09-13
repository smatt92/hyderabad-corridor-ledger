"""Hash chains: the nightly verification, and a port of the canonical formats.

    python collector/chain.py

records a walk of both chains through public.record_chain_verification(),
prints each head hash and first break to the job log and summary, and exits
non-zero on any break.

The port of public.samples_canonical (v1) and public.failed_samples_canonical
(f1) lets the archive job check rows before it uploads them, and lets anyone
holding the archive re-verify the chain without the database. Any change to
either SQL function is a new format version, and this port changes with it.
"""

import hashlib
import os
import sys
from datetime import UTC, datetime

GENESIS = bytes(32)

FORMATS = {
    "samples": ("v1", "raw_gz", (
        "seq", "corridor_id", "requested_at", "http_status", "length_m", "travel_time_s",
        "traffic_delay_s", "no_traffic_travel_time_s", "historic_travel_time_s", "raw_gz_sha256",
        "collector_run", "collector_sha", "inserted_at",
    )),
    "failed_samples": ("f1", "detail_gz", (
        "seq", "corridor_id", "scheduled_slot", "requested_at", "attempts", "error_class",
        "http_status", "detail_gz_sha256", "collector_run", "collector_sha", "inserted_at",
    )),
}
TIMESTAMPS = {"requested_at", "inserted_at", "scheduled_slot"}


def as_bytes(value) -> bytes | None:
    """bytea as PostgREST returns it (\\x hex) or as bytes read from Parquet."""
    if value is None or isinstance(value, bytes):
        return value
    if isinstance(value, bytearray | memoryview):
        return bytes(value)
    if isinstance(value, str) and value.startswith("\\x"):
        return bytes.fromhex(value[2:])
    raise TypeError(f"not a bytea value: {type(value).__name__}")


def as_utc(value) -> datetime:
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ValueError(f"timestamp without a time zone: {value!r}")
    return moment.astimezone(UTC)


def _field(name: str, value) -> str:
    if value is None:
        return ""
    if name in TIMESTAMPS:
        return as_utc(value).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if name.endswith("_sha256"):
        return as_bytes(value).hex()
    return str(value)


def canonical(table: str, row: dict) -> str:
    version, _, fields = FORMATS[table]
    return "|".join([version, *(_field(name, row[name]) for name in fields)])


def row_hash(table: str, row: dict) -> bytes:
    return hashlib.sha256(as_bytes(row["prev_hash"]) + canonical(table, row).encode()).digest()


def breaks(table: str, rows, before: bytes | None = None) -> list[tuple[int, str]]:
    """Every problem in rows given in seq order, as the SQL walk reports them.
    `before` is the row_hash preceding the first row, when it is known."""
    _, payload, _ = FORMATS[table]
    problems = []
    last_seq, last_hash = None, before
    for row in rows:
        seq, stored, prev = row["seq"], as_bytes(row["row_hash"]), as_bytes(row["prev_hash"])
        if stored != row_hash(table, row):
            problems.append((seq, "row_hash does not match row contents"))
        body = as_bytes(row[payload])
        if as_bytes(row[f"{payload}_sha256"]) != (body and hashlib.sha256(body).digest()):
            problems.append((seq, f"{payload}_sha256 does not match {payload}"))
        if last_seq is not None and seq != last_seq + 1:
            problems.append((seq, "seq gap before this row"))
        if last_hash is not None and prev != last_hash:
            problems.append((seq, "prev_hash does not link to the previous row"))
        if last_seq is None and seq == 1 and prev != GENESIS:
            problems.append((seq, "genesis prev_hash is not all zeros"))
        last_seq, last_hash = seq, stored
    return problems


def main() -> int:
    from store import Database

    _, results = Database.from_env().request("POST", "rpc/record_chain_verification", body={})
    lines = ["## Hash chains", "", "| table | rows | seq | head row_hash | breaks | first break |",
             "|---|---|---|---|---|---|"]
    broken = []
    for r in results or []:
        first = (f"seq {r['first_break_seq']}: {r['first_break_problem']}"
                 if r["breaks"] else "none")
        span = f"{r['first_seq']}..{r['head_seq']}" if r["rows_checked"] else "empty"
        lines.append(f"| {r['table_name']} | {r['rows_checked']} | {span} | "
                     f"`{r['head_row_hash'] or '-'}` | {r['breaks']} | {first} |")
        if not r["ok"]:
            broken.append(f"{r['table_name']} chain broken at {first}")
    print("\n".join(lines))
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    if len(results or []) != len(FORMATS):
        broken.append("record_chain_verification did not report both chains")
    for problem in broken:
        print(f"::error::{problem}", file=sys.stderr)
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
