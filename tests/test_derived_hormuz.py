"""The Hormuz scenario writer (pipelines/derived/hormuz.py).

Assumptions are split deliberately. The scenario levers -- the flow-share path and each
producer's recovery ceiling -- are committed, because they are the user's own choices and
should be reviewable in a diff. The undisrupted/disrupted baselines come from a
git-ignored drop under data/manual/hormuz/, because they derive from a licensed workbook.

Every figure in this file is SYNTHETIC. Real producers and real rates are deliberately
absent: the licensed source may not be reproduced in a tracked file. The arithmetic is
hand-checkable instead, which is the property these tests actually need.
"""

from __future__ import annotations

import pandas as pd
import pytest
from pipelines.derived.hormuz import (
    build_scenario_rows,
    read_baselines,
    read_levers,
)

_LEVERS = """producer,recovery_ceiling
Northport,1.0
Eastbay,0.5
Southcape,0.8
Westreach,0.9
Midshoal,1.0
"""

_FLOW = """quarter,open_share
2026-01-01,
2026-04-01,0.5
"""

_BASELINES = """producer,quarter,undisrupted_mbd,disrupted_mbd
Northport,2026-04-01,10.0,6.0
Eastbay,2026-04-01,8.0,2.0
Southcape,2026-04-01,5.0,4.0
Westreach,2026-04-01,4.0,1.0
Midshoal,2026-04-01,2.0,0.5
"""


@pytest.fixture
def assumptions(tmp_path):
    """Two directories, because that is the real layout: committed levers beside the
    module, baselines in the git-ignored drop. A fixture that put all three in
    one place would let a single-directory bug pass -- it did, once."""
    levers = tmp_path / "levers"
    drop = tmp_path / "drop"
    levers.mkdir()
    drop.mkdir()
    (levers / "recovery_ceilings.csv").write_text(_LEVERS, encoding="utf-8")
    (levers / "flow_share.csv").write_text(_FLOW, encoding="utf-8")
    (drop / "baselines.csv").write_text(_BASELINES, encoding="utf-8")
    return levers, drop


def test_read_levers_returns_a_ceiling_per_producer(assumptions) -> None:
    levers, _ = assumptions
    ceilings, flow = read_levers(levers)
    assert ceilings["Eastbay"] == pytest.approx(0.5)
    assert flow[pd.Timestamp("2026-04-01")] == pytest.approx(0.5)


def test_an_empty_flow_share_reads_as_unknown_not_zero(assumptions) -> None:
    """The workbook's first quarter is "-". Zero would assert a total closure."""
    levers, _ = assumptions
    _, flow = read_levers(levers)
    assert flow[pd.Timestamp("2026-01-01")] is None


def test_read_baselines_returns_one_row_per_producer_quarter(assumptions) -> None:
    _, drop = assumptions
    baselines = read_baselines(drop)
    assert len(baselines) == 5
    assert set(baselines.columns) == {"producer", "quarter", "undisrupted_mbd", "disrupted_mbd"}


def test_baselines_are_not_read_from_the_committed_levers_directory(assumptions) -> None:
    """The licensed baselines must never be expected beside the committed files, or the
    whole reason for the split is lost."""
    levers, _ = assumptions
    with pytest.raises(FileNotFoundError, match=r"baselines\.csv"):
        read_baselines(levers)


def test_a_missing_baselines_drop_is_a_clear_skip(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match=r"baselines\.csv"):
        read_baselines(tmp_path)


def test_scenario_rows_reproduce_the_published_workbook_figure(assumptions) -> None:
    levers, drop = assumptions
    rows = build_scenario_rows(levers, drop, ingested_at=pd.Timestamp("2026-10-10"))
    northport = rows[
        (rows["series_id"] == "derived.hormuz.scenario.northport.supply")
        & (rows["ts"] == pd.Timestamp("2026-04-01"))
    ]
    # 6.0 + (10.0 - 6.0) * 0.5 * 1.0
    assert northport["value"].iloc[0] == pytest.approx(8.0)


def test_scenario_rows_carry_the_lake_conventions(assumptions) -> None:
    levers, drop = assumptions
    rows = build_scenario_rows(levers, drop, ingested_at=pd.Timestamp("2026-10-10"))
    assert set(rows["source"]) == {"derived"}
    assert set(rows["freq"]) == {"Q"}
    assert set(rows["unit"]) == {"mb/d", "ratio"}
    assert rows["value"].dtype == "float64"


def test_every_series_carries_the_unit_its_own_values_are_in(assumptions) -> None:
    """A unit a reader cannot trust is worse than no unit. `open_share` was written as
    "%" while holding 0.15 ... 1.0, so any exhibit honouring the unit rendered a 90%
    reopening as "0.9%". The share is stored as the fraction the scenario formula
    actually multiplies by, so the unit must say `ratio`, and nothing here may claim "%"
    unless its values really run 0-100."""
    levers, drop = assumptions
    rows = build_scenario_rows(levers, drop, ingested_at=pd.Timestamp("2026-10-10"))

    units = rows.groupby("series_id")["unit"].agg(lambda values: set(values))
    assert units["derived.hormuz.scenario.open_share"] == {"ratio"}
    assert all(
        unit == {"mb/d"}
        for series_id, unit in units.items()
        if series_id != "derived.hormuz.scenario.open_share"
    )

    ratios = rows[rows["unit"] == "ratio"]
    assert not ratios.empty
    assert ratios["value"].between(0.0, 1.0).all()
    # The inverted form of the same mistake: a percentage-labelled fraction.
    percentages = rows[rows["unit"] == "%"]
    assert percentages.empty or percentages["value"].abs().max() > 1.0


def test_every_series_id_says_scenario_so_no_reader_mistakes_it_for_an_observation(
    assumptions,
) -> None:
    levers, drop = assumptions
    rows = build_scenario_rows(levers, drop, ingested_at=pd.Timestamp("2026-10-10"))
    assert all(sid.startswith("derived.hormuz.scenario.") for sid in rows["series_id"])


def test_a_quarter_with_no_known_flow_share_writes_no_rows(assumptions) -> None:
    """1Q 2026 is unknown, so it has no scenario supply. Absent, never zero."""
    levers, drop = assumptions
    rows = build_scenario_rows(levers, drop, ingested_at=pd.Timestamp("2026-10-10"))
    assert pd.Timestamp("2026-01-01") not in set(rows["ts"])


def test_the_gulf_total_is_written_and_sums_the_producers(assumptions) -> None:
    levers, drop = assumptions
    rows = build_scenario_rows(levers, drop, ingested_at=pd.Timestamp("2026-10-10"))
    total = rows[rows["series_id"] == "derived.hormuz.scenario.gulf_total.supply"]
    assert total["value"].iloc[0] == pytest.approx(8.0 + 3.5 + 4.4 + 2.35 + 1.25)
