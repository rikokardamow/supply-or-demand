from __future__ import annotations

import pandas as pd
import pytest
from pipelines.derived.publish_flows import (
    SERVING_FLOWS_COLUMNS,
    period_for,
    to_serving_flows,
)


def _flows(source: str, mode: str, n: int = 2) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source": source,
            "from_node": "PADD2",
            "to_node": "PADD1",
            "value": [1.0] * n,
            "unit": "MBBL",
            "ts": pd.date_range("2026-09-01", periods=n, freq="D"),
            "mode": mode,
        }
    )


def test_period_reflects_the_measured_cadence_not_the_spec_s_two_values() -> None:
    # Spec 32 §2 annotates the column 'weekly','monthly'. Measured live 2026-09-09 from
    # the median gap between consecutive observations on one corridor, this lake actually
    # holds hourly, daily and monthly -- and none of it is weekly.
    assert period_for("eia", "grid_interchange") == "hourly"
    assert period_for("entsog", "pipeline") == "daily"
    assert period_for("entsog", "nomination") == "daily"
    assert period_for("eia", "rail") == "monthly"
    assert period_for("eia", "tanker_barge") == "monthly"


def test_pipeline_means_a_different_cadence_in_each_source() -> None:
    # ENTSOG's `pipeline` is daily EU gas; EIA's is monthly inter-PADD crude movements.
    # Mode alone cannot separate them, and `period` is part of serving.flows' primary
    # key -- getting it wrong would collapse one corridor's rows onto another's.
    assert period_for("entsog", "pipeline") == "daily"
    assert period_for("eia", "pipeline") == "monthly"


def test_an_unknown_mode_raises_rather_than_defaulting() -> None:
    # Defaulting would write a false cadence into a primary-key column, silently.
    with pytest.raises(ValueError, match="no known cadence"):
        period_for("eia", "teleportation")


def test_to_serving_flows_returns_the_serving_schema_columns() -> None:
    rows = to_serving_flows(_flows("entsog", "pipeline"))

    assert list(rows.columns) == SERVING_FLOWS_COLUMNS
    assert set(rows["period"]) == {"daily"}


def test_to_serving_flows_assigns_each_source_its_own_period_in_one_frame() -> None:
    mixed = pd.concat([_flows("eia", "pipeline"), _flows("entsog", "pipeline")], ignore_index=True)

    rows = to_serving_flows(mixed)

    by_source = rows.groupby("source")["period"].unique().to_dict()
    assert by_source["eia"].tolist() == ["monthly"]
    assert by_source["entsog"].tolist() == ["daily"]


def test_to_serving_flows_handles_an_empty_frame() -> None:
    rows = to_serving_flows(pd.DataFrame())

    assert rows.empty
    assert list(rows.columns) == SERVING_FLOWS_COLUMNS


def test_multiple_physical_points_on_one_corridor_are_summed_not_silently_dropped() -> None:
    # ENTSOG maps 21 physical interconnection points onto 8 corridors (see
    # pipelines/entsog/CLAUDE.md), and the lake's flows schema has no point dimension --
    # so LNG->FR, NO->DE and NO->GB each land as two rows per timestamp, distinguishable
    # only by value. Confirmed live 2026-09-09: 4,365 such groups, always exactly two
    # rows. Deduping would report one terminal's send-out as the whole corridor, roughly
    # halving it; the corridor total is the sum of its points.
    two_points = pd.DataFrame(
        {
            "source": "entsog",
            "from_node": "LNG",
            "to_node": "FR",
            "value": [99.466446, 121.675045],
            "unit": "GWh/d",
            "ts": pd.to_datetime(["2024-09-09", "2024-09-09"]),
            "mode": "nomination",
        }
    )

    rows = to_serving_flows(two_points)

    assert len(rows) == 1
    assert rows["value"].iloc[0] == pytest.approx(221.141491)


def test_summing_does_not_merge_genuinely_different_modes() -> None:
    # A corridor carrying both a pipeline and a tanker/barge movement on the same date is
    # two real flows, not one -- `mode` stays part of the grouping.
    both = pd.concat(
        [_flows("eia", "pipeline", n=1), _flows("eia", "tanker_barge", n=1)],
        ignore_index=True,
    )

    rows = to_serving_flows(both)

    assert len(rows) == 2
    assert set(rows["mode"]) == {"pipeline", "tanker_barge"}
