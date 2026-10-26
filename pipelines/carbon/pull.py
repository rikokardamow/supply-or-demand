"""Entrypoint: EEX EU ETS primary auctions and Union Registry totals into the lake.

    python -m pipelines.carbon.pull

EEX (``source="eex"``, ``geo="EU"``, one row per auction day):

- ``eex.<eua|euaa>.auction.<metric>``: ``price`` (€/t, the auction clearing price, NOT a market
  price), ``volume`` and ``bids_volume`` (t), ``cover_ratio``, ``bidders``, ``revenue`` (€).
  ``eua`` is contract T3PA (general allowances), ``euaa`` is EAA3 (aviation; none after 2024).
- ``eex.<eua|euaa>.auction.cancelled``: 1 on a day whose auction was cancelled (no price).

Union Registry (``source="eu_registry"``, annual, ts = 1 January of the compliance year):

- ``eu_ets.<metric>.<sector>.<registry>``: ``verified_emissions`` and ``free_allocation`` in
  tonnes, ``reporting`` as a count of accounts, plus ``allocation_feets`` and
  ``allocation_byiceland`` (undocumented families, kept apart). Sector: ``combustion``,
  ``industry``, ``aviation``, ``maritime``. Registry: lower-case code (``de``, ``gb``, ``xi``).

Both are pulled in full every run. EEX: every year from 2020 that EEX has published.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import requests
from core.failures import fails_loudly, record_failure
from core.storage import write_ts_long

from pipelines.carbon.client import FIRST_EEX_YEAR, CarbonClient, parse_eex, parse_registry

_PRODUCT = {"T3PA": "eua", "EAA3": "euaa"}
_EEX_UNITS = {"price": "EUR/t", "volume": "t", "bids_volume": "t", "cover_ratio": "ratio",
              "bidders": "count", "revenue": "EUR"}  # fmt: skip


def _frame(ids, ts, values, unit, geo, freq, source, at) -> pd.DataFrame:  # type: ignore[no-untyped-def]
    return pd.DataFrame(
        {"series_id": ids, "source": source, "ts": ts, "value": values, "unit": unit,
         "geo": geo, "freq": freq, "revision_date": at}
    )  # fmt: skip


def eex_rows(auctions: pd.DataFrame, at: pd.Timestamp) -> pd.DataFrame:
    """Successful auctions give one row per metric. A cancelled one gives only its flag."""
    known = auctions[auctions["contract"].isin(_PRODUCT)]
    product = known["contract"].map(_PRODUCT)
    ok = known["status"].astype(str).str.lower() == "successful"
    frames = []
    for metric, unit in _EEX_UNITS.items():
        part = known[ok & known[metric].notna()]
        frames.append(
            _frame("eex." + product[part.index] + f".auction.{metric}", part["date"],
                   part[metric].astype("float64"), unit, "EU", "D", "eex", at)
        )  # fmt: skip
    cancelled = known[~ok]
    frames.append(
        _frame("eex." + product[cancelled.index] + ".auction.cancelled", cancelled["date"],
               1.0, "flag", "EU", "D", "eex", at)
    )  # fmt: skip
    return pd.concat(frames, ignore_index=True)


def registry_rows(totals: pd.DataFrame, at: pd.Timestamp) -> pd.DataFrame:
    unit = totals["metric"].map(lambda m: "count" if m == "reporting" else "t")
    ids = ("eu_ets." + totals["metric"] + "." + totals["sector"] + "."
           + totals["registry"].str.lower())  # fmt: skip
    ts = pd.to_datetime(totals["year"].astype(str) + "-01-01")
    return _frame(ids, ts, totals["value"].astype("float64"), unit,
                  totals["registry"].str.upper(), "A", "eu_registry", at)  # fmt: skip


@fails_loudly("carbon")
def main() -> None:
    client = CarbonClient()
    at = pd.Timestamp(datetime.now(UTC)).tz_localize(None)

    auctions = []
    for year in range(FIRST_EEX_YEAR, at.year + 1):
        try:
            content = client.eex_report(year)
        except requests.RequestException as exc:
            record_failure(f"carbon eex {year}", exc)
            continue
        if content is None:
            continue  # not published (yet)
        try:
            auctions.append(parse_eex(content))
        except (ValueError, StopIteration) as exc:
            record_failure(f"carbon eex {year} parse", exc)
    if auctions:
        rows = eex_rows(pd.concat(auctions, ignore_index=True), at)
        write_ts_long(rows, source="eex")
        print(f"eex: wrote {len(rows)} rows, {rows['ts'].min():%Y-%m-%d} to "
              f"{rows['ts'].max():%Y-%m-%d}", flush=True)  # fmt: skip
    else:
        record_failure("carbon eex", RuntimeError("no EEX year parsed"))

    try:
        year, url = client.registry_link()
        totals = parse_registry(client.registry_file(url))
    except (requests.RequestException, ValueError, KeyError) as exc:
        record_failure("carbon registry", exc)
        return
    rows = registry_rows(totals, at)
    write_ts_long(rows, source="eu_registry")
    print(f"eu_registry: wrote {len(rows)} rows from verified_emissions_{year}_en.xlsx",
          flush=True)  # fmt: skip


if __name__ == "__main__":
    main()
