"""core/uk_gas_balance.py. All figures synthetic."""

from __future__ import annotations

import math

import pandas as pd
import pytest
from core import uk_gas_balance as uk

JUL = pd.Timestamp("2026-07-01")
MAPPING = pd.DataFrame(
    {
        "type": ["pipeline", "pipeline", "pipeline", "pipeline", "lng", "lng", "lng"],
        "country": ["norway", "belgium", "republic_of_ireland", "isle_of_man", "usa", "qatar", "*"],
        "route": ["norway_pipeline", "continent_pipeline", "ireland_exports",
                  "isle_of_man_exports", "lng_us", "lng_qatar", "lng_other"],
    }
)  # fmt: skip


def _trade(rows: list[tuple[str, str, str, str, float]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["flow", "type", "country", "pipeline", "value"])
    return frame.assign(ts=JUL)


TRADE = _trade(
    [
        ("imports", "pipeline", "norway", "langeled", 2000.0),
        ("imports", "pipeline", "norway", "total_norwegian_pipeline", 2000.0),
        ("imports", "pipeline", "belgium", "iuk", 100.0),
        ("exports", "pipeline", "belgium", "iuk", 400.0),
        ("exports", "pipeline", "republic_of_ireland", "moffat", 300.0),
        ("imports", "lng", "usa", "na", 500.0),
        ("imports", "lng", "peru", "na", 50.0),
        ("exports", "lng", "reload", "na", 20.0),
        ("imports", "lng", "total_lng", "na", 550.0),
        ("net", "net_imports", "net_imports", "na", 1930.0),
    ]
)


def test_routes_are_net_with_exports_negative_and_totals_left_out() -> None:
    routes = uk.route_table(TRADE, MAPPING).loc[JUL]

    assert routes["norway_pipeline"] == 2000.0  # the Norwegian total row is not added again
    assert routes["continent_pipeline"] == -300.0
    assert routes["ireland_exports"] == -300.0
    assert routes["lng_other"] == 30.0  # Peru less the reload export
    assert routes["lng_qatar"] == 0.0


def test_route_gap_is_zero_when_routes_add_up_to_published_net_imports() -> None:
    routes = uk.route_table(TRADE, MAPPING)

    assert uk.route_gaps(TRADE, routes).loc[JUL] == 0.0


def test_an_unmapped_pipeline_country_raises() -> None:
    trade = _trade([("imports", "pipeline", "denmark", "baltic", 1.0)])

    with pytest.raises(ValueError, match="no route"):
        uk.route_table(trade, MAPPING)


def _balance(values: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame({"line": list(values), "ts": JUL, "value": list(values.values())})


BALANCE = _balance(
    {
        "production": 2300.0, "net_imports": 1930.0, "stock_change": -100.0, "biomethane": 40.0,
        "synthetic": -3.5, "net_supply": 4170.0, "demand": 4120.0, "power": 1500.0,
        "domestic": 800.0, "industrial": 400.0, "services": 500.0, "producer_own_use": 200.0,
        "operator_own_use": 5.0, "lng_own_use": 3.0, "storage_own_use": 0.0, "other": 712.0,
    }
)  # fmt: skip


def test_net_supply_identity_excludes_synthetic_gas() -> None:
    table = uk.balance_table(BALANCE).loc[JUL]

    assert table["supply_gap"] == 0.0  # 2300 + 1930 - 100 + 40 = 4170
    assert table["losses_statdiff"] == 50.0
    assert table["demand_own_use"] == 208.0


def test_a_demand_group_with_a_missing_part_is_blank() -> None:
    partial = BALANCE[BALANCE["line"] != "lng_own_use"]

    assert math.isnan(uk.balance_table(partial).loc[JUL, "demand_own_use"])


def test_lng_call_on_history_equals_net_lng_imports() -> None:
    routes = uk.route_table(TRADE, MAPPING)
    lines = pd.concat([uk.balance_table(BALANCE), routes], axis=1)

    call = uk.lng_call(lines).loc[JUL]

    assert call == pytest.approx(routes.loc[JUL, list(uk.LNG_ROUTES)].sum())


def test_the_eu_mirror_counts_ireland_but_not_the_isle_of_man() -> None:
    routes = pd.DataFrame(
        {
            "continent_pipeline": [-300.0],
            "ireland_exports": [-250.0],
            "isle_of_man_exports": [-9.0],
        },
        index=[JUL],
    )

    assert uk.eu_mirror(routes).loc[JUL] == 550.0
