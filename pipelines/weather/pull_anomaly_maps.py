"""Session B entrypoint: fetches the latest IFS 2t forecast and renders the 4 anomaly
maps (EU/CONUS x D+3/D+7). Session C's later pull_daily.py will call this alongside the
HDD/CDD pull; this script stays runnable standalone in the meantime."""

from __future__ import annotations

import pandas as pd

from pipelines.weather.anomaly_maps import render_anomaly_map
from pipelines.weather.climatology_grid import REGION_BOUNDS
from pipelines.weather.ecmwf_client import fetch_2t_forecast, load_2t_dataset


def main() -> None:
    path = fetch_2t_forecast()
    ds = load_2t_dataset(path)
    t2m = ds["t2m"]

    rendered = []
    for region in REGION_BOUNDS:
        for step_index in range(t2m.sizes["step"]):
            step_slice = t2m.isel(step=step_index)
            step_hours = int(step_slice.step.values / pd.Timedelta(hours=1))
            valid_time = pd.Timestamp(step_slice.valid_time.values)
            rendered.append(
                render_anomaly_map(
                    step_slice,
                    step_hours=step_hours,
                    valid_time=valid_time,
                    region=region,
                    model="ecmwf",
                )
            )

    print(f"rendered {len(rendered)} anomaly maps: {[str(p) for p in rendered]}")


if __name__ == "__main__":
    main()
