from __future__ import annotations

import pandas as pd
import pytest


def test_steo_registry_holds_the_confirmed_codes_and_the_petroleum_based_denominators() -> None:
    """The `_P` series are the RFS denominator -- the headline totals include the renewable
    volume already blended in, so using them double-counts. Confirmed live 2026-10-10."""
    from pipelines.eia.steo_series import RFS_DENOMINATOR_CODES, STEO_SERIES

    for code in ("MGTCPUSX", "DFTCPUS", "JFTCPUS", "EOTCPUS", "BDTCPUS_PS",
                 "RDTCPUS_PS", "PATCPUSX", "MGTCPUSX_P", "DFTCPUS_P"):
        assert code in STEO_SERIES, code
        assert STEO_SERIES[code].unit == "million barrels per day"
        assert STEO_SERIES[code].freq == "M"

    # Codes the workbook's own labels imply but EIA does not publish. Confirmed live.
    for absent in ("MGTCPUS", "JKTCPUS", "COTCPUS"):
        assert absent not in STEO_SERIES, f"{absent} is not published by EIA"

    assert RFS_DENOMINATOR_CODES == ("MGTCPUSX_P", "DFTCPUS_P")


@pytest.mark.vcr
def test_get_steo_series_reads_steos_own_field_names() -> None:
    """STEO returns `seriesId`/`unit`/`seriesDescription` and no `area-name`. The existing
    `get_series` reads `series`/`units`/`area-name` and cannot be pointed at this route."""
    from pipelines.eia.client import EIAClient

    df = EIAClient().get_steo_series(["MGTCPUSX"], "monthly")

    assert list(df.columns) == [
        "series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"
    ]
    assert (df["source"] == "eia_steo").all(), "source must distinguish an outlook from eia actuals"
    assert (df["series_id"] == "MGTCPUSX").all()
    assert (df["unit"] == "million barrels per day").all()
    assert (df["geo"] == "US").all()
    assert df["value"].notna().all()
    assert pd.api.types.is_datetime64_any_dtype(df["ts"])
    assert df["ts"].max() >= pd.Timestamp("2027-01-01"), "STEO must carry its forward path"
