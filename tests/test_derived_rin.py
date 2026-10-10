"""Tests for pipelines/derived/rin.py.

Every demand figure here is synthetic. Expected values are computed by hand, with the working
beside each assertion: gallons = (gasoline + distillate) mbd * 1e6 * days * 42, and
billion RINs = gallons * pct / 1e9.
"""

from __future__ import annotations

import pandas as pd
import pytest

_INGESTED = pd.Timestamp("2026-10-10")
_ID = "derived.rin.mandate"


def _standards(rows: list[tuple[int, str, float, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "year": [r[0] for r in rows],
            "category": [r[1] for r in rows],
            "pct": [r[2] for r in rows],
            "status": [r[3] for r in rows],
            "source": "synthetic",
            "as_of": pd.Timestamp("2026-10-10"),
        }
    )


_STANDARDS = _standards(
    [
        (2026, "total", 0.10, "final"),
        (2026, "advanced", 0.04, "final"),
        (2027, "total", 0.10, "final"),
        (2028, "total", 0.10, "final"),
    ]
)


def _steo(series: str, label: str, periods: list[str], value: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": f"steo.{series}.{label}",
            "source": "eia_steo",
            "ts": pd.to_datetime(periods),
            "value": value,
            "unit": "million barrels per day",
            "geo": "US",
            "freq": "M",
            "revision_date": _INGESTED,
        }
    )


def _legs(period: str, label: str, gasoline: float = 6.0, distillate: float = 4.0) -> pd.DataFrame:
    return pd.concat(
        [
            _steo("mgtcpusx_p", label, [period], gasoline),
            _steo("dftcpus_p", label, [period], distillate),
        ]
    )


def _build(steo: pd.DataFrame, standards: pd.DataFrame = _STANDARDS) -> pd.DataFrame:
    from pipelines.derived.rin import build_mandate_rows

    return build_mandate_rows(steo, standards, _INGESTED)


def _value(rows: pd.DataFrame, series_id: str, ts: str) -> float:
    hit = rows[(rows["series_id"] == series_id) & (rows["ts"] == pd.Timestamp(ts))]
    assert len(hit) == 1, (series_id, ts, rows[["series_id", "ts"]])
    return float(hit["value"].iloc[0])


# --- one full month, end to end -------------------------------------------------------


def test_one_month_end_to_end_is_computed_by_hand() -> None:
    # January 2026: 31 days. (6.0 + 4.0) = 10 mbd -> 10e6 * 31 * 42 = 13.02e9 gallons.
    # total   10.0 per cent: 13.02e9 * 0.10 / 1e9 = 1.302
    # advanced 4.0 per cent: 13.02e9 * 0.04 / 1e9 = 0.5208
    rows = _build(_legs("2026-01-01", "observed"))

    assert _value(rows, f"{_ID}.total.observed.final", "2026-01-01") == pytest.approx(1.302)
    assert _value(rows, f"{_ID}.advanced.observed.final", "2026-01-01") == pytest.approx(0.5208)
    assert set(rows["unit"]) == {"billion RINs"}
    assert set(rows["source"]) == {"derived"}
    assert rows["value"].dtype == "float64"
    assert set(rows["series_id"]) == {
        f"{_ID}.total.observed.final",
        f"{_ID}.advanced.observed.final",
    }


# --- observed beats projected ---------------------------------------------------------


def test_prefer_observed_drops_the_projected_twin_of_an_observed_month() -> None:
    from pipelines.derived.rin import prefer_observed

    steo = pd.concat(
        [
            _steo("mgtcpusx_p", "observed", ["2026-01-01"], 6.0),
            _steo("mgtcpusx_p", "projected", ["2026-01-01", "2026-02-01"], 9.0),
        ]
    )
    kept = prefer_observed(steo)

    by_month = {
        ts: (sid, val)
        for ts, sid, val in zip(kept["ts"], kept["series_id"], kept["value"], strict=True)
    }
    assert by_month[pd.Timestamp("2026-01-01")] == ("steo.mgtcpusx_p.observed", 6.0)
    # February exists only as a projection, so it is kept.
    assert by_month[pd.Timestamp("2026-02-01")] == ("steo.mgtcpusx_p.projected", 9.0)
    assert len(kept) == 2


def test_a_month_under_both_labels_uses_the_observed_value() -> None:
    # Observed legs 6.0 + 4.0 = 10 mbd -> 1.302 (see the end-to-end test). The stale
    # projected legs (9.0 + 8.0 = 17 mbd) would give 17e6*31*42*0.10/1e9 = 2.2134.
    steo = pd.concat([_legs("2026-01-01", "observed"), _legs("2026-01-01", "projected", 9.0, 8.0)])
    rows = _build(steo)

    assert list(rows[rows["series_id"].str.contains(".total.")]["series_id"]) == [
        f"{_ID}.total.observed.final"
    ]
    assert _value(rows, f"{_ID}.total.observed.final", "2026-01-01") == pytest.approx(1.302)


# --- labels ---------------------------------------------------------------------------


def test_one_projected_leg_makes_the_derived_row_projected() -> None:
    # Gasoline measured, distillate projected: the month rests on a projection.
    steo = pd.concat(
        [
            _steo("mgtcpusx_p", "observed", ["2026-01-01"], 6.0),
            _steo("dftcpus_p", "projected", ["2026-01-01"], 4.0),
        ]
    )
    rows = _build(steo)

    assert set(rows["series_id"]) == {
        f"{_ID}.total.projected.final",
        f"{_ID}.advanced.projected.final",
    }
    assert _value(rows, f"{_ID}.total.projected.final", "2026-01-01") == pytest.approx(1.302)


def test_observed_and_projected_months_land_in_separate_series() -> None:
    rows = _build(pd.concat([_legs("2026-01-01", "observed"), _legs("2026-03-01", "projected")]))

    ids = set(rows["series_id"])
    assert f"{_ID}.total.observed.final" in ids
    assert f"{_ID}.total.projected.final" in ids
    for series_id in ids:
        assert series_id.split(".")[-2] in ("observed", "projected"), series_id
        assert series_id.split(".")[-1] in ("final", "proposed"), series_id


def test_the_status_label_comes_from_the_reference_row_not_a_constant() -> None:
    # 2026 final, 2027 proposed (synthetic): each month takes its own year's status.
    # Jan 2026: 1.302 (31 days). Jan 2027 is also 31 days and 10 mbd: 1.302.
    standards = _standards([(2026, "total", 0.10, "final"), (2027, "total", 0.10, "proposed")])
    steo = pd.concat([_legs("2026-01-01", "observed"), _legs("2027-01-01", "projected")])
    rows = _build(steo, standards)

    assert _value(rows, f"{_ID}.total.observed.final", "2026-01-01") == pytest.approx(1.302)
    assert _value(rows, f"{_ID}.total.projected.proposed", "2027-01-01") == pytest.approx(1.302)
    assert set(rows["series_id"]) == {
        f"{_ID}.total.observed.final",
        f"{_ID}.total.projected.proposed",
    }


def test_duplicate_standard_rows_are_refused() -> None:
    standards = _standards([(2026, "total", 0.10, "final"), (2026, "total", 0.11, "proposed")])
    with pytest.raises(ValueError, match="duplicate"):
        _build(_legs("2026-01-01", "observed"), standards)


# --- missing data is not zero ---------------------------------------------------------


def test_a_month_missing_one_denominator_leg_writes_no_row() -> None:
    steo = pd.concat(
        [
            _legs("2026-01-01", "observed"),
            _steo("mgtcpusx_p", "observed", ["2026-02-01"], 6.0),  # no distillate in February
        ]
    )
    rows = _build(steo)

    assert set(rows["ts"]) == {pd.Timestamp("2026-01-01")}


def test_a_month_missing_a_leg_entirely_gives_an_empty_frame() -> None:
    assert _build(_steo("mgtcpusx_p", "observed", ["2026-01-01"], 6.0)).empty


def test_a_year_with_no_standard_writes_no_row() -> None:
    # 2025 demand, standards only for 2026-28: not a mandate for either year.
    assert _build(_legs("2025-06-01", "observed")).empty


def test_a_category_with_no_standard_that_year_writes_no_row_for_it() -> None:
    standards = _standards([(2026, "total", 0.10, "final")])
    rows = _build(_legs("2026-01-01", "observed"), standards)
    assert set(rows["series_id"]) == {f"{_ID}.total.observed.final"}


# --- days come from the period itself -------------------------------------------------


def test_february_in_a_leap_year_has_one_more_day_than_a_common_year() -> None:
    # 10 mbd. Feb 2027 (28 days): 10e6 * 28 * 42 = 11.76e9 gal -> *0.10/1e9 = 1.176
    #         Feb 2028 (29 days): 10e6 * 29 * 42 = 12.18e9 gal -> *0.10/1e9 = 1.218
    steo = pd.concat([_legs("2027-02-01", "projected"), _legs("2028-02-01", "projected")])
    rows = _build(steo)

    assert _value(rows, f"{_ID}.total.projected.final", "2027-02-01") == pytest.approx(1.176)
    assert _value(rows, f"{_ID}.total.projected.final", "2028-02-01") == pytest.approx(1.218)


def test_days_in_period_reads_the_calendar() -> None:
    from pipelines.derived.rin import days_in_period

    assert days_in_period(pd.Timestamp("2028-02-01")) == 29
    assert days_in_period(pd.Timestamp("2027-02-01")) == 28
    assert days_in_period(pd.Timestamp("2026-04-01")) == 30
    assert days_in_period(pd.Timestamp("2026-12-01")) == 31


# --- the denominator ------------------------------------------------------------------


def test_the_headline_series_are_never_used() -> None:
    # Only the headline (renewables-inclusive) pair present: nothing may be derived.
    headline = pd.concat(
        [
            _steo("mgtcpusx", "observed", ["2026-01-01"], 8.0),
            _steo("dftcpus", "observed", ["2026-01-01"], 5.0),
        ]
    )
    assert _build(headline).empty

    # Both pairs present: the _P pair (10 mbd -> 1.302) wins. The headline pair
    # (13 mbd) would give 13e6*31*42*0.10/1e9 = 1.6926.
    rows = _build(pd.concat([headline, _legs("2026-01-01", "observed")]))
    assert _value(rows, f"{_ID}.total.observed.final", "2026-01-01") == pytest.approx(1.302)


def test_the_series_read_are_the_registered_denominator_codes() -> None:
    from pipelines.derived.rin import DENOMINATOR_SERIES
    from pipelines.eia.steo_series import RFS_DENOMINATOR_CODES

    assert tuple(f"steo.{c.lower()}" for c in RFS_DENOMINATOR_CODES) == DENOMINATOR_SERIES
    assert all(s.endswith("_p") for s in DENOMINATOR_SERIES)


# --- input wiring ---------------------------------------------------------------------


def test_the_standards_are_not_read_from_beside_the_lake(tmp_path, monkeypatch) -> None:
    """Guards the hormuz lesson: standards arrive as an argument, never by path discovery."""
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")
    assert not list(tmp_path.rglob("percentage_standards.csv"))

    assert not _build(_legs("2026-01-01", "observed")).empty


# --- main, through a temporary lake ----------------------------------------------------


@pytest.fixture
def lake(tmp_path, monkeypatch):
    from core import storage
    from pipelines.derived import rin

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")
    monkeypatch.setattr(rin, "load_percentage_standards", lambda: _STANDARDS)
    return storage


def test_main_writes_the_series_and_leaves_gaps_as_gaps(lake) -> None:
    from pipelines.derived import rin

    seeded = pd.concat(
        [
            _legs("2026-01-01", "observed"),
            _legs("2026-01-01", "projected", 9.0, 8.0),  # stale twin, must lose
            _steo("mgtcpusx_p", "projected", ["2026-02-01"], 6.0),  # distillate missing
            _legs("2026-03-01", "projected"),
            _legs("2025-06-01", "observed"),  # no 2025 standard
        ]
    )
    lake.write_ts_long(seeded, source="eia_steo")

    rin.main()

    written = lake.read_ts_long(source="derived")
    assert set(written["series_id"]) == {
        f"{_ID}.total.observed.final",
        f"{_ID}.advanced.observed.final",
        f"{_ID}.total.projected.final",
        f"{_ID}.advanced.projected.final",
    }
    # Jan 2026 observed 1.302; Mar 2026 (31 days) projected 1.302; nothing for Feb or 2025.
    total = written[written["series_id"].str.contains(r"\.total\.")]
    assert sorted(total["ts"]) == [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-03-01")]
    assert _value(written, f"{_ID}.total.observed.final", "2026-01-01") == pytest.approx(1.302)
    assert _value(written, f"{_ID}.total.projected.final", "2026-03-01") == pytest.approx(1.302)


def test_main_fails_loudly_and_writes_nothing_on_an_empty_lake(lake) -> None:
    from core.failures import PartialFailureError
    from pipelines.derived import rin

    with pytest.raises(PartialFailureError):
        rin.main()

    assert lake.read_ts_long(source="derived").empty


def test_main_fails_loudly_when_no_row_can_be_derived(lake) -> None:
    from core.failures import PartialFailureError
    from pipelines.derived import rin

    lake.write_ts_long(_legs("2025-06-01", "observed"), source="eia_steo")  # no 2025 standard

    with pytest.raises(PartialFailureError):
        rin.main()

    assert lake.read_ts_long(source="derived").empty
