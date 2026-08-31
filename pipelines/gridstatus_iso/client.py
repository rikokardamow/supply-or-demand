"""gridstatus ISO client -- normalises CAISO/NYISO load, fuel mix, and hub/zone-level
LMP into ts_long-ready long frames, downsampled to hourly per the spec's data model.
Gotchas documented in pipelines/gridstatus_iso/NOTES.md -- confirmed live, not
assumed from gridstatus's docs, since real behaviour differs across its ISO classes
(e.g. ERCOT is blocked by the site's own bot-protection, and MISO's real-time
load/fuel-mix endpoints only serve "today" for the current year -- neither is used
here; see NOTES.md for the full story)."""

from __future__ import annotations

from datetime import date
from typing import Any

import gridstatus
import pandas as pd

from pipelines.gridstatus_iso.hubs import HUBS

_ISO_CLASSES: dict[str, Any] = {"CAISO": gridstatus.CAISO, "NYISO": gridstatus.NYISO}

_LMP_MARKET = "REAL_TIME_5_MIN"


class GridstatusISOClient:
    def __init__(self, iso_name: str) -> None:
        self.iso_name = iso_name
        self._iso = _ISO_CLASSES[iso_name]()

    def get_load(self, start: date, end: date) -> pd.DataFrame:
        """Returns ["ts", "value"], hourly, MW."""
        raw = self._iso.get_load(date=start, end=end)
        if raw.empty:
            return pd.DataFrame(columns=["ts", "value"])
        hourly = _downsample_hourly(raw.set_index("Time")[["Load"]])
        return hourly.reset_index().rename(columns={"Time": "ts", "Load": "value"})

    def get_fuel_mix(self, start: date, end: date) -> pd.DataFrame:
        """Returns ["ts", "fuel_type", "value"], hourly, MW."""
        raw = self._iso.get_fuel_mix(date=start, end=end)
        if raw.empty:
            return pd.DataFrame(columns=["ts", "fuel_type", "value"])
        fuel_cols = [c for c in raw.columns if c not in ("Time", "Interval Start", "Interval End")]
        wide = raw.set_index("Time")[fuel_cols].apply(pd.to_numeric, errors="coerce")
        hourly = _downsample_hourly(wide)
        return hourly.reset_index().melt(
            id_vars="Time", var_name="fuel_type", value_name="value"
        ).rename(columns={"Time": "ts"})

    def get_lmp(self, start: date, end: date) -> pd.DataFrame:
        """Returns ["ts", "hub", "value"], hourly, $/MWh."""
        hubs = HUBS[self.iso_name]
        raw = self._iso.get_lmp(date=start, end=end, market=_LMP_MARKET, locations=hubs)
        if raw.empty:
            return pd.DataFrame(columns=["ts", "hub", "value"])
        wide = raw.pivot_table(index="Time", columns="Location", values="LMP")
        hourly = _downsample_hourly(wide)
        return hourly.reset_index().melt(
            id_vars="Time", var_name="hub", value_name="value"
        ).rename(columns={"Time": "ts"})


def _downsample_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a tz-aware index to naive UTC (matching this project's ts_long
    convention) then mean-resample to hourly -- works for both a single-column
    (load) and multi-column (fuel mix, LMP-wide) frame."""
    df = df.copy()
    index = pd.DatetimeIndex(df.index)
    df.index = index.tz_convert("UTC").tz_localize(None)
    return df.resample("h").mean()
