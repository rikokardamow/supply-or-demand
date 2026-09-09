"""Front-month futures closes from Yahoo Finance, via `yfinance`.

**Why this exists.** Every other real futures source in this package has stopped: EIA's
`petroleum/pri/fut` was discontinued on 2024-04-05, the Barchart curve is a single
reconstructed snapshot, and IBKR needs a Gateway nobody is running. That left the lake
with no current futures price at all. Yahoo is free, keyless and covers all five roots
this project already tracks, so it closes the gap for the *front month* -- and only the
front month. It is not a curve source: Yahoo's individual contract symbols are patchy,
and `serving.curve_settles`/Spec 18's curve analytics still need IBKR or a Barchart drop.

**`close`, not `settle` -- measured, not assumed.** Yahoo publishes a daily bar whose
close is the last trade, which is *nearly* but not actually the exchange settlement.
Compared live on 2026-09-09 against the 5,915 overlapping days of EIA's own
`fut.cl.f01.settle` (2000-08-23 to 2024-04-05): 96.4% agree within one cent and the mean
absolute difference is 0.27 cents, but only 3.6% match exactly, 0.49% differ by more than
ten cents, and the worst day differs by $1.50 -- 2001-09-14, the week the market reopened
after 11 September, exactly the sort of disorderly session where a last trade and a
settlement part company.

So these are two different quantities and must not share a series id. Writing Yahoo's
close as `.settle` would put two conflicting values under the same `(series_id, ts)` for
24 overlapping years, which any reader concatenating sources would silently pick between.
The suffix is `.close`, and `source="yfinance"` records the provenance -- the same
"different things get different ids" rule that keeps `hu` and `rb` separate roots.

`yfinance` is an unofficial client for an undocumented Yahoo endpoint: it has no SLA and
breaks when Yahoo changes shape. Treat a failure here as expected maintenance, not an
incident, and never as a reason to fall back to stale numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

import pandas as pd

SOURCE: Final = "yfinance"


@dataclass(frozen=True)
class YahooFuture:
    """One Yahoo continuous front-month symbol and the lake series it becomes."""

    symbol: str
    root: str
    unit: str
    geo: str


# The five roots this project already tracks, mapped onto Yahoo's own continuous
# front-month symbols. `lco` is Brent: Yahoo's `BZ=F` is ICE Brent, matching the root
# `pipelines/futures/contract_specs.csv` already defines. Units follow the lake's
# existing `fut.*` convention exactly (confirmed live against the EIA-sourced rows:
# cl -> USD/bbl, ho/rb -> USD/gal), so a chart axis can label them unchanged.
YAHOO_FUTURES: Final[tuple[YahooFuture, ...]] = (
    YahooFuture("CL=F", "cl", "USD/bbl", "US"),
    YahooFuture("BZ=F", "lco", "USD/bbl", "GB"),
    YahooFuture("NG=F", "ng", "USD/MMBtu", "US"),
    YahooFuture("HO=F", "ho", "USD/gal", "PADD1"),
    YahooFuture("RB=F", "rb", "USD/gal", "PADD1"),
)


def series_id(root: str) -> str:
    """`fut.<root>.f01.close` -- front month, a close rather than a settlement."""
    return f"fut.{root}.f01.close"


def history_to_ts_long(history: pd.DataFrame, future: YahooFuture) -> pd.DataFrame:
    """One Yahoo OHLCV frame (a DatetimeIndex and a `Close` column) as `ts_long` rows.

    Rows with no close are dropped rather than carried as zero or filled -- a holiday or
    a halted session is an absence, not a price of nothing.
    """
    if history.empty or "Close" not in history.columns:
        return pd.DataFrame(
            columns=["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]
        )

    ts = pd.to_datetime(history.index)
    # Yahoo returns exchange-local timestamps; the lake stores naive dates, and a
    # futures close belongs to its trade date, not to an instant.
    if ts.tz is not None:
        ts = ts.tz_localize(None)

    frame = pd.DataFrame({"ts": ts.normalize(), "value": history["Close"].to_numpy()})
    frame = frame.dropna(subset=["value"])
    frame["series_id"] = series_id(future.root)
    frame["source"] = SOURCE
    frame["unit"] = future.unit
    frame["geo"] = future.geo
    frame["freq"] = "D"
    # Yahoo exposes no per-row vintage, so this is ingestion time -- the same convention
    # pipelines/eia/CLAUDE.md documents for the EIA client, for the same reason.
    frame["revision_date"] = datetime.now(UTC).replace(tzinfo=None)
    frame["value"] = frame["value"].astype("float64")
    return frame[
        ["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]
    ].reset_index(drop=True)
