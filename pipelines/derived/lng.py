"""Atlantic LNG: US exports by destination, Europe's imports by origin, both sides compared.

    python -m pipelines.derived.lng
    (after pipelines.eia.pull_lng_exports, pipelines.eurostat_gas.pull, pipelines.desnz_gas.pull)

Series written (``source="derived"``, monthly, bcm):

- ``derived.lng.us_exports.<region>.observed``: ``core.lng_balance.REGIONS``, geo US
- ``derived.lng.europe_imports.<origin>.observed``: EU-27 and UK LNG imports from outside
  Europe, by origin, geo EU+UK
- ``derived.lng.mirror_<eu|uk>.<us_reported|europe_reported>.observed``: the same US cargoes
  as each side's statistics record them

Observed only. A projection waits for Asian demand (JODI-Gas needs an account). Read through
``pipelines.derived.eu_gas_balance.latest_run``. Not scheduled.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from core import eu_gas_balance as egb
from core import lng_balance as lb
from core.failures import fails_loudly, record_failure
from core.storage import read_ts_long, write_ts_long

from pipelines.derived.eu_gas_balance import read_trade as read_eu_trade
from pipelines.derived.uk_gas_balance import read_trade as read_uk_trade

DESTINATIONS_CSV = Path(__file__).parent / "lng" / "destinations.csv"
_PREFIX = "derived.lng"


def read_us_exports() -> pd.DataFrame:
    rows = read_ts_long(series_prefix="eia.lng.", source="eia")
    rows = rows.sort_values("revision_date").drop_duplicates(["series_id", "ts"], keep="last")
    parts = rows["series_id"].str.split(".")
    return pd.DataFrame(
        {"kind": parts.str[2], "destination": parts.str[3], "ts": rows["ts"],
         "value": rows["value"]}
    )  # fmt: skip


def _rows(table: pd.DataFrame, kind: str, geo: str, at: pd.Timestamp) -> pd.DataFrame:
    long = table.rename_axis("ts").reset_index().melt(id_vars="ts", var_name="name").dropna()
    return pd.DataFrame(
        {
            "series_id": f"{_PREFIX}.{kind}." + long["name"].astype(str) + ".observed",
            "source": "derived",
            "ts": long["ts"],
            "value": long["value"].astype("float64") / 1000,  # mcm -> bcm
            "unit": "bcm",
            "geo": geo,
            "freq": "M",
            "revision_date": at,
        }
    )


def build_rows(
    us_exports: pd.DataFrame,
    eu_trade: pd.DataFrame,
    uk_trade: pd.DataFrame,
    destinations: pd.DataFrame,
    at: pd.Timestamp,
) -> pd.DataFrame:
    region = lb.us_exports_by(us_exports, destinations, "region")
    bloc = lb.us_exports_by(us_exports, destinations, "bloc")
    months = egb.complete_months(eu_trade)
    eu_lng = eu_trade[
        (eu_trade["product"] == "lng") & (eu_trade["flow"] == "imports")
        & eu_trade["ts"].isin(months)
    ]  # fmt: skip
    uk_lng = uk_trade[(uk_trade["flow"] == "imports") & (uk_trade["type"] == "lng")]
    europe = lb.europe_lng_imports(
        eu_lng[["partner", "ts", "value"]], uk_lng[["country", "ts", "value"]]
    )
    frames = [
        _rows(region, "us_exports", "US", at),
        _rows(europe, "europe_imports", "EU+UK", at),
    ]
    for name, us_side, europe_side in (
        ("eu", bloc.get("eu"), eu_lng[eu_lng["partner"] == "us"].groupby("ts")["value"].sum()),
        ("uk", bloc.get("uk"), uk_lng[uk_lng["country"] == "usa"].groupby("ts")["value"].sum()),
    ):
        if us_side is not None:
            mirror = lb.mirror(us_side, europe_side)[["us_reported", "europe_reported"]]
            frames.append(_rows(mirror, f"mirror_{name}", name.upper(), at))
    return pd.concat(frames, ignore_index=True)


@fails_loudly("derived.lng")
def main() -> None:
    us, eu, uk = read_us_exports(), read_eu_trade(), read_uk_trade()
    if us.empty or eu.empty or uk.empty:
        record_failure(
            "derived.lng",
            RuntimeError(
                "missing inputs: run pipelines.eia.pull_lng_exports, pipelines.eurostat_gas.pull "
                "and pipelines.desnz_gas.pull"
            ),
        )
        return
    rows = build_rows(
        us, eu, uk, pd.read_csv(DESTINATIONS_CSV), pd.Timestamp(datetime.now(UTC)).tz_localize(None)
    )
    write_ts_long(rows, source="derived")
    print(
        f"derived.lng: wrote {len(rows)} rows across {rows['series_id'].nunique()} series, "
        f"{rows['ts'].min():%Y-%m} to {rows['ts'].max():%Y-%m}",
        flush=True,
    )


if __name__ == "__main__":
    main()
