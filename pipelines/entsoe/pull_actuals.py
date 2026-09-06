"""Pull generation mix, load, and wind/solar forecast for all 13 covered zones into
ts_long. A shorter lookback than pull_prices.py's 90 days -- generation/wind-solar are
per-PSR-type (multiple rows per timestamp), so the row count multiplies fast across 13
zones; 14 days is enough for a meaningful generation-mix chart and residual-load calc
without an excessive pull given the Transparency Platform's confirmed live flakiness."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
from core.failures import fails_loudly, record_failure
from core.storage import write_ts_long

from pipelines.entsoe.client import ENTSOEClient
from pipelines.entsoe.zones import ZONES

LOOKBACK_DAYS = 14


def _slug(psr_type: str) -> str:
    return psr_type.lower().replace(" ", "_").replace("/", "_").replace("-", "_")


def pull_actuals(
    client: ENTSOEClient, zones: list[str], start: date, end: date
) -> dict[str, pd.DataFrame]:
    """Shared by main()'s full backfill and pull_daily.py's prior-day re-pull — same
    per-zone, per-indicator resilience (one flaky zone/indicator must never abort the
    rest). Returns {"load": ..., "generation": ..., "wind_solar": ...}, each an
    empty-but-columned ts_long frame if nothing was pulled."""
    pulled_at = datetime.now(UTC)

    load_frames = []
    generation_frames = []
    wind_solar_frames = []

    for zone in zones:
        try:
            load = client.get_load(zone, start, end)
        except RuntimeError as exc:
            # One flaky zone/indicator shouldn't abort the whole 13-zone pull -- see
            # pull_prices.py's identical reasoning. Re-run to retry whatever failed.
            record_failure(f"{zone} load", exc)
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
            record_failure(f"{zone} generation", exc)
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
            record_failure(f"{zone} wind/solar forecast", exc)
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

    empty = pd.DataFrame(
        columns=["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]
    )
    return {
        "load": pd.concat(load_frames, ignore_index=True) if load_frames else empty,
        "generation": pd.concat(generation_frames, ignore_index=True)
        if generation_frames
        else empty,
        "wind/solar forecast": pd.concat(wind_solar_frames, ignore_index=True)
        if wind_solar_frames
        else empty,
    }


@fails_loudly("entsoe.pull_actuals")
def main() -> None:
    client = ENTSOEClient()
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)

    actuals = pull_actuals(client, ZONES, start, end)
    for label, df in actuals.items():
        if df.empty:
            print(f"no {label} rows pulled", flush=True)
            continue
        write_ts_long(df, source="entsoe")
        print(f"wrote {len(df)} {label} rows", flush=True)


if __name__ == "__main__":
    main()
