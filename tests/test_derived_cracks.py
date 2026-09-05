from __future__ import annotations

import pandas as pd
import pytest
from pipelines.derived.cracks import CRACK_DEFS, build_cracks, derived_rows


def _panel() -> pd.DataFrame:
    """Two dates of spot legs, in the same wide shape the lake read produces.

    WTI stops a day early on purpose: FRED genuinely publishes DCOILWTICO a few days
    behind the product spots, so the ragged right-hand end is the real-world case.
    """
    idx = pd.to_datetime(["2026-01-02", "2026-01-05"])
    return pd.DataFrame(
        {
            "fred.dcoilwtico": [70.0, float("nan")],
            "fred.dcoilbrenteu": [72.0, float("nan")],
            "fred.dgasnyh": [2.20, 2.30],
            "fred.dhoilnyh": [2.40, 2.50],
            "fred.dgasusgulf": [2.10, 2.20],
            "fred.ddfuelusgulf": [2.35, 2.45],
        },
        index=idx,
    )


def test_every_crack_def_names_legs_that_exist_in_the_lake_convention() -> None:
    """Guards the project's own 'never guess a series_id' rule -- every leg must be a
    lowercase-dotted fred.* id, the verified convention for this source."""
    for spec in CRACK_DEFS.values():
        for leg in spec.legs:
            assert leg.startswith("fred."), leg
            assert leg == leg.lower(), leg


def test_build_cracks_computes_the_us_321_from_nyh_legs() -> None:
    cracks = build_cracks(_panel())
    assert cracks.loc[pd.Timestamp("2026-01-02"), "us321"] == pytest.approx(25.20, abs=0.01)


def test_build_cracks_drops_dates_where_the_crude_leg_has_not_printed() -> None:
    cracks = build_cracks(_panel())
    assert cracks["us321"].dropna().index.tolist() == [pd.Timestamp("2026-01-02")]


def test_build_cracks_computes_the_gulf_321_from_gulf_legs() -> None:
    # (2*2.10*42 + 2.35*42 - 3*70)/3 = (176.40 + 98.70 - 210)/3 = 65.10/3 = 21.70
    cracks = build_cracks(_panel())
    assert cracks.loc[pd.Timestamp("2026-01-02"), "gulf321"] == pytest.approx(21.70, abs=0.01)


def test_build_cracks_skips_a_crack_whose_legs_are_absent() -> None:
    """No ICE gasoil or Singapore gasoil exists in the lake, so those cracks must be
    omitted rather than produced as a column of NaN."""
    panel = _panel().drop(columns=["fred.dgasusgulf", "fred.ddfuelusgulf"])
    cracks = build_cracks(panel)
    assert "gulf321" not in cracks.columns
    assert "us321" in cracks.columns


def test_derived_rows_use_the_spec_series_id_and_are_float64() -> None:
    """`derived.crack.<name>.<tenor>` per Spec 20, and float64 per the v0.11 lesson in
    specs/00_TRADING_CONVENTIONS.md (a sub-dollar crack must not read back as 0)."""
    cracks = build_cracks(_panel())
    rows = derived_rows("us321", cracks["us321"].dropna(), pd.Timestamp("2026-02-01"))
    assert rows["series_id"].unique().tolist() == ["derived.crack.us321.spot"]
    assert rows["value"].dtype == "float64"
    assert rows["unit"].unique().tolist() == ["USD/bbl"]
    assert rows["source"].unique().tolist() == ["derived"]


def test_derived_rows_is_empty_for_an_empty_series() -> None:
    rows = derived_rows("us321", pd.Series(dtype=float), pd.Timestamp("2026-02-01"))
    assert rows.empty
