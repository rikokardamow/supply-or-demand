from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from core.cracks import (
    GAL_PER_BBL,
    GASOIL_BBL_PER_TONNE,
    RBOB_SPLICE_DATE,
    crack_211,
    crack_321,
    crack_board,
    crack_gasoil_nwe,
    crack_ho,
    crack_rbob,
    crack_seasonal_heatmap,
    crack_sg_go,
    gal_to_bbl,
    rbob_splice_flag,
    tonne_to_bbl_gasoil,
)

# --- unit conversions -------------------------------------------------------------


def test_gal_to_bbl_uses_42_gallons_per_barrel() -> None:
    assert GAL_PER_BBL == 42.0
    assert gal_to_bbl(2.20) == pytest.approx(92.40)


def test_gal_to_bbl_converts_a_series_elementwise() -> None:
    prices = pd.Series([2.20, 2.40], index=pd.to_datetime(["2026-01-02", "2026-01-05"]))
    converted = gal_to_bbl(prices)
    assert isinstance(converted, pd.Series)
    assert converted.tolist() == pytest.approx([92.40, 100.80])


def test_tonne_to_bbl_gasoil_divides_by_7_45() -> None:
    """ICE gasoil trades in $/tonne; the spec's conversion is $/t / 7.45 -> $/bbl."""
    assert GASOIL_BBL_PER_TONNE == 7.45
    assert tonne_to_bbl_gasoil(745.0) == pytest.approx(100.0)


# --- crack formulae ---------------------------------------------------------------


def test_crack_321_matches_the_worked_example() -> None:
    """Spec 20 Session A's own worked example, with its arithmetic corrected.

    The spec text asserts 28.53 for these inputs. That constant is wrong:
    2.20*42 = 92.40, 2.40*42 = 100.80, (2*92.40 + 100.80 - 3*70)/3 = 75.60/3 = 25.20.
    No gallons-per-barrel factor yields 28.53 (it would need 43.47), and both readings
    of the 3:2:1 formula -- (2*rb42 + ho42 - 3*cl)/3 and (2*rb42 + ho42)/3 - cl -- are
    algebraically identical. Correction recorded in the spec file itself.
    """
    assert crack_321(70.0, 2.20, 2.40) == pytest.approx(25.20, abs=0.01)


def test_crack_321_two_algebraic_forms_agree() -> None:
    cl, rb, ho = 82.5, 2.31, 2.57
    grouped = (2 * gal_to_bbl(rb) + gal_to_bbl(ho) - 3 * cl) / 3
    netted = (2 * gal_to_bbl(rb) + gal_to_bbl(ho)) / 3 - cl
    assert crack_321(cl, rb, ho) == pytest.approx(grouped)
    assert crack_321(cl, rb, ho) == pytest.approx(netted)


def test_crack_211_weights_gasoline_and_distillate_equally() -> None:
    # (92.40 + 100.80 - 2*70)/2 = 53.20/2 = 26.60
    assert crack_211(70.0, 2.20, 2.40) == pytest.approx(26.60, abs=0.01)


def test_crack_rbob_is_a_single_product_crack() -> None:
    assert crack_rbob(70.0, 2.20) == pytest.approx(22.40, abs=0.01)


def test_crack_ho_is_a_single_product_crack() -> None:
    assert crack_ho(70.0, 2.40) == pytest.approx(30.80, abs=0.01)


def test_crack_gasoil_nwe_converts_tonnes_before_subtracting_brent() -> None:
    # 745/7.45 = 100.00 $/bbl gasoil, less 70 Brent = 30.00
    assert crack_gasoil_nwe(70.0, 745.0) == pytest.approx(30.00, abs=0.01)


def test_crack_sg_go_takes_both_legs_already_in_dollars_per_barrel() -> None:
    """Singapore gasoil arrives from the manual physical drop already in $/bbl -- this
    crack must not apply a second unit conversion to either leg."""
    assert crack_sg_go(70.0, 88.5) == pytest.approx(18.50, abs=0.01)


def test_crack_321_operates_on_aligned_series() -> None:
    idx = pd.to_datetime(["2026-01-02", "2026-01-05"])
    cl = pd.Series([70.0, 60.0], index=idx)
    rb = pd.Series([2.20, 2.00], index=idx)
    ho = pd.Series([2.40, 2.10], index=idx)
    result = crack_321(cl, rb, ho)
    assert isinstance(result, pd.Series)
    # 2026-01-05: (2*84.00 + 88.20 - 3*60)/3 = 76.20/3 = 25.40
    assert result.tolist() == pytest.approx([25.20, 25.40])


def test_crack_321_aligns_ragged_series_and_drops_unmatched_dates() -> None:
    """WTI/Brent publish a few days behind the product spots on FRED, so the crude and
    product legs genuinely have ragged right-hand ends in the real lake."""
    cl = pd.Series([70.0], index=pd.to_datetime(["2026-01-02"]))
    rb = pd.Series([2.20, 2.00], index=pd.to_datetime(["2026-01-02", "2026-01-05"]))
    ho = pd.Series([2.40, 2.10], index=pd.to_datetime(["2026-01-02", "2026-01-05"]))
    result = crack_321(cl, rb, ho)
    assert result.index.tolist() == [pd.Timestamp("2026-01-02")]
    assert result.iloc[0] == pytest.approx(25.20)


# --- RBOB splice ------------------------------------------------------------------


def test_rbob_splice_flag_marks_pre_2006_observations() -> None:
    """NYMEX unleaded (HU) became RBOB at the start of 2006 -- a crack series spanning
    that change is spliced across two different contracts and must say so."""
    idx = pd.to_datetime(["2005-06-01", "2006-06-01"])
    flags = rbob_splice_flag(idx)
    assert pd.Timestamp("2006-01-01") == RBOB_SPLICE_DATE
    assert flags.tolist() == [True, False]


# --- board ------------------------------------------------------------------------


def _synthetic_cracks() -> pd.DataFrame:
    """Five full years of daily cracks. 'crack_321' rises 20 -> 24 across 2022-2026;
    'crack_ho' is flat at 15 except in 2020, which is a wild outlier the seasonal maths
    must exclude."""
    bases = {2020: 99.0, 2022: 20.0, 2023: 21.0, 2024: 22.0, 2025: 23.0, 2026: 24.0}
    frames = []
    for year, base in bases.items():
        dates = pd.date_range(f"{year}-01-01", f"{year}-03-31", freq="D")
        frames.append(
            pd.DataFrame(
                {"ts": dates, "crack_321": base, "crack_ho": 99.0 if year == 2020 else 15.0}
            )
        )
    return pd.concat(frames, ignore_index=True).set_index("ts")


def test_crack_board_reports_latest_spot_per_crack() -> None:
    board = crack_board(_synthetic_cracks(), as_of=pd.Timestamp("2026-03-31"))
    row = board.set_index("crack").loc["crack_321"]
    assert row["spot"] == pytest.approx(24.0)


def test_crack_board_has_the_columns_the_spec_names() -> None:
    board = crack_board(_synthetic_cracks(), as_of=pd.Timestamp("2026-03-31"))
    assert list(board.columns) == [
        "crack",
        "spot",
        "m1",
        "m2",
        "m6",
        "seasonal_5y_mean",
        "pct_rank_5y",
    ]


def test_crack_board_tenor_columns_are_nan_without_a_futures_panel() -> None:
    """No fut.* settlements exist in the lake yet (Spec 18 has never ingested real
    data), so m1/m2/m6 must read as 'not available', never as 0.0."""
    board = crack_board(_synthetic_cracks(), as_of=pd.Timestamp("2026-03-31"))
    assert board[["m1", "m2", "m6"]].isna().all().all()


def test_crack_board_fills_tenors_from_a_supplied_futures_panel() -> None:
    tenors = pd.DataFrame({"m1": [24.5], "m2": [24.8], "m6": [25.6]}, index=["crack_321"])
    board = crack_board(
        _synthetic_cracks(), tenors=tenors, as_of=pd.Timestamp("2026-03-31")
    ).set_index("crack")
    assert board.loc["crack_321", "m1"] == pytest.approx(24.5)
    assert np.isnan(board.loc["crack_ho", "m1"])


def test_crack_board_seasonal_mean_excludes_2020() -> None:
    """crack_ho is 15.0 in every year except 2020's 99.0 outlier.

    as_of is deliberately 2024, so 2020 falls *inside* the five-year window
    (2020-2024) and the exclusion has to do real work -- with a 2026 as_of the window
    starts at 2022 and the guard would pass vacuously. A leaked 2020 gives
    (99 + 15 + 15 + 15)/4 = 36.0, nowhere near 15.
    """
    board = crack_board(_synthetic_cracks(), as_of=pd.Timestamp("2024-03-31")).set_index("crack")
    assert board.loc["crack_ho", "seasonal_5y_mean"] == pytest.approx(15.0, abs=0.01)


def test_crack_board_pct_rank_is_100_at_a_five_year_high() -> None:
    """crack_321 ends at its highest level in the sample, so it ranks at the top."""
    board = crack_board(_synthetic_cracks(), as_of=pd.Timestamp("2026-03-31")).set_index("crack")
    assert board.loc["crack_321", "pct_rank_5y"] == pytest.approx(100.0, abs=0.5)


def test_crack_board_as_of_ignores_later_observations() -> None:
    """A board struck mid-sample must not see the future -- the same look-ahead guard
    Session C's signal needs."""
    board = crack_board(_synthetic_cracks(), as_of=pd.Timestamp("2024-02-01")).set_index("crack")
    assert board.loc["crack_321", "spot"] == pytest.approx(22.0)


# --- seasonal heatmap -------------------------------------------------------------


def test_crack_seasonal_heatmap_is_years_by_months() -> None:
    crack = _synthetic_cracks()["crack_321"]
    heat = crack_seasonal_heatmap(crack)
    assert heat.index.name == "year"
    assert heat.columns.tolist() == [1, 2, 3]
    assert heat.loc[2026, 1] == pytest.approx(24.0)


def test_crack_seasonal_heatmap_keeps_2020_visible() -> None:
    """Unlike the seasonal *statistics*, the heatmap is a descriptive picture of what
    actually happened -- 2020 belongs on it, clearly visible as the outlier it was."""
    heat = crack_seasonal_heatmap(_synthetic_cracks()["crack_321"])
    assert 2020 in heat.index
