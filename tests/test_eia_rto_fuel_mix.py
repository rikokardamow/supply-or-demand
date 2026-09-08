from __future__ import annotations

import pytest
from core.schemas import validate_ts_long
from pipelines.eia import pull_rto_fuel_mix
from pipelines.eia.rto import ERCOT, NATURAL_GAS, PJM


@pytest.fixture(scope="module")
def vcr_config(vcr_config: dict[str, object]) -> dict[str, object]:
    """`_hour_bounds` stamps start/end from `datetime.now(UTC)`, so the recorded
    request's query string carries a fixed timestamp that will not match a later
    replay's freshly-computed one. Relaxed match_on (method+path only, dropping the
    query string) rather than freezing time: freezegun isn't already a dependency here,
    and the pull module deliberately takes no clock parameter to satisfy a cassette (see
    pull_rto_fuel_mix.py's docstring) -- a test-local match_on relaxation is the narrower
    fix and needs no new dependency."""
    return {**vcr_config, "match_on": ["method", "path"]}


@pytest.mark.vcr
def test_fuel_mix_returns_valid_ts_long() -> None:
    df = pull_rto_fuel_mix.pull_fuel_mix(pull_rto_fuel_mix.EIAClient(), days=2)

    validate_ts_long(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    assert ERCOT in set(df["geo"])
    assert PJM in set(df["geo"])


@pytest.mark.vcr
def test_gas_fired_generation_is_present_for_both_target_markets() -> None:
    # Gas-fired generation in ERCOT and PJM is the actual gas-demand signal this whole
    # item exists to capture. Everything else here is context.
    df = pull_rto_fuel_mix.pull_fuel_mix(pull_rto_fuel_mix.EIAClient(), days=2)

    gas_ids = {f"RTO.FUEL.{ba}.{NATURAL_GAS}.H" for ba in (ERCOT, PJM)}
    assert gas_ids <= set(df["series_id"]), (
        f"missing gas-fired generation for: {gas_ids - set(df['series_id'])}"
    )


@pytest.mark.vcr
def test_fuel_ids_never_collide_with_region_ids() -> None:
    # `type=NG` (net generation) and `fueltype=NG` (natural gas) are the same two
    # characters on different routes. Without the FUEL/REGION segment one would
    # overwrite the other in the lake with nothing raised.
    df = pull_rto_fuel_mix.pull_fuel_mix(pull_rto_fuel_mix.EIAClient(), days=2)
    assert all(sid.startswith("RTO.FUEL.") for sid in df["series_id"])
