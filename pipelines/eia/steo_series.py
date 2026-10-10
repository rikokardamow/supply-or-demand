"""Hand-maintained STEO series reference table -- same precedent as
pipelines/macro/fred_series.py. Every (unit, freq) pair was read from that code's own live
`/v2/steo/facet/seriesId` + data response on 2026-10-10, never guessed from the code.

Three codes the workbook's labels imply -- MGTCPUS, JKTCPUS, COTCPUS -- are NOT published by
EIA. They are recorded in the spec rather than here, so a future reader does not re-guess them.

The `_P` pair is the one that changes the arithmetic: the RFS percentage standards apply to
non-renewable gasoline and distillate, so `MGTCPUSX_P`/`DFTCPUS_P` are the correct denominator.
`MGTCPUSX`/`DFTCPUS` include the renewable volume already blended in, and using them inflates
the implied mandate invisibly."""

from __future__ import annotations

from typing import NamedTuple


class SteoMeta(NamedTuple):
    unit: str
    freq: str
    geo: str
    description: str


MBD = "million barrels per day"

STEO_SERIES: dict[str, SteoMeta] = {
    "MGTCPUSX": SteoMeta(MBD, "M", "US", "Motor Gasoline Product Supplied"),
    "DFTCPUS": SteoMeta(MBD, "M", "US", "Distillate Fuel Oil Product Supplied"),
    "JFTCPUS": SteoMeta(MBD, "M", "US", "Jet Fuel Product Supplied"),
    "EOTCPUS": SteoMeta(MBD, "M", "US", "Fuel Ethanol Consumption"),
    "BDTCPUS_PS": SteoMeta(MBD, "M", "US", "Biodiesel Product Supplied"),
    "RDTCPUS_PS": SteoMeta(MBD, "M", "US", "Renewable Diesel Product Supplied"),
    "PATCPUSX": SteoMeta(MBD, "M", "US", "Total Petroleum and Other Liquids Product Supplied"),
    # The RFS denominator -- non-renewable only. See the module docstring.
    "MGTCPUSX_P": SteoMeta(MBD, "M", "US", "Petroleum-based Gasoline Consumption"),
    "DFTCPUS_P": SteoMeta(MBD, "M", "US", "Petroleum-based Distillate Consumption"),
}

RFS_DENOMINATOR_CODES: tuple[str, str] = ("MGTCPUSX_P", "DFTCPUS_P")


def lake_series_id(code: str) -> str:
    """Lake series id (without the observed/projected label) for a STEO code.

    The one place the mapping lives: ``pull_steo`` writes ``steo.<code>.<label>`` with it and
    ``derived.rin`` reads with it, so the two cannot drift apart."""
    return f"steo.{code.lower()}"
