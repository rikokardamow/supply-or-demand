from __future__ import annotations

import pandas as pd
import pytest
from pipelines.futures.eia_futures import (
    EIA_FUTURES,
    MAX_RANK,
    ROUTE,
    eia_series_ids,
    rows_to_ts_long,
)


def _eia_rows() -> pd.DataFrame:
    """The shape pipelines/eia/client.py::EIAClient.get_series actually returns."""
    ts = pd.to_datetime(["2024-04-04", "2024-04-05"])
    frames = []
    for eia_id, value, unit in (
        ("RCLC1", 86.59, "$/BBL"),
        ("EER_EPMRR_PE1_Y35NY_DPG", 2.794, "$/GAL"),
        ("EER_EPD2F_PE1_Y35NY_DPG", 2.741, "$/GAL"),
        ("EER_EPMR_PE1_Y35NY_DPG", 1.512, "$/GAL"),
    ):
        frames.append(
            pd.DataFrame(
                {
                    "series_id": eia_id,
                    "source": "eia",
                    "ts": ts,
                    "value": [value, value + 0.1],
                    "unit": unit,
                    "geo": "US",
                    "freq": "daily",
                    "revision_date": pd.Timestamp("2026-09-05"),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def test_route_is_the_discontinued_eia_futures_route() -> None:
    assert ROUTE == "petroleum/pri/fut"


def test_every_mapped_series_has_a_rank_inside_eias_own_1_to_4_limit() -> None:
    """EIA only ever published contracts 1-4 -- there is no m6 to be had here."""
    assert MAX_RANK == 4
    for spec in EIA_FUTURES:
        assert 1 <= spec.rank <= MAX_RANK


def test_eia_series_ids_are_unique_and_non_empty() -> None:
    ids = eia_series_ids()
    assert len(ids) == len(set(ids))
    assert len(ids) == len(EIA_FUTURES)


def test_rows_to_ts_long_maps_crude_to_the_conventions_rank_series_id() -> None:
    """specs/00_TRADING_CONVENTIONS.md fixes unadjusted nearby ranks as
    fut.<root>.f01.settle ... f36."""
    out = rows_to_ts_long(_eia_rows())
    crude = out[out["series_id"] == "fut.cl.f01.settle"]
    assert len(crude) == 2
    assert crude["value"].iloc[0] == pytest.approx(86.59)


def test_rows_to_ts_long_zero_pads_the_rank() -> None:
    out = rows_to_ts_long(_eia_rows())
    assert all(sid.split(".")[2].startswith("f0") for sid in out["series_id"].unique())


def test_rbob_and_pre_2006_regular_gasoline_get_different_roots() -> None:
    """NYMEX unleaded (HU) and RBOB are two different contracts. Splicing them into one
    `rb` series at ingestion would bake an analytical choice into the lake -- the splice
    stays an explicit downstream decision, which is what core.cracks.rbob_splice_flag is
    for.
    """
    out = rows_to_ts_long(_eia_rows())
    roots = {sid.split(".")[1] for sid in out["series_id"]}
    assert "rb" in roots
    assert "hu" in roots


def test_rows_to_ts_long_keeps_the_quoted_unit_per_root() -> None:
    """Crude settles in $/bbl and the products in $/gal. core.cracks does the 42x
    conversion itself, so converting here would double-count it."""
    out = rows_to_ts_long(_eia_rows()).set_index("series_id")
    assert out.loc["fut.cl.f01.settle", "unit"].iloc[0] == "USD/bbl"
    assert out.loc["fut.rb.f01.settle", "unit"].iloc[0] == "USD/gal"


def test_rows_to_ts_long_marks_the_source_as_eia() -> None:
    """Not "futures" -- the source column records which provider produced the row, so a
    later IBKR pull can coexist rather than being indistinguishable."""
    out = rows_to_ts_long(_eia_rows())
    assert out["source"].unique().tolist() == ["eia"]


def test_rows_to_ts_long_writes_float64_values() -> None:
    assert rows_to_ts_long(_eia_rows())["value"].dtype == "float64"


def test_rows_to_ts_long_ignores_an_unmapped_eia_series() -> None:
    rows = _eia_rows()
    rows.loc[rows["series_id"] == "RCLC1", "series_id"] = "SOMETHING_ELSE"
    out = rows_to_ts_long(rows)
    assert "fut.cl.f01.settle" not in set(out["series_id"])
    assert len(out) > 0


def test_rows_to_ts_long_on_an_empty_frame_returns_empty() -> None:
    assert rows_to_ts_long(pd.DataFrame()).empty
