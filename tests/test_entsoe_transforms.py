from __future__ import annotations

import pandas as pd
from pipelines.entsoe.transforms import net_position, residual_load


def test_residual_load_subtracts_wind_and_solar() -> None:
    dates = pd.date_range("2026-01-01", periods=3, freq="h")
    load = pd.Series([1000.0, 1100.0, 1200.0], index=dates)
    wind = pd.Series([200.0, 250.0, 300.0], index=dates)
    solar = pd.Series([50.0, 0.0, 100.0], index=dates)

    result = residual_load(load, wind, solar)

    assert result.tolist() == [750.0, 850.0, 800.0]


def test_residual_load_treats_missing_wind_or_solar_as_zero() -> None:
    dates = pd.date_range("2026-01-01", periods=2, freq="h")
    load = pd.Series([1000.0, 1100.0], index=dates)
    wind = pd.Series([200.0, 250.0], index=dates)
    solar = pd.Series(dtype=float)  # a landlocked zone with no solar series at all

    result = residual_load(load, wind, solar)

    assert result.tolist() == [800.0, 850.0]


def test_net_position_hand_checked() -> None:
    ts = pd.Timestamp("2026-05-01")
    flows = pd.DataFrame(
        {
            "from_node": ["DE_LU", "FR"],
            "to_node": ["FR", "DE_LU"],
            "value": [100.0, 30.0],
            "ts": [ts, ts],
        }
    )

    result = net_position(flows).set_index("zone")

    # DE_LU sends 100, receives 30 -> net +70. FR sends 30, receives 100 -> net -70.
    assert result.loc["DE_LU", "net_position"] == 70.0
    assert result.loc["FR", "net_position"] == -70.0


def test_net_position_handles_zone_with_only_outbound() -> None:
    ts = pd.Timestamp("2026-05-01")
    flows = pd.DataFrame(
        {
            "from_node": ["DE_LU"],
            "to_node": ["FR"],
            "value": [50.0],
            "ts": [ts],
        }
    )

    result = net_position(flows).set_index("zone")

    assert result.loc["DE_LU", "net_position"] == 50.0
    assert result.loc["FR", "net_position"] == -50.0
