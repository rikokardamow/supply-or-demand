from __future__ import annotations

import re

import pandas as pd
import pytest
from pipelines.futures.barchart_curve import (
    MONTH_CODES,
    contract_code,
    curve_to_ts_long,
    load_spreads,
    reconstruct_curve,
)


def _spreads() -> pd.DataFrame:
    """The three-contract core of a real Barchart export, values taken verbatim from the
    2026-09-04 Brent Financial file."""
    return pd.DataFrame(
        [
            # SA is the strip average of its legs; SP is leg1 - leg2.
            {"Leg1": "QAX6", "Leg2": "QAZ6", "Leg3": None, "Type": "SA", "Latest": 94.30},
            {"Leg1": "QAX6", "Leg2": "QAZ6", "Leg3": None, "Type": "SP", "Latest": 3.96},
            {"Leg1": "QAX6", "Leg2": "QAF7", "Leg3": None, "Type": "SP", "Latest": 7.13},
            {"Leg1": "QAX6", "Leg2": "QAG7", "Leg3": None, "Type": "SP", "Latest": 9.63},
            # A butterfly must not be mistaken for a two-leg spread.
            {"Leg1": "QAX6", "Leg2": "QAZ6", "Leg3": "QAF7", "Type": "BF", "Latest": 0.79},
        ]
    )


# --- contract codes ---------------------------------------------------------------


def test_month_codes_follow_the_exchange_convention() -> None:
    assert MONTH_CODES["F"] == 1
    assert MONTH_CODES["X"] == 11
    assert MONTH_CODES["Z"] == 12
    assert len(MONTH_CODES) == 12


def test_contract_code_uses_a_four_digit_year() -> None:
    """Barchart writes a single-digit year (QAX6); the lake uses a FOUR-digit year.

    A two-digit year would collide with the nearby-rank namespace: January's exchange
    month letter is "F", so a Jan-2027 contract written `f27` is indistinguishable from
    rank 27 in the conventions' own `fut.<root>.f01.settle ... f36` scheme. Four digits
    cannot collide with a two-digit rank.
    """
    assert contract_code("QAX6", as_of_year=2026) == "x2026"
    assert contract_code("QAZ6", as_of_year=2026) == "z2026"
    assert contract_code("QAF7", as_of_year=2026) == "f2027"


def test_contract_code_rolls_a_single_digit_year_forward_past_the_decade() -> None:
    """A curve struck in 2026 running to 2034 cycles the year digit back through 0-4.
    Those are 2030-2034, never 2020-2024 -- the digit resolves to the first year at or
    after the as-of year."""
    assert contract_code("QAZ3", as_of_year=2026) == "z2033"
    assert contract_code("QAH4", as_of_year=2026) == "h2034"


def test_no_contract_code_can_be_mistaken_for_a_nearby_rank() -> None:
    """The regression guard for the collision this change exists to remove: no January
    (or any) contract code may match the rank pattern f01..f36."""
    for symbol in ("QAF7", "QAF3", "QAF0", "QAX6", "QAZ6"):
        code = contract_code(symbol, as_of_year=2026)
        rank_shaped = re.fullmatch(r"f(0[1-9]|[12][0-9]|3[0-6])", code)
        assert not rank_shaped, code


# --- reconstruction ---------------------------------------------------------------


def test_reconstruct_curve_solves_both_legs_from_a_strip_average_and_a_spread() -> None:
    """SA = (a+b)/2 and SP = a-b together pin both outrights: a = SA + SP/2."""
    curve = reconstruct_curve(_spreads(), as_of_year=2026)
    assert curve["x2026"] == pytest.approx(96.28, abs=0.005)
    assert curve["z2026"] == pytest.approx(92.32, abs=0.005)


def test_reconstruct_curve_matches_the_published_settlement() -> None:
    """The real independent check: Barchart quotes QAX26 at 96.28s, and the curve is
    rebuilt from spread quotes alone without ever reading that outright."""
    curve = reconstruct_curve(_spreads(), as_of_year=2026)
    assert curve["x2026"] == pytest.approx(96.28, abs=0.005)


def test_reconstruct_curve_extends_through_the_anchored_spreads() -> None:
    curve = reconstruct_curve(_spreads(), as_of_year=2026)
    assert curve["f2027"] == pytest.approx(96.28 - 7.13, abs=0.005)
    assert curve["g2027"] == pytest.approx(96.28 - 9.63, abs=0.005)


def test_reconstruct_curve_ignores_butterflies() -> None:
    """A BF row shares Leg1/Leg2 with a real spread; treating it as one would corrupt
    the curve."""
    curve = reconstruct_curve(_spreads(), as_of_year=2026)
    assert curve["z2026"] == pytest.approx(92.32, abs=0.005)


def test_reconstruct_curve_is_monotonically_ordered_by_delivery() -> None:
    curve = reconstruct_curve(_spreads(), as_of_year=2026)
    assert list(curve.index) == ["x2026", "z2026", "f2027", "g2027"]


def test_reconstruct_curve_without_a_strip_average_cannot_anchor() -> None:
    """Spreads alone fix the curve's shape but not its level. Returning an unanchored
    curve would be silently wrong, so this raises instead."""
    spreads = _spreads()
    with pytest.raises(ValueError, match="anchor"):
        reconstruct_curve(spreads[spreads["Type"] != "SA"], as_of_year=2026)


# --- lake rows --------------------------------------------------------------------


def test_curve_to_ts_long_uses_the_conventions_contract_series_id() -> None:
    curve = reconstruct_curve(_spreads(), as_of_year=2026)
    rows = curve_to_ts_long(curve, as_of=pd.Timestamp("2026-09-04"), root="lco")
    assert "fut.lco.x2026.settle" in set(rows["series_id"])
    assert rows["ts"].unique().tolist() == [pd.Timestamp("2026-09-04")]


def test_curve_to_ts_long_is_float64_and_dollars_per_barrel() -> None:
    curve = reconstruct_curve(_spreads(), as_of_year=2026)
    rows = curve_to_ts_long(curve, as_of=pd.Timestamp("2026-09-04"), root="lco")
    assert rows["value"].dtype == "float64"
    assert rows["unit"].unique().tolist() == ["USD/bbl"]


def test_curve_to_ts_long_records_the_real_provenance() -> None:
    """These settles are *reconstructed* from spread quotes, not published outrights --
    the source must say so rather than posing as an exchange settlement feed."""
    curve = reconstruct_curve(_spreads(), as_of_year=2026)
    rows = curve_to_ts_long(curve, as_of=pd.Timestamp("2026-09-04"), root="lco")
    assert rows["source"].unique().tolist() == ["manual"]


# --- the real file ----------------------------------------------------------------


def test_load_spreads_drops_barcharts_footer_row(tmp_path) -> None:
    """The export ends with a 'Downloaded from Barchart.com...' line in the Leg1 column,
    which is not a quote."""
    path = tmp_path / "spreads.csv"
    path.write_text(
        "Leg1,Leg2,Leg3,Leg4,Type,Latest,Change,Open,High,Low,Previous,Volume,Time\n"
        "QAX6,QAZ6,,,SA,94.30,0.72,0,94.3,94.3,93.58,N/A,16:40 CT\n"
        "QAX6,QAZ6,,,SP,3.96,0.07,3.99,4.09,3.31,3.89,6514,2026-09-04\n"
        "Downloaded from Barchart.com as of 09-05-2026 04:06am CDT,,,,,,,,,,,,\n",
        encoding="utf-8",
    )
    spreads = load_spreads(path)
    assert len(spreads) == 2
    assert spreads["Leg1"].str.startswith("QA").all()
