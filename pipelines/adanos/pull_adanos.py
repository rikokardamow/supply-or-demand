"""Weekly entrypoint: pulls buzz_score/sentiment_score for the curated 57-ticker
basket (tickers.py) across all four platforms (Reddit/X/News/Polymarket) in
batches of <=10 per `/compare` call, plus one Reddit `/trending/sectors` call
filtered to Energy. 57 tickers -> 6 batches/platform x 4 platforms = 24, + 1 =
25 calls/pull -- see specs/17_adanos-sentiment-overlay.md for the full budget
arithmetic (~108 calls/month, 43% of the 250/month free-tier cap).

Per-platform resilience, not just per-request retry -- matches
pipelines/macro/pull_macro.py's established pattern: one flaky platform must never
abort the rest of the pull."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import requests
from core.failures import fails_loudly, record_failure
from core.storage import write_ts_long
from pipelines.adanos.client import AdanosClient
from pipelines.adanos.tickers import COMPARE_BATCH_SIZE, PLATFORMS, TICKERS

BUZZ_UNIT = "score_0_100"
SENTIMENT_UNIT = "score_neg1_to_1"
SECTOR_SERIES_ID = "adanos.reddit.sector_energy.buzz_score"


def _batches(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def pull_platform(client: AdanosClient, platform: str, ingested_at: pd.Timestamp) -> pd.DataFrame:
    tickers = list(TICKERS)
    frames = []
    for batch in _batches(tickers, COMPARE_BATCH_SIZE):
        try:
            df = client.compare(batch, platform)
        except requests.exceptions.RequestException as exc:
            record_failure(f"adanos {platform} compare({batch})", exc)
            continue

        print(
            f"adanos {platform} compare({len(batch)} tickers): "
            f"{len(df)} rows, remaining={client.last_rate_limit_remaining}",
            flush=True,
        )
        # company_name is null for a ticker Adanos doesn't recognise at all --
        # confirmed live even a completely fake ticker returns HTTP 200 with a
        # zeroed row, so this is the real existence filter (see client.py).
        df = df[df["company_name"].notna()]
        if df.empty:
            continue

        rows = []
        for _, row in df.iterrows():
            ticker_lower = str(row["ticker"]).lower()
            geo = TICKERS.get(row["ticker"], "US")
            rows.append(
                {
                    "series_id": f"adanos.{platform}.{ticker_lower}.buzz_score",
                    "source": "adanos",
                    "ts": ingested_at.normalize(),
                    "value": float(row["buzz_score"]),
                    "unit": BUZZ_UNIT,
                    "geo": geo,
                    "freq": "D",
                    "revision_date": ingested_at,
                }
            )
            # sentiment_score is nullable (confirmed live: null when a ticker has no
            # qualifying directional signal this period) -- ts_long's own `value`
            # column must be a real float, so a null sentiment_score is skipped
            # rather than written as a fabricated 0.0 (which would misleadingly
            # read as "neutral sentiment" instead of "no data").
            if pd.notna(row["sentiment_score"]):
                rows.append(
                    {
                        "series_id": f"adanos.{platform}.{ticker_lower}.sentiment_score",
                        "source": "adanos",
                        "ts": ingested_at.normalize(),
                        "value": float(row["sentiment_score"]),
                        "unit": SENTIMENT_UNIT,
                        "geo": geo,
                        "freq": "D",
                        "revision_date": ingested_at,
                    }
                )
        frames.append(pd.DataFrame(rows))

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def pull_sector_trend(client: AdanosClient, ingested_at: pd.Timestamp) -> pd.DataFrame:
    try:
        sectors = client.trending_sectors(platform="reddit")
    except requests.exceptions.RequestException as exc:
        record_failure("adanos sector trend", exc)
        return pd.DataFrame()

    print(f"adanos sector trend: remaining={client.last_rate_limit_remaining}", flush=True)
    energy_row = sectors[sectors["sector"] == "Energy"]
    if energy_row.empty:
        print("adanos sector trend: no Energy row in response", flush=True)
        return pd.DataFrame()

    return pd.DataFrame(
        [
            {
                "series_id": SECTOR_SERIES_ID,
                "source": "adanos",
                "ts": ingested_at.normalize(),
                "value": float(energy_row.iloc[0]["buzz_score"]),
                "unit": BUZZ_UNIT,
                "geo": "US",
                "freq": "D",
                "revision_date": ingested_at,
            }
        ]
    )


@fails_loudly("adanos.pull_adanos")
def main() -> None:
    ingested_at = pd.Timestamp(datetime.now(UTC))
    client = AdanosClient()

    frames = []
    for platform in PLATFORMS:
        frames.append(pull_platform(client, platform, ingested_at))
    frames.append(pull_sector_trend(client, ingested_at))

    rows = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    if rows.empty:
        print("no Adanos rows pulled", flush=True)
        return

    write_ts_long(rows, source="adanos")
    print(f"wrote {len(rows)} Adanos rows", flush=True)


if __name__ == "__main__":
    main()
