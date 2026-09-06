from __future__ import annotations

import pytest
from core.schemas import validate_ts_long
from pipelines.eia import pull_gas_consumption


@pytest.mark.vcr
def test_consumption_returns_valid_ts_long_for_every_sector() -> None:
    df = pull_gas_consumption.pull_consumption(pull_gas_consumption.EIAClient())

    validate_ts_long(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    # Every requested sector must come back with rows. A sector that silently
    # returns nothing would leave a gap in the demand picture that no error reports.
    assert set(df["series_id"]) == set(pull_gas_consumption.CONSUMPTION)


def test_sectors_are_named_constants_not_positional() -> None:
    # Spec 30 shipped GENERATOR_FUEL[0]; reordering that list would have plotted the
    # wrong unit against a price axis, raising nothing. Sectors are selected by name.
    assert pull_gas_consumption.RESIDENTIAL in pull_gas_consumption.CONSUMPTION
    assert pull_gas_consumption.ELECTRIC_POWER in pull_gas_consumption.CONSUMPTION
    assert len(set(pull_gas_consumption.CONSUMPTION)) == len(pull_gas_consumption.CONSUMPTION)
