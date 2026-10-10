"""Transformation tests for `pipelines/futures/publish_curve.py` (Spec 32 Session 3).

These never touch a real database: `main()` is exercised against the same fake psycopg
connection `tests/test_publish.py` uses, and every other test drives the two frame
builders directly. The risk in this module is entirely in the transformation -- series-id
parsing, the rank pivot, and the spread sign convention -- not in the publish call.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
import pytest
from core.curve import time_spreads
from pipelines.futures.publish_curve import (
    SPREAD_LEGS,
    curve_settles_frame,
    main,
    spreads_frame,
)


def _row(series_id: str, ts: str, value: float, source: str) -> dict[str, Any]:
    return {
        "series_id": series_id,
        "source": source,
        "ts": pd.Timestamp(ts),
        "value": value,
        "unit": "USD/bbl",
        "geo": "GLOBAL",
        "freq": "D",
        "revision_date": pd.Timestamp("2026-09-09"),
    }


def _lake() -> pd.DataFrame:
    """A miniature stand-in for the real lake: one contract-coded root plus one
    rank-based root, in the two shapes `fut.*` genuinely takes."""
    rows = [
        _row("fut.lco.x2026.settle", "2026-09-04", 96.28, "manual"),
        _row("fut.lco.z2026.settle", "2026-09-04", 95.10, "manual"),
        _row("fut.lco.f2027.settle", "2026-09-04", 94.05, "manual"),
        # Two complete rank sets, plus a third date missing f04.
        _row("fut.cl.f01.settle", "2024-04-04", 86.59, "eia"),
        _row("fut.cl.f02.settle", "2024-04-04", 85.90, "eia"),
        _row("fut.cl.f03.settle", "2024-04-04", 85.10, "eia"),
        _row("fut.cl.f04.settle", "2024-04-04", 84.30, "eia"),
        _row("fut.cl.f01.settle", "2024-04-05", 86.91, "eia"),
        _row("fut.cl.f02.settle", "2024-04-05", 86.20, "eia"),
        _row("fut.cl.f03.settle", "2024-04-05", 85.40, "eia"),
        _row("fut.cl.f04.settle", "2024-04-05", 84.55, "eia"),
        _row("fut.rb.f01.settle", "2024-04-05", 2.79, "eia"),
        _row("fut.rb.f02.settle", "2024-04-05", 2.75, "eia"),
        _row("fut.rb.f03.settle", "2024-04-05", 2.70, "eia"),
    ]
    return pd.DataFrame(rows)


# --- curve_settles -------------------------------------------------------------------


def test_curve_settles_takes_only_the_contract_coded_series() -> None:
    out = curve_settles_frame(_lake())

    assert list(out.columns) == [
        "root",
        "trade_date",
        "contract",
        "expiry",
        "settle",
        "oi",
        "source",
    ]
    assert len(out) == 3
    assert set(out["root"]) == {"LCO"}
    assert sorted(out["contract"]) == ["F2027", "X2026", "Z2026"]
    assert set(out["source"]) == {"manual"}


def test_curve_settles_carries_the_trade_date_as_a_date_and_the_settle_as_the_value() -> None:
    out = curve_settles_frame(_lake())
    x6 = out[out["contract"] == "X2026"].iloc[0]

    assert x6["trade_date"] == date(2026, 9, 4)
    assert x6["settle"] == pytest.approx(96.28)


def test_curve_settles_leaves_expiry_and_oi_null_because_the_lake_has_neither() -> None:
    # The Barchart-reconstructed curve carries no expiry date and no open interest
    # (pipelines/futures/CLAUDE.md). Guessing either would fabricate data.
    out = curve_settles_frame(_lake())

    assert out["expiry"].isna().all()
    assert out["oi"].isna().all()


def test_curve_settles_is_empty_when_no_contract_coded_series_exist() -> None:
    ranks_only = _lake()
    ranks_only = ranks_only[ranks_only["source"] == "eia"]

    out = curve_settles_frame(ranks_only)

    assert out.empty
    assert list(out.columns) == [
        "root",
        "trade_date",
        "contract",
        "expiry",
        "settle",
        "oi",
        "source",
    ]


# --- spreads -------------------------------------------------------------------------


def test_spreads_are_front_minus_back_so_a_positive_value_is_backwardation() -> None:
    out = spreads_frame(_lake())
    cl = out[(out["root"] == "CL") & (out["trade_date"] == date(2024, 4, 5))]
    by_legs = dict(zip(cl["legs"], cl["value"], strict=True))

    assert by_legs["M1-M2"] == pytest.approx(86.91 - 86.20)
    assert by_legs["M1-M3"] == pytest.approx(86.91 - 85.40)
    assert by_legs["M1-M4"] == pytest.approx(86.91 - 84.55)
    assert by_legs["M2-M3"] == pytest.approx(86.20 - 85.40)
    assert by_legs["M3-M4"] == pytest.approx(85.40 - 84.55)
    assert by_legs["M1-M2"] > 0  # this curve is backwardated


def test_spread_sign_convention_matches_core_curve_time_spreads() -> None:
    # core/curve.py::time_spreads is this project's existing rank-spread definition
    # (s12 = f01 - f02). The serving copy must not invent a second convention.
    unadj = pd.DataFrame(
        {"f01": [86.91], "f02": [86.20], "f03": [85.40], "f04": [84.55]},
        index=pd.to_datetime(["2024-04-05"]),
    )
    reference = time_spreads(unadj)

    out = spreads_frame(_lake())
    cl = out[(out["root"] == "CL") & (out["trade_date"] == date(2024, 4, 5))]
    by_legs = dict(zip(cl["legs"], cl["value"], strict=True))

    assert by_legs["M1-M2"] == pytest.approx(reference["s12"].iloc[0])
    assert by_legs["M1-M3"] == pytest.approx(reference["s13"].iloc[0])
    assert by_legs["M2-M3"] == pytest.approx(reference["s23"].iloc[0])


def test_spreads_emits_only_the_legs_four_ranks_permit() -> None:
    out = spreads_frame(_lake())

    assert set(out["legs"]) <= {legs for legs, _, _ in SPREAD_LEGS}
    assert {legs for legs, _, _ in SPREAD_LEGS} == {
        "M1-M2",
        "M1-M3",
        "M1-M4",
        "M2-M3",
        "M3-M4",
    }
    # M1-M12 appears in the spec's own example but only ranks 1-4 exist in the lake,
    # so it is not computable and must never be emitted.
    assert "M1-M12" not in set(out["legs"])


def test_spreads_skips_a_leg_whose_second_rank_is_missing_rather_than_filling_it() -> None:
    # The rb rows carry f01..f03 only for 2024-04-05, so every M*-M4 leg is absent --
    # an inner join, never a forward fill.
    out = spreads_frame(_lake())
    rb = out[out["root"] == "RB"]

    assert sorted(rb["legs"]) == ["M1-M2", "M1-M3", "M2-M3"]


def test_spreads_ignores_the_contract_coded_series() -> None:
    out = spreads_frame(_lake())

    assert "LCO" not in set(out["root"])
    assert set(out["root"]) == {"CL", "RB"}


def test_spreads_covers_every_trade_date_with_a_complete_rank_set() -> None:
    out = spreads_frame(_lake())
    cl = out[out["root"] == "CL"]

    assert sorted(set(cl["trade_date"])) == [date(2024, 4, 4), date(2024, 4, 5)]
    assert len(cl) == 10  # two dates x five legs


def test_spreads_frame_has_exactly_the_serving_columns() -> None:
    out = spreads_frame(_lake())

    assert list(out.columns) == ["root", "trade_date", "legs", "value"]


def test_spreads_is_empty_when_no_rank_series_exist() -> None:
    contracts_only = _lake()
    contracts_only = contracts_only[contracts_only["source"] == "manual"]

    out = spreads_frame(contracts_only)

    assert out.empty
    assert list(out.columns) == ["root", "trade_date", "legs", "value"]


# --- main ----------------------------------------------------------------------------


class _FakeCopy:
    def __init__(self, cursor: _FakeCursor, sql: str) -> None:
        self.cursor = cursor
        self.sql = sql

    def __enter__(self) -> _FakeCopy:
        self.cursor.copy_calls.append(self.sql)
        return self

    def __exit__(self, *exc: object) -> None:
        pass

    def write(self, data: str) -> None:
        self.cursor.copied_data.append(data)


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

    def cursor(self) -> _FakeCursor:
        return self.cur

    def commit(self) -> None:
        pass

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *exc: object) -> None:
        pass


def test_main_publishes_both_tables_without_touching_a_real_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _FakeConnection()
    monkeypatch.setattr("core.publish.psycopg.connect", lambda *a, **k: conn)
    monkeypatch.setattr("core.publish.settings.supabase_db_url", "postgresql://fake")
    monkeypatch.setattr(
        "pipelines.futures.publish_curve.read_futures_settles", lambda: _lake()
    )

    main()

    logged = [
        params
        for sql, params in conn.cur.executed
        if "insert into serving.publish_log" in sql
    ]
    assert [p[0] for p in logged if p is not None] == ["curve_settles", "spreads"]
    assert all(p is not None and p[4] == "curve" for p in logged)
    assert all(p is not None and isinstance(p[1], datetime) for p in logged)

    upserts = [sql for sql, _ in conn.cur.executed if "on conflict" in sql]
    assert any("(root, trade_date, contract) do update" in sql for sql in upserts)
    assert any("(root, trade_date, legs) do update" in sql for sql in upserts)
