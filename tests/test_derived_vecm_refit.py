from __future__ import annotations

import numpy as np
import pandas as pd
from pipelines.derived.vecm_refit import (
    CARD_COLUMNS,
    CRACK_SERIES,
    WTI_SERIES,
    build_panel,
    card_to_row,
    refit,
)


def _lake_panel(months: int = 180, break_at_month: int | None = 60) -> pd.DataFrame:
    """A wide lake-shaped panel: daily rows, one column per series_id.

    Long enough (15 years by default) that a post-break sample still clears
    MIN_POST_BREAK, with a deliberate level shift at `break_at_month` so the break search
    has something real and deterministic to find rather than latching onto noise.
    """
    rng = np.random.default_rng(0)
    index = pd.bdate_range("2005-01-03", periods=months * 22)
    crack = 15.0 + np.cumsum(rng.normal(0, 0.1, len(index)))
    if break_at_month is not None:
        crack[break_at_month * 22 :] += 12.0
    wti = 60.0 + 2.0 * crack + rng.normal(0, 1.0, len(index))
    return pd.DataFrame({WTI_SERIES: wti, CRACK_SERIES: crack}, index=index)


def test_build_panel_produces_log_wti_and_the_crack_level() -> None:
    """The spec's own variables: log(WTI spot) and the 3:2:1 crack in levels."""
    panel = build_panel(_lake_panel())
    assert list(panel.columns) == ["log_wti", "crack321"]
    assert panel["log_wti"].max() < 10  # a log, not a raw price


def test_build_panel_is_monthly_on_the_last_business_day() -> None:
    panel = build_panel(_lake_panel())
    assert (panel.index.dayofweek < 5).all()
    gaps = panel.index.to_series().diff().dropna().dt.days
    # Consecutive business-month-ends can sit up to 33 days apart (e.g. Fri 29 Jul 2005
    # to Wed 31 Aug 2005), so the upper bound is not 31.
    assert gaps.between(26, 34).all()


def test_build_panel_logs_wti_rather_than_the_crack() -> None:
    """The crack goes in as a level -- it can be negative, so logging it would be wrong
    as well as off-spec."""
    raw = _lake_panel()
    panel = build_panel(raw)
    monthly_crack = panel["crack321"]
    assert monthly_crack.max() > 5  # still on the dollar scale, not logged


def test_build_panel_drops_months_where_either_leg_is_missing() -> None:
    raw = _lake_panel()
    raw.loc[raw.index[-40:], WTI_SERIES] = np.nan
    panel = build_panel(raw)
    assert panel.notna().all().all()


def test_refit_returns_a_card_with_every_required_column() -> None:
    card = refit(build_panel(_lake_panel()), test_size=24)
    for column in CARD_COLUMNS:
        assert column in card, column


def test_card_to_row_is_a_single_flat_parquet_safe_row() -> None:
    """The card is written as a plain Parquet manifest (the series_meta precedent), so
    every value has to be a scalar -- no nested dicts or arrays."""
    card = refit(build_panel(_lake_panel()), test_size=24)
    row = card_to_row(card)
    assert len(row) == 1
    for column in CARD_COLUMNS:
        value = row.iloc[0][column]
        assert not isinstance(value, dict | list | np.ndarray), column


def test_refit_records_the_spot_not_futures_deviation() -> None:
    """The single most important caveat on this model must travel with the card, not
    live only in a docstring."""
    card = refit(build_panel(_lake_panel()), test_size=24)
    assert "spot" in card["deviation"].lower()


def test_refit_reports_both_the_full_and_post_break_samples() -> None:
    """The spec estimates on the post-break sample and shows the full sample beside it."""
    card = refit(build_panel(_lake_panel()), test_size=24)
    assert card["estimation_start"] <= card["post_break_start"]
    assert card["sample"] == "post_break"


def test_refit_falls_back_to_the_full_sample_when_the_break_leaves_too_little_data(
) -> None:
    """A break near the end of the sample must not leave the VECM with a handful of
    observations -- it falls back to the full sample and says so."""
    panel = build_panel(_lake_panel())
    card = refit(panel, test_size=24, min_post_break=10_000)
    assert card["sample"] == "full"
