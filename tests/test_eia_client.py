from __future__ import annotations

import pytest
from core.schemas import validate_flows
from pipelines.eia.client import EIAClient

EXPECTED_COLUMNS = {
    "series_id",
    "source",
    "ts",
    "value",
    "unit",
    "geo",
    "freq",
    "revision_date",
}


@pytest.mark.vcr
def test_get_series_returns_ts_long_conformant_dataframe() -> None:
    client = EIAClient()
    df = client.get_series(route="petroleum/stoc/wstk", series=["WCESTUS1"], frequency="weekly")

    assert not df.empty
    assert set(df.columns) == EXPECTED_COLUMNS
    assert (df["series_id"] == "WCESTUS1").all()
    assert (df["source"] == "eia").all()
    assert df["value"].dtype.kind == "f"


@pytest.mark.vcr
def test_national_series_geo_is_us() -> None:
    # Regression: client used to read row["area"] (doesn't exist in the EIA response;
    # only "area-name" does), so geo silently came out "" for every row.
    client = EIAClient()
    df = client.get_series(route="petroleum/stoc/wstk", series=["WCESTUS1"], frequency="weekly")

    assert (df["geo"] == "US").all()


@pytest.mark.vcr
def test_padd_series_geo_is_normalised() -> None:
    client = EIAClient()
    df = client.get_series(
        route="petroleum/pnp/wiup", series=["W_NA_YUP_R10_PER"], frequency="weekly"
    )

    assert (df["geo"] == "PADD1").all()


@pytest.mark.vcr
def test_wiup_route_returns_ts_long_conformant_dataframe() -> None:
    client = EIAClient()
    df = client.get_series(route="petroleum/pnp/wiup", series=["WPULEUS3"], frequency="weekly")

    assert not df.empty
    assert set(df.columns) == EXPECTED_COLUMNS
    assert (df["unit"] == "%").all()


@pytest.mark.vcr
def test_wpsup_route_returns_ts_long_conformant_dataframe() -> None:
    client = EIAClient()
    df = client.get_series(route="petroleum/cons/wpsup", series=["WRPUPUS2"], frequency="weekly")

    assert not df.empty
    assert set(df.columns) == EXPECTED_COLUMNS


@pytest.mark.vcr
def test_wkly_route_returns_ts_long_conformant_dataframe() -> None:
    client = EIAClient()
    df = client.get_series(route="petroleum/move/wkly", series=["WCEIMUS2"], frequency="weekly")

    assert not df.empty
    assert set(df.columns) == EXPECTED_COLUMNS


@pytest.mark.vcr
def test_list_series_returns_id_and_name_facets() -> None:
    client = EIAClient()
    facets = client.list_series(route="petroleum/move/pipe")

    assert facets
    assert all({"id", "name"} <= set(f) for f in facets)
    assert any(f["id"] == "MCRMPP2P31" for f in facets)


@pytest.mark.vcr
def test_sndw_route_returns_ts_long_conformant_dataframe() -> None:
    client = EIAClient()
    df = client.get_series(route="petroleum/sum/sndw", series=["WCRFPUS2"], frequency="weekly")

    assert not df.empty
    assert set(df.columns) == EXPECTED_COLUMNS
    assert (df["geo"] == "US").all()


@pytest.mark.vcr
def test_get_flows_returns_flows_schema_conformant_dataframe() -> None:
    client = EIAClient()
    df = client.get_flows(
        route="petroleum/move/pipe",
        corridors={"MCRMPP2P31": ("PADD3", "PADD2", "pipeline")},
        frequency="monthly",
    )

    assert not df.empty
    validate_flows(df)  # raises on schema mismatch
    assert (df["from_node"] == "PADD3").all()
    assert (df["to_node"] == "PADD2").all()
    assert (df["mode"] == "pipeline").all()
