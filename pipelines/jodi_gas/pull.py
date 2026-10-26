"""Entrypoint: JODI-Gas monthly flows for every reporting country into the lake.

    python -m pipelines.jodi_gas.pull

Writes ``ts_long`` under ``source="jodi_gas"``, monthly, in mcm (JODI unit ``M3``):
``jodi_gas.<flow>.<country>`` for each of ``FLOWS``, ``geo`` = the JODI country code.
LNG imports and exports are ``implng`` / ``explng``. Needs ``JODI_USERNAME`` /
``JODI_PASSWORD`` in ``.env``. Full history from ``FIRST_MONTH`` every run, because JODI
revises recent months and the whole pull is a few requests.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import requests
from core.failures import fails_loudly, record_failure
from core.storage import write_ts_long

from pipelines.jodi_gas.client import JodiGasClient

SOURCE = "jodi_gas"
FIRST_MONTH = "2010-01"
# LNG and pipeline trade, production and gross inland deliveries: the LNG model uses the
# first two; the rest cost nothing extra and serve later gas work.
FLOWS = ("IMPLNG", "EXPLNG", "IMPPIP", "EXPPIP", "INDPROD", "TOTDEMO")


def to_rows(frame: pd.DataFrame, at: pd.Timestamp) -> pd.DataFrame:
    """API rows -> ts_long. Only unit ``M3`` (million m3) and product ``NATGAS``. A null
    quantity gives no row."""
    frame = frame[(frame["unit"] == "M3") & (frame["product"] == "NATGAS")]
    frame = frame.dropna(subset=["quantity"])
    return pd.DataFrame(
        {
            "series_id": "jodi_gas."
            + frame["flow"].str.lower()
            + "."
            + frame["country"].str.lower(),
            "source": SOURCE,
            "ts": pd.to_datetime(frame["date"] + "-01"),
            "value": frame["quantity"].astype("float64"),
            "unit": "mcm",
            "geo": frame["country"],
            "freq": "M",
            "revision_date": at,
        }
    )


@fails_loudly("jodi_gas")
def main() -> None:
    at = pd.Timestamp(datetime.now(UTC)).tz_localize(None)
    try:
        client = JodiGasClient()
        frame = client.gas_data(
            products="NATGAS", flows=",".join(FLOWS), units="M3",
            dateFrom=FIRST_MONTH, dateTo=f"{at:%Y-%m}",
        )  # fmt: skip
    except (requests.RequestException, ValueError, KeyError) as exc:
        record_failure("jodi_gas", exc)
        return
    rows = to_rows(frame, at)
    if rows.empty:
        record_failure("jodi_gas", RuntimeError("no rows returned"))
        return
    write_ts_long(rows, source=SOURCE)
    print(
        f"jodi_gas: wrote {len(rows)} rows, {rows['geo'].nunique()} countries, "
        f"{rows['ts'].min():%Y-%m} to {rows['ts'].max():%Y-%m}",
        flush=True,
    )


if __name__ == "__main__":
    main()
