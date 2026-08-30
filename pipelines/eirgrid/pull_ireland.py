"""Pull 90 days of ROI demand, generation, wind, CO2 intensity, and interconnection
into ts_long. NI/ALL regions and the wider EU-power sessions' zone list aren't in scope
here — Session C is ROI only, per the spec."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
from core.storage import write_ts_long

from pipelines.eirgrid.client import EirGridClient

REGION = "ROI"
LOOKBACK_DAYS = 90

# EirGrid's own FieldName -> (series_id suffix, unit). One row per area except
# "interconnection", which returns three fields at once (see NOTES.md).
FIELD_MAP: dict[str, tuple[str, str]] = {
    "SYSTEM_DEMAND": ("demand", "MW"),
    "GEN_EXP": ("generation", "MW"),
    "WIND_ACTUAL": ("wind", "MW"),
    "CO2_INTENSITY": ("co2_intensity", "gCO2/kWh"),
    "INTER_EWIC": ("inter_ewic", "MW"),
    "INTER_GRNLK": ("inter_greenlink", "MW"),
    "INTER_NET_ROI": ("inter_net", "MW"),
}
AREAS = ["demandactual", "generationactual", "windactual", "co2intensity", "interconnection"]


def main() -> None:
    client = EirGridClient()
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    pulled_at = datetime.now(UTC)

    frames = []
    for area in AREAS:
        try:
            raw = client.get_series(area, REGION, start, end)
        except (RuntimeError, ValueError) as exc:
            print(f"{area}: FAILED ({exc}) — skipping", flush=True)
            continue
        print(f"{area}: {len(raw)} rows", flush=True)
        if raw.empty:
            continue
        for field_name_raw, group in raw.groupby("field_name"):
            field_name = str(field_name_raw)
            suffix, unit = FIELD_MAP.get(field_name, (field_name.lower(), "MW"))
            frames.append(
                pd.DataFrame(
                    {
                        "series_id": f"eirgrid.{REGION}.{suffix}",
                        "source": "eirgrid",
                        "ts": group["ts"],
                        "value": group["value"],
                        "unit": unit,
                        "geo": REGION,
                        "freq": "15T",
                        "revision_date": pulled_at,
                    }
                )
            )

    if not frames:
        print("no rows pulled", flush=True)
        return
    df = pd.concat(frames, ignore_index=True)
    write_ts_long(df, source="eirgrid")
    print(f"wrote {len(df)} rows across {len(frames)} series", flush=True)


if __name__ == "__main__":
    main()
