from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import pytest
from core.publish import UnknownServingTableError, publish
from core.rights import UnregisteredSourceError


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


def test_publish_returns_the_row_count_it_actually_wrote(fake_conn: _FakeConnection) -> None:
    written = publish(
        "series_long", _df(), as_of=datetime.now(UTC), source_note="t", key=["series_id", "ts"]
    )
    assert written == 2


def test_publish_returns_zero_when_it_skipped(
    fake_conn: _FakeConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Callers print "published N rows" after publish() returns. Returning len(df) from
    # the caller's own frame would claim a publish that never happened when the skip
    # path was taken -- a log line asserting something the code did not verify.
    monkeypatch.setattr("core.publish.settings.supabase_db_url", None)

    written = publish(
        "series_long", _df(), as_of=datetime.now(UTC), source_note="t", key=["series_id", "ts"]
    )

    assert written == 0


def test_publish_rejects_a_column_name_that_is_not_a_plain_identifier(
    fake_conn: _FakeConnection,
) -> None:
    # Column names and key names are interpolated into the SQL text, unlike row values
    # which go through COPY and parameters. No current caller can reach this (every one
    # passes a literal or a canonical schema frame), so this asserts the precondition
    # rather than patching a reachable hole -- it turns an implicit contract into an
    # enforced one.
    df = _df().rename(columns={"value": 'value"; drop table serving.series_long; --'})

    with pytest.raises(ValueError, match="identifier"):
        publish(
            "series_long", df, as_of=datetime.now(UTC), source_note="t", key=["series_id", "ts"]
        )
    assert fake_conn.cur.executed == []


def test_publish_calls_the_revalidate_hook_after_a_successful_publish(
    fake_conn: _FakeConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def _fake_post(url: str, **kwargs: Any) -> Any:
        calls.append((url, kwargs))

        class _Resp:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

        return _Resp()

    monkeypatch.setattr("core.publish.requests.post", _fake_post)
    monkeypatch.setattr("core.publish.settings.vercel_url", "https://data.example.com")
    monkeypatch.setattr("core.publish.settings.revalidate_secret", "s3cret")

    publish(
        "series_long", _df(), as_of=datetime.now(UTC), source_note="t", key=["series_id", "ts"]
    )

    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url == "https://data.example.com/api/revalidate"
    assert kwargs["params"] == {"tag": "series_long"}
    # The secret travels in a header, never in the query string: a URL is logged by
    # proxies and CDNs, a header is not.
    assert kwargs["headers"] == {"x-revalidate-secret": "s3cret"}


def test_publish_does_not_fail_when_the_revalidate_hook_is_unreachable(
    fake_conn: _FakeConnection, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Spec 32 §3: "Failure to revalidate is logged, not raised -- ISR fallback covers it."
    # The rows are already committed at this point; failing the pipeline over a stale
    # cache would turn a cosmetic delay into a red scheduled task.
    def _boom(*_a: Any, **_k: Any) -> Any:
        raise OSError("connection refused")

    monkeypatch.setattr("core.publish.requests.post", _boom)
    monkeypatch.setattr("core.publish.settings.vercel_url", "https://data.example.com")
    monkeypatch.setattr("core.publish.settings.revalidate_secret", "s3cret")

    written = publish(
        "series_long", _df(), as_of=datetime.now(UTC), source_note="t", key=["series_id", "ts"]
    )

    assert written == 2  # the publish itself still succeeded
    assert "revalidate" in capsys.readouterr().out


def test_publish_skips_the_revalidate_hook_when_it_is_not_configured(
    fake_conn: _FakeConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No Vercel deployment exists yet, which is the normal state today -- it must not
    # produce a warning on every publish.
    called = False

    def _fake_post(*_a: Any, **_k: Any) -> Any:
        nonlocal called
        called = True

    monkeypatch.setattr("core.publish.requests.post", _fake_post)
    monkeypatch.setattr("core.publish.settings.vercel_url", None)
    monkeypatch.setattr("core.publish.settings.revalidate_secret", None)

    publish(
        "series_long", _df(), as_of=datetime.now(UTC), source_note="t", key=["series_id", "ts"]
    )

    assert called is False


def test_publish_clamps_a_future_as_of_to_now(
    fake_conn: _FakeConnection, capsys: pytest.CaptureFixture[str]
) -> None:
    # A forecast series' max(ts) is in the future -- OPEC's MOMR runs quarters out to
    # 2027 -- and callers derive as_of from it. Left alone, serving.publish_log claimed
    # "data as of 1 October 2027" and the staleness badge could never fire, because the
    # data was permanently newer than now. Confirmed live 2026-09-09.
    future = datetime.now(UTC) + timedelta(days=400)

    publish(
        "series_long", _df(), as_of=future, source_note="t", key=["series_id", "ts"]
    )

    params = next(
        p for sql, p in fake_conn.cur.executed if "insert into serving.publish_log" in sql
    )
    assert params is not None
    assert params[1] <= datetime.now(UTC)
    assert "future" in capsys.readouterr().out


def test_publish_leaves_a_past_as_of_alone(fake_conn: _FakeConnection) -> None:
    # The clamp must not touch a genuinely stale source: serving.spreads reports April
    # 2024 because its EIA route was discontinued, and that is the finding.
    stale = datetime(2024, 4, 5, tzinfo=UTC)

    publish("series_long", _df(), as_of=stale, source_note="t", key=["series_id", "ts"])

    params = next(
        p for sql, p in fake_conn.cur.executed if "insert into serving.publish_log" in sql
    )
    assert params is not None
    assert params[1] == stale


# --- the class d guard (I-01) ----------------------------------------------------------


def _mixed_df() -> pd.DataFrame:
    """Three EIA rows (class b) and two Yahoo closes (class d, pipelines/futures/NOTES.md:330)."""
    return pd.DataFrame(
        {
            "series_id": ["WCESTUS1"] * 3 + ["fut.cl.f01.close"] * 2,
            "ts": pd.to_datetime(
                ["2026-09-01", "2026-09-08", "2026-09-15", "2026-09-14", "2026-09-15"]
            ),
            "value": [420.0, 415.0, 410.0, 70.5, 71.0],
            "unit": ["mb"] * 3 + ["USD"] * 2,
            "geo": ["US"] * 5,
            "freq": ["W"] * 3 + ["D"] * 2,
            "source": ["eia"] * 3 + ["yfinance"] * 2,
            "revision_date": pd.to_datetime(["2026-09-16"] * 5).date,
        }
    )


def _publish(df: pd.DataFrame, table: str = "series_long", **kw: Any) -> int:
    return publish(
        table,
        df,
        as_of=datetime.now(UTC),
        source_note="test",
        key=kw.pop("key", ["series_id", "ts"]),
        **kw,
    )


def test_publish_drops_class_d_rows_and_publishes_the_rest(
    fake_conn: _FakeConnection, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _publish(_mixed_df()) == 3

    assert fake_conn.cur.copied_data[0].count("\n") == 3
    assert "fut.cl.f01.close" not in fake_conn.cur.copied_data[0]
    out = capsys.readouterr().out
    assert "serving.series_long: 2 licence-restricted row(s) not published" in out
    assert "fut.cl.f01.close" in out
    log = next(p for sql, p in fake_conn.cur.executed if "insert into serving.publish_log" in sql)
    assert log is not None and log[3] == 3  # row_count is what was written


def test_publish_of_only_class_d_rows_writes_nothing_and_no_log_row(
    fake_conn: _FakeConnection,
) -> None:
    only_yahoo = _mixed_df().iloc[3:]
    assert _publish(only_yahoo) == 0
    assert fake_conn.cur.executed == []
    assert fake_conn.cur.copy_calls == []
    assert not fake_conn.committed


def test_publish_refuses_an_unregistered_source_before_any_sql(
    fake_conn: _FakeConnection,
) -> None:
    mystery = _mixed_df().iloc[:1].assign(source="mystery")
    with pytest.raises(UnregisteredSourceError, match="mystery"):
        _publish(mystery)
    assert fake_conn.cur.executed == []


def test_the_guard_runs_even_when_no_database_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An unset SUPABASE_DB_URL skips the publish; it must not skip the rights check, or a
    # sweep on a machine with no database would never learn that a source is unregistered.
    monkeypatch.setattr("core.publish.settings.supabase_db_url", None)
    mystery = _mixed_df().iloc[:1].assign(source="mystery")
    with pytest.raises(UnregisteredSourceError):
        _publish(mystery)


def test_publish_drops_a_restricted_series_id_from_a_frame_with_no_source_column(
    fake_conn: _FakeConnection,
) -> None:
    seasonal = pd.DataFrame(
        {"series_id": ["fut.ng.f01.close"] * 2, "doy": [1, 2], "median": [3.0, 3.1]}
    )
    assert _publish(seasonal, "seasonal", key=["series_id", "doy"], pipeline="wpsr") == 0
    assert fake_conn.cur.executed == []


def test_publish_drops_derived_rows_by_the_class_of_their_inputs(
    fake_conn: _FakeConnection,
) -> None:
    base = _mixed_df().iloc[:2].assign(source="derived")
    moving_average = base.assign(series_id="derived.ma.cl.50")
    cushing = base.assign(series_id="derived.cushing.stocks")
    assert _publish(moving_average) == 0
    assert _publish(cushing) == 2
