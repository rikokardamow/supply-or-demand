"""Parse an archived IBKR MCP curve capture into lake rows.

The connector is an MCP tool, not a Python library, so nothing here fetches anything:
the capture is archived by an agent session under data/raw/ibkr/ and this module parses
it. See docs/superpowers/specs/2026-10-10-ibkr-curve-design.md.

Prices from this source are LAST TRADE, not exchange settlement -- the response reports
its own price source as "Last". Series are therefore `.close`, never `.settle`. See
pipelines/futures/CLAUDE.md for what that difference is worth, measured.
"""

from __future__ import annotations

import re
from typing import Any, Final

import pandas as pd

MONTH_CODES: Final[dict[int, str]] = {
    1: "f", 2: "g", 3: "h", 4: "j", 5: "k", 6: "m",
    7: "n", 8: "q", 9: "u", 10: "v", 11: "x", 12: "z",
}
"""Standard exchange delivery-month letters, January to December."""

_MONTH_RE: Final = re.compile(r"\d{6}")


def contract_code_from_month(contract_month: str) -> str:
    """IBKR's `contract_month` ("202612") -> this lake's contract code ("z2026").

    The year is deliberately four digits. A two-digit year collides with the nearby-rank
    namespace (January is "f", so "f27" is indistinguishable from rank 27) -- see
    client.looks_like_rank_code, which this module's callers assert against.
    """
    if not _MONTH_RE.fullmatch(contract_month):
        raise ValueError(f"contract_month must be YYYYMM, got {contract_month!r}")
    year = int(contract_month[:4])
    month = int(contract_month[4:])
    if month not in MONTH_CODES:
        raise ValueError(f"contract_month names no real month: {contract_month!r}")
    return f"{MONTH_CODES[month]}{year}"


_BAR_COLUMNS: Final = ["ts", "open", "high", "low", "close", "volume"]

REJECTION_REASONS: Final[tuple[str, ...]] = (
    "no_close",
    "non_positive_close",
    "stale_print",
    "zero_volume",
)
"""Why a bar was refused, in the precedence it is tested in -- most specific first, so a
rejected bar is counted exactly once. A zero-volume bar whose open, high, low and close are
all equal is a `stale_print`, which is the more informative of the two reasons."""


def bars_from_history(history: dict[str, Any]) -> pd.DataFrame:
    """A get_price_history response's parallel arrays -> one row per bar.

    `time` is stamped at the session open (13:30Z for NYMEX daily bars); the lake's daily
    convention is the plain date, so it is normalised to midnight. Every other daily series
    in this project does the same.
    """
    times = history.get("time") or []
    if not times:
        return pd.DataFrame({column: pd.Series(dtype="float64") for column in _BAR_COLUMNS}).assign(
            ts=pd.Series(dtype="datetime64[ns]")
        )[_BAR_COLUMNS]

    frame = pd.DataFrame(
        {
            "ts": pd.to_datetime(times, utc=True).tz_localize(None).normalize(),
            "open": pd.to_numeric(history.get("open", []), errors="coerce"),
            "high": pd.to_numeric(history.get("high", []), errors="coerce"),
            "low": pd.to_numeric(history.get("low", []), errors="coerce"),
            "close": pd.to_numeric(history.get("close", []), errors="coerce"),
            "volume": pd.to_numeric(history.get("volume", []), errors="coerce"),
        }
    )
    return frame.astype({column: "float64" for column in _BAR_COLUMNS if column != "ts"})


def liquid_bars(bars: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Keep only bars that record a real trade; count and return the rest by reason.

    A bar with no volume is a carried reference price, not a market. Once in the lake it is
    indistinguishable from a real observation, and every spread, convexity and regime value
    downstream inherits it while every test still passes. 00_TRADING_CONVENTIONS.md's
    "degenerate inputs fail loudly" rule: reject, count, report -- never fill, never zero.
    """
    rejected = dict.fromkeys(REJECTION_REASONS, 0)
    if bars.empty:
        return bars, rejected

    no_close = bars["close"].isna()
    non_positive = ~no_close & (bars["close"] <= 0)
    flat = (
        bars[["open", "high", "low", "close"]].nunique(axis=1).eq(1) & bars["volume"].eq(0)
    )
    stale = ~no_close & ~non_positive & flat
    zero_volume = ~no_close & ~non_positive & ~stale & bars["volume"].eq(0)

    rejected["no_close"] = int(no_close.sum())
    rejected["non_positive_close"] = int(non_positive.sum())
    rejected["stale_print"] = int(stale.sum())
    rejected["zero_volume"] = int(zero_volume.sum())

    keep = ~(no_close | non_positive | stale | zero_volume)
    return bars[keep].reset_index(drop=True), rejected
