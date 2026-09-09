from __future__ import annotations

import pytest
from core.schemas import validate_ts_long
from pipelines.coal import pull_coal


@pytest.mark.vcr
def test_coal_returns_valid_ts_long_under_its_own_source() -> None:
    df = pull_coal.pull_coal(pull_coal.EIAClient())

    validate_ts_long(df)
    assert not df.empty
    # The whole reason item 4 gets its own source: read_ts_long(source="coal") must be
    # meaningful. If the client's hardcoded "eia" leaked through, these rows would be
    # filed under coal/ while claiming to be eia -- nothing raises, and every freshness
    # query misreports them.
    assert set(df["source"]) == {"coal"}


@pytest.mark.vcr
def test_price_and_heat_content_both_arrive_with_their_own_units() -> None:
    # A switching calculation needs price AND heat content together; that they share one
    # route is the spec's stated reason for choosing it. They are in different units, and
    # units are stored exactly as published -- so a single unit across both would mean
    # one of them was overwritten.
    df = pull_coal.pull_coal(pull_coal.EIAClient())

    price = df[df["series_id"].str.contains(".PRICE.", regex=False)]
    heat = df[df["series_id"].str.contains(".HEAT_CONTENT.", regex=False)]
    assert not price.empty, "no price rows -- a switching calculation needs them"
    assert not heat.empty, "no heat-content rows -- a switching calculation needs them"
    assert set(price["unit"]) != set(heat["unit"]), (
        "price and heat content share a unit -- one has overwritten the other"
    )


@pytest.mark.vcr
def test_every_requested_data_key_produced_rows() -> None:
    df = pull_coal.pull_coal(pull_coal.EIAClient())
    for key in pull_coal.DATA_KEYS:
        marker = f".{key.upper().replace('-', '_')}."
        assert any(marker in sid for sid in df["series_id"]), f"no rows for {key}"


def test_data_keys_are_named_constants_not_positional() -> None:
    assert pull_coal.PRICE in pull_coal.DATA_KEYS
    assert pull_coal.HEAT_CONTENT in pull_coal.DATA_KEYS
    assert len(set(pull_coal.DATA_KEYS)) == len(pull_coal.DATA_KEYS)


def test_coal_series_ids_are_deterministic() -> None:
    row = {"location": "US", "sector": "1"}
    minted = pull_coal.coal_series_id(pull_coal.PRICE, row)
    assert minted == "COAL.PRICE.US-1.Q"
    # Permanent once written: the same row must always mint the same id.
    assert minted == pull_coal.coal_series_id(pull_coal.PRICE, dict(row))
