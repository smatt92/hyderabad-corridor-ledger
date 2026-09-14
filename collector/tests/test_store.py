from datetime import UTC, datetime

from store import Ledger

START, END = datetime(2026, 9, 14, tzinfo=UTC), datetime(2026, 9, 15, tzinfo=UTC)


class FakeDb:
    """Returns each table's rows whatever the filter: the filters are PostgREST's job."""

    def __init__(self, tables):
        self.tables = tables

    def select_all(self, table, params, order="seq.asc"):
        return self.tables[table]


def test_attempts_count_each_run_by_the_larger_of_its_two_records():
    db = FakeDb({
        "samples": [{"collector_run": "r1", "attempts": 1}, {"collector_run": "r1", "attempts": 2},
                    {"collector_run": "r2", "attempts": 1}],
        "failed_samples": [{"collector_run": "r3", "attempts": 3},
                           {"collector_run": None, "attempts": 1}],
        "collector_runs": [{"id": "r1", "attempts": 5}, {"id": "r2", "attempts": 0},
                           {"id": "r4", "attempts": 2}],
        "corridor_route_checks": [{"collector_run": "r5", "attempts": 1}],
        "probe_calls": [{"id": 1}, {"id": 2}],
    })
    # r1: its run row counts 5, its outcome rows 3 (an outcome was never inserted)
    # r2: killed before finishing, so only its outcome rows count
    # r3: started before the window; r4: made calls but kept no outcome
    # r5: a road call, counted like any other attempt; and two probe attempts, outside any run
    assert Ledger(db).attempts_between(START, END) == 5 + 1 + 3 + 1 + 2 + 1 + 2
