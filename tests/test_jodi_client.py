from __future__ import annotations

from pathlib import Path

import pytest
from pipelines.jodi import client

_SAMPLE_CSV = (
    b"REF_AREA,TIME_PERIOD,ENERGY_PRODUCT,FLOW_BREAKDOWN,UNIT_MEASURE,OBS_VALUE,ASSESSMENT_CODE\n"
    b"US,2026-06,CRUDEOIL,INDPROD,KBD,13818.0000,3\n"
)


class _FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "CACHE_DIR", tmp_path)


def test_download_annual_csv_fetches_and_caches_a_closed_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_get(url: str, timeout: int) -> _FakeResponse:
        calls.append(url)
        return _FakeResponse(_SAMPLE_CSV)

    monkeypatch.setattr(client.requests, "get", fake_get)

    df = client.download_annual_csv(2025, is_current_year=False)
    assert len(df) == 1
    assert df.iloc[0]["REF_AREA"] == "US"
    assert calls == [
        "https://www.jodidata.org/_resources/files/downloads/oil-data/annual-csv/primary/2025.csv"
    ]

    # Second call for the same closed year is a cache hit -- no second request.
    df_again = client.download_annual_csv(2025, is_current_year=False)
    assert len(df_again) == 1
    assert len(calls) == 1


def test_download_annual_csv_always_refetches_the_current_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_get(url: str, timeout: int) -> _FakeResponse:
        calls.append(url)
        return _FakeResponse(_SAMPLE_CSV)

    monkeypatch.setattr(client.requests, "get", fake_get)

    client.download_annual_csv(2026, is_current_year=True)
    client.download_annual_csv(2026, is_current_year=True)

    assert len(calls) == 2
    assert all("primaryyear2026.csv" in url for url in calls)


def test_download_annual_csv_url_pattern_differs_for_current_vs_closed_year() -> None:
    assert client._csv_url(2026, is_current_year=True).endswith("primaryyear2026.csv")
    assert client._csv_url(2025, is_current_year=False).endswith("/2025.csv")


def test_download_annual_csv_matches_real_schema_columns() -> None:
    # A quick sanity check that our synthetic fixture's columns match the real
    # schema confirmed live (Session C) -- not a network test.
    import io

    import pandas as pd

    df = pd.read_csv(io.BytesIO(_SAMPLE_CSV), dtype={"OBS_VALUE": str})
    assert list(df.columns) == [
        "REF_AREA", "TIME_PERIOD", "ENERGY_PRODUCT", "FLOW_BREAKDOWN",
        "UNIT_MEASURE", "OBS_VALUE", "ASSESSMENT_CODE",
    ]  # fmt: skip


def test_download_annual_csv_reads_the_secondary_table_under_its_own_url_and_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Same filename split as the primary table, different path segment -- confirmed live
    2026-10-10. The cache name must differ too, or a secondary file would be served to a
    primary caller for the same year."""
    calls: list[str] = []

    def fake_get(url: str, timeout: int) -> _FakeResponse:
        calls.append(url)
        return _FakeResponse(_SAMPLE_CSV)

    monkeypatch.setattr(client.requests, "get", fake_get)

    client.download_annual_csv(2025, is_current_year=False, table="secondary")
    client.download_annual_csv(2026, is_current_year=True, table="secondary")
    client.download_annual_csv(2025, is_current_year=False)

    base = "https://www.jodidata.org/_resources/files/downloads/oil-data/annual-csv"
    assert calls == [
        f"{base}/secondary/2025.csv",
        f"{base}/secondary/secondaryyear2026.csv",
        f"{base}/primary/2025.csv",
    ]
    assert (tmp_path / "jodi-secondary-2025.csv").exists()
    assert (tmp_path / "jodi-primary-2025.csv").exists()


def test_download_annual_csv_rejects_an_unknown_table() -> None:
    with pytest.raises(ValueError, match="tertiary"):
        client.download_annual_csv(2025, is_current_year=False, table="tertiary")
