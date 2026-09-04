"""Manual physical-market reader covering Spec 19's own Data section (agency
spare-capacity estimates, quality/grade differentials, Saudi OSPs, benchmark-health
counts) plus Spec 18's own 4 named physical-differential series. Same convention as
every other manual source in this project (`data/manual/<source>/*.csv`, git-ignored,
`source="manual"`, file's own as-of date as `revision_date`).

Specs 18 and 19 each built this package independently on separate branches; the two
`SERIES_META` dicts were merged (not one file picked over the other) when the second
of the two PRs landed -- see NOTES.md for the resolution record."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from core.storage import write_ts_long

MANUAL_PHYSICAL_DIR = Path("data/manual/physical")

# series_id -> (unit, geo, freq). Spec 19's own Data section, verbatim, followed by
# Spec 18's own 4 series (merged in when PR #42 landed first -- see NOTES.md).
SERIES_META: dict[str, tuple[str, str, str]] = {
    "manual.eia_steo.spare_capacity": ("mb/d", "GLOBAL", "M"),
    "manual.iea_omr.spare_capacity": ("mb/d", "GLOBAL", "M"),
    "manual.platts.dubai_m1": ("USD/bbl", "ASIA", "D"),
    "manual.platts.dubai_m3": ("USD/bbl", "ASIA", "D"),
    "manual.dme.oman": ("USD/bbl", "ASIA", "D"),
    "manual.platts.brent_dubai_efs": ("USD/bbl", "GLOBAL", "D"),
    "manual.argus.wcs_diff": ("USD/bbl", "US", "D"),
    "manual.argus.lls_diff": ("USD/bbl", "US", "D"),
    "manual.argus.maya_diff": ("USD/bbl", "GLOBAL", "D"),
    "manual.argus.mars_diff": ("USD/bbl", "US", "D"),
    "manual.argus.urals_diff": ("USD/bbl", "GLOBAL", "D"),
    "manual.saudi_aramco.osp_arab_light_asia": ("USD/bbl", "ASIA", "M"),
    "manual.saudi_aramco.osp_arab_light_nwe": ("USD/bbl", "EU", "M"),
    "manual.saudi_aramco.osp_arab_light_us": ("USD/bbl", "US", "M"),
    "manual.platts.dated_brent_window_trades": ("count", "GLOBAL", "D"),
    "manual.platts.dubai_partials": ("count", "ASIA", "D"),
    "manual.argus.wti_midland_share_bfoet": ("pct", "US", "D"),
    # Spec 18's own Data table. Dated Brent / DFL are the global Brent complex; the two
    # Argus WTI diffs are US Permian-linked physical differentials -- all USD/bbl daily.
    "manual.platts.dated_brent": ("USD/bbl", "GLOBAL", "D"),
    "manual.platts.dfl_m1": ("USD/bbl", "GLOBAL", "D"),
    "manual.argus.wti_midland_diff": ("USD/bbl", "US", "D"),
    "manual.argus.wti_houston_diff": ("USD/bbl", "US", "D"),
}
SERIES_IDS = tuple(SERIES_META)

_COLUMNS = ["date", "series_id", "value"]


def read_physical_csvs(data_dir: Path = MANUAL_PHYSICAL_DIR) -> pd.DataFrame:
    """Reads every data_dir/*.csv (columns: date, series_id, value). Rejects a
    series_id outside SERIES_IDS and a duplicate (date, series_id) row."""
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
    """Wide (date, series_id, value) -> long ts_long rows, unit/geo/freq per
    SERIES_META. These series genuinely differ in unit -- mb/d, USD/bbl, count, pct --
    and in freq -- daily differentials vs monthly OSPs and agency spare-capacity
    estimates -- so all three are looked up per series rather than hardcoded."""
    if df.empty:
        return pd.DataFrame(
            columns=["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]
        )

    units = df["series_id"].map(lambda sid: SERIES_META[sid][0])
    geos = df["series_id"].map(lambda sid: SERIES_META[sid][1])
    freqs = df["series_id"].map(lambda sid: SERIES_META[sid][2])

    return pd.DataFrame(
        {
            "series_id": df["series_id"],
            "source": "manual",
            "ts": df["date"],
            "value": df["value"].astype(float),
            "unit": units,
            "geo": geos,
            "freq": freqs,
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
