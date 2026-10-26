"""core/lng_balance.py. All figures synthetic."""

from __future__ import annotations

import pandas as pd
import pytest
from core import lng_balance as lb

JUL = pd.Timestamp("2026-07-01")
MAPPING = pd.DataFrame(
    {"destination": ["japan", "germany", "united_kingdom"], "region": ["asia", "europe", "europe"],
     "bloc": ["other", "eu", "uk"]}
)  # fmt: skip


def _exports(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["kind", "destination", "value"])
    return frame.assign(ts=JUL)


def test_regions_sum_to_the_total_with_gaps_named_not_dropped() -> None:
    exports = _exports(
        [
            ("exports", "total", 1000.0),
            ("exports", "japan", 300.0),
            ("exports", "germany", 400.0),
            ("exports", "atlantis", 100.0),  # a destination nobody mapped
            ("truck", "mexico", 50.0),  # mapped nowhere: unmapped too
            ("reexports", "japan", 999.0),  # not part of the total
        ]
    )

    table = lb.us_exports_by(exports, MAPPING, "region").loc[JUL] / lb.MCM_PER_MMCF

    assert table["asia"] == pytest.approx(300.0)
    assert table["unmapped"] == pytest.approx(150.0)
    assert table["unallocated"] == pytest.approx(150.0)
    assert table.sum() == pytest.approx(1000.0)


def test_europe_counts_only_lng_from_outside_europe() -> None:
    eu = pd.DataFrame(
        {"partner": ["us", "qa", "es", "uk", "total", "pe"], "ts": JUL,
         "value": [50.0, 20.0, 9.0, 4.0, 83.0, 3.0]}
    )  # fmt: skip
    uk = pd.DataFrame(
        {"country": ["usa", "france", "total_lng", "peru"], "ts": JUL,
         "value": [10.0, 2.0, 13.0, 1.0]}
    )  # fmt: skip

    europe = lb.europe_lng_imports(eu, uk).loc[JUL]

    assert europe["united_states"] == 60.0
    assert europe["qatar"] == 20.0
    assert europe["other"] == 4.0  # Peru on both sides; Spain, the UK, France are not new supply
    assert europe.sum() == 84.0


def test_a_month_only_one_side_publishes_is_left_out() -> None:
    eu = pd.DataFrame({"partner": ["us"], "ts": [JUL], "value": [1.0]})
    uk = pd.DataFrame({"country": ["usa"], "ts": [pd.Timestamp("2026-08-01")], "value": [1.0]})

    assert lb.europe_lng_imports(eu, uk).empty


def test_mirror_gap_is_europe_minus_us() -> None:
    out = lb.mirror(pd.Series({JUL: 10.0}), pd.Series({JUL: 7.0}))

    assert out.loc[JUL, "gap"] == -3.0


def _jodi(rows: list[tuple[str, str, str, float]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["flow", "country", "ts", "value"])
    return frame.assign(ts=pd.to_datetime(frame["ts"]))


def test_taiwans_placeholder_zero_is_unreported_but_a_real_zero_elsewhere_counts() -> None:
    rows = _jodi([("implng", "tw", "2026-01-01", 0.0), ("implng", "jp", "2026-01-01", 0.0)])

    table = lb.by_country(rows, "implng")

    assert "tw" not in table.columns
    assert table.loc[pd.Timestamp("2026-01-01"), "jp"] == 0.0


def test_coverage_weights_countries_by_their_past_volume() -> None:
    months = [f"2025-{m:02d}-01" for m in range(1, 13)]
    rows = [("implng", "cn", m, 90.0) for m in months] + [("implng", "mt", m, 10.0) for m in months]
    rows.append(("implng", "mt", "2026-01-01", 10.0))  # China has not filed January yet
    share = lb.coverage(lb.by_country(_jodi(rows), "implng"))

    assert share[pd.Timestamp("2025-12-01")] == pytest.approx(1.0)
    assert share[pd.Timestamp("2026-01-01")] == pytest.approx(0.1)


def test_grouped_puts_every_other_country_in_rest() -> None:
    table = pd.DataFrame({"cn": [5.0], "gr": [2.0], "zz": [1.0]}, index=[JUL])

    out = lb.grouped(table, lb.IMPORTER_GROUPS).loc[JUL]

    assert out["china"] == 5.0 and out["europe"] == 2.0  # Greece is "gr" in JODI
    assert out["rest"] == 1.0
