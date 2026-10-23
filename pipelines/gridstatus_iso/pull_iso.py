"""Pull trailing 60 days of hourly load, fuel mix, and zone/hub-level LMP for CAISO
and NYISO into ts_long. ERCOT, PJM, and MISO are all out of scope for now -- see
pipelines/gridstatus_iso/NOTES.md for why (ERCOT's site blocks scraping; PJM needs
a free API key I can't currently get; MISO's real-time load/fuel-mix
endpoints only serve "today" for the current year, no genuine historical window)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
from core.failures import fails_loudly, record_failure
from core.storage import write_ts_long

from pipelines.gridstatus_iso.client import GridstatusISOClient

ISOS = ["CAISO", "NYISO"]
LOOKBACK_DAYS = 60


def _slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")


@fails_loudly("gridstatus_iso.pull_iso")
def main() -> None:
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    pulled_at = datetime.now(UTC)

    load_frames = []
    fuel_mix_frames = []
    lmp_frames = []

    for iso_name in ISOS:
        client = GridstatusISOClient(iso_name)

        try:
            load = client.get_load(start, end)
        except Exception as exc:  # broad: gridstatus raises a mix of error types
            record_failure(f"{iso_name} load", exc)
        else:
            print(f"{iso_name} load: {len(load)} rows", flush=True)
            if not load.empty:
                load_frames.append(
                    pd.DataFrame(
                        {
                            "series_id": f"gridstatus.{iso_name}.load",
                            "source": "gridstatus",
                            "ts": load["ts"],
                            "value": load["value"],
                            "unit": "MW",
                            "geo": iso_name,
                            "freq": "H",
                            "revision_date": pulled_at,
                        }
                    )
                )

        try:
            fuel_mix = client.get_fuel_mix(start, end)
        except Exception as exc:  # broad: gridstatus raises a mix of error types
            record_failure(f"{iso_name} fuel_mix", exc)
        else:
            print(f"{iso_name} fuel_mix: {len(fuel_mix)} rows", flush=True)
            if not fuel_mix.empty:
                fuel_mix_frames.append(
                    pd.DataFrame(
                        {
                            "series_id": "gridstatus."
                            + iso_name
                            + ".fuel_mix."
                            + fuel_mix["fuel_type"].map(_slug),
                            "source": "gridstatus",
                            "ts": fuel_mix["ts"],
                            "value": fuel_mix["value"],
                            "unit": "MW",
                            "geo": iso_name,
                            "freq": "H",
                            "revision_date": pulled_at,
                        }
                    )
                )

        try:
            lmp = client.get_lmp(start, end)
        except Exception as exc:  # broad: gridstatus raises a mix of error types
            record_failure(f"{iso_name} lmp", exc)
        else:
            print(f"{iso_name} lmp: {len(lmp)} rows", flush=True)
            if not lmp.empty:
                lmp_frames.append(
                    pd.DataFrame(
                        {
                            "series_id": "gridstatus."
                            + iso_name
                            + ".lmp."
                            + lmp["hub"].map(_slug),
                            "source": "gridstatus",
                            "ts": lmp["ts"],
                            "value": lmp["value"],
                            "unit": "USD/MWh",
                            "geo": iso_name + "." + lmp["hub"],
                            "freq": "H",
                            "revision_date": pulled_at,
                        }
                    )
                )

    for label, frames in [
        ("load", load_frames),
        ("fuel_mix", fuel_mix_frames),
        ("lmp", lmp_frames),
    ]:
        if not frames:
            print(f"no {label} rows pulled", flush=True)
            continue
        df = pd.concat(frames, ignore_index=True)
        write_ts_long(df, source="gridstatus")
        print(f"wrote {len(df)} {label} rows", flush=True)


if __name__ == "__main__":
    main()
