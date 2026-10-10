from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from core.storage import LAKE_ROOT, read_ts_long, write_ts_long
from pipelines.futures.client import ContractMeta
from pipelines.futures.to_ts_long import settles_to_ts_long

_CL_Z26 = ContractMeta(
    root="cl",
    contract="z26",
    expiry=date(2026, 11, 20),
    tick_size=0.01,
    contract_unit="1000 bbl",
    currency="USD",
)
_CL_F27 = ContractMeta(
    root="cl",
    contract="f27",
    expiry=date(2026, 12, 19),
    tick_size=0.01,
    contract_unit="1000 bbl",
    currency="USD",
)
_TFM_Z26 = ContractMeta(
    root="tfm",
    contract="z26",
    expiry=date(2026, 11, 20),
    tick_size=0.001,
    contract_unit="1000 MWh",
    currency="EUR",
)


@pytest.fixture(autouse=True)
def _isolated_lake(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)


def test_settles_to_ts_long_shape() -> None:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-08-01", "2026-08-01"]),
            "root": ["cl", "tfm"],
            "contract": ["z26", "z26"],
            "settle": [61.35, 30.5],
            "oi": [125000, None],
            "volume": [180000, 5000],
        }
    )
    revision_date = pd.Timestamp("2026-08-02")

    result = settles_to_ts_long(df, revision_date, [_CL_Z26, _TFM_Z26], source="manual")

    assert set(result["series_id"]) == {
        "fut.cl.z26.settle",
        "fut.cl.z26.oi",
        "fut.cl.z26.volume",
        "fut.tfm.z26.settle",
        "fut.tfm.z26.volume",
        # tfm's null oi is dropped, not written as a fake 0.0
    }
    assert (result["source"] == "manual").all()
    cl_settle = result[result["series_id"] == "fut.cl.z26.settle"].iloc[0]
    assert cl_settle["unit"] == "USD/1000 bbl"
    tfm_settle = result[result["series_id"] == "fut.tfm.z26.settle"].iloc[0]
    assert tfm_settle["unit"] == "EUR/1000 MWh"  # tfm (ICE TTF) settles in EUR


def test_settles_to_ts_long_uses_the_real_provider_as_source() -> None:
    """A hardcoded source here would break the moment FUTURES_SOURCE is ever switched
    -- two providers writing the same series_id must stay physically partitioned by
    their own real source, not collide under one shared literal."""
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-08-01"]),
            "root": ["cl"],
            "contract": ["z26"],
            "settle": [61.35],
            "oi": [125000],
            "volume": [180000],
        }
    )
    result = settles_to_ts_long(df, pd.Timestamp("2026-08-02"), [_CL_Z26], source="ibkr")
    assert (result["source"] == "ibkr").all()


def test_settles_to_ts_long_float64_regression() -> None:
    """Mirrors tests/test_storage.py's existing v0.11 int64-coercion guard exactly: a
    genuinely int64-typed sibling source in the same glob must never truncate this
    pipeline's own sub-dollar values (a real settle of 61.35, and a hand-written
    spread-like 0.35) when read back via read_ts_long."""
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-08-01", "2026-08-01"]),
            "root": ["cl", "cl"],
            "contract": ["z26", "f27"],
            "settle": [61.35, 0.35],  # 0.35 stands in for a spread-like sub-dollar value
            "oi": [125000, 98000],
            "volume": [180000, 110000],
        }
    )
    long_rows = settles_to_ts_long(
        df, pd.Timestamp("2026-08-02"), [_CL_Z26, _CL_F27], source="manual"
    )
    write_ts_long(long_rows, source="manual")

    # A deliberately int64-typed sibling source, bypassing write_ts_long's own float64
    # coercion on purpose, to reproduce the original v0.11 bug's exact conditions.
    intlike_dir = LAKE_ROOT / "ts_long" / "source=intsource" / "year=2026"
    intlike_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "series_id": ["INTSERIES"],
            "source": ["intsource"],
            "ts": pd.to_datetime(["2026-08-01"]),
            "value": pd.array([500], dtype="int64"),
            "unit": ["count"],
            "geo": ["US"],
            "freq": ["D"],
            "revision_date": pd.to_datetime(["2026-08-02"]),
        }
    ).to_parquet(intlike_dir / "part-0.parquet", index=False)

    settle_result = read_ts_long(series_ids=["fut.cl.z26.settle"])
    spread_result = read_ts_long(series_ids=["fut.cl.f27.settle"])

    assert settle_result.iloc[0]["value"] == pytest.approx(61.35)
    assert spread_result.iloc[0]["value"] == pytest.approx(0.35)
    assert settle_result["value"].dtype == "float64"
    assert spread_result["value"].dtype == "float64"
