"""Hormuz supply overlay (core/hormuz.py).

The acceptance cases are the source workbook's own published numbers: with 2Q 2026's
flow share of 0.15, ~/Desktop/skill-pdfs/oil_demand.xlsx rows 9-13 read
7.705 / 2.325 / 3.136 / 1.94425 / 1.043 for Saudi Arabia, the UAE, Iran, Iraq and
Kuwait. A port that does not reproduce those to the digit has changed the model.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest
from core.hormuz import ProducerDisruption, scenario_path, scenario_supply, total_supply

SAUDI = ProducerDisruption(
    "Saudi Arabia", undisrupted_mbd=10.0, disrupted_mbd=7.3, recovery_ceiling=1.0
)
IRAQ = ProducerDisruption("Iraq", undisrupted_mbd=4.3, disrupted_mbd=1.6, recovery_ceiling=0.85)
UAE = ProducerDisruption("UAE", undisrupted_mbd=3.6, disrupted_mbd=2.1, recovery_ceiling=1.0)
KUWAIT = ProducerDisruption("Kuwait", undisrupted_mbd=2.6, disrupted_mbd=0.8, recovery_ceiling=0.9)
IRAN = ProducerDisruption("Iran", undisrupted_mbd=3.4, disrupted_mbd=3.1, recovery_ceiling=0.8)

GULF = [SAUDI, IRAQ, UAE, KUWAIT, IRAN]


def test_total_closure_leaves_only_the_disrupted_floor() -> None:
    assert scenario_supply(SAUDI, 0.0) == pytest.approx(7.3)


def test_full_reopening_with_a_complete_ceiling_restores_the_undisrupted_rate() -> None:
    assert scenario_supply(SAUDI, 1.0) == pytest.approx(10.0)


def test_a_ceiling_below_one_never_restores_the_whole_loss() -> None:
    """Iran's 0.8 is a cap on recovery, not a speed: even at fully reopened flows it
    regains 80% of the barrels it lost, and that is the model's intent."""
    recovered = scenario_supply(IRAN, 1.0)
    assert recovered == pytest.approx(3.1 + 0.8 * (3.4 - 3.1))
    assert recovered < IRAN.undisrupted_mbd


def test_reproduces_every_published_workbook_figure_for_2q_2026() -> None:
    expected = {
        "Saudi Arabia": 7.705,
        "UAE": 2.325,
        "Iran": 3.136,
        "Iraq": 1.94425,
        "Kuwait": 1.043,
    }
    for producer in GULF:
        assert scenario_supply(producer, 0.15) == pytest.approx(
            expected[producer.producer]
        ), producer.producer


def test_an_unknown_flow_share_is_not_treated_as_a_closure() -> None:
    """The workbook writes 1Q 2026 as "-", meaning not applicable. Read as 0.0 it would
    assert a total closure -- the inversion of its meaning. Absent stays absent."""
    assert math.isnan(scenario_supply(SAUDI, None))


def test_a_flow_share_outside_zero_to_one_is_refused() -> None:
    with pytest.raises(ValueError, match="flow share"):
        scenario_supply(SAUDI, 1.4)


def test_a_recovery_ceiling_outside_zero_to_one_is_refused() -> None:
    with pytest.raises(ValueError, match="recovery_ceiling"):
        ProducerDisruption(
            "Nowhere", undisrupted_mbd=5.0, disrupted_mbd=1.0, recovery_ceiling=1.2
        )


def test_a_disrupted_rate_above_the_undisrupted_rate_is_refused() -> None:
    """A floor above the ceiling is not a disruption, and interpolating between them
    would silently return a supply that rises as the strait closes."""
    with pytest.raises(ValueError, match="disrupted_mbd"):
        ProducerDisruption("Nowhere", undisrupted_mbd=1.0, disrupted_mbd=5.0, recovery_ceiling=1.0)


def test_scenario_path_returns_one_row_per_producer_per_quarter() -> None:
    quarters = {
        pd.Timestamp("2026-04-01"): 0.15,
        pd.Timestamp("2026-07-01"): 0.60,
    }
    path = scenario_path(GULF, quarters)
    assert list(path.columns) == ["ts", "producer", "supply_mbd", "open_share"]
    assert len(path) == len(GULF) * len(quarters)
    saudi_q2 = path[
        (path["producer"] == "Saudi Arabia") & (path["ts"] == pd.Timestamp("2026-04-01"))
    ]
    assert saudi_q2["supply_mbd"].iloc[0] == pytest.approx(7.705)


def test_scenario_path_keeps_an_unknown_quarter_as_missing_not_zero() -> None:
    path = scenario_path(GULF, {pd.Timestamp("2026-01-01"): None})
    assert path["supply_mbd"].isna().all()


def test_total_supply_sums_the_producers_for_each_quarter() -> None:
    quarters = {pd.Timestamp("2026-04-01"): 0.15}
    totals = total_supply(scenario_path(GULF, quarters))
    assert totals.loc[pd.Timestamp("2026-04-01")] == pytest.approx(
        7.705 + 1.94425 + 2.325 + 1.043 + 3.136
    )


def test_total_supply_refuses_to_sum_across_a_missing_producer() -> None:
    """A quarter where one producer is unknown has no known total. Summing the rest
    would publish a number that looks like a global figure and is not one."""
    quarters = {pd.Timestamp("2026-01-01"): None}
    totals = total_supply(scenario_path(GULF, quarters))
    assert math.isnan(totals.loc[pd.Timestamp("2026-01-01")])
