from __future__ import annotations

import numpy as np
import pandas as pd
from pipelines.derived.systematic import (
    POSITION_ROOTS,
    inputs_for_root,
    position_rows,
    rows_for_root,
)


def _lake(n: int = 900) -> pd.DataFrame:
    """ts_long rows for one root: four ranks, the adjusted front month, and both
    conditioners."""
    idx = pd.bdate_range("2015-01-01", periods=n)
    rng = np.random.default_rng(0)
    base = 70 + np.cumsum(rng.normal(0, 0.5, n))
    frames = []

    def add(series_id: str, values: np.ndarray) -> None:
        frames.append(
            pd.DataFrame(
                {
                    "series_id": series_id,
                    "source": "eia",
                    "ts": idx,
                    "value": values,
                    "unit": "USD/bbl",
                    "geo": "US",
                    "freq": "D",
                    "revision_date": pd.Timestamp("2026-09-05"),
                }
            )
        )

    for r in (1, 2, 3, 4):
        add(f"fut.cl.f{r:02d}.settle", base - 0.4 * (r - 1))
    add("derived.curve.cl.f01_adj", base)
    add("derived.cushing.util_decile", rng.integers(0, 10, n).astype(float))
    add("derived.cot.cl.mm_pct_3y", rng.uniform(0, 1, n))
    return pd.concat(frames, ignore_index=True)


def test_position_roots_are_the_ones_with_rank_data() -> None:
    assert set(POSITION_ROOTS) == {"cl", "rb", "ho", "hu"}


def test_inputs_for_root_assembles_every_leg() -> None:
    data = inputs_for_root(_lake(), "cl")
    assert list(data.unadj.columns) == ["f01", "f02", "f03", "f04"]
    assert len(data.f01_adj) == 900
    assert data.util_decile is not None
    assert data.cot_pct is not None


def test_inputs_for_a_root_with_no_data_is_none() -> None:
    assert inputs_for_root(_lake(), "rb") is None


def test_position_rows_use_the_conventions_series_id() -> None:
    """specs/00_TRADING_CONVENTIONS.md: positions are derived.pos.<strategy>.<root>."""
    pos = pd.Series(0.5, index=pd.bdate_range("2020-01-01", periods=3))
    rows = position_rows("MOM_100", "cl", pos, pd.Timestamp("2026-09-05"))
    assert rows["series_id"].unique().tolist() == ["derived.pos.MOM_100.cl"]
    assert rows["value"].dtype == "float64"
    assert rows["source"].unique().tolist() == ["derived"]
    assert rows["unit"].unique().tolist() == ["position"]


def test_position_rows_are_empty_for_an_empty_series() -> None:
    assert position_rows("MOM_100", "cl", pd.Series(dtype=float), pd.Timestamp("2026-09-05")).empty


def test_rows_for_root_skips_the_strategies_that_need_deferred_ranks() -> None:
    """CARRY_1_13 and FWD_SPREAD_MR need ranks 13 and 7; EIA publishes 1-4. They must be
    absent from the output, not written as flat positions."""
    rows, skipped = rows_for_root(_lake(), "cl", pd.Timestamp("2026-09-05"))
    written = {sid.split(".")[2] for sid in rows["series_id"].unique()}
    assert "CARRY_1_13" not in written
    assert "FWD_SPREAD_MR" not in written
    assert {"CARRY_1_13", "FWD_SPREAD_MR"} <= set(skipped)


def test_rows_for_root_writes_the_strategies_that_do_work() -> None:
    rows, _ = rows_for_root(_lake(), "cl", pd.Timestamp("2026-09-05"))
    written = {sid.split(".")[2] for sid in rows["series_id"].unique()}
    assert {"MOM_100", "CONVEX_SPREAD", "SHORT_SPREAD_STATIC", "CARRY_REACT"} <= written


def test_skipped_strategies_carry_a_reason() -> None:
    """A skip with no reason is indistinguishable from a bug."""
    _, skipped = rows_for_root(_lake(), "cl", pd.Timestamp("2026-09-05"))
    assert all(reason for reason in skipped.values())
    assert "f13" in skipped["CARRY_1_13"]


def test_a_root_with_no_data_produces_nothing() -> None:
    rows, skipped = rows_for_root(_lake(), "ho", pd.Timestamp("2026-09-05"))
    assert rows.empty
    assert skipped == {}
