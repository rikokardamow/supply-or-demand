"""Hormuz supply overlay (core/hormuz.py).

**Every figure in this file is synthetic.** The real producers and their undisrupted,
disrupted and recovery-ceiling values are licensed content from the source workbook and
live only in the git-ignored drop at `data/manual/hormuz/baselines.csv`; reproducing them
in a tracked file would defeat the reason that file is ignored.

Nothing is lost by the substitution. The workbook's own published scenario figures are
algebraically determined by its inputs and the formula, so asserting them could never
distinguish a correct port from a recomputation — it only ever tested the arithmetic, which
these round numbers test more legibly. The real validation of the port lives elsewhere: the
cell-by-cell comparison against the workbook's own `Scenario` columns recorded in
`pipelines/derived/hormuz/README.md`, and the corroboration against OPEC's public
`momr.doc_crude_secondary.*` production series in the lake.

The arithmetic here is hand-checkable: at a flow share of 0.5, Northport recovers
6.0 + (10.0 - 6.0) x 0.5 x 1.0 = 8.0.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest
from core.hormuz import ProducerDisruption, scenario_path, scenario_supply, total_supply

NORTHPORT = ProducerDisruption(
    "Northport", undisrupted_mbd=10.0, disrupted_mbd=6.0, recovery_ceiling=1.0
)
EASTBAY = ProducerDisruption(
    "Eastbay", undisrupted_mbd=8.0, disrupted_mbd=2.0, recovery_ceiling=0.5
)
SOUTHCAPE = ProducerDisruption(
    "Southcape", undisrupted_mbd=5.0, disrupted_mbd=4.0, recovery_ceiling=0.8
)
WESTREACH = ProducerDisruption(
    "Westreach", undisrupted_mbd=4.0, disrupted_mbd=1.0, recovery_ceiling=0.9
)
MIDSHOAL = ProducerDisruption(
    "Midshoal", undisrupted_mbd=2.0, disrupted_mbd=0.5, recovery_ceiling=1.0
)

GULF = [NORTHPORT, EASTBAY, SOUTHCAPE, WESTREACH, MIDSHOAL]


def test_total_closure_leaves_only_the_disrupted_floor() -> None:
    assert scenario_supply(NORTHPORT, 0.0) == pytest.approx(6.0)


def test_full_reopening_with_a_complete_ceiling_restores_the_undisrupted_rate() -> None:
    assert scenario_supply(NORTHPORT, 1.0) == pytest.approx(10.0)


def test_a_ceiling_below_one_never_restores_the_whole_loss() -> None:
    """A ceiling is a cap on recovery, not a speed: even at fully reopened flows Eastbay
    regains only half the barrels it lost, and that is the model's intent."""
    recovered = scenario_supply(EASTBAY, 1.0)
    assert recovered == pytest.approx(2.0 + 0.5 * (8.0 - 2.0))
    assert recovered < EASTBAY.undisrupted_mbd


def test_every_producer_interpolates_between_its_two_bounds() -> None:
    """At a half-open strait each producer recovers half of its loss, scaled by its own
    ceiling. Hand-computed, so a change to the formula is visible here first."""
    expected = {
        "Northport": 8.0,  # 6.0 + 4.0 * 0.5 * 1.0
        "Eastbay": 3.5,  # 2.0 + 6.0 * 0.5 * 0.5
        "Southcape": 4.4,  # 4.0 + 1.0 * 0.5 * 0.8
        "Westreach": 2.35,  # 1.0 + 3.0 * 0.5 * 0.9
        "Midshoal": 1.25,  # 0.5 + 1.5 * 0.5 * 1.0
    }
    for producer in GULF:
        assert scenario_supply(producer, 0.5) == pytest.approx(
            expected[producer.producer]
        ), producer.producer


def test_an_unknown_flow_share_is_not_treated_as_a_closure() -> None:
    """The source writes a pre-disruption quarter as "-", meaning not applicable. Read as
    0.0 it would assert a total closure -- the inversion of its meaning. Absent stays
    absent."""
    assert math.isnan(scenario_supply(NORTHPORT, None))


def test_a_flow_share_outside_zero_to_one_is_refused() -> None:
    with pytest.raises(ValueError, match="flow share"):
        scenario_supply(NORTHPORT, 1.4)


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
        pd.Timestamp("2026-04-01"): 0.5,
        pd.Timestamp("2026-07-01"): 0.75,
    }
    path = scenario_path(GULF, quarters)
    assert list(path.columns) == ["ts", "producer", "supply_mbd", "open_share"]
    assert len(path) == len(GULF) * len(quarters)
    northport_q2 = path[
        (path["producer"] == "Northport") & (path["ts"] == pd.Timestamp("2026-04-01"))
    ]
    assert northport_q2["supply_mbd"].iloc[0] == pytest.approx(8.0)


def test_scenario_path_keeps_an_unknown_quarter_as_missing_not_zero() -> None:
    path = scenario_path(GULF, {pd.Timestamp("2026-01-01"): None})
    assert path["supply_mbd"].isna().all()


def test_total_supply_sums_the_producers_for_each_quarter() -> None:
    quarters = {pd.Timestamp("2026-04-01"): 0.5}
    totals = total_supply(scenario_path(GULF, quarters))
    assert totals.loc[pd.Timestamp("2026-04-01")] == pytest.approx(
        8.0 + 3.5 + 4.4 + 2.35 + 1.25
    )


def test_total_supply_refuses_to_sum_across_a_missing_producer() -> None:
    """A quarter where one producer is unknown has no known total. Summing the rest
    would publish a number that looks like a regional figure and is not one."""
    quarters = {pd.Timestamp("2026-01-01"): None}
    totals = total_supply(scenario_path(GULF, quarters))
    assert math.isnan(totals.loc[pd.Timestamp("2026-01-01")])
