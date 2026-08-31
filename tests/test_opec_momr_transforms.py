from __future__ import annotations

import pandas as pd
from pipelines.opec_momr.transforms import production_vs_quota, revision_waterfall


def test_production_vs_quota_computes_compliance() -> None:
    actual = pd.Series({"Saudi Arabia": 7352.0, "Russia": 8887.0, "Oman": 926.0})
    quotas = pd.DataFrame(
        {
            "country": ["Saudi Arabia", "Russia", "Oman"],
            "effective_from": pd.to_datetime(["2026-09-01"] * 3),
            "quota_kbd": [10478, 9949, 841],
        }
    )

    result = production_vs_quota(actual, quotas)

    assert list(result["country"]) == ["Saudi Arabia", "Russia", "Oman"]  # sorted by quota desc
    oman = result[result["country"] == "Oman"].iloc[0]
    assert oman["compliance_pct"] > 100  # confirmed live: Oman overproduces vs. its target
    assert oman["gap_kbd"] == 926.0 - 841


def test_production_vs_quota_only_includes_countries_in_both() -> None:
    actual = pd.Series({"Saudi Arabia": 7352.0, "Nigeria": 1546.0})  # Nigeria has no quota row
    quotas = pd.DataFrame(
        {
            "country": ["Saudi Arabia"],
            "effective_from": pd.to_datetime(["2026-09-01"]),
            "quota_kbd": [10478],
        }
    )

    result = production_vs_quota(actual, quotas)

    assert list(result["country"]) == ["Saudi Arabia"]


def test_production_vs_quota_uses_most_recent_quota_row() -> None:
    actual = pd.Series({"Saudi Arabia": 7352.0})
    quotas = pd.DataFrame(
        {
            "country": ["Saudi Arabia", "Saudi Arabia"],
            "effective_from": pd.to_datetime(["2026-08-01", "2026-09-01"]),
            "quota_kbd": [10416, 10478],
        }
    )

    result = production_vs_quota(actual, quotas)

    assert result.iloc[0]["quota_kbd"] == 10478


def test_revision_waterfall_extracts_one_period_sorted_by_magnitude() -> None:
    df = pd.DataFrame(
        {
            "series_id": [
                "momr.demand_balance_revision.world_demand.europe.quarterly",
                "momr.demand_balance_revision.world_demand.china.quarterly",
                "momr.demand_balance_revision.world_demand.africa.quarterly",
            ],
            "ts": pd.to_datetime(["2026-04-01", "2026-04-01", "2026-04-01"]),
            "value": [-0.2, 0.1, 0.05],
        }
    )

    result = revision_waterfall(df, pd.Timestamp("2026-04-01"))

    assert list(result["label"]) == [
        "world_demand.europe",
        "world_demand.china",
        "world_demand.africa",
    ]
    assert list(result["value"]) == [-0.2, 0.1, 0.05]


def test_revision_waterfall_filters_to_requested_period_only() -> None:
    df = pd.DataFrame(
        {
            "series_id": [
                "momr.demand_balance_revision.world_demand.europe.quarterly",
                "momr.demand_balance_revision.world_demand.europe.quarterly",
            ],
            "ts": pd.to_datetime(["2026-04-01", "2026-07-01"]),
            "value": [-0.2, 0.3],
        }
    )

    result = revision_waterfall(df, pd.Timestamp("2026-04-01"))

    assert len(result) == 1
    assert result.iloc[0]["value"] == -0.2
