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
    from pipelines.eia.steo_series import RFS_DENOMINATOR_CODES, lake_series_id

    assert tuple(lake_series_id(c) for c in RFS_DENOMINATOR_CODES) == DENOMINATOR_SERIES
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


# --- tie-break and calendar-year standards -----------------------------------------------


def test_prefer_observed_takes_the_latest_revision_of_the_same_label() -> None:
    from pipelines.derived.rin import prefer_observed

    old = _steo("mgtcpusx_p", "observed", ["2026-01-01"], 5.0).assign(
        revision_date=pd.Timestamp("2026-08-01")
    )
    new = _steo("mgtcpusx_p", "observed", ["2026-01-01"], 6.0).assign(
        revision_date=pd.Timestamp("2026-09-01")
    )
    for frame in (pd.concat([old, new]), pd.concat([new, old])):
        kept = prefer_observed(frame)
        assert list(kept["value"]) == [6.0]


def test_december_and_january_each_take_their_own_years_standard() -> None:
    # 10 mbd, 31 days: 13.02e9 gal. Dec 2026 at 0.10 -> 1.302; Jan 2027 at 0.20 -> 2.604.
    standards = _standards([(2026, "total", 0.10, "final"), (2027, "total", 0.20, "final")])
    steo = pd.concat([_legs("2026-12-01", "observed"), _legs("2027-01-01", "observed")])
    rows = _build(steo, standards)

    assert _value(rows, f"{_ID}.total.observed.final", "2026-12-01") == pytest.approx(1.302)
    assert _value(rows, f"{_ID}.total.observed.final", "2027-01-01") == pytest.approx(2.604)


# --- reading derived rows back: one row per category and month ---------------------------


def _derived(
    category: str, month: str, label: str, status: str, value: float, revision: str = "2026-10-10"
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": f"{_ID}.{category}.{label}.{status}",
            "source": "derived",
            "ts": pd.to_datetime([month]),
            "value": value,
            "unit": "billion RINs",
            "geo": "US",
            "freq": "M",
            "revision_date": pd.Timestamp(revision),
        }
    )


def _resolve(*frames: pd.DataFrame) -> pd.DataFrame:
    from pipelines.derived.rin import resolve_mandate_twins

    return resolve_mandate_twins(pd.concat(frames))


def test_observed_beats_projected_for_the_same_month() -> None:
    out = _resolve(
        _derived("total", "2026-01-01", "projected", "final", 9.0),
        _derived("total", "2026-01-01", "observed", "final", 1.0),
    )
    assert len(out) == 1
    assert out["value"].iloc[0] == 1.0
    assert (out["label"].iloc[0], out["status"].iloc[0]) == ("observed", "final")


def test_final_beats_proposed_for_the_same_month() -> None:
    out = _resolve(
        _derived("total", "2026-01-01", "projected", "proposed", 9.0),
        _derived("total", "2026-01-01", "projected", "final", 2.0),
    )
    assert len(out) == 1
    assert out["value"].iloc[0] == 2.0
    assert (out["label"].iloc[0], out["status"].iloc[0]) == ("projected", "final")


def test_observed_proposed_beats_projected_final() -> None:
    # Observed is ranked first, so a measured-but-proposed row wins; status stays visible.
    out = _resolve(
        _derived("total", "2026-01-01", "projected", "final", 9.0),
        _derived("total", "2026-01-01", "observed", "proposed", 3.0),
    )
    assert len(out) == 1
    assert out["value"].iloc[0] == 3.0
    assert (out["label"].iloc[0], out["status"].iloc[0]) == ("observed", "proposed")


def test_a_full_tie_goes_to_the_latest_revision() -> None:
    out = _resolve(
        _derived("total", "2026-01-01", "observed", "final", 1.0, "2026-09-01"),
        _derived("total", "2026-01-01", "observed", "final", 1.5, "2026-10-01"),
    )
    assert list(out["value"]) == [1.5]


def test_a_single_row_comes_back_unchanged_and_other_series_are_ignored() -> None:
    other = _derived("total", "2026-01-01", "observed", "final", 7.0).assign(
        series_id="derived.crack.us321.spot"
    )
    out = _resolve(_derived("advanced", "2026-02-01", "projected", "final", 0.5), other)
    assert out.to_dict("records") == [
        {
            "category": "advanced",
            "ts": pd.Timestamp("2026-02-01"),
            "value": 0.5,
            "unit": "billion RINs",
            "label": "projected",
            "status": "final",
        }
    ]


def test_never_two_rows_for_one_category_and_month() -> None:
    frames = [
        _derived(cat, month, label, status, 1.0)
        for cat in ("total", "advanced")
        for month in ("2026-01-01", "2026-02-01")
        for label in ("observed", "projected")
        for status in ("final", "proposed")
    ]
    out = _resolve(*frames)
    assert len(out) == 4
    assert not out.duplicated(["category", "ts"]).any()
    assert set(out["label"]) == {"observed"} and set(out["status"]) == {"final"}


def test_an_empty_frame_resolves_to_an_empty_frame_with_the_columns() -> None:
    from pipelines.derived.rin import resolve_mandate_twins

    out = resolve_mandate_twins(pd.DataFrame())
    assert out.empty
    assert list(out.columns) == ["category", "ts", "value", "unit", "label", "status"]


def test_two_runs_with_a_moved_boundary_leave_twins_that_the_reader_resolves(lake) -> None:
    from pipelines.derived import rin

    # Run 1: January is still a projection.
    lake.write_ts_long(_legs("2026-01-01", "projected"), source="eia_steo")
    rin.main()
    # Run 2: the boundary has moved; January is now measured (different value, 12 mbd).
    lake.write_ts_long(_legs("2026-01-01", "observed", 7.0, 5.0), source="eia_steo")
    rin.main()

    raw = lake.read_ts_long(source="derived")
    total = raw[raw["series_id"].str.contains(r"\.total\.")]
    assert set(total["series_id"]) == {
        f"{_ID}.total.projected.final",
        f"{_ID}.total.observed.final",
    }

    out = rin.resolve_mandate_twins(raw)
    total_out = out[out["category"] == "total"]
    # Observed legs 7.0 + 5.0 = 12 mbd: 12e6 * 31 * 42 = 15.624e9 gal * 0.10 / 1e9 = 1.5624.
    assert len(total_out) == 1
    assert total_out["label"].iloc[0] == "observed"
    assert total_out["value"].iloc[0] == pytest.approx(1.5624)
