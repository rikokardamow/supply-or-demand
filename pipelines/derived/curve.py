"""Reads the futures settlement lake, computes nearby ranks/spreads/convexity/regime via
core/curve.py, and writes derived.spread.<root>.*/derived.curve.<root>.* series back.
Registered as a Spec 13 orchestration step (infra/run_scheduled.py's daily cadence group),
run after pipelines.futures.pull_daily -- not GitHub Actions, per the lake-on-laptop
decision. Per-root failure isolation, matching every other pipeline's own pull loop and
pipelines/futures/pull.py::pull_root.

## Rank-based series are only trustworthy from `valid_rank_window` onward (found 2026-10-10)

`core.curve.nearby_panel` ranks whatever contracts are actually present in
`contract_panel` -- f01 is just "nearest expiry among the columns it was given", not
"the real front month". The IBKR MCP connector's `search_futures` returns only
contracts still live at capture time *unless called with `include_expired=true`*, and
the capture behind this lake's real `cl`/`lco` data did not pass it -- it took the
nearest N non-expired contracts as of the capture date. Every contract that was the
true front month at some earlier date, and has since expired, is simply absent from
the panel. Confirmed live: on 2026-04-02 the panel's nearest-expiry contracts were
x2026 (expiry 2026-10-20) and z2026 (2026-11-20) -- the real front month that date
expired in May 2026 and was never captured, so the row written as `f01` that day was
actually a deferred contract, and `derived.spread.cl.s12` was a spread between two
deferred contracts wearing a front-month label. Cross-checked against the lake's own
independent yfinance front-month series: 294 overlapping days, median absolute
difference 2.61, only 0.3% agreeing to within a cent -- these are not the same
instrument.

`valid_rank_window` below is the fix: ranks are only trustworthy from
`min(expiries) - smallest_gap_between_consecutive_expiries` onward, because before that
date a contract nearer than anything the panel holds would have been live and is the
one actually missing. `pull_root` suppresses every rank-based write (`s12`/`s13`/`s16`/
`s1_12`/`s23`/`cv123`/`regime`) before that date and prints the window plus how many
rows were suppressed -- silent truncation is not acceptable here (root CLAUDE.md's
"a degenerate input fails loudly and visibly" rule). Contract-coded series (`dec_dec_*`,
and `fut.<root>.<contract>.close` itself) carry no rank claim at all and are written
over their full real history, unaffected by any of this.

**Do not "simplify" this window away.** The real fix for a future capture that wants
genuine historical ranks is to re-run the IBKR pull with `include_expired=true`, which
would make the panel actually complete back through history and let `valid_rank_window`
naturally widen on its own (a wider, correctly-populated panel has a smaller
min(expiries), and real early contracts, not a code change here). Until a capture does
that, most of a monthly root's rank history is honestly unsupported -- for the current
`cl` panel (earliest expiry 2026-10-20, monthly contracts) that is only the last few
weeks, which is the correct answer, not a bug in this window."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Final, Literal, overload

import pandas as pd
from core.curve import (
    REGIME_CODES,
    convexity,
    curve_regime,
    dec_dec,
    nearby_panel,
    time_spreads,
)
from core.failures import fails_loudly, record_failure
from core.storage import read_ts_long, write_ts_long

from pipelines.futures.client import ROOTS
from pipelines.futures.series_meta import read_series_meta

_SPREAD_COLUMNS = ("s12", "s13", "s16", "s1_12", "s23")


_METRIC_SUFFIXES: Final[tuple[str, ...]] = ("settle", "close")
"""The metric suffixes a futures price series can carry in this lake -- the two series ids
`contract_panel_for` reads per contract (`fut.<root>.<contract>.settle` and `.close`).

Order is the tie-break order, and nothing more: settle first, because an exchange
settlement is the better number where one exists in comparable volume. `.close` is
last-trade data, from sources like the IBKR MCP connector -- see
pipelines/futures/CLAUDE.md for the measured difference between the two.

This was called `_METRICS_BY_PREFERENCE`, and its docstring described a preference order
the code had stopped implementing: the selection sat in a hardcoded
`row["settle"] >= row["close"]`, which would have raised KeyError had an entry been
removed here. `contract_panel_for` now drives the comparison off this tuple (`idxmax`
over the row-count columns, in this order), so the name, the docstring and the code say
the same thing and adding or removing a suffix needs no second edit."""


@overload
def contract_panel_for(
    root: str, meta: pd.DataFrame, return_provenance: Literal[False] = False
) -> tuple[pd.DataFrame, pd.Series]: ...
@overload
def contract_panel_for(
    root: str, meta: pd.DataFrame, return_provenance: Literal[True]
) -> tuple[pd.DataFrame, pd.Series, dict[str, str]]: ...
def contract_panel_for(
    root: str, meta: pd.DataFrame, return_provenance: bool = False
) -> tuple[pd.DataFrame, pd.Series] | tuple[pd.DataFrame, pd.Series, dict[str, str]]:
    """Public (not module-private) so apps/dashboard/pages/18_curve.py can reuse this same
    pivot logic directly, matching pipelines/eia/transforms.py's own "page imports a
    pipeline's transform helper" precedent.

    Reads both `.settle` and `.close` and picks ONE metric per contract -- whichever has
    more rows for that contract, ties going to settle (`_METRIC_SUFFIXES` is both the list
    of suffixes read and the tie-break order). Per contract, never per row: a settlement
    and a last trade are different quantities, and blending them inside one column would
    leave every spread downstream measuring something nobody chose.

    Selection is deliberately NOT "settle if the contract has any settle rows at all" --
    that wording was tried and broken by the real lake. `lco` holds a settle row for all
    ~89 contracts, but exactly ONE row each (2026-09-04, the Barchart reconstruction,
    source="manual"); IBKR's `contract_code_from_month` emits the identical contract-code
    format, so "any settle rows" would resolve every lco contract to that single stale
    settle and silently discard the whole IBKR daily close history, pinning the lco curve
    to one date forever.
    """
    root_meta = meta[meta["root"] == root]
    empty: tuple[pd.DataFrame, pd.Series] = (
        pd.DataFrame(),
        pd.Series(dtype="datetime64[ns]"),
    )
    if root_meta.empty:
        return (*empty, {}) if return_provenance else empty

    contracts = root_meta["contract"].tolist()
    series_ids = [
        f"fut.{root}.{contract}.{metric}"
        for contract in contracts
        for metric in _METRIC_SUFFIXES
    ]
    long_df = read_ts_long(series_ids=series_ids)
    if long_df.empty:
        return (*empty, {}) if return_provenance else empty

    long_df = long_df.copy()
    parts = long_df["series_id"].str.split(".")
    long_df["contract"] = parts.str[2]
    long_df["metric"] = parts.str[3]

    # Row counts per (contract, metric) -- the selection is by volume, not mere presence.
    # `idxmax` returns the FIRST maximum and the columns are in _METRIC_SUFFIXES order, so
    # "more rows wins, ties go to settle" falls out of the tuple itself rather than being
    # restated as a hardcoded comparison between two named metrics.
    counts = long_df.groupby(["contract", "metric"]).size().unstack(fill_value=0)
    counts = counts.reindex(columns=list(_METRIC_SUFFIXES), fill_value=0)
    chosen: dict[str, str] = {
        str(contract): str(row.idxmax()) for contract, row in counts.iterrows()
    }
    picked = long_df[
        [chosen.get(c) == m for c, m in zip(long_df["contract"], long_df["metric"], strict=True)]
    ]

    contract_panel = picked.pivot_table(index="ts", columns="contract", values="value")
    expiries = root_meta.set_index("contract")["expiry"]
    # Only contracts that actually have rows in the lake -- series_meta can list a contract
    # before any real price data for it has landed.
    expiries = expiries.loc[expiries.index.intersection(contract_panel.columns)]
    if return_provenance:
        return contract_panel, expiries, chosen
    return contract_panel, expiries


def valid_rank_window(expiries: pd.Series) -> pd.Timestamp:
    """Earliest date from which `expiries`' own contracts can support a trustworthy
    rank (f01, f02, ...) -- see this module's own docstring for the full story of why
    an IBKR-captured panel needs this at all.

    `expiries` sorted ascending gives the gaps between consecutive contracts actually
    present in the panel; before `min(expiries) - min(gaps)`, a contract that has since
    expired and was never captured would have been nearer than the panel's own
    earliest-expiry contract, so whatever the panel calls f01 on that date is not really
    the front month. Needs at least two contracts to have a gap to measure from at all --
    callers (`pull_root`) already require that before computing a panel.

    **The smallest gap, not the median.** The median was tried first and is unsound for
    any panel that is not evenly spaced: a ladder that is monthly at the front and annual
    behind it (perfectly ordinary once a capture reaches far out, and the direction cl's
    own real panel already leans -- its gaps run min 28 / median 31 / max 63 days) has a
    median gap of roughly a year, which would open the window a year before the panel's
    earliest expiry and declare nearly twelve months of mislabelled f01 rows trustworthy.
    The smallest observed gap is the tightest spacing the panel itself evidences, so it
    errs in the safe direction: the window can only be too narrow, never too wide, and a
    narrow window suppresses real rows rather than publishing wrong ones."""
    if len(expiries) < 2:
        raise ValueError("valid_rank_window needs at least two contracts to measure a gap")
    sorted_expiries = pd.Series(pd.to_datetime(expiries.to_numpy())).sort_values()
    smallest_gap = sorted_expiries.diff().dropna().min()
    return pd.Timestamp(sorted_expiries.iloc[0]) - smallest_gap


def _suppress_before_window(
    series: pd.Series, window_start: pd.Timestamp
) -> tuple[pd.Series, int]:
    """Masks `series` to NaN before `window_start` -- so `_write_derived`'s own
    `dropna()` simply never writes those rows -- and returns how many real values were
    suppressed, for the run output's own "stated, not silent" count."""
    in_window = series.index >= window_start
    suppressed = int((~in_window & series.notna()).sum())
    return series.where(in_window), suppressed


def _determined_regime_codes(regime: pd.DataFrame, s12: pd.Series) -> pd.Series:
    """`REGIME_CODES` values for the rows whose state its inputs actually determine, NaN
    for the rest -- so `_write_derived`'s own `dropna()` simply never writes them.

    `core.curve.curve_regime` classifies with `np.select(..., default="flat")`. Each of
    the six named states comes from a condition over `s12`/`cv`/`s1_12`, and a comparison
    against NaN is False, so a named state can only fire on inputs that are really there.
    The default cannot: a row reaches `"flat"` either on the genuine `s12 == 0` knife edge
    the state was added for, or because nothing could be evaluated at all -- `s12` absent,
    or `cv` absent on a panel with fewer than three ranks. The second kind is not a flat
    curve; it is an unknown one, and publishing it as code 6.0 states a definite market
    structure on a date with no curve to measure. It is also invisible to every NaN guard
    downstream, because 6.0 is an ordinary number: the real lake holds 8 such rows for
    `lco` on dates where `derived.spread.lco.s12` and `derived.curve.lco.cv123` have no
    rows at all.

    Masking here rather than in `core.curve.curve_regime` keeps that module pure and
    unchanged -- which state a classifier returns is its own business; whether a row is
    fit to write into the lake is this package's (see pipelines/derived/CLAUDE.md)."""
    codes = regime["state"].map(REGIME_CODES).astype(float)
    determined = regime["state"].ne("flat") | s12.eq(0.0)
    return codes.where(determined)


def _write_derived(
    root: str, series_id_suffix: str, values: pd.Series, ingested_at: pd.Timestamp
) -> int:
    values = values.dropna()
    if values.empty:
        return 0
    df = pd.DataFrame(
        {
            "series_id": f"derived.{series_id_suffix}",
            "source": "derived",
            "ts": values.index,
            "value": values.to_numpy(dtype=float),
            "unit": "USD",
            "geo": root.upper(),
            "freq": "D",
            "revision_date": ingested_at,
        }
    )
    write_ts_long(df, source="derived")
    return len(df)


def pull_root(root: str, meta: pd.DataFrame, ingested_at: pd.Timestamp) -> int:
    contract_panel, expiries, provenance = contract_panel_for(root, meta, return_provenance=True)
    if contract_panel.empty or len(expiries) < 2:
        print(f"{root}: not enough contracts for a curve yet", flush=True)
        return 0

    # A mixed panel (some contracts settle, some close) blends two different quantities
    # across columns of the same panel -- not within one, but still worth stating in the
    # run output rather than leaving silent. See contract_panel_for's own docstring.
    metric_mix = Counter(provenance.values())
    print(f"{root}: per-contract metric mix {dict(metric_mix)}", flush=True)

    _adjusted, unadj, _roll_dates = nearby_panel(contract_panel, expiries)
    spreads = time_spreads(unadj)
    cv123 = convexity(unadj)
    regime = curve_regime(unadj)
    decs = dec_dec(contract_panel)

    # Rank-based series only -- dec_dec (contract-coded) is written over its full
    # history below, unaffected by any of this. See the module docstring for why this
    # window exists at all.
    window_start = valid_rank_window(expiries)
    # Before the window is applied: a regime row whose own inputs are absent is dropped
    # outright, not suppressed by date -- see _determined_regime_codes.
    regime_codes = _determined_regime_codes(regime, spreads["s12"])
    suppressed = 0
    for col in _SPREAD_COLUMNS:
        spreads[col], col_suppressed = _suppress_before_window(spreads[col], window_start)
        suppressed += col_suppressed
    cv123, cv_suppressed = _suppress_before_window(cv123, window_start)
    regime_codes, regime_suppressed = _suppress_before_window(regime_codes, window_start)
    suppressed += cv_suppressed + regime_suppressed

    total = 0
    for col in _SPREAD_COLUMNS:
        total += _write_derived(root, f"spread.{root}.{col}", spreads[col], ingested_at)
    for col in decs.columns:
        total += _write_derived(root, f"spread.{root}.{col}", decs[col], ingested_at)
    total += _write_derived(root, f"curve.{root}.cv123", cv123, ingested_at)
    total += _write_derived(root, f"curve.{root}.regime", regime_codes, ingested_at)

    print(
        f"{root}: rank series (s12/s13/s16/s1_12/s23/cv123/regime) valid only from "
        f"{window_start.date()} onward -- the panel is missing every contract that "
        f"expired before capture (see module docstring); {suppressed} row(s) before "
        f"that date suppressed, not written. A future IBKR capture with "
        f"include_expired=true would widen this window for real.",
        flush=True,
    )
    print(f"{root}: wrote {total} derived rows", flush=True)
    return total


@fails_loudly("derived.curve")
def main() -> None:
    ingested_at = pd.Timestamp(datetime.now())
    meta = read_series_meta()

    total_rows = 0
    for root in ROOTS:
        try:
            total_rows += pull_root(root, meta, ingested_at)
        except Exception as exc:
            record_failure(f"{root}", exc)

    print(f"derived.curve: {total_rows} total rows written", flush=True)


if __name__ == "__main__":
    main()
