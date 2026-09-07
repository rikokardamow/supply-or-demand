from __future__ import annotations

import pandas as pd
import pytest
from core.failures import PartialFailureError
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
    # This route resolves area-name to "US" cleanly for all four sectors (unlike its
    # sibling natural-gas/stor/cap, which returns the literal "NA") -- the module
    # docstring spends three lines on that decision, so pin it rather than leave it
    # as prose only.
    assert set(df["geo"]) == {"US"}
    # Capacity's sibling pull stores MMcf; this route also publishes MMcf (not the
    # $/MCF of pull_prices.py's gas prices) -- confirmed live against the cassette
    # (1,896 rows). Pin the exact string so a republish in a different unit fails
    # loudly here, not silently on a chart.
    assert set(df["unit"]) == {"MMCF"}


def test_sectors_are_named_constants_not_positional() -> None:
    # Spec 30 shipped GENERATOR_FUEL[0]; reordering that list would have plotted the
    # wrong unit against a price axis, raising nothing. Sectors are selected by name.
    assert pull_gas_consumption.RESIDENTIAL in pull_gas_consumption.CONSUMPTION
    assert pull_gas_consumption.ELECTRIC_POWER in pull_gas_consumption.CONSUMPTION
    assert len(set(pull_gas_consumption.CONSUMPTION)) == len(pull_gas_consumption.CONSUMPTION)


def test_main_raises_when_no_consumption_rows_pulled(monkeypatch: pytest.MonkeyPatch) -> None:
    # An empty (or wholly missing) pull must not report success to the scheduler --
    # see core/failures.py's docstring on why a swallowed failure has to raise so the
    # exit status is honest. No cassette: pull_consumption is monkeypatched directly.
    empty = pd.DataFrame(
        columns=["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]
    )
    monkeypatch.setattr(pull_gas_consumption, "pull_consumption", lambda client: empty)

    with pytest.raises(PartialFailureError):
        pull_gas_consumption.main()
