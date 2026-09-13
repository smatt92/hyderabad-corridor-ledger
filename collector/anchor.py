"""Anchor both hash-chain heads in Sigstore's public log, and check every anchor.

    python anchor.py write heads.json
    python anchor.py publish heads.json heads.sigstore.json
    python anchor.py check

A head hash kept only inside the database it describes proves nothing: whoever
can rewrite the chain can rewrite the record of its head. Each night, after
chain.py records a walk, daily.yml runs `write`, signs the file with
`cosign sign-blob`, and runs `publish`. Signing is keyless: GitHub's OIDC token
names the workflow, Sigstore certifies that identity, and the signature is
entered in Rekor, a public append-only log that no one, the repository's owner
included, can edit or backdate. `publish` stores the file and its Sigstore
bundle in the public archive bucket and lists them in heads/index.json.

`check` needs only SUPABASE_URL, a key that can read public tables
(SUPABASE_KEY, or the service key in CI) and cosign on the PATH, so anyone can
run it. For every anchor in the index it verifies the bundle was signed by
daily.yml on main of this repository. It then walks each chain from seq 1,
archive files first and the hot table after, recomputing every row_hash with the
ported canonical formats, and requires the walk to hold, at every anchored seq,
exactly the anchored row_hash. Each row_hash covers its predecessor, so passing
means the live chain extends every anchored head.

Limits. An anchor proves what this workflow published and when, not that the
rows were right when inserted. Rows rewritten before the first anchor cannot be
detected. Deleting anchor files from the bucket removes them from this check,
although their Rekor entries stay in the public log.
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from chain import FORMATS, as_bytes, as_utc, breaks

BUCKET = "archive"
PREFIX = "heads"
INDEX = f"{PREFIX}/index.json"
FORMAT = "heads-v1"
REPOSITORY = "smatt92/hyderabad-corridor-ledger"
IDENTITY = f"https://github.com/{REPOSITORY}/.github/workflows/daily.yml@refs/heads/main"
ISSUER = "https://token.actions.githubusercontent.com"
MAX_AGE = timedelta(hours=2)  # the walk being anchored must be tonight's
WALK_FIELDS = ("table_name", "verified_at", "rows_checked", "first_seq", "head_seq",
               "head_row_hash", "breaks", "first_break_seq", "first_break_problem", "ok")


def heads_document(walks: list[dict], now: datetime) -> dict:
    """The latest recorded walk of each chain: the document that gets signed."""
    latest: dict[str, dict] = {}
    for walk in sorted(walks, key=lambda w: as_utc(w["verified_at"]), reverse=True):
        latest.setdefault(walk["table_name"], walk)
    missing = sorted(set(FORMATS) - set(latest))
    if missing:
        raise RuntimeError(f"no recorded walk of {', '.join(missing)}; run chain.py first")
    for table, walk in latest.items():
        if now - as_utc(walk["verified_at"]) > MAX_AGE:
            raise RuntimeError(f"the latest walk of {table} is older than {MAX_AGE}; "
                               "run chain.py first")
    return {"format": FORMAT, "repository": REPOSITORY,
            "chains": [{k: latest[t].get(k) for k in WALK_FIELDS} for t in sorted(latest)]}


def encode(document: dict) -> bytes:
    """Canonical bytes: the exact bytes signed, stored and verified."""
    return (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()


def anchor_name(document: dict) -> str:
    moment = max(as_utc(c["verified_at"]) for c in document["chains"])
    return f"{PREFIX}/{moment:%Y%m%dT%H%M%SZ}.json"


def anchor_problems(anchors: list[tuple[str, dict]], chains: dict[str, list[dict]]) -> list[str]:
    """Everything wrong between the anchors and the chains as walked now. Rows are in seq
    order from seq 1. A chain anchored while empty is extended by any rows since."""
    problems = []
    hashes = {}
    for table, rows in chains.items():
        if rows and rows[0]["seq"] != 1:
            problems.append(f"{table}: the walk starts at seq {rows[0]['seq']}, not 1")
        problems += [f"{table} seq {seq}: {problem}"
                     for seq, problem in breaks(table, rows, payloads=False)]
        hashes[table] = {row["seq"]: as_bytes(row["row_hash"]).hex() for row in rows}
    for name, document in anchors:
        if document.get("format") != FORMAT or document.get("repository") != REPOSITORY:
            problems.append(f"{name}: not a {FORMAT} document for {REPOSITORY}")
            continue
        for anchored in document["chains"]:
            table, seq = anchored["table_name"], anchored["head_seq"]
            if seq is None:
                continue
            head = max(hashes.get(table, {}), default=0)
            found = hashes.get(table, {}).get(seq)
            if found is None:
                problems.append(f"{name}: {table} was anchored at seq {seq}, but the chain "
                                f"now ends at seq {head}")
            elif found != anchored["head_row_hash"]:
                problems.append(f"{name}: {table} seq {seq} now hashes to {found[:16]}, not "
                                f"the anchored {anchored['head_row_hash'][:16]}")
    return problems


class Storage:
    """The public archive bucket and the public tables, through the project URL."""

    def __init__(self, db):
        self.db = db

    def read(self, path: str) -> bytes | None:
        from store import DatabaseError
        try:
            return self.db.raw("GET", f"storage/v1/object/public/{BUCKET}/{path}")[1]
        except DatabaseError as exc:
            if "HTTP 400" in str(exc) or "HTTP 404" in str(exc):
                return None
            raise

    def write(self, path: str, payload: bytes, content_type: str, replace: bool) -> None:
        self.db.raw("POST", f"storage/v1/object/{BUCKET}/{path}", payload,
                    {"Content-Type": content_type, "x-upsert": "true" if replace else "false"})
        if self.read(path) != payload:
            raise RuntimeError(f"{path} did not read back as written")

    def walks(self) -> list[dict]:
        _, rows = self.db.request("GET", "chain_verifications", [
            ("select", ",".join(WALK_FIELDS)), ("order", "verified_at.desc"), ("limit", "20")])
        return rows or []

    def chain(self, table: str) -> list[dict]:
        """Every row of a chain from seq 1: archive files, then the hot table."""
        _, _, fields = FORMATS[table]
        rows: list[dict] = []
        archives = self.db.select_all("sample_archives", [
            ("select", "first_seq,last_seq,object_path"), ("table_name", f"eq.{table}")],
            order="first_seq.asc")
        if archives:
            from archive import from_parquet
            for archive in archives:
                payload = self.read(archive["object_path"])
                if payload is None:
                    raise RuntimeError(f"{archive['object_path']} is listed but not stored")
                rows += from_parquet(payload)
        after = rows[-1]["seq"] if rows else 0
        rows += self.db.select_all(table, [("select", ",".join([*fields, "prev_hash", "row_hash"])),
                                           ("seq", f"gt.{after}")])
        return rows


def cosign_verify(heads: bytes, bundle: bytes, cosign: str = "cosign") -> str | None:
    """None when the bundle is a valid signature over heads by daily.yml on main."""
    with tempfile.TemporaryDirectory() as directory:
        heads_path, bundle_path = Path(directory, "heads.json"), Path(directory, "bundle.json")
        heads_path.write_bytes(heads)
        bundle_path.write_bytes(bundle)
        result = subprocess.run(
            [cosign, "verify-blob", "--bundle", str(bundle_path), "--certificate-identity",
             IDENTITY, "--certificate-oidc-issuer", ISSUER, str(heads_path)],
            capture_output=True, text=True)
    return None if result.returncode == 0 else (result.stderr or result.stdout).strip()[-300:]


def publish(storage: Storage, heads: bytes, bundle: bytes) -> str:
    name = anchor_name(json.loads(heads))
    bundle_name = name.removesuffix(".json") + ".sigstore.json"
    storage.write(name, heads, "application/json", replace=False)
    storage.write(bundle_name, bundle, "application/json", replace=False)
    index = json.loads(storage.read(INDEX) or b"[]")
    index.append({"heads": name, "bundle": bundle_name})
    storage.write(INDEX, (json.dumps(index, indent=1) + "\n").encode(), "application/json",
                  replace=True)
    return name


def check(storage: Storage, verify=cosign_verify) -> tuple[list[str], int, dict[str, list[dict]]]:
    """(problems, anchors verified, chains walked)."""
    index = json.loads(storage.read(INDEX) or b"[]")
    problems, anchors = [], []
    for entry in index:
        heads, bundle = storage.read(entry["heads"]), storage.read(entry["bundle"])
        if heads is None or bundle is None:
            problems.append(f"{entry['heads']}: listed in {INDEX} but not stored")
            continue
        if (failure := verify(heads, bundle)) is not None:
            problems.append(f"{entry['heads']}: signature does not verify: {failure}")
            continue
        anchors.append((entry["heads"], json.loads(heads)))
    chains = {table: storage.chain(table) for table in FORMATS}
    return problems + anchor_problems(anchors, chains), len(anchors), chains


def main(argv: list[str]) -> int:
    from store import Database

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_KEY (or SUPABASE_SERVICE_KEY) must be set",
              file=sys.stderr)
        return 2
    storage = Storage(Database(url, key))
    command = argv[1] if len(argv) > 1 else ""
    if command == "write" and len(argv) == 3:
        Path(argv[2]).write_bytes(encode(heads_document(storage.walks(), datetime.now(UTC))))
        return 0
    if command == "publish" and len(argv) == 4:
        name = publish(storage, Path(argv[2]).read_bytes(), Path(argv[3]).read_bytes())
        print(f"anchored {name} and its Sigstore bundle in the {BUCKET} bucket")
        return 0
    if command == "check" and len(argv) == 2:
        problems, n_anchors, chains = check(storage)
        lines = [f"anchors checked: {n_anchors}"]
        lines += [f"{table}: {len(rows)} rows walked" for table, rows in chains.items()]
        print("\n".join(lines))
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(summary, "a", encoding="utf-8") as f:
                f.write("## Anchored heads\n\n" + "\n".join(f"- {line}" for line in lines)
                        + "\n")
        for problem in problems:
            print(f"::error::{problem}", file=sys.stderr)
        return 1 if problems else 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
