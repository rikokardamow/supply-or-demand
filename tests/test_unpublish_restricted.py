"""`pipelines.derived.unpublish_restricted` (I-02): dry run by default, fixtures only.

Nothing here connects to a database. The connection is a fake that records statements,
and the lake read is replaced by a small frame.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
import pytest
from core import rights
from pipelines.derived import unpublish_restricted as tool


class _Cursor:
    """Records statements. `count` answers every count(*); `deleted` is what a DELETE
    reports; `last_as_of` answers the publish_log lookup (None means no earlier row)."""

    def __init__(self, count: int, deleted: int | None, last_as_of: datetime | None) -> None:
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []
        self.count = count
        self.deleted = count if deleted is None else deleted
        self.last_as_of = last_as_of
        self.rowcount = -1
        self._row: tuple[Any, ...] | None = None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.executed.append((sql, params))
        if sql.startswith("select count(*)"):
            self._row = (self.count,)
        elif sql.startswith("select max(as_of)"):
            self._row = (self.last_as_of,)
        elif sql.startswith("delete from"):
            self.rowcount = self.deleted

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *exc: object) -> None:
        pass


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cur = cursor
        self.commits = 0

    def cursor(self) -> _Cursor:
        return self.cur

    def commit(self) -> None:
        self.commits += 1

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *exc: object) -> None:
        pass


LAKE = pd.DataFrame(
    {
        "source": ["eia", "yfinance", "yfinance", "derived", "derived", "derived", "reddit"],
        "series_id": [
            "WCESTUS1",
            "fut.cl.f01.close",
            "fut.ng.f01.close",
            "derived.ma.cl.50",
            "derived.cushing.util",
            "derived.mystery.x",
            "social.reddit.oil.post_count",
        ],
    }
)


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"conn": None, "connects": 0}

    def make(
        count: int = 7, deleted: int | None = None, last_as_of: datetime | None = None
    ) -> _Connection:
        as_of = last_as_of or datetime(2026, 10, 2, tzinfo=UTC)
        conn = _Connection(_Cursor(count, deleted, as_of))
        state["conn"] = conn
        return conn

    def connect(*args: Any, **kwargs: Any) -> _Connection:
        state["connects"] += 1
        assert state["conn"] is not None, "a test connected without wiring a fake"
        return state["conn"]  # type: ignore[no-any-return]

    monkeypatch.setattr(tool.psycopg, "connect", connect)
    monkeypatch.setattr(tool.settings, "supabase_db_url", "postgresql://fake")
    monkeypatch.setattr(tool, "lake_series", lambda: LAKE)
    monkeypatch.setattr(tool, "_revalidate", lambda table: None)
    state["make"] = make
    return state


def test_the_plan_names_every_restricted_pattern_on_the_tables_that_can_carry_it() -> None:
    plan = tool.build_targets(LAKE)
    labels = {(t.table, t.label) for t in plan}
    for pattern in rights.RESTRICTED_SERIES:
        assert ("series_long", pattern.pattern) in labels
        assert ("seasonal", pattern.pattern) in labels


def test_the_plan_selects_class_d_sources_by_their_source_column() -> None:
    plan = tool.build_targets(LAKE)
    by_source = [t for t in plan if t.where == "source = any(%s)"]
    assert {t.table for t in by_source} == {"series_long", "flows", "events"}
    sources = by_source[0].params[0]
    assert "yfinance" in sources and "manual" in sources
    assert "eia" not in sources and "gie" not in sources  # b, and held-at-a for the six


def test_the_plan_takes_lake_series_of_class_d_including_derived_by_inheritance() -> None:
    plan = tool.build_targets(LAKE)
    ids = next(t for t in plan if t.table == "seasonal" and t.where == "series_id = any(%s)")
    listed = set(ids.params[0])
    assert "fut.cl.f01.close" in listed
    assert "derived.ma.cl.50" in listed  # derived from Yahoo
    assert "derived.mystery.x" in listed  # no input mapping: d
    assert "social.reddit.oil.post_count" in listed
    assert "WCESTUS1" not in listed
    assert "derived.cushing.util" not in listed  # EIA


def test_whole_tables_fed_only_by_a_class_d_source_are_in_the_plan() -> None:
    whole = {t.table for t in tool.build_targets(LAKE) if t.where == "true"}
    assert whole == {"curve_settles", "vessel_latest", "sanctions"}


def test_dry_run_only_counts_and_prints(
    wired: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    conn = wired["make"](count=7)

    result = tool.run(apply=False)

    statements = [sql for sql, _ in conn.cur.executed]
    assert statements and all(sql.startswith("select count(*)") for sql in statements)
    assert conn.commits == 0
    out = capsys.readouterr().out
    assert r"^fut\.[a-z0-9]+\.f\d{2}\.close$: 7 rows in series_long" in out
    assert "dry run" in out.lower()
    assert result.removed == 0
    assert result.would_remove > 0


def test_apply_deletes_each_target_logs_per_table_and_commits_once(
    wired: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    conn = wired["make"](count=3)

    result = tool.run(apply=True)

    deletes = [(sql, p) for sql, p in conn.cur.executed if sql.startswith("delete from")]
    assert (
        "delete from serving.series_long where series_id ~ %s",
        (rights.RESTRICTED_SERIES[0].pattern,),
    ) in deletes
    assert any(sql == "delete from serving.curve_settles where true" for sql, _ in deletes)
    logs = [p for sql, p in conn.cur.executed if "insert into serving.publish_log" in sql]
    assert logs, "a publish_log row per table touched"
    for p in logs:
        assert p is not None
        assert p[2].startswith("unpublished ") and p[2].endswith(" licence-restricted rows")
        assert p[1] == datetime(2026, 10, 2, tzinfo=UTC)  # the table's own as_of, kept
        assert p[3] == 0
        assert p[4] == "unpublish_restricted"
    assert conn.commits == 1
    assert result.removed == result.would_remove > 0
    assert "deleted" in capsys.readouterr().out.lower()


def test_apply_keeps_the_staleness_clock_by_reusing_the_last_as_of(wired: dict[str, Any]) -> None:
    # serving.publish_log's newest row drives each table's as-of badge; a log row stamped
    # "now" would make stale data look fresh.
    conn = wired["make"](count=2, last_as_of=datetime(2026, 9, 1, tzinfo=UTC))
    tool.run(apply=True)
    inserts = [p for sql, p in conn.cur.executed if "insert into serving.publish_log" in sql]
    stamps = {p[1] for p in inserts if p}
    assert stamps == {datetime(2026, 9, 1, tzinfo=UTC)}


def test_apply_with_nothing_to_remove_writes_nothing(wired: dict[str, Any]) -> None:
    conn = wired["make"](count=0)
    result = tool.run(apply=True)
    assert not any(sql.startswith(("delete", "insert")) for sql, _ in conn.cur.executed)
    assert conn.commits == 0
    assert result.removed == 0


def test_apply_rolls_back_when_a_delete_removes_a_different_number_than_was_counted(
    wired: dict[str, Any],
) -> None:
    conn = wired["make"](count=3, deleted=4)
    with pytest.raises(tool.DeleteMismatchError):
        tool.run(apply=True)
    assert conn.commits == 0


def test_without_a_database_the_dry_run_prints_the_plan_and_connects_to_nothing(
    wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tool.settings, "supabase_db_url", None)
    result = tool.run(apply=False)
    assert wired["connects"] == 0
    out = capsys.readouterr().out
    assert "SUPABASE_DB_URL not configured" in out
    assert "fut" in out
    assert result.removed == 0


def test_apply_without_a_database_is_refused(
    wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tool.settings, "supabase_db_url", None)
    with pytest.raises(SystemExit):
        tool.run(apply=True)
    assert wired["connects"] == 0


def test_main_defaults_to_a_dry_run(wired: dict[str, Any]) -> None:
    conn = wired["make"](count=1)
    tool.main([])
    assert conn.commits == 0
    assert not any(sql.startswith("delete") for sql, _ in conn.cur.executed)


def test_main_apply_flag_deletes(wired: dict[str, Any]) -> None:
    conn = wired["make"](count=1)
    tool.main(["--apply"])
    assert conn.commits == 1
