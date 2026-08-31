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
def test_production_route_returns_ts_long_conformant_dataframe() -> None:
    client = EIAClient()
    df = client.get_series(route="natural-gas/prod/sum", series=["N9070US2"], frequency="monthly")

    assert not df.empty
    assert set(df.columns) == EXPECTED_COLUMNS
    assert (df["geo"] == "US").all()


@pytest.mark.vcr
def test_lng_exports_cross_checks_against_pipeline_plus_total() -> None:
    # Confirmed live (Spec 05 Session C): the spec's originally-named
    # natural-gas/move/poe2 route only has partial per-destination-country series
    # that sum to a small fraction of real exports -- natural-gas/sum/lsum has the
    # genuine pre-aggregated national total instead. This cross-check (pipeline +
    # LNG == combined total, all three from the same route) is why.
    client = EIAClient()
    df = client.get_series(
        route="natural-gas/sum/lsum",
        series=["N9130US2", "N9132US2", "N9133US2"],
        frequency="monthly",
    )

    latest_ts = df["ts"].max()
    latest = df[df["ts"] == latest_ts].set_index("series_id")["value"]
    assert latest["N9132US2"] + latest["N9133US2"] == pytest.approx(latest["N9130US2"], abs=1.0)


@pytest.mark.vcr
def test_gas_storage_area_name_is_literal_na() -> None:
    # Documents a real API gotcha (confirmed live, Spec 05 Session A): this route
    # never populates area-name at all -- it's the literal string "NA" for every
    # row, not a genuine missing-value case like Cushing's -- which is why
    # get_series needs an explicit geo_map for this route rather than relying on
    # _normalise_geo(area-name).
    client = EIAClient()
    rows = client._fetch_rows(
        route="natural-gas/stor/wkly", series=["NW2_EPG0_SWO_R48_BCF"], frequency="weekly"
    )

    assert rows
    assert all(row["area-name"] == "NA" for row in rows)


@pytest.mark.vcr
def test_get_series_geo_map_overrides_area_name() -> None:
    client = EIAClient()
    df = client.get_series(
        route="natural-gas/stor/wkly",
        series=["NW2_EPG0_SWO_R48_BCF"],
        frequency="weekly",
        geo_map={"NW2_EPG0_SWO_R48_BCF": "L48"},
    )

    assert not df.empty
    assert (df["geo"] == "L48").all()


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
