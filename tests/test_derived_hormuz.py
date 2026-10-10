"""The Hormuz scenario writer (pipelines/derived/hormuz.py).

Assumptions are split deliberately. The scenario levers -- the flow-share path and each
producer's recovery ceiling -- are committed, because they are the user's own choices and
should be reviewable in a diff. The undisrupted/disrupted baselines come from a
git-ignored drop under data/manual/hormuz/, because they derive from a licensed Bloomberg
Intelligence workbook.
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
Saudi Arabia,1.0
Iraq,0.85
UAE,1.0
Kuwait,0.9
Iran,0.8
"""

_FLOW = """quarter,open_share
2026-01-01,
2026-04-01,0.15
"""

_BASELINES = """producer,quarter,undisrupted_mbd,disrupted_mbd
Saudi Arabia,2026-04-01,10.0,7.3
Iraq,2026-04-01,4.3,1.6
UAE,2026-04-01,3.6,2.1
Kuwait,2026-04-01,2.6,0.8
Iran,2026-04-01,3.4,3.1
"""


@pytest.fixture
def assumptions(tmp_path):
    """Two directories, because that is the real layout: committed levers beside the
    module, licensed baselines in the git-ignored drop. A fixture that put all three in
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
    assert ceilings["Iran"] == pytest.approx(0.8)
    assert flow[pd.Timestamp("2026-04-01")] == pytest.approx(0.15)


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
    saudi = rows[
        (rows["series_id"] == "derived.hormuz.scenario.saudi_arabia.supply")
        & (rows["ts"] == pd.Timestamp("2026-04-01"))
    ]
    assert saudi["value"].iloc[0] == pytest.approx(7.705)


def test_scenario_rows_carry_the_lake_conventions(assumptions) -> None:
    levers, drop = assumptions
    rows = build_scenario_rows(levers, drop, ingested_at=pd.Timestamp("2026-10-10"))
    assert set(rows["source"]) == {"derived"}
    assert set(rows["freq"]) == {"Q"}
    assert set(rows["unit"]) <= {"mb/d", "%"}
    assert rows["value"].dtype == "float64"


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
    assert total["value"].iloc[0] == pytest.approx(7.705 + 1.94425 + 2.325 + 1.043 + 3.136)
