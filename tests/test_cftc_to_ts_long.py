from __future__ import annotations

import pandas as pd
from core.schemas import TS_LONG_SCHEMA, validate_ts_long
from pipelines.cftc.to_ts_long import disaggregated_to_ts_long

REVISION_DATE = pd.Timestamp("2026-09-05")


def _wide_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-08-25", "2026-09-01"]),
            "mm_long": [120_000, 125_000],
            "mm_short": [40_000, 38_000],
            "prod_merc_long": [200_000, 205_000],
            "prod_merc_short": [260_000, 262_000],
            "oi": [1_800_000, 1_810_000],
        }
    )


def test_every_metric_column_becomes_its_own_series() -> None:
    result = disaggregated_to_ts_long(_wide_frame(), root="cl", revision_date=REVISION_DATE)

    assert set(result["series_id"]) == {
        "cftc.cl.mm_long",
        "cftc.cl.mm_short",
        "cftc.cl.prod_merc_long",
        "cftc.cl.prod_merc_short",
        "cftc.cl.oi",
    }
    assert len(result) == 10  # 5 metrics x 2 report dates


def test_values_are_carried_across_unchanged_and_as_floats() -> None:
    result = disaggregated_to_ts_long(_wide_frame(), root="cl", revision_date=REVISION_DATE)

    mm_long = result[result["series_id"] == "cftc.cl.mm_long"].sort_values("ts")
    assert mm_long["value"].tolist() == [120_000.0, 125_000.0]
    # float64, never the source int: an int64-typed `value` column is the exact shape of
    # the incident core/NOTES.md documents, where one source's ints truncated the whole
    # column on read.
    assert mm_long["value"].dtype == "float64"


def test_output_conforms_to_the_ts_long_schema() -> None:
    result = disaggregated_to_ts_long(_wide_frame(), root="cl", revision_date=REVISION_DATE)

    validate_ts_long(result)  # must not raise -- these rows go straight to write_ts_long
    assert list(result.columns) == list(TS_LONG_SCHEMA.names)
    assert set(result["geo"]) == {"CL"}
    assert set(result["freq"]) == {"W"}  # CFTC COT is weekly
    assert set(result["unit"]) == {"contracts"}
    assert set(result["source"]) == {"cftc"}


def test_an_empty_pull_returns_an_empty_frame_of_the_right_shape() -> None:
    """A root with no rows this week must still hand write_ts_long something it can
    validate, not a bare DataFrame() with no columns."""
    result = disaggregated_to_ts_long(pd.DataFrame(), root="cl", revision_date=REVISION_DATE)

    assert result.empty
    assert list(result.columns) == list(TS_LONG_SCHEMA.names)


def test_root_is_namespaced_into_every_series_id() -> None:
    ng = disaggregated_to_ts_long(_wide_frame(), root="ng", revision_date=REVISION_DATE)

    assert all(sid.startswith("cftc.ng.") for sid in ng["series_id"])
    assert set(ng["geo"]) == {"NG"}
