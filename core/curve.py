"""Futures curve structure: roll-adjusted nearby ranks, time spreads, convexity, and a
six-state curve-regime classifier. Never touches DuckDB (root CLAUDE.md rule) -- callers
(pipelines/derived/curve.py) read the lake, call these pure functions, and write the
results back. Every input is a wide DataFrame (index=date, columns=contract code or rank
label) -- see nearby_panel's own docstring for how contract_panel/expiries are built.

Business-day arithmetic is plain Mon-Fri (numpy.busday_offset), not a real CME/ICE holiday
calendar -- confirmed with the user before this session: core/calendars.py has no
business-day helper at all today, and there is no real settlement data yet to need
holiday-exact roll dates against. Revisit once real data demands more precision.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# CME/ICE's own fixed, standardised delivery-month letter codes -- a contract code like
# "z26" IS the December 2026 contract by construction, not something to look up or guess.
CME_MONTH_CODES: dict[str, int] = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}

# Regime state -> small int, for the lake (`derived.curve.<root>.regime`). A fixed, static
# enum -- not per-contract data, so it lives here as a plain constant rather than in
# pipelines/futures/series_meta.py's per-contract schema (see this session's own CLAUDE.md
# note for why that table doesn't fit). Import this dict to decode a stored code; don't
# guess the mapping. "flat" (6) is a real seventh value this module adds for the s12==0
# knife-edge the spec's own six named states don't cover.
REGIME_CODES: dict[str, int] = {
    "super_contango": 0,
    "super_backwardation": 1,
    "convex_contango": 2,
    "concave_contango": 3,
    "convex_backwardation": 4,
    "concave_backwardation": 5,
    "flat": 6,
}

_RANK_COLUMN = "f{:02d}"


def _rank_col(i: int) -> str:
    return _RANK_COLUMN.format(i)


def _business_days_before(expiry: pd.Timestamp, n: int) -> pd.Timestamp:
    """expiry minus n Mon-Fri business days. A non-business-day expiry is first rolled
    back to the preceding business day (roll="backward"), then n days are subtracted."""
    return pd.Timestamp(np.busday_offset(expiry.date(), -n, roll="backward"))


def nearby_panel(
    contract_panel: pd.DataFrame,
    expiries: pd.Series,
    roll_days_before_expiry: int = 5,
    adjust: str = "ratio",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """`contract_panel`: wide, index=date, one column per contract code, values=settle
    price. `expiries`: index=contract code, value=expiry date (pipelines/futures/
    series_meta.py's own `expiry` column, one row per contract).

    Ranking rule: for date d, a contract "retires" from the curve entirely (not just
    demoted a rank) the business day its own roll_date = expiry - roll_days_before_expiry
    arrives -- valid_contracts(d) = every contract with d < roll_date(c), sorted by expiry
    ascending; f0i on date d is the i-th (1-indexed) element of valid_contracts(d). This
    means a contract's own rank naturally decreases (f03->f02->f01) as earlier contracts
    roll off, and it disappears from every rank once its own roll date passes.

    Returns (adjusted, unadjusted, roll_dates): `unadjusted` columns f01..fn hold raw
    prices (genuinely discontinuous at each roll -- this is what spreads/convexity/regime
    must use, per specs/00_TRADING_CONVENTIONS.md's "spreads never from a back-adjusted
    series" rule). `adjusted` has only an f01 column, ratio/Panama-style back-adjusted so
    the return crossing a roll boundary equals the *new* front contract's own real return,
    never an artificial cross-contract jump. `roll_dates` is indexed by date, value = the
    contract code occupying f01 that day (None where fewer contracts remain than ranks
    needed)."""
    if adjust != "ratio":
        raise NotImplementedError(f"adjust={adjust!r} not implemented -- only 'ratio' exists")

    contracts_sorted = expiries.sort_values().index.tolist()
    n = len(contracts_sorted)
    roll_dates_by_contract = {
        c: _business_days_before(pd.Timestamp(expiries[c]), roll_days_before_expiry)
        for c in contracts_sorted
    }
    roll_dates_arr = np.array(
        [roll_dates_by_contract[c].to_datetime64() for c in contracts_sorted],
        dtype="datetime64[D]",
    )

    dates = contract_panel.index
    dates64 = dates.values.astype("datetime64[D]")
    # k(d) = number of contracts already retired (roll_date <= d) on date d -- vectorised
    # across every date at once, not a per-date Python loop.
    k = np.searchsorted(roll_dates_arr, dates64, side="right")

    values = contract_panel[contracts_sorted].to_numpy(dtype=float)
    row_idx = np.arange(len(dates))
    contracts_arr = np.array(contracts_sorted, dtype=object)

    unadjusted = pd.DataFrame(index=dates)
    front_contract = np.full(len(dates), None, dtype=object)
    for i in range(1, n + 1):
        idx = k + (i - 1)
        valid = idx < n
        col_idx = np.clip(idx, 0, n - 1)
        col_values = np.where(valid, values[row_idx, col_idx], np.nan)
        unadjusted[_rank_col(i)] = col_values
        if i == 1:
            front_contract = np.full(len(dates), None, dtype=object)
            front_contract[valid] = contracts_arr[col_idx[valid]]

    roll_dates = pd.Series(front_contract, index=dates, name="f01_contract")

    # Ratio back-adjustment for f01 only, built backward from the most recent (ratio=1)
    # segment -- a bounded loop over roll TRANSITIONS (proportional to contract count, not
    # date count), which is the "roll handling" the project's own vectorisation rule
    # explicitly allows a loop for.
    f01_raw = unadjusted[_rank_col(1)].to_numpy(dtype=float)
    cumulative_factor = np.ones(len(dates))
    transition_positions = [
        p for p in range(1, len(dates)) if front_contract[p] != front_contract[p - 1]
    ]
    for p in reversed(transition_positions):
        old_c, new_c = front_contract[p - 1], front_contract[p]
        if old_c is None or new_c is None:
            continue
        old_price = contract_panel[old_c].iloc[p - 1]
        new_price = contract_panel[new_c].iloc[p - 1]
        if pd.isna(old_price) or pd.isna(new_price) or old_price == 0:
            continue
        cumulative_factor[:p] *= new_price / old_price

    adjusted = pd.DataFrame({_rank_col(1): f01_raw * cumulative_factor}, index=dates)
    return adjusted, unadjusted, roll_dates


def time_spreads(unadj: pd.DataFrame) -> pd.DataFrame:
    """s12=f01-f02, s13=f01-f03, s16=f01-f06, s1_12=f01-f12, s23=f02-f03. A column needing
    a rank `unadj` doesn't have (e.g. s1_12 needs f12, impossible with fewer than 12
    contracts) is NaN, never a crash or a fabricated value. dec_dec is deliberately NOT
    here -- see the module-level `dec_dec()` function; it needs real contract codes, which
    rank-labelled `unadj` columns (f01..fn) no longer carry."""

    def _diff(a: int, b: int) -> pd.Series:
        ca, cb = _rank_col(a), _rank_col(b)
        if ca not in unadj.columns or cb not in unadj.columns:
            return pd.Series(np.nan, index=unadj.index)
        return unadj[ca] - unadj[cb]

    return pd.DataFrame(
        {
            "s12": _diff(1, 2),
            "s13": _diff(1, 3),
            "s16": _diff(1, 6),
            "s1_12": _diff(1, 12),
            "s23": _diff(2, 3),
        },
        index=unadj.index,
    )


def dec_dec(contract_panel: pd.DataFrame) -> pd.DataFrame:
    """Dec(y) - Dec(y+1), read directly off contract codes -- "z" is CME/ICE's own fixed
    December month code, so a "z26" column IS the Dec 2026 contract by construction, no
    roll-calendar lookup needed (corrected from an earlier draft of this plan, which
    wrongly deferred this to Session C). One column per consecutive December pair actually
    present in `contract_panel`; empty DataFrame if fewer than two December contracts
    exist."""
    dec_years = {}
    for code in contract_panel.columns:
        if not code or code[0].upper() != "Z":
            continue
        try:
            year = 2000 + int(code[1:])
        except ValueError:
            continue
        dec_years[year] = code

    result = pd.DataFrame(index=contract_panel.index)
    for year in sorted(dec_years):
        if year + 1 not in dec_years:
            continue
        result[f"dec_dec_{year}_{year + 1}"] = (
            contract_panel[dec_years[year]] - contract_panel[dec_years[year + 1]]
        )
    return result


def annualised_slope(unadj: pd.DataFrame) -> pd.Series:
    """(f01-f12)/f01 -- NaN if unadj has fewer than 12 ranks."""
    if _rank_col(12) not in unadj.columns:
        return pd.Series(np.nan, index=unadj.index)
    f01, f12 = unadj[_rank_col(1)], unadj[_rank_col(12)]
    return (f01 - f12) / f01


def roll_yield(unadj: pd.DataFrame) -> pd.Series:
    """(f01-f02)/f02*12, annualised monthly roll yield."""
    f01, f02 = unadj[_rank_col(1)], unadj[_rank_col(2)]
    return (f01 - f02) / f02 * 12


def convexity(unadj: pd.DataFrame, k: tuple[int, int, int] = (1, 2, 3)) -> pd.Series:
    """cv = F_k1 - 2*F_k2 + F_k3. NaN if any of the three ranks isn't in `unadj`."""
    cols = [_rank_col(i) for i in k]
    if not all(c in unadj.columns for c in cols):
        return pd.Series(np.nan, index=unadj.index)
    return unadj[cols[0]] - 2 * unadj[cols[1]] + unadj[cols[2]]


def curve_regime(
    unadj: pd.DataFrame, storage_cost_m1m2: float = 0.60, lookback: int = 252
) -> pd.DataFrame:
    """Six states plus a seventh, undocumented-by-the-spec "flat" value for the s12==0
    knife edge. Evaluated in the spec's own stated order, first match wins (np.select's
    own semantics match this exactly, so evaluation order is structural, not incidental).
    `slope_pct` (the spec's own p95(lookback)) is today's s12 percentile rank within its
    own trailing lookback-day window, inclusive of today -- NaN for the first
    lookback-1 rows (not enough history), which safely fails every slope_pct>0.95
    comparison via pandas' own NaN semantics, never raising and never false-triggering
    super_backwardation early."""
    f01, f02 = unadj[_rank_col(1)], unadj[_rank_col(2)]
    s12 = f01 - f02
    cv = convexity(unadj)  # default k=(1,2,3) -- the triple this regime classifier uses
    s1_12 = time_spreads(unadj)["s1_12"]

    slope_pct = s12.rolling(lookback).apply(lambda w: (w <= w.iloc[-1]).mean(), raw=False)

    conditions = [
        (s12 < -1.5 * storage_cost_m1m2) & (s1_12 < 0),
        (slope_pct > 0.95) & (s12 > 2.0),
        (s12 < 0) & (cv > 0),
        (s12 < 0) & (cv <= 0),
        (s12 > 0) & (cv > 0),
        (s12 > 0) & (cv <= 0),
    ]
    choices = [
        "super_contango",
        "super_backwardation",
        "convex_contango",
        "concave_contango",
        "convex_backwardation",
        "concave_backwardation",
    ]
    state = np.select(conditions, choices, default="flat")

    return pd.DataFrame(
        {
            "slope_sign": np.sign(s12),
            "cv_sign": np.sign(cv),
            "slope_pct": slope_pct,
            "state": state,
        },
        index=unadj.index,
    )


def transition_matrix(states: pd.Series) -> pd.DataFrame:
    """Row-normalised state[t] -> state[t+1] transition counts. Rows sum to 1 by
    construction; a state observed with zero outgoing transitions in the sample gets an
    all-NaN row (not silently zeroed -- a zero would imply a transition probability that
    was never actually observed)."""
    current = states.iloc[:-1].reset_index(drop=True)
    following = states.iloc[1:].reset_index(drop=True)
    all_states = sorted(states.dropna().unique())

    counts = pd.crosstab(current, following).reindex(
        index=all_states, columns=all_states, fill_value=0
    )
    row_sums = counts.sum(axis=1)
    return counts.div(row_sums, axis=0)
