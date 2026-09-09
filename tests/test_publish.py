from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
import pytest
from core.publish import UnknownServingTableError, publish


class _FakeCopy:
    """Fakes psycopg's `with cursor.copy(sql) as copy: copy.write(data)` context manager."""

    def __init__(self, cursor: _FakeCursor, sql: str) -> None:
        self.cursor = cursor
        self.sql = sql
        self.written = ""

    def __enter__(self) -> _FakeCopy:
        self.cursor.copy_calls.append(self.sql)
        return self

    def __exit__(self, *exc: object) -> None:
        self.cursor.copied_data.append(self.written)

    def write(self, data: str) -> None:
        self.written += data


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []
        self.copy_calls: list[str] = []
        self.copied_data: list[str] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.executed.append((sql, params))

    def copy(self, sql: str) -> _FakeCopy:
        return _FakeCopy(self, sql)

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        pass


class _FakeConnection:
    def __init__(self) -> None:
        self.cur = _FakeCursor()
        self.committed = False

    def cursor(self) -> _FakeCursor:
        return self.cur

    def commit(self) -> None:
        self.committed = True

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *exc: object) -> None:
        pass


@pytest.fixture
def fake_conn(monkeypatch: pytest.MonkeyPatch) -> _FakeConnection:
    conn = _FakeConnection()
    monkeypatch.setattr("core.publish.psycopg.connect", lambda *a, **k: conn)
    monkeypatch.setattr("core.publish.settings.supabase_db_url", "postgresql://fake")
    return conn


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": ["eia.wcestus1", "eia.wcestus1"],
            "ts": pd.to_datetime(["2026-09-01", "2026-09-08"]),
            "value": [420.0, 415.0],
            "unit": ["MBBL", "MBBL"],
            "geo": ["US", "US"],
            "freq": ["W", "W"],
            "source": ["eia", "eia"],
            "revision_date": pd.to_datetime(["2026-09-09", "2026-09-09"]).date,
        }
    )


def test_publish_rejects_a_table_outside_the_serving_whitelist(fake_conn: _FakeConnection) -> None:
    with pytest.raises(UnknownServingTableError):
        publish(
            "not_a_real_table",
            _df(),
            as_of=datetime.now(UTC),
            source_note="test",
            key=["series_id", "ts"],
        )
    assert fake_conn.cur.executed == []


def test_publish_does_nothing_for_an_empty_dataframe(fake_conn: _FakeConnection) -> None:
    publish(
        "series_long",
        _df().iloc[0:0],
        as_of=datetime.now(UTC),
        source_note="test",
        key=["series_id", "ts"],
    )
    assert fake_conn.cur.executed == []
    assert fake_conn.cur.copy_calls == []


def test_publish_copies_into_a_staging_table_then_upserts_on_the_given_key(
    fake_conn: _FakeConnection,
) -> None:
    publish(
        "series_long",
        _df(),
        as_of=datetime.now(UTC),
        source_note="test",
        key=["series_id", "ts"],
    )

    assert len(fake_conn.cur.copy_calls) == 1
    assert "copy _publish_staging" in fake_conn.cur.copy_calls[0]
    assert "from stdin" in fake_conn.cur.copy_calls[0]
    assert fake_conn.cur.copied_data[0].count("\n") == 2  # two data rows written to COPY

    upsert_sql = next(
        sql for sql, _ in fake_conn.cur.executed if "insert into serving.series_long" in sql
    )
    assert "on conflict (series_id, ts) do update set" in upsert_sql
    assert "value = excluded.value" in upsert_sql
    # key columns must never appear on the SET side of the upsert
    assert "series_id = excluded.series_id" not in upsert_sql
    assert "ts = excluded.ts" not in upsert_sql


def test_publish_appends_one_publish_log_row_with_the_real_row_count(
    fake_conn: _FakeConnection,
) -> None:
    as_of = datetime(2026, 9, 8, tzinfo=UTC)
    publish(
        "series_long",
        _df(),
        as_of=as_of,
        source_note="EIA WPSR · week ending 8 Sep 2026",
        key=["series_id", "ts"],
        pipeline="wpsr",
    )

    log_calls = [
        (sql, params)
        for sql, params in fake_conn.cur.executed
        if "insert into serving.publish_log" in sql
    ]
    assert len(log_calls) == 1
    _, params = log_calls[0]
    assert params == ("series_long", as_of, "EIA WPSR · week ending 8 Sep 2026", 2, "wpsr")
    assert fake_conn.committed is True


def test_publish_dedups_rows_sharing_a_key_before_upserting(
    fake_conn: _FakeConnection, capsys: pytest.CaptureFixture[str]
) -> None:
    # Postgres refuses an ON CONFLICT DO UPDATE whose own INSERT proposes the same
    # constrained key twice ("cannot affect row a second time"). Real EIA responses do
    # contain such rows: confirmed live 2026-09-09, the WPSR pull returned 10 rows in 5
    # duplicate (series_id, ts) groups, all clustered at the client's 5,000-row
    # pagination boundaries and all carrying identical values. write_ts_long's own
    # dedup absorbs these for the lake, so publish() must do the same for the serving
    # copy rather than blowing up on data the lake accepts.
    duplicated = pd.concat([_df(), _df().iloc[[0]]], ignore_index=True)  # 3 rows, 2 keys

    publish(
        "series_long",
        duplicated,
        as_of=datetime.now(UTC),
        source_note="test",
        key=["series_id", "ts"],
    )

    assert fake_conn.cur.copied_data[0].count("\n") == 2  # 2 unique keys, not 3 rows
    log_params = next(
        params
        for sql, params in fake_conn.cur.executed
        if "insert into serving.publish_log" in sql
    )
    assert log_params is not None
    assert log_params[3] == 2  # row_count reflects what was actually published
    assert "duplicate" in capsys.readouterr().out


def test_publish_skips_cleanly_when_supabase_is_not_configured(
    fake_conn: _FakeConnection, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # An unset SUPABASE_DB_URL is a legitimate state -- CI, and any machine that hasn't
    # opted into the serving layer -- and must not fail a pipeline whose lake write has
    # already succeeded. A *configured but broken* connection is a different case: that
    # one propagates, so a real Supabase outage surfaces as a non-zero exit.
    monkeypatch.setattr("core.publish.settings.supabase_db_url", None)

    publish(
        "series_long",
        _df(),
        as_of=datetime.now(UTC),
        source_note="test",
        key=["series_id", "ts"],
    )

    assert fake_conn.cur.executed == []
    assert "not configured" in capsys.readouterr().out


def test_publish_chunks_large_frames_into_multiple_copy_calls(fake_conn: _FakeConnection) -> None:
    # Six genuinely distinct keys -- repeating _df() would collapse to 2 rows under
    # publish()'s own dedup and test nothing about chunking.
    big = pd.concat([_df()] * 3, ignore_index=True)
    big["ts"] = pd.to_datetime(
        ["2026-09-01", "2026-09-08", "2026-09-15", "2026-09-22", "2026-09-29", "2026-10-06"]
    )
    publish(
        "series_long",
        big,
        as_of=datetime.now(UTC),
        source_note="test",
        key=["series_id", "ts"],
        chunk_size=2,
    )
    assert len(fake_conn.cur.copy_calls) == 3  # 6 rows / chunk_size 2

    # Each chunk must drop its own staging table before the next one creates it again.
    # All chunks share one transaction (the commit only happens at the end), so `on
    # commit drop` alone would leave chunk 2 hitting "relation _publish_staging already
    # exists" against a real Postgres -- something these fakes cannot reproduce.
    creates = [sql for sql, _ in fake_conn.cur.executed if "create temporary table" in sql]
    drops = [sql for sql, _ in fake_conn.cur.executed if "drop table" in sql]
    assert len(creates) == 3
    assert len(drops) == 3
