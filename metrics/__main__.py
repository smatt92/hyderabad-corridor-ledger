"""python -m metrics backfill [--archive-dir DIR] [--dry-run OUT_DIR] [--window-end DATE]
python -m metrics verify

backfill recomputes every derived table from raw responses (the Parquet
archive plus the hot samples table), replaces them wholesale and republishes
the open dataset. Raw is the source of truth, so a changed metric definition
only needs a new METHOD_VERSION and another backfill.

verify walks both hash chains in the database, records the result for
/verify, and exits non-zero if either is broken.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from metrics import io
from metrics.exports import OBJECTS
from metrics.pipeline import compute_all
from metrics.raw import combine_sources, missing_seqs, parse_samples


def backfill(args: argparse.Namespace) -> int:
    db = io.Supabase.from_env(read_only=args.dry_run is not None)
    sources = [io.load_hot_samples(db)]
    if args.archive_dir:
        sources.append(io.load_archive(args.archive_dir))
    rows = combine_sources(*sources)
    if rows.empty:
        print("no samples yet; nothing to compute")
        return 0

    gaps = missing_seqs(rows)
    if gaps:
        print(
            f"raw record incomplete: {len(gaps)} seq values missing (first: {gaps[:10]}). "
            "Older history lives in the archive; pass --archive-dir.",
            file=sys.stderr,
        )
        return 1

    tables = compute_all(
        parse_samples(rows), io.load_corridors(db), io.load_interventions(db),
        window_end=args.window_end,
    )
    corridors = io.load_corridor_metadata(db)
    if args.dry_run:
        args.dry_run.mkdir(parents=True, exist_ok=True)
        for name, frame in tables.items():
            frame.to_parquet(args.dry_run / f"{name}.parquet", index=False)
            print(f"{name}: {len(frame)} rows")
        for fmt, payload, _type, row in io.export_payloads(tables, corridors):
            (args.dry_run / Path(OBJECTS[fmt]).name).write_bytes(payload)
            print(f"export {fmt}: {row['n_rows']} rows, sha256 {row['sha256']}")
        return 0

    for name, frame in tables.items():
        io.replace_table(db, name, frame)
        print(f"{name}: {len(frame)} rows")
    io.publish_exports(db, tables, corridors)
    return 0


def verify(_args: argparse.Namespace) -> int:
    db = io.Supabase.from_env(read_only=False)
    return io.exit_on_broken_chain(io.record_chain_verification(db))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m metrics")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("backfill", help="recompute all derived tables from raw")
    run.add_argument("--archive-dir", type=Path, help="directory of archive .parquet files")
    run.add_argument(
        "--dry-run", type=Path, metavar="OUT_DIR",
        help="write each table and export to OUT_DIR instead of the database",
    )
    run.add_argument("--window-end", type=pd.Timestamp, help="ranking window end date")
    run.set_defaults(handler=backfill)
    commands.add_parser("verify", help="walk the sample hash chain and record the result") \
        .set_defaults(handler=verify)
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
