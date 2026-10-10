from __future__ import annotations

import pandas as pd
import pytest
from pipelines.eia.wpsr_lines import (
    WPSR_LINES_COLUMNS,
    WPSR_REPORT_LINES,
    build_wpsr_lines,
)

CRUDE = "WCESTUS1"


def _weekly(series_id: str, values: list[float], end: str = "2026-09-04") -> pd.DataFrame:
    """A weekly ts_long-shaped frame ending on `end`, oldest first."""
    ts = pd.date_range(end=end, periods=len(values), freq="7D")
    return pd.DataFrame({"series_id": series_id, "ts": ts, "value": values, "unit": "MBBL"})


def test_build_wpsr_lines_returns_the_serving_schema_columns() -> None:
    rows = build_wpsr_lines(_weekly(CRUDE, [400.0, 402.0]))

    assert list(rows.columns) == WPSR_LINES_COLUMNS
    assert rows["line"].tolist() == ["crude_ex_spr"]
    assert rows["week_ending"].tolist() == [pd.Timestamp("2026-09-04").date()]


def test_wow_is_an_absolute_change_in_the_line_s_own_unit() -> None:
    # EIA and every trade report quote a weekly stock move in barrels, not per cent --
    # "crude drew 2.1 million barrels", never "crude fell 0.5%".
    rows = build_wpsr_lines(_weekly(CRUDE, [400.0, 397.9]))

    assert rows["wow"].iloc[0] == pytest.approx(-2.1)


def test_yoy_is_a_percentage_against_the_observation_a_year_earlier() -> None:
    # 53 weekly points: the first is 364 days before the last.
    values = [100.0] + [0.0] * 51 + [110.0]
    values[1:52] = [105.0] * 51
    rows = build_wpsr_lines(_weekly(CRUDE, values))

    assert rows["yoy_pct"].iloc[0] == pytest.approx(10.0)


def test_missing_comparisons_are_null_never_zero() -> None:
    # A single observation has no prior week and no year-ago week. Publishing 0.0 would
    # render as "unchanged" on the screen, which is a different claim from "unknown".
    rows = build_wpsr_lines(_weekly(CRUDE, [400.0]))

    assert rows["wow"].iloc[0] is None
    assert rows["yoy_pct"].iloc[0] is None


def test_a_year_ago_observation_outside_the_tolerance_does_not_count() -> None:
    # Only two points, six months apart: nothing sits near 364 days back, so there is no
    # year-on-year figure to report rather than a wrong one drawn from a nearby date.
    df = pd.DataFrame(
        {
            "series_id": CRUDE,
            "ts": pd.to_datetime(["2026-03-06", "2026-09-04"]),
            "value": [380.0, 400.0],
            "unit": "MBBL",
        }
    )

    rows = build_wpsr_lines(df)

    assert rows["yoy_pct"].iloc[0] is None


def test_vs_median_is_measured_against_the_seasonal_band_excluding_2020() -> None:
    # Six years of flat 100.0 with 2020 spiking to 999.0. The median the level is
    # compared against must ignore 2020 entirely (golden rule 4), so a latest value of
    # 110.0 reads as +10% -- not the deep negative a 999-inflated median would give.
    frames = []
    for year in [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]:
        value = 999.0 if year == 2020 else 100.0
        ts = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="7D")
        frames.append(pd.DataFrame({"series_id": CRUDE, "ts": ts, "value": value, "unit": "MBBL"}))
    latest = pd.DataFrame(
        {
            "series_id": CRUDE,
            "ts": pd.to_datetime(["2026-09-04"]),
            "value": [110.0],
            "unit": "MBBL",
        }
    )

    rows = build_wpsr_lines(pd.concat([*frames, latest], ignore_index=True))

    assert rows["vs_median_pct"].iloc[0] == pytest.approx(10.0, abs=0.5)


def test_a_series_absent_from_the_lake_is_skipped_not_published_as_a_blank_row() -> None:
    rows = build_wpsr_lines(_weekly(CRUDE, [400.0, 402.0]))

    assert len(rows) == 1  # only the one series present, not all 15 configured lines
    assert set(rows["line"]) == {"crude_ex_spr"}


def test_line_order_is_stable_and_matches_the_configured_reading_order() -> None:
    df = pd.concat(
        [_weekly(line.series_id, [100.0, 101.0]) for line in WPSR_REPORT_LINES],
        ignore_index=True,
    )

    rows = build_wpsr_lines(df)

    assert len(rows) == len(WPSR_REPORT_LINES)
    assert rows["line_order"].tolist() == list(range(1, len(WPSR_REPORT_LINES) + 1))
    assert rows["line"].tolist() == [line.line for line in WPSR_REPORT_LINES]


def test_every_configured_line_has_a_distinct_slug_and_series() -> None:
    # `line` is half the primary key of serving.wpsr_lines -- a duplicate would make one
    # line silently overwrite another on publish.
    slugs = [line.line for line in WPSR_REPORT_LINES]
    series = [line.series_id for line in WPSR_REPORT_LINES]

    assert len(set(slugs)) == len(slugs)
    assert len(set(series)) == len(series)


def test_vs_median_uses_only_its_own_series_not_every_series_in_the_frame() -> None:
    # Caught on real data 2026-09-09: the median was computed from the whole multi-series
    # frame rather than the line's own series, so crude stocks (~424,000 MBBL) were
    # compared against a median blended with refinery utilisation (~98%) and daily rates
    # (~17,000 MBBL/D). Published vs_median_pct read +11,462% for crude and -97.3% for
    # utilisation. Every earlier fixture held a single series, so nothing caught it.
    #
    # Two series of wildly different magnitude, each flat across the band years: both
    # must read ~0% against their own median.
    frames = []
    for year in range(2018, 2026):
        ts = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="7D")
        frames.append(
            pd.DataFrame({"series_id": CRUDE, "ts": ts, "value": 400000.0, "unit": "MBBL"})
        )
        frames.append(pd.DataFrame({"series_id": "WPULEUS3", "ts": ts, "value": 90.0, "unit": "%"}))
    latest = pd.DataFrame(
        {
            "series_id": [CRUDE, "WPULEUS3"],
            "ts": pd.to_datetime(["2026-09-04", "2026-09-04"]),
            "value": [400000.0, 90.0],
            "unit": ["MBBL", "%"],
        }
    )

    rows = build_wpsr_lines(pd.concat([*frames, latest], ignore_index=True)).set_index("line")

    assert rows.loc["crude_ex_spr", "vs_median_pct"] == pytest.approx(0.0, abs=0.5)
    assert rows.loc["refinery_utilisation", "vs_median_pct"] == pytest.approx(0.0, abs=0.5)
