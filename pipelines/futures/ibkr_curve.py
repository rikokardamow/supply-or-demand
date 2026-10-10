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
from datetime import datetime
from typing import Any, Final

import pandas as pd
from core.schemas import TS_LONG_SCHEMA

from pipelines.futures.client import ContractMeta, looks_like_rank_code
from pipelines.futures.series_meta import ROLL_RULE

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


def _required_array(history: dict[str, Any], key: str) -> Any:
    """Fetch a required OHLCV array from a history response, or raise naming it.

    A response that carries `time` but omits one of the OHLCV keys entirely is a
    malformed capture, not an absent reading -- 00_TRADING_CONVENTIONS.md's "degenerate
    inputs fail loudly" rule argues for naming the gap here rather than silently filling
    a fabricated NaN column (a fill is exactly what that rule forbids), or letting it
    surface downstream as an opaque pandas "All arrays must be of the same length" error.
    """
    value = history.get(key)
    if value is None:
        raise ValueError(f"get_price_history response has no {key!r} array")
    return value


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
            "open": pd.to_numeric(_required_array(history, "open"), errors="coerce"),
            "high": pd.to_numeric(_required_array(history, "high"), errors="coerce"),
            "low": pd.to_numeric(_required_array(history, "low"), errors="coerce"),
            "close": pd.to_numeric(_required_array(history, "close"), errors="coerce"),
            "volume": pd.to_numeric(_required_array(history, "volume"), errors="coerce"),
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


_METRICS: Final[tuple[str, ...]] = ("close", "volume")
"""No `oi`. The connector was asked for `future_open_interest` on three contracts and
returned it on none; absent is not zero."""


def closes_to_ts_long(
    bars_by_contract: dict[str, pd.DataFrame],
    root: str,
    revision_date: pd.Timestamp,
    contracts: list[ContractMeta],
    source: str,
) -> pd.DataFrame:
    """Per-contract liquid bars -> `ts_long` rows at `fut.<root>.<contract>.close/.volume`.

    `source` is passed explicitly, never hardcoded: the DataFrame's own `source` column is a
    real parquet value that every read filters on, and a shared transform that hardcodes it
    misclassifies rows on read-back.
    """
    ambiguous = sorted(code for code in bars_by_contract if looks_like_rank_code(code))
    if ambiguous:
        raise ValueError(
            f"contract codes collide with the nearby-rank namespace f01..f36: {ambiguous}. "
            f"Use a four-digit year (e.g. 'f2027', not 'f27')."
        )

    unit_by_contract = {
        meta.contract: f"{meta.currency}/{meta.contract_unit}" for meta in contracts
    }

    frames: list[pd.DataFrame] = []
    for contract, bars in sorted(bars_by_contract.items()):
        if bars.empty:
            continue
        for metric in _METRICS:
            values = pd.to_numeric(bars[metric], errors="coerce").dropna()
            if values.empty:
                continue
            frames.append(
                pd.DataFrame(
                    {
                        "series_id": f"fut.{root}.{contract}.{metric}",
                        "source": source,
                        "ts": bars.loc[values.index, "ts"],
                        "value": values.astype("float64"),
                        "unit": (
                            unit_by_contract.get(contract, "unknown")
                            if metric == "close"
                            else "contracts"
                        ),
                        "geo": root.upper(),
                        "freq": "D",
                        "revision_date": revision_date,
                    }
                )
            )

    if not frames:
        empty: pd.DataFrame = TS_LONG_SCHEMA.empty_table().to_pandas()
        return empty
    return pd.concat(frames, ignore_index=True)


def contracts_from_ladder(
    ladder: list[dict[str, Any]], root: str, specs: pd.DataFrame
) -> list[ContractMeta]:
    """A capture's ladder rows -> ContractMeta, sorted by delivery month.

    `symbol` is deliberately ignored: the connector's own documentation says it must not be
    surfaced, and the contract code is derived from `contract_month` instead.
    """
    spec = specs[specs["root"] == root]
    if spec.empty:
        raise ValueError(f"no contract_specs.csv row for root {root!r}")
    row = spec.iloc[0]

    contracts = [
        ContractMeta(
            root=root,
            contract=contract_code_from_month(str(entry["contract_month"])),
            expiry=datetime.strptime(str(entry["last_trading_date"]), "%Y%m%d").date(),
            tick_size=float(row["tick_size"]),
            contract_unit=str(row["contract_unit"]),
            currency=str(row["currency"]),
        )
        for entry in ladder
    ]
    return sorted(contracts, key=lambda meta: meta.expiry)


def series_meta_rows(contracts: list[ContractMeta], source: str) -> pd.DataFrame:
    """ContractMeta -> rows for series_meta.parquet. Its de-dup key is (root, contract)
    without source, so a real exchange expiry here replaces an earlier NULL one."""
    return pd.DataFrame(
        {
            "root": [meta.root for meta in contracts],
            "contract": [meta.contract for meta in contracts],
            "expiry": [meta.expiry for meta in contracts],
            "tick_size": [meta.tick_size for meta in contracts],
            "contract_unit": [meta.contract_unit for meta in contracts],
            "currency": [meta.currency for meta in contracts],
            "roll_rule": ROLL_RULE,
            "source": source,
        }
    )


def parse_envelope(
    envelope: dict[str, Any], specs: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict[str, int]]]:
    """An archived capture -> (ts_long rows, series_meta rows, rejections by contract).

    `revision_date` is the capture's own `captured_at`, so re-parsing the same archive is
    idempotent under write_ts_long's (series_id, ts) de-dup and a later capture supersedes
    an earlier one.
    """
    root = str(envelope["root"])
    revision_date = pd.Timestamp(str(envelope["captured_at"])).tz_localize(None)
    ladder = list(envelope.get("ladder") or [])
    contracts = contracts_from_ladder(ladder, root=root, specs=specs)

    code_by_id = {
        str(entry["contract_id"]): contract_code_from_month(str(entry["contract_month"]))
        for entry in ladder
    }

    bars_by_contract: dict[str, pd.DataFrame] = {}
    rejections: dict[str, dict[str, int]] = {}
    for contract_id, history in (envelope.get("history") or {}).items():
        code = code_by_id.get(str(contract_id))
        if code is None:
            raise ValueError(
                f"history carries contract_id {contract_id!r} absent from the ladder"
            )
        kept, rejected = liquid_bars(bars_from_history(history or {}))
        rejections[code] = rejected
        if not kept.empty:
            bars_by_contract[code] = kept

    rows = closes_to_ts_long(
        bars_by_contract,
        root=root,
        revision_date=revision_date,
        contracts=contracts,
        source="ibkr",
    )
    return rows, series_meta_rows(contracts, source="ibkr"), rejections
