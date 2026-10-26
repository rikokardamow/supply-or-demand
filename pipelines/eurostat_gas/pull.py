"""Entrypoint: EU-27 monthly gas balance and trade by partner from Eurostat into the lake.

    python -m pipelines.eurostat_gas.pull

Writes ``ts_long`` under ``source="eurostat_gas"``, monthly:

- ``estat.gas.balance.<line>.<geo>``: balance line in million m3 (``mcm``), for ``eu`` and
  each member state (``de``, ``el``...). Eurostat leaves the EU-27 total blank whenever a
  member's cell is missing, so the members are kept to rebuild it (see
  ``core.eu_gas_balance.fill_from_members``).
- ``estat.gas.balance_tj.<line>.eu``: the same line in TJ on a gross calorific basis.
  It is kept so the balance can be compared with GIE storage, which reports TWh.
- ``estat.gas.<imports|exports>.<gas|lng>.<partner>.eu``: trade by partner, in mcm.
  ``gas`` is ALL natural gas, LNG included. ``lng`` is the LNG part only.

``<line>`` and ``<partner>`` are Eurostat's own codes, lower-cased (``ic_obs``, ``no``,
``nsp``). Full history every run: the datasets are small, and Eurostat revises recent months.
Each dataset fails on its own; one failure never aborts the others.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import requests
from core.failures import fails_loudly, record_failure
from core.storage import write_ts_long

from pipelines.eurostat_gas.client import (
    BALANCE,
    EU_GEO,
    EXPORTS,
    IMPORTS,
    MEMBER_GEOS,
    EurostatGasClient,
)

SOURCE = "eurostat_gas"
_PRODUCT = {"G3000": "gas", "G3200": "lng"}
_FLOW = {IMPORTS: "imports", EXPORTS: "exports"}
_UNITS = {"MIO_M3": ("balance", "mcm"), "TJ_GCV": ("balance_tj", "TJ GCV")}


def _geo(frame: pd.DataFrame) -> pd.Series:
    return frame["geo"].replace({EU_GEO: "EU"})


def _ts_long(
    frame: pd.DataFrame, series_id: pd.Series, unit: str, ingested_at: pd.Timestamp
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": series_id,
            "source": SOURCE,
            "ts": pd.to_datetime(frame["time"]),
            "value": frame["value"].astype("float64"),
            "unit": unit,
            "geo": _geo(frame),
            "freq": "M",
            "revision_date": ingested_at,
        }
    )


def balance_rows(
    frame: pd.DataFrame, eurostat_unit: str, ingested_at: pd.Timestamp
) -> pd.DataFrame:
    prefix, unit = _UNITS[eurostat_unit]
    ids = f"estat.gas.{prefix}." + frame["nrg_bal"].str.lower() + "." + _geo(frame).str.lower()
    return _ts_long(frame, ids, unit, ingested_at)


def trade_rows(frame: pd.DataFrame, dataset: str, ingested_at: pd.Timestamp) -> pd.DataFrame:
    frame = frame[frame["siec"].isin(_PRODUCT)]
    ids = (
        f"estat.gas.{_FLOW[dataset]}."
        + frame["siec"].map(_PRODUCT)
        + "."
        + frame["partner"].str.lower()
        + ".eu"
    )
    return _ts_long(frame, ids, "mcm", ingested_at)


@fails_loudly("eurostat_gas")
def main() -> None:
    client = EurostatGasClient()
    ingested_at = pd.Timestamp(datetime.now(UTC)).tz_localize(None)
    frames: list[pd.DataFrame] = []

    balance_geos = {"MIO_M3": [EU_GEO, *MEMBER_GEOS], "TJ_GCV": [EU_GEO]}
    for eurostat_unit, geos in balance_geos.items():
        try:
            frame = client.balance(eurostat_unit, geo=geos)
            frames.append(balance_rows(frame, eurostat_unit, ingested_at))
        except (requests.RequestException, ValueError, KeyError) as exc:
            record_failure(f"eurostat_gas {BALANCE} {eurostat_unit}", exc)

    for dataset in (IMPORTS, EXPORTS):
        try:
            frames.append(trade_rows(client.trade(dataset), dataset, ingested_at))
        except (requests.RequestException, ValueError, KeyError) as exc:
            record_failure(f"eurostat_gas {dataset}", exc)

    frames = [f for f in frames if not f.empty]
    if not frames:
        record_failure("eurostat_gas", RuntimeError("no dataset returned any row"))
        return
    rows = pd.concat(frames, ignore_index=True)
    write_ts_long(rows, source=SOURCE)
    print(
        f"eurostat_gas: wrote {len(rows)} rows across {rows['series_id'].nunique()} series, "
        f"{rows['ts'].min():%Y-%m} to {rows['ts'].max():%Y-%m}",
        flush=True,
    )


if __name__ == "__main__":
    main()
