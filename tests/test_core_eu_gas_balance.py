"""core/eu_gas_balance.py -- every rule the model rests on. All figures synthetic."""

from __future__ import annotations

import math

import pandas as pd
import pytest
from core import eu_gas_balance as egb

JAN, FEB, MAR = pd.Timestamp("2025-01-01"), pd.Timestamp("2025-02-01"), pd.Timestamp("2025-03-01")


def _trade(rows: list[tuple[str, str, str, pd.Timestamp, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["flow", "product", "partner", "ts", "value"])


def _with_totals(rows):
    """Add imports/exports 'total' rows equal to the partner sums, so the month is complete."""
    frame = _trade(rows)
    totals = (
        frame.groupby(["flow", "product", "ts"], as_index=False)["value"].sum()
        .assign(partner="total")
    )  # fmt: skip
    return pd.concat([frame, totals[frame.columns]], ignore_index=True)


def _mapping(rules: list[tuple[str, str, str, str | None, str | None]]) -> pd.DataFrame:
    frame = pd.DataFrame(rules, columns=["partner", "product", "route", "valid_from", "valid_to"])
    for col in ("valid_from", "valid_to"):
        frame[col] = pd.to_datetime(frame[col])
    return frame


# --- net_by_partner ------------------------------------------------------------------


def test_transit_gas_nets_out_rather_than_double_counting() -> None:
    """TAP: Greece exports to Albania and Italy imports the same gas from Albania."""
    trade = _with_totals(
        [
            ("imports", "gas", "tr", JAN, 10.0),
            ("imports", "gas", "al", JAN, 8.0),
            ("exports", "gas", "al", JAN, 8.0),
        ]
    )

    net = egb.net_by_partner(trade).set_index(["partner", "product"])["value"]

    assert net[("al", "pipeline")] == 0.0
    assert net[("tr", "pipeline")] == 10.0


def test_lng_is_inside_natural_gas_so_pipeline_is_the_difference() -> None:
    trade = _with_totals([("imports", "gas", "us", JAN, 5.0), ("imports", "lng", "us", JAN, 5.0)])

    net = egb.net_by_partner(trade).set_index(["partner", "product"])["value"]

    assert net[("us", "lng")] == 5.0
    assert net[("us", "pipeline")] == 0.0


def test_a_month_whose_partners_do_not_add_up_to_its_total_is_left_out() -> None:
    complete = _with_totals([("imports", "gas", "no", JAN, 7.0)])
    partial = _trade([("imports", "gas", "total", FEB, 30.0), ("imports", "gas", "no", FEB, 8.0)])

    net = egb.net_by_partner(pd.concat([complete, partial]))

    assert set(net["ts"]) == {JAN}


def test_a_month_with_no_imports_total_yields_no_rows() -> None:
    trade = _trade([("imports", "gas", "no", JAN, 7.0)])

    assert egb.net_by_partner(trade).empty


# --- assign_routes ---------------------------------------------------------------------


def test_intra_eu_partners_are_dropped_and_dated_rules_switch_route() -> None:
    net = pd.DataFrame(
        {
            "ts": [JAN, MAR, JAN],
            "partner": ["ua", "ua", "de"],
            "product": ["pipeline"] * 3,
            "value": [5.0, -1.0, 9.0],
        }
    )
    mapping = _mapping(
        [
            ("ua", "pipeline", "russia_pipeline", None, "2025-02-01"),
            ("ua", "pipeline", "neighbour_exports", "2025-02-01", None),
        ]
    )
    # The two rules share 2025-02-01; neither month in the data is that one.
    routed = egb.assign_routes(net, mapping).set_index("ts")["route"]

    assert routed[JAN] == "russia_pipeline"
    assert routed[MAR] == "neighbour_exports"
    assert "de" not in set(egb.assign_routes(net, mapping)["partner"])


def test_a_specific_partner_rule_beats_the_wildcard() -> None:
    net = pd.DataFrame(
        {"ts": [JAN, JAN], "partner": ["us", "pe"], "product": ["lng", "lng"], "value": [1.0, 2.0]}
    )
    mapping = _mapping([("*", "lng", "lng_other", None, None), ("us", "lng", "lng_us", None, None)])

    routed = egb.assign_routes(net, mapping).set_index("partner")["route"]

    assert routed["us"] == "lng_us" and routed["pe"] == "lng_other"


def test_an_unmapped_partner_raises_rather_than_dropping_gas() -> None:
    net = pd.DataFrame({"ts": [JAN], "partner": ["qa"], "product": ["lng"], "value": [1.0]})

    with pytest.raises(ValueError, match="no route"):
        egb.assign_routes(net, _mapping([("us", "lng", "lng_us", None, None)]))


def test_overlapping_rules_and_unknown_routes_raise() -> None:
    net = pd.DataFrame({"ts": [JAN], "partner": ["ua"], "product": ["pipeline"], "value": [1.0]})
    overlapping = _mapping(
        [
            ("ua", "pipeline", "russia_pipeline", None, None),
            ("ua", "pipeline", "neighbour_exports", None, None),
        ]
    )

    with pytest.raises(ValueError, match="overlapping"):
        egb.assign_routes(net, overlapping)
    with pytest.raises(ValueError, match="unknown route"):
        egb.assign_routes(net, _mapping([("ua", "pipeline", "nowhere", None, None)]))


def test_route_totals_carry_every_route_with_zero_for_no_trade() -> None:
    routed = pd.DataFrame(
        {"ts": [JAN], "partner": ["no"], "product": ["pipeline"], "value": [7.0],
         "route": ["norway_pipeline"]}
    )  # fmt: skip

    table = egb.route_totals(routed)

    assert list(table.columns) == list(egb.ROUTES)
    assert table.loc[JAN, "lng_qatar"] == 0.0


# --- balance, members, reconciliation -------------------------------------------------


def _balance(line: str, values: dict[pd.Timestamp, float]) -> pd.DataFrame:
    return pd.DataFrame({"line": line, "ts": list(values), "value": list(values.values())})


def test_other_uses_is_consumption_minus_the_three_published_uses() -> None:
    frame = pd.concat(
        [
            _balance("ic_obs", {JAN: 100.0, FEB: 90.0}),
            _balance("ti_ehg_map", {JAN: 30.0, FEB: 25.0}),
            _balance("fc_ind", {JAN: 20.0}),
            _balance("fc_oth", {JAN: 40.0, FEB: 35.0}),
        ]
    )

    table = egb.balance_table(frame)

    assert table.loc[JAN, "other_uses"] == 10.0
    assert math.isnan(table.loc[FEB, "other_uses"])  # a missing part is not zero
    assert math.isnan(table.loc[FEB, "industry"])


def test_blank_eu_cells_are_rebuilt_only_when_members_cover_the_line() -> None:
    eu = pd.DataFrame({"iprd": [float("nan"), float("nan")]}, index=[JAN, FEB])
    members = pd.DataFrame(
        {
            "line": "iprd",
            "geo": ["nl", "ro", "fi", "nl", "fi"],
            "ts": [JAN, JAN, JAN, FEB, FEB],
            "value": [60.0, 40.0, 0.0, 60.0, 0.0],
        }
    )

    filled, mask = egb.fill_from_members(eu, members)

    assert filled.loc[JAN, "iprd"] == 100.0 and mask.loc[JAN, "iprd"]
    # February lacks Romania, ~40% of the line: left blank.
    assert math.isnan(filled.loc[FEB, "iprd"]) and not mask.loc[FEB, "iprd"]


def test_a_published_eu_cell_is_never_overwritten_by_members() -> None:
    eu = pd.DataFrame({"iprd": [55.0]}, index=[JAN])
    members = pd.DataFrame({"line": "iprd", "geo": ["nl"], "ts": [JAN], "value": [99.0]})

    filled, mask = egb.fill_from_members(eu, members)

    assert filled.loc[JAN, "iprd"] == 55.0 and not mask.loc[JAN, "iprd"]


def test_reconcile_measures_both_residuals() -> None:
    routes = pd.DataFrame({"norway_pipeline": [30.0]}, index=[JAN])
    balance = pd.DataFrame(
        {"imports": [50.0], "exports": [19.0], "production": [5.0], "consumption": [40.0],
         "stock_build": [-6.0]},
        index=[JAN],
    )  # fmt: skip

    checks = egb.reconcile(routes, balance).loc[JAN]

    assert checks["intra_eu_asymmetry"] == 1.0  # 31 - 30
    assert checks["implied_stock_build"] == -5.0  # 5 + 30 - 40
    assert checks["unexplained"] == 1.0


def test_storage_check_takes_month_ends_even_from_unsorted_input() -> None:
    days = pd.date_range("2024-12-30", "2025-02-28", freq="D")
    level = pd.Series(range(len(days)), index=days, dtype="float64")[::-1]  # unsorted
    stock_tj = pd.Series([31 * 3600.0, 28 * 3600.0], index=[JAN, FEB])

    out = egb.storage_check(stock_tj, level)

    assert out.loc[JAN, "gie_twh"] == 31.0
    assert out.loc[FEB, "gap_twh"] == 0.0


def test_a_year_missing_a_month_has_no_annual_total() -> None:
    months = pd.date_range("2024-01-01", "2025-12-01", freq="MS")
    table = pd.DataFrame({"a": 1.0, "b": 1.0}, index=months)
    table.loc["2025-03-01", "b"] = float("nan")

    years = egb.calendar_year(table)

    assert years.loc[2025, "a"] == 12.0
    assert math.isnan(years.loc[2025, "b"])


# --- projection ------------------------------------------------------------------------


def test_projection_keeps_the_seasonal_shape_and_chains_years() -> None:
    months = pd.date_range("2025-01-01", "2025-12-01", freq="MS")
    history = pd.DataFrame({"consumption": [float(m.month) for m in months]}, index=months)
    assumptions = pd.DataFrame(
        {"line": ["consumption", "consumption"], "year": [2026, 2027], "yoy_pct": [10.0, 0.0]}
    )

    out = egb.project(history, assumptions, pd.Timestamp("2027-02-01"))

    assert out.loc["2026-02-01", "consumption"] == pytest.approx(2.2)
    assert out.loc["2027-02-01", "consumption"] == pytest.approx(2.2)


def test_a_line_with_no_assumption_is_not_projected_as_flat() -> None:
    history = pd.DataFrame({"production": [1.0]}, index=[pd.Timestamp("2025-12-01")])
    assumptions = pd.DataFrame({"line": [], "year": [], "yoy_pct": []})

    out = egb.project(history, assumptions, pd.Timestamp("2026-12-01"))

    assert out["production"].isna().all()


def test_storage_path_stops_at_the_first_gap() -> None:
    months = pd.date_range("2026-01-01", periods=3, freq="MS")
    build = pd.Series([10.0, float("nan"), 5.0], index=months)

    path = egb.storage_path(100.0, build)

    assert list(path) == [110.0]
