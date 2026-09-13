"""Every column the pipeline publishes must exist in the migrations. A mismatch
would otherwise surface only as a failed insert in the nightly workflow."""

import re
from pathlib import Path

import pandas as pd

from metrics.pipeline import compute_all
from tests.test_pipeline_io import synthetic_panel

MIGRATIONS = sorted(Path(__file__).parent.parent.glob("supabase/migrations/*.sql"))
COLUMN = re.compile(
    r"^\s+([a-z_][a-z0-9_]*)\s+(text|integer|bigint|smallint|double precision|boolean|date|"
    r"timestamptz|jsonb|bytea)\b"
)
STATEMENT = re.compile(
    r"create table public\.(?P<create>\w+) \((?P<body>.*?)\n\);"
    r"|alter table public\.(?P<alter>\w+)\s+(?P<changes>.*?);"
    r"|drop table public\.(?P<drop>\w+);",
    re.S,
)


def declared_columns() -> dict[str, set[str]]:
    tables: dict[str, set[str]] = {}
    for path in MIGRATIONS:
        for m in STATEMENT.finditer(path.read_text()):
            if m["create"]:
                tables[m["create"]] = {
                    c[1] for line in m["body"].splitlines() if (c := COLUMN.match(line))
                }
            elif m["alter"]:
                tables.setdefault(m["alter"], set()).update(
                    re.findall(r"add column (\w+)", m["changes"])
                )
            else:
                tables.pop(m["drop"], None)
    return tables


def test_published_columns_exist_in_migrations():
    corridors = pd.DataFrame({"corridor_id": ["a", "b"], "tier": ["B", "B"],
                              "pair_id": ["PR-01", "PR-01"], "role": ["primary", "alternate"]})
    interventions = pd.DataFrame({"id": ["a-retiming"], "corridor_id": ["a"],
                                  "effective_at": ["2026-08-22T00:00:00+05:30"]})
    declared = declared_columns()
    for name, frame in compute_all(synthetic_panel(), corridors, interventions).items():
        assert name in declared, f"{name} has no migration"
        extra = set(frame.columns) - declared[name]
        assert not extra, f"{name} publishes columns missing from migrations: {sorted(extra)}"
