from __future__ import annotations

import pandas as pd
from pipelines.entsog.corridors import PointSpec
from pipelines.entsog.transforms import (
    corridor_aggregate,
    latest_complete_date,
    pair_daily_totals,
)


def test_corridor_aggregate_sums_points_within_a_corridor() -> None:
    corridors = {
        "NO_EXPORTS": [
            PointSpec("ITP-A", "entry", "NO", "DE"),
            PointSpec("ITP-B", "entry", "NO", "BE"),
        ],
        "TAP": [PointSpec("ITP-C", "entry", "TAP", "IT")],
    }
    flows_df = pd.DataFrame(
        {
            "from_node": ["NO", "NO", "TAP", "NO"],
            "to_node": ["DE", "BE", "IT", "DE"],
            "value": [100.0, 50.0, 10.0, 200.0],
            "ts": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-01", "2024-01-02"]),
            "mode": ["pipeline", "pipeline", "pipeline", "pipeline"],
        }
    )

    result = corridor_aggregate(flows_df, corridors)

    no_exports_day1 = result[
        (result["corridor"] == "NO_EXPORTS") & (result["ts"] == "2024-01-01")
    ]["value"].iloc[0]
    assert no_exports_day1 == 150.0

    tap_day1 = result[(result["corridor"] == "TAP") & (result["ts"] == "2024-01-01")][
        "value"
    ].iloc[0]
    assert tap_day1 == 10.0


def test_corridor_aggregate_filters_by_mode() -> None:
    corridors = {"NO_EXPORTS": [PointSpec("ITP-A", "entry", "NO", "DE")]}
    flows_df = pd.DataFrame(
        {
            "from_node": ["NO", "NO"],
            "to_node": ["DE", "DE"],
            "value": [100.0, 90.0],
            "ts": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "mode": ["pipeline", "nomination"],
        }
    )

    result = corridor_aggregate(flows_df, corridors, mode="nomination")

    assert len(result) == 1
    assert result.iloc[0]["value"] == 90.0


def test_corridor_aggregate_drops_points_outside_any_corridor() -> None:
    corridors = {"NO_EXPORTS": [PointSpec("ITP-A", "entry", "NO", "DE")]}
    flows_df = pd.DataFrame(
        {
            "from_node": ["NO", "RU"],
            "to_node": ["DE", "UA"],
            "value": [100.0, 999.0],
            "ts": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "mode": ["pipeline", "pipeline"],
        }
    )

    result = corridor_aggregate(flows_df, corridors)

    assert len(result) == 1
    assert result.iloc[0]["corridor"] == "NO_EXPORTS"


def test_pair_daily_totals_sums_multiple_points_sharing_a_pair() -> None:
    # Two points both landing NO->DE on the same day must combine into one total —
    # skipping this step silently understates a multi-point pair's trailing average
    # (divides by days*points instead of just days).
    flows_df = pd.DataFrame(
        {
            "from_node": ["NO", "NO"],
            "to_node": ["DE", "DE"],
            "value": [100.0, 50.0],
            "ts": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "mode": ["pipeline", "pipeline"],
        }
    )

    result = pair_daily_totals(flows_df)

    assert len(result) == 1
    assert result.iloc[0]["value"] == 150.0


def test_sankey_link_totals_reconcile_with_corridor_time_series() -> None:
    # The spec's Session B acceptance criterion, as an actual regression test: summing
    # the Sankey's per-link (from_node, to_node) 7-day averages within a corridor must
    # exactly equal that corridor's own 7-day average from corridor_aggregate. Includes
    # a multi-point pair (NO->DE, 2 points) and a staggered per-pair reporting lag
    # (NO->GB stops one day early) — both confirmed live gotchas from the real pull.
    corridors = {
        "NO_EXPORTS": [
            PointSpec("ITP-A", "entry", "NO", "DE"),
            PointSpec("ITP-B", "entry", "NO", "DE"),
            PointSpec("ITP-C", "entry", "NO", "GB"),
        ],
    }
    dates = pd.date_range("2024-01-01", periods=8, freq="D")
    rows = []
    for d in dates:
        rows.append({"from_node": "NO", "to_node": "DE", "value": 100.0, "ts": d})
        rows.append({"from_node": "NO", "to_node": "DE", "value": 20.0, "ts": d})
        if d != dates[-1]:  # NO->GB lags one day behind NO->DE
            rows.append({"from_node": "NO", "to_node": "GB", "value": 50.0, "ts": d})
    flows_df = pd.DataFrame(rows)
    flows_df["mode"] = "pipeline"

    daily_pairs = pair_daily_totals(flows_df)
    latest_ts = latest_complete_date(daily_pairs, ["from_node", "to_node"])
    window_start = latest_ts - pd.Timedelta(days=6)
    recent = daily_pairs[(daily_pairs["ts"] >= window_start) & (daily_pairs["ts"] <= latest_ts)]

    link_means = recent.groupby(["from_node", "to_node"])["value"].mean()
    sankey_corridor_total = link_means.sum()

    corridor_df = corridor_aggregate(flows_df, corridors, mode="pipeline")
    corridor_recent = corridor_df[
        (corridor_df["ts"] >= window_start) & (corridor_df["ts"] <= latest_ts)
    ]
    corridor_7d_avg = corridor_recent["value"].mean()

    assert sankey_corridor_total == corridor_7d_avg


def test_latest_complete_date_is_the_earliest_of_each_group_s_own_latest() -> None:
    # NO->GB stops one day earlier than NO->DE (a real, confirmed ENTSOG per-operator
    # publication lag) — the shared "complete" date must be the earlier one, or a
    # trailing-window average would silently include a partially-reported day for one
    # pair but not the other.
    daily_df = pd.DataFrame(
        {
            "from_node": ["NO", "NO", "NO"],
            "to_node": ["DE", "DE", "GB"],
            "ts": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-01"]),
            "value": [100.0, 110.0, 50.0],
        }
    )

    result = latest_complete_date(daily_df, ["from_node", "to_node"])

    assert result == pd.Timestamp("2024-01-01")
