"""Pull generation mix, load, and wind/solar forecast for all 13 covered zones into
ts_long. A shorter lookback than pull_prices.py's 90 days -- generation/wind-solar are
per-PSR-type (multiple rows per timestamp), so the row count multiplies fast across 13
zones; 14 days is enough for a meaningful generation-mix chart and residual-load calc
without an excessive pull given the Transparency Platform's confirmed live flakiness."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
from core.storage import write_ts_long

from pipelines.entsoe.client import ENTSOEClient
from pipelines.entsoe.zones import ZONES

LOOKBACK_DAYS = 14


def _slug(psr_type: str) -> str:
    return psr_type.lower().replace(" ", "_").replace("/", "_").replace("-", "_")


def main() -> None:
    client = ENTSOEClient()
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    pulled_at = datetime.now(UTC)

    load_frames = []
    generation_frames = []
    wind_solar_frames = []

    for zone in ZONES:
        try:
            load = client.get_load(zone, start, end)
        except RuntimeError as exc:
            # One flaky zone/indicator shouldn't abort the whole 13-zone pull -- see
            # pull_prices.py's identical reasoning. Re-run to retry whatever failed.
            print(f"{zone} load: FAILED ({exc}) — skipping", flush=True)
        else:
            print(f"{zone} load: {len(load)} rows", flush=True)
            if not load.empty:
                load_frames.append(
                    pd.DataFrame(
                        {
                            "series_id": f"entsoe.{zone}.load",
                            "source": "entsoe",
                            "ts": load["ts"],
                            "value": load["value"],
                            "unit": "MW",
                            "geo": zone,
                            "freq": load["freq"],
                            "revision_date": pulled_at,
                        }
                    )
                )

        try:
            generation = client.get_generation(zone, start, end)
        except RuntimeError as exc:
            print(f"{zone} generation: FAILED ({exc}) — skipping", flush=True)
        else:
            print(f"{zone} generation: {len(generation)} rows", flush=True)
            if not generation.empty:
                generation_frames.append(
                    pd.DataFrame(
                        {
                            "series_id": "entsoe."
                            + zone
                            + ".generation."
                            + generation["psr_type"].map(_slug),
                            "source": "entsoe",
                            "ts": generation["ts"],
                            "value": generation["value"],
                            "unit": "MW",
                            "geo": zone,
                            "freq": generation["freq"],
                            "revision_date": pulled_at,
                        }
                    )
                )

        try:
            wind_solar = client.get_wind_and_solar_forecast(zone, start, end)
        except RuntimeError as exc:
            print(f"{zone} wind/solar forecast: FAILED ({exc}) — skipping", flush=True)
        else:
            print(f"{zone} wind/solar forecast: {len(wind_solar)} rows", flush=True)
            if not wind_solar.empty:
                wind_solar_frames.append(
                    pd.DataFrame(
                        {
                            "series_id": "entsoe."
                            + zone
                            + ".forecast."
                            + wind_solar["psr_type"].map(_slug),
                            "source": "entsoe",
                            "ts": wind_solar["ts"],
                            "value": wind_solar["value"],
                            "unit": "MW",
                            "geo": zone,
                            "freq": wind_solar["freq"],
                            "revision_date": pulled_at,
                        }
                    )
                )

    for label, frames in [
        ("load", load_frames),
        ("generation", generation_frames),
        ("wind/solar forecast", wind_solar_frames),
    ]:
        if not frames:
            print(f"no {label} rows pulled", flush=True)
            continue
        df = pd.concat(frames, ignore_index=True)
        write_ts_long(df, source="entsoe")
        print(f"wrote {len(df)} {label} rows", flush=True)


if __name__ == "__main__":
    main()
