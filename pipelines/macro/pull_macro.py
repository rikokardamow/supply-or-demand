"""Entrypoint: pulls all 38 FRED series (fred_series.py::FRED_SERIES), Frankfurter FX
rates (EUR/GBP/TRY vs USD), and Eurostat's ESI (EU/DE/FR/IT/ES/IE) into the lake.

Per-series/per-currency/per-geo resilience, not just per-request retry -- matches
pipelines/entsoe/pull_actuals.py's precedent: one flaky item must never abort the rest
of the pull. Full-history pulls are cheap here (the largest series, DGS10, is ~16,870
daily points), so there's no backfill-vs-daily split needed -- this script doubles as
its own daily-safe entrypoint, same reasoning as pipelines/news/pull_news.py."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
import requests
from core.failures import fails_loudly, record_failure
from core.storage import write_ts_long

from pipelines.macro.eurostat_client import EurostatESIClient
from pipelines.macro.frankfurter_client import FrankfurterClient
from pipelines.macro.fred_client import FREDClient
from pipelines.macro.fred_series import FRED_SERIES

FX_SYMBOLS = ["EUR", "GBP", "TRY"]
FX_HISTORY_START = date(2018, 1, 1)
ESI_UNIT = "Index"


def pull_fred(client: FREDClient, ingested_at: pd.Timestamp) -> pd.DataFrame:
    frames = []
    for series_id, meta in FRED_SERIES.items():
        try:
            df = client.get_series(series_id)
        except (ValueError, requests.exceptions.RequestException) as exc:
            # ValueError: fredapi's own response to a bad/retired series id
            # ("Bad Request. The series does not exist."), confirmed live earlier
            # this session -- RequestException covers genuine connectivity failures.
            # One flaky series must never abort the rest of the 38.
            record_failure(f"fred {series_id}", exc)
            continue

        print(f"fred {series_id}: {len(df)} rows", flush=True)
        if df.empty:
            continue
        frames.append(
            pd.DataFrame(
                {
                    "series_id": f"fred.{series_id.lower()}",
                    "source": "fred",
                    "ts": df["ts"],
                    "value": df["value"],
                    "unit": meta.unit,
                    "geo": meta.geo,
                    "freq": meta.freq,
                    "revision_date": ingested_at,
                }
            )
        )

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def pull_fx(client: FrankfurterClient, ingested_at: pd.Timestamp) -> pd.DataFrame:
    try:
        rates = client.get_rates(FX_HISTORY_START, date.today(), FX_SYMBOLS)
    except requests.exceptions.RequestException as exc:
        record_failure("frankfurter fx", exc)
        return pd.DataFrame()

    print(f"frankfurter fx: {len(rates)} rows", flush=True)
    if rates.empty:
        return rates

    return pd.DataFrame(
        {
            "series_id": "fx.usd_" + rates["currency"].str.lower(),
            "source": "frankfurter",
            "ts": rates["ts"],
            "value": rates["rate"],
            "unit": rates["currency"] + " per USD",
            "geo": rates["currency"],
            "freq": "D",
            "revision_date": ingested_at,
        }
    )


def pull_esi(client: EurostatESIClient, ingested_at: pd.Timestamp) -> pd.DataFrame:
    try:
        esi = client.get_esi()
    except requests.exceptions.RequestException as exc:
        record_failure("eurostat esi", exc)
        return pd.DataFrame()

    print(f"eurostat esi: {len(esi)} rows", flush=True)
    if esi.empty:
        return esi

    return pd.DataFrame(
        {
            "series_id": "estat.esi." + esi["geo"],
            "source": "eurostat",
            "ts": esi["ts"],
            "value": esi["value"],
            "unit": ESI_UNIT,
            "geo": esi["geo"],
            "freq": "M",
            "revision_date": ingested_at,
        }
    )


@fails_loudly("macro.pull_macro")
def main() -> None:
    ingested_at = pd.Timestamp(datetime.now(UTC))

    fred_rows = pull_fred(FREDClient(), ingested_at)
    if not fred_rows.empty:
        write_ts_long(fred_rows, source="fred")
        print(f"wrote {len(fred_rows)} FRED rows", flush=True)
    else:
        print("no FRED rows pulled", flush=True)

    fx_rows = pull_fx(FrankfurterClient(), ingested_at)
    if not fx_rows.empty:
        write_ts_long(fx_rows, source="frankfurter")
        print(f"wrote {len(fx_rows)} FX rows", flush=True)
    else:
        print("no FX rows pulled", flush=True)

    esi_rows = pull_esi(EurostatESIClient(), ingested_at)
    if not esi_rows.empty:
        write_ts_long(esi_rows, source="eurostat")
        print(f"wrote {len(esi_rows)} ESI rows", flush=True)
    else:
        print("no ESI rows pulled", flush=True)


if __name__ == "__main__":
    main()
