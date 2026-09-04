"""Stub reader for Spec 18's own 4 named physical-differential series -- Spec 19 owns the
full manual_physical scope (EIA STEO/IEA OMR spare capacity, Dubai/Oman/WCS/Maya/Urals
diffs, Saudi OSPs, benchmark-health counts). This session builds only enough to read the
4 series Spec 18's own Data table names, matching pipelines/futures/client.py's
ManualCSVClient convention: a small, hand-dropped, git-ignored CSV directory, source
"manual"."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from core.storage import write_ts_long

MANUAL_PHYSICAL_DIR = Path("data/manual/physical")

# Spec 18's own Data table, verbatim.
SERIES_IDS = (
    "manual.platts.dated_brent",
    "manual.platts.dfl_m1",
    "manual.argus.wti_midland_diff",
    "manual.argus.wti_houston_diff",
)

# Dated Brent / DFL are the global Brent complex; the two Argus WTI diffs are US
# Permian-basin-linked physical differentials -- both priced in USD/bbl either way.
_GEO_BY_SERIES = {
    "manual.platts.dated_brent": "GLOBAL",
    "manual.platts.dfl_m1": "GLOBAL",
    "manual.argus.wti_midland_diff": "US",
    "manual.argus.wti_houston_diff": "US",
}

_COLUMNS = ["date", "series_id", "value"]


def read_physical_csvs(data_dir: Path = MANUAL_PHYSICAL_DIR) -> pd.DataFrame:
    """Reads every data_dir/*.csv (columns: date, series_id, value). Rejects a series_id
    outside SERIES_IDS and a duplicate (date, series_id) row -- same validation discipline
    as ManualCSVClient._validate."""
    files = sorted(data_dir.glob("*.csv"))
    if not files:
        return pd.DataFrame(columns=_COLUMNS)

    frames = [pd.read_csv(f) for f in files]
    combined = pd.concat(frames, ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"])

    missing = set(_COLUMNS) - set(combined.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")

    unknown = set(combined["series_id"]) - set(SERIES_IDS)
    if unknown:
        raise ValueError(f"unrecognised series_id(s): {sorted(unknown)}")

    duplicated = combined.duplicated(subset=["date", "series_id"], keep=False)
    if duplicated.any():
        dupes = combined.loc[duplicated, ["date", "series_id"]].drop_duplicates()
        raise ValueError(f"duplicate (date, series_id) rows: {dupes.to_dict('records')}")

    return combined


def physical_to_ts_long(df: pd.DataFrame, revision_date: pd.Timestamp) -> pd.DataFrame:
    """Wide (date, series_id, value) -> long ts_long rows, unit="USD/bbl" (every one of
    Spec 18's own 4 series is an outright price or a price differential), geo per
    _GEO_BY_SERIES, freq="D"."""
    if df.empty:
        return pd.DataFrame(
            columns=["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]
        )
    return pd.DataFrame(
        {
            "series_id": df["series_id"],
            "source": "manual",
            "ts": df["date"],
            "value": df["value"].astype(float),
            "unit": "USD/bbl",
            "geo": df["series_id"].map(_GEO_BY_SERIES),
            "freq": "D",
            "revision_date": revision_date,
        }
    )


def main() -> None:
    ingested_at = pd.Timestamp(pd.Timestamp.now())
    df = read_physical_csvs()
    if df.empty:
        print(
            "manual_physical: no CSVs found under data/manual/physical -- nothing to write",
            flush=True,
        )
        return

    long_df = physical_to_ts_long(df, ingested_at)
    write_ts_long(long_df, source="manual")
    print(f"manual_physical: wrote {len(long_df)} rows", flush=True)


if __name__ == "__main__":
    main()
