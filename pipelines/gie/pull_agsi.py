"""Pull AGSI+ daily storage history (2018-present) for the top 5 EU storage countries by
working gas volume: DE, IT, NL, FR, AT (see pipelines/gie/NOTES.md for how these were
picked). ~530 paginated requests total, paced to be considerate of GIE's rate limit."""

from __future__ import annotations

import time
from datetime import date

import pandas as pd
from core.storage import write_ts_long

from pipelines.gie.client import GIEClient

COUNTRIES = ["DE", "IT", "NL", "FR", "AT"]
START = date(2018, 1, 1)
COUNTRY_PACING_SECONDS = 1.0


def main() -> None:
    client = GIEClient()
    end = date.today()

    frames = []
    for i, country in enumerate(COUNTRIES):
        frames.append(client.get_agsi_history(country, START, end))
        if i < len(COUNTRIES) - 1:
            time.sleep(COUNTRY_PACING_SECONDS)

    df = pd.concat(frames, ignore_index=True)
    write_ts_long(df, source="gie")
    print(f"wrote {len(df)} rows across {len(COUNTRIES)} countries")


if __name__ == "__main__":
    main()
