# Spec 21 — Systematic Strategies Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the signal, sizing and backtesting layer that Specs 20, 24, 25, 26 and 27 all import, plus page `21_systematic.py`.

**Architecture:** Three flat modules under `core/` — `systematic.py` (pure signal and sizing maths, no lake I/O), `backtest.py` (vectorised backtester and fractionation), `strategies.py` (the registry that composes them). One daily entrypoint `pipelines/derived/systematic.py` writes positions to the lake; the page reads them back. Vectorised pandas only — no per-date loops.

**Tech Stack:** pandas, numpy, statsmodels, plotly, streamlit, pytest.

**Spec:** `specs/21_systematic-engine.md`, with conventions in `specs/00_TRADING_CONVENTIONS.md` and `CLAUDE.md`.

## Global Constraints

Inherited verbatim from `docs/superpowers/plans/2026-09-05-completion-roadmap.md` § Global Constraints. In addition, specific to this spec:

- Vectorised pandas only. No per-date Python loops in `core/systematic.py` or `core/backtest.py`.
- Import spreads, convexity, regime and utilisation from `core/curve.py`. Never recompute them.
- Spreads never from back-adjusted series: `carry`, `carry_pct` and `convexity_signal` take the **unadjusted** rank panel; `momentum_*` and `value` take the **adjusted** f01 series.
- Positions are lagged one day inside `backtest()`. No caller may pre-lag.
- Published anchors to display beside repo estimates: carry C(1,13) ≈ 20.3% annualised log-return, Sharpe 0.53, 1992–2022 unleveraged; carry–momentum blend ≈ 24.7%, Sharpe 0.64; static short front spread ≈ IR 0.50.
- `vol_target()` in this spec is a **temporary fallback**. Spec 22 replaces it with `core.risk.realised_vol`. Mark it in the docstring so Phase 2 finds it.

## File Structure

| File | Responsibility |
|---|---|
| `core/curve.py` (modify) | Gains one public `rank_col(i)` wrapper so `core/systematic.py` stops reaching for the private `_rank_col` |
| `core/systematic.py` (create) | Signals and sizing. Pure functions over Series/DataFrames, no I/O |
| `core/backtest.py` (create) | `BacktestResult`, `backtest`, `fractionate`, `inventory_predictability_test` |
| `core/strategies.py` (create) | The eight-entry strategy registry composing the two above |
| `core/theme.py` (modify) | Five new chart primitives for page 21 |
| `pipelines/derived/systematic.py` (create) | Daily entrypoint writing `derived.pos.<strategy>.<root>` |
| `infra/run_scheduled.py` (modify) | Register the entrypoint in the `daily` cadence, after `derived_curve` |
| `apps/dashboard/pages/21_systematic.py` (create) | The page |
| `tests/test_core_systematic.py` (create) | Task 1–3 |
| `tests/test_core_backtest.py` (create) | Task 4–5 |
| `tests/test_strategies.py` (create) | Task 6 |
| `tests/test_derived_systematic.py` (create) | Task 7 |

---

## Open question to settle before Task 3

Spec 21's guardrail line reads: *"util≥9: cap short-spread at 25%; util≤2: cap long-backwardation/short-spread; cot>0.95 halve longs; <0.05 halve shorts"*.

The `util≤2` clause is ambiguous — "cap long-backwardation/short-spread" could mean cap *both* directions at 25%, or cap only the short leg. Task 3 implements **both tails capping short positions at 25%** and records the reading in the docstring. Confirm or correct before merging Task 3; it changes backtest results, not the interface, so a later correction is cheap.

---

## Session A — signals and sizing

### Task 1: Sizing primitives (`zscore`, `reaction`, `reaction_piecewise`)

**Files:**
- Create: `core/systematic.py`
- Test: `tests/test_core_systematic.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `zscore(x: pd.Series, window: int = 252) -> pd.Series`; `reaction(z: pd.Series) -> pd.Series`; `reaction_piecewise(z: pd.Series, plateau: float = 1.0, cutoff: float = 2.5) -> pd.Series`. All three return float64 Series on the input index.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core_systematic.py
import numpy as np
import pandas as pd
import pytest

from core import systematic


def _idx(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2020-01-01", periods=n)


def test_reaction_has_its_published_fixed_points() -> None:
    z = pd.Series([0.0, 1.0, 2.0], index=_idx(3))
    got = systematic.reaction(z)
    assert got.iloc[0] == pytest.approx(0.0)
    assert got.iloc[1] == pytest.approx(1.0)
    assert got.iloc[2] == pytest.approx(2.0 * np.exp(-1.5))


def test_reaction_rises_to_one_then_decays() -> None:
    z = pd.Series(np.linspace(0.0, 3.0, 61), index=_idx(61))
    got = systematic.reaction(z)
    rising = got.iloc[:21]
    falling = got.iloc[20:]
    assert (rising.diff().dropna() > 0).all()
    assert (falling.diff().dropna() < 0).all()


def test_reaction_is_odd_and_clips_beyond_three() -> None:
    z = pd.Series([-5.0, 5.0, -1.0, 1.0], index=_idx(4))
    got = systematic.reaction(z)
    assert got.iloc[0] == pytest.approx(-got.iloc[1])
    assert got.iloc[2] == pytest.approx(-1.0)
    assert got.iloc[0] == pytest.approx(systematic.reaction(pd.Series([-3.0])).iloc[0])


def test_reaction_piecewise_ramps_plateaus_then_decays() -> None:
    z = pd.Series([0.5, 1.0, 2.0, 2.5, 3.0], index=_idx(5))
    got = systematic.reaction_piecewise(z)
    assert got.iloc[0] == pytest.approx(0.5)
    assert got.iloc[1] == pytest.approx(1.0)
    assert got.iloc[2] == pytest.approx(1.0)
    assert got.iloc[3] == pytest.approx(1.0)
    assert got.iloc[4] == pytest.approx(0.0)


def test_reaction_piecewise_rejects_a_cutoff_at_the_clip_bound() -> None:
    with pytest.raises(ValueError, match="cutoff"):
        systematic.reaction_piecewise(pd.Series([1.0]), cutoff=3.0)


def test_zscore_is_nan_until_the_window_fills() -> None:
    x = pd.Series(np.arange(10, dtype="float64"), index=_idx(10))
    got = systematic.zscore(x, window=5)
    assert got.iloc[:4].isna().all()
    assert got.iloc[4:].notna().all()


def test_zscore_of_a_constant_series_is_not_infinite() -> None:
    x = pd.Series([3.0] * 10, index=_idx(10))
    got = systematic.zscore(x, window=5)
    assert not np.isinf(got.to_numpy()).any()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core_systematic.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.systematic'`

- [ ] **Step 3: Write the minimal implementation**

```python
# core/systematic.py
"""Spec 21 — systematic signals and reaction-function sizing.

Pure maths over pandas objects. No lake I/O lives here: `pipelines/derived/systematic.py`
reads the lake, calls these, and writes positions back.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_CLIP = 3.0


def zscore(x: pd.Series, window: int = 252) -> pd.Series:
    """Rolling z-score. NaN until `window` observations exist.

    A flat window has zero standard deviation; the division is masked rather than
    allowed to produce an infinity, because `reaction` would turn one infinity into
    a whole run of NaN positions downstream.
    """
    rolling = x.astype("float64").rolling(window, min_periods=window)
    sd = rolling.std(ddof=0)
    return ((x - rolling.mean()) / sd.where(sd > 0.0)).astype("float64")


def reaction(z: pd.Series) -> pd.Series:
    """R(z) = z * exp(0.5 * (1 - z**2)), input clipped to [-3, 3].

    Peaks at exactly 1.0 when z = 1: full size at a one-sigma signal, then smaller
    as the signal gets extreme, which is the whole point of the reaction function.
    """
    clipped = z.astype("float64").clip(-_CLIP, _CLIP)
    return (clipped * np.exp(0.5 * (1.0 - clipped**2))).astype("float64")


def reaction_piecewise(
    z: pd.Series, plateau: float = 1.0, cutoff: float = 2.5
) -> pd.Series:
    """Linear ramp to `plateau`, flat to `cutoff`, then linear decay to zero at |z| = 3."""
    if not 0.0 < cutoff < _CLIP:
        raise ValueError(f"cutoff must lie strictly between 0 and {_CLIP}, got {cutoff}")
    clipped = z.astype("float64").clip(-_CLIP, _CLIP)
    magnitude = clipped.abs()
    out = magnitude.clip(upper=plateau)
    decaying = magnitude > cutoff
    out = out.where(
        ~decaying, plateau * (_CLIP - magnitude) / (_CLIP - cutoff)
    )
    return (np.sign(clipped) * out).astype("float64")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core_systematic.py -v`
Expected: PASS, 7 tests

- [ ] **Step 5: Lint, type-check and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy core
git add core/systematic.py tests/test_core_systematic.py
git commit -m "feat(systematic): Spec 21 Session A -- reaction function and z-score primitives"
```

---

### Task 2: Signals (`momentum_*`, `carry`, `carry_pct`, `value`, `convexity_signal`)

**Files:**
- Modify: `core/curve.py` — add a public `rank_col` wrapper beside `_rank_col` (line 48)
- Modify: `core/systematic.py`
- Test: `tests/test_core_systematic.py`

**Interfaces:**
- Consumes: `core.curve.convexity(unadj: pd.DataFrame, k=(1,2,3)) -> pd.Series`, `core.curve._RANK_COLUMN` (`"f{:02d}"`).
- Produces: `momentum_ma(f01_adj, n=100)`, `momentum_ret(f01_adj, n=252)`, `carry(unadj, near=1, far=13)`, `carry_pct(unadj, near=1, far=13)`, `value(f01_adj, n=1260)`, `convexity_signal(unadj)`, `momentum_on_carry(carry_series, n=60)` — all `-> pd.Series`. Plus `core.curve.rank_col(i: int) -> str`.

Note the split: `carry`, `carry_pct` and `convexity_signal` take the **unadjusted rank panel** (a DataFrame with `f01`…`f13` columns); the momentum and value functions take the **back-adjusted f01 Series**. Mixing them up silently produces the roll-artefact bug the conventions file warns about.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_core_systematic.py
from core import curve


def _backwardated_panel(n: int = 30) -> pd.DataFrame:
    """f01 highest, each further rank lower -- a backwardated curve."""
    idx = _idx(n)
    data = {curve.rank_col(i): pd.Series(80.0 - i, index=idx) for i in range(1, 14)}
    return pd.DataFrame(data)


def test_rank_col_matches_the_curve_module_convention() -> None:
    assert curve.rank_col(1) == "f01"
    assert curve.rank_col(13) == "f13"


def test_carry_is_positive_on_a_backwardated_curve() -> None:
    got = systematic.carry(_backwardated_panel())
    assert (got > 0).all()
    assert got.iloc[0] == pytest.approx(12.0)


def test_carry_pct_annualises_a_twelve_month_spread_one_for_one() -> None:
    panel = _backwardated_panel()
    got = systematic.carry_pct(panel, near=1, far=13)
    expected = np.log(79.0 / 67.0)
    assert got.iloc[0] == pytest.approx(expected)


def test_carry_pct_scales_a_six_month_spread_up_to_annual() -> None:
    panel = _backwardated_panel()
    got = systematic.carry_pct(panel, near=1, far=7)
    expected = np.log(79.0 / 73.0) * 2.0
    assert got.iloc[0] == pytest.approx(expected)


def test_momentum_ma_is_positive_on_a_rising_price() -> None:
    px = pd.Series(np.arange(1, 61, dtype="float64"), index=_idx(60))
    got = systematic.momentum_ma(px, n=10)
    assert got.dropna().gt(0).all()


def test_momentum_ret_is_the_log_change_over_n() -> None:
    px = pd.Series(np.linspace(50.0, 100.0, 40), index=_idx(40))
    got = systematic.momentum_ret(px, n=10)
    assert got.iloc[10] == pytest.approx(np.log(px.iloc[10] / px.iloc[0]))


def test_value_is_positive_when_price_sits_below_its_long_run_mean() -> None:
    px = pd.Series([100.0] * 40 + [50.0] * 10, index=_idx(50))
    got = systematic.value(px, n=30)
    assert got.iloc[-1] > 0


def test_momentum_on_carry_is_carry_less_its_own_rolling_mean() -> None:
    carry_series = pd.Series(np.arange(1, 41, dtype="float64"), index=_idx(40))
    got = systematic.momentum_on_carry(carry_series, n=10)
    expected = carry_series - carry_series.rolling(10, min_periods=10).mean()
    pd.testing.assert_series_equal(got, expected, check_names=False)
    assert got.iloc[:9].isna().all()
    assert got.dropna().gt(0).all()


def test_convexity_signal_is_the_sign_of_curve_convexity() -> None:
    panel = _backwardated_panel()
    expected = np.sign(curve.convexity(panel))
    pd.testing.assert_series_equal(
        systematic.convexity_signal(panel), expected.astype("float64"),
        check_names=False,
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core_systematic.py -v -k "carry or momentum or value or convexity or rank_col"`
Expected: FAIL — `AttributeError: module 'core.curve' has no attribute 'rank_col'`

- [ ] **Step 3: Add the public wrapper to `core/curve.py`**

Insert immediately after the existing `_rank_col` definition (around line 48–50). The private helper stays; existing callers are untouched.

```python
def rank_col(i: int) -> str:
    """Public name for the rank-column convention, for modules outside this file."""
    return _rank_col(i)
```

- [ ] **Step 4: Write the signals in `core/systematic.py`**

```python
# add to core/systematic.py -- imports at top of file
from core import curve


def momentum_ma(f01_adj: pd.Series, n: int = 100) -> pd.Series:
    """Price less its own n-day moving average. Takes the BACK-ADJUSTED f01 series."""
    series = f01_adj.astype("float64")
    return (series - series.rolling(n, min_periods=n).mean()).astype("float64")


def momentum_ret(f01_adj: pd.Series, n: int = 252) -> pd.Series:
    """Log return over n days. Takes the BACK-ADJUSTED f01 series."""
    series = f01_adj.astype("float64")
    return np.log(series / series.shift(n)).astype("float64")


def carry(unadj: pd.DataFrame, near: int = 1, far: int = 13) -> pd.Series:
    """F_near - F_far in price units. Takes the UNADJUSTED rank panel."""
    return (unadj[curve.rank_col(near)] - unadj[curve.rank_col(far)]).astype("float64")


def carry_pct(unadj: pd.DataFrame, near: int = 1, far: int = 13) -> pd.Series:
    """Annualised log carry between two ranks. Takes the UNADJUSTED rank panel.

    Log rather than simple, so the signal is additive across tenors and directly
    comparable with the published annualised-log-return anchors in the spec.
    """
    months = far - near
    if months <= 0:
        raise ValueError(f"far ({far}) must exceed near ({near})")
    ratio = unadj[curve.rank_col(near)] / unadj[curve.rank_col(far)]
    return (np.log(ratio) * (12.0 / months)).astype("float64")


def value(f01_adj: pd.Series, n: int = 1260) -> pd.Series:
    """Long-run mean less price: positive means cheap. Overlay only, never standalone."""
    series = f01_adj.astype("float64")
    return (series.rolling(n, min_periods=n).mean() - series).astype("float64")


def convexity_signal(unadj: pd.DataFrame) -> pd.Series:
    """sign(cv123), delegated to core.curve.convexity. Takes the UNADJUSTED rank panel."""
    return np.sign(curve.convexity(unadj)).astype("float64")


def momentum_on_carry(carry_series: pd.Series, n: int = 60) -> pd.Series:
    """Carry less its own n-day mean -- momentum applied to the carry signal itself."""
    series = carry_series.astype("float64")
    return (series - series.rolling(n, min_periods=n).mean()).astype("float64")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core_systematic.py tests/test_core_curve.py -v`
Expected: PASS, all tests including the pre-existing curve suite

- [ ] **Step 6: Lint, type-check and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy core
git add core/curve.py core/systematic.py tests/test_core_systematic.py
git commit -m "feat(systematic): Spec 21 Session A -- carry, momentum, value and convexity signals"
```

---

### Task 3: Sizing and guardrails (`vol_target`, `blend`, `position`, `apply_guardrails`)

**Files:**
- Modify: `core/systematic.py`
- Test: `tests/test_core_systematic.py`

**Interfaces:**
- Consumes: `reaction`, `reaction_piecewise` from Task 1.
- Produces: `vol_target(returns, target_ann=0.10, window=63) -> pd.Series`; `blend(signals: dict[str, pd.Series], weights: dict[str, float]) -> pd.Series`; `position(blended_z, sizing="reaction") -> pd.Series` bounded to [-1, 1]; `apply_guardrails(pos, util_decile, cot_pct) -> pd.Series`.

`util_decile` is `core.curve.utilisation_decile(...)` output (integers 0–9). `cot_pct` is the `derived.cot.<root>.mm_pct_3y` series from Spec 19 (a percentile in [0, 1]).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_core_systematic.py

def test_vol_target_halves_size_when_realised_vol_doubles() -> None:
    rng = np.random.default_rng(0)
    quiet = pd.Series(rng.normal(0, 0.01, 200), index=_idx(200))
    loud = quiet * 2.0
    q = systematic.vol_target(quiet, target_ann=0.10, window=63).iloc[-1]
    l = systematic.vol_target(loud, target_ann=0.10, window=63).iloc[-1]
    assert l == pytest.approx(q / 2.0, rel=1e-9)


def test_vol_target_masks_a_zero_vol_window_rather_than_returning_inf() -> None:
    flat = pd.Series([0.0] * 100, index=_idx(100))
    got = systematic.vol_target(flat, window=63)
    assert not np.isinf(got.to_numpy()).any()


def test_blend_is_a_weighted_mean_normalised_by_total_absolute_weight() -> None:
    idx = _idx(5)
    signals = {"a": pd.Series(1.0, index=idx), "b": pd.Series(3.0, index=idx)}
    got = systematic.blend(signals, {"a": 0.5, "b": 0.5})
    assert got.iloc[0] == pytest.approx(2.0)


def test_blend_rejects_mismatched_signal_and_weight_keys() -> None:
    idx = _idx(3)
    with pytest.raises(ValueError, match="keys"):
        systematic.blend({"a": pd.Series(1.0, index=idx)}, {"b": 1.0})


def test_position_is_bounded_to_plus_minus_one() -> None:
    z = pd.Series(np.linspace(-4.0, 4.0, 81), index=_idx(81))
    for sizing in ("reaction", "piecewise", "sign"):
        got = systematic.position(z, sizing=sizing)
        assert got.abs().max() <= 1.0 + 1e-12


def test_position_rejects_an_unknown_sizing_mode() -> None:
    with pytest.raises(ValueError, match="sizing"):
        systematic.position(pd.Series([0.5]), sizing="kelly")


def test_guardrail_caps_shorts_at_quarter_size_when_cushing_is_full() -> None:
    idx = _idx(3)
    pos = pd.Series([-1.0, -1.0, 1.0], index=idx)
    util = pd.Series([9, 5, 9], index=idx)
    cot = pd.Series([0.5, 0.5, 0.5], index=idx)
    got = systematic.apply_guardrails(pos, util, cot)
    assert got.iloc[0] == pytest.approx(-0.25)
    assert got.iloc[1] == pytest.approx(-1.0)
    assert got.iloc[2] == pytest.approx(1.0)


def test_guardrail_caps_shorts_when_cushing_is_near_empty_too() -> None:
    idx = _idx(2)
    pos = pd.Series([-1.0, -1.0], index=idx)
    util = pd.Series([2, 5], index=idx)
    cot = pd.Series([0.5, 0.5], index=idx)
    got = systematic.apply_guardrails(pos, util, cot)
    assert got.iloc[0] == pytest.approx(-0.25)
    assert got.iloc[1] == pytest.approx(-1.0)


def test_guardrail_halves_crowded_longs_and_crowded_shorts() -> None:
    idx = _idx(4)
    pos = pd.Series([1.0, -1.0, 1.0, -1.0], index=idx)
    util = pd.Series([5, 5, 5, 5], index=idx)
    cot = pd.Series([0.98, 0.98, 0.02, 0.02], index=idx)
    got = systematic.apply_guardrails(pos, util, cot)
    assert got.iloc[0] == pytest.approx(0.5)
    assert got.iloc[1] == pytest.approx(-1.0)
    assert got.iloc[2] == pytest.approx(1.0)
    assert got.iloc[3] == pytest.approx(-0.5)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core_systematic.py -v -k "vol_target or blend or position or guardrail"`
Expected: FAIL — `AttributeError: module 'core.systematic' has no attribute 'vol_target'`

- [ ] **Step 3: Write the implementation**

```python
# add to core/systematic.py

_SHORT_CAP = -0.25
_CROWDED_HIGH = 0.95
_CROWDED_LOW = 0.05


def vol_target(
    returns: pd.Series, target_ann: float = 0.10, window: int = 63
) -> pd.Series:
    """Scalar that takes a return stream to `target_ann` annualised vol.

    SPEC 21 FALLBACK. Spec 22 supersedes this with `core.risk.realised_vol`; delete
    this function and repoint callers when Spec 22 Session A lands.
    """
    realised = returns.astype("float64").rolling(window, min_periods=window).std(
        ddof=0
    ) * np.sqrt(252.0)
    return (target_ann / realised.where(realised > 0.0)).astype("float64")


def blend(signals: dict[str, pd.Series], weights: dict[str, float]) -> pd.Series:
    """Weighted mean of aligned signals, normalised by total absolute weight."""
    if set(signals) != set(weights):
        raise ValueError(
            f"signal keys {sorted(signals)} do not match weight keys {sorted(weights)}"
        )
    total = sum(abs(w) for w in weights.values())
    if total == 0.0:
        raise ValueError("weights sum to zero in absolute value")
    frame = pd.DataFrame(signals).astype("float64")
    weighted = frame.mul(pd.Series(weights), axis=1)
    return (weighted.sum(axis=1, min_count=len(weights)) / total).astype("float64")


def position(blended_z: pd.Series, sizing: str = "reaction") -> pd.Series:
    """Map a blended z-score to a position in [-1, 1]."""
    if sizing == "reaction":
        raw = reaction(blended_z)
    elif sizing == "piecewise":
        raw = reaction_piecewise(blended_z)
    elif sizing == "sign":
        raw = np.sign(blended_z.astype("float64"))
    else:
        raise ValueError(f"unknown sizing mode {sizing!r}")
    return raw.clip(-1.0, 1.0).astype("float64")


def apply_guardrails(
    pos: pd.Series, util_decile: pd.Series, cot_pct: pd.Series
) -> pd.Series:
    """Cap positions on storage extremes and halve them when positioning is crowded.

    Reading of the spec's `util<=2` clause: at both storage extremes the SHORT leg is
    capped at 25% of full size -- near-full Cushing because a short spread is exposed
    to a storage-boundary blow-out, near-empty because backwardation can run further
    than the signal expects. Longs are left alone at both tails.
    """
    out = pos.astype("float64").copy()
    util = util_decile.reindex(out.index)
    cot = cot_pct.reindex(out.index)

    storage_extreme = (util >= 9) | (util <= 2)
    capped = storage_extreme & (out < 0.0)
    out[capped] = out[capped].clip(lower=_SHORT_CAP)

    crowded_long = (cot > _CROWDED_HIGH) & (out > 0.0)
    out[crowded_long] = out[crowded_long] * 0.5
    crowded_short = (cot < _CROWDED_LOW) & (out < 0.0)
    out[crowded_short] = out[crowded_short] * 0.5
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core_systematic.py -v`
Expected: PASS, all Session A tests

- [ ] **Step 5: Lint, type-check and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy core
git add core/systematic.py tests/test_core_systematic.py
git commit -m "feat(systematic): Spec 21 Session A -- vol targeting, blending and guardrails"
```

**Session A DoD:** [x] functions, [x] tests.

---

## Session B — backtester and strategy registry

### Task 4: The backtester (`BacktestResult`, `backtest`)

**Files:**
- Create: `core/backtest.py`
- Test: `tests/test_core_backtest.py`

**Interfaces:**
- Consumes: nothing from Session A — `backtest` takes positions as data.
- Produces: `BacktestResult` (frozen dataclass with `daily_pnl: pd.Series`, `equity: pd.Series`, `stats: dict[str, float]`, `worst_5: pd.Series`, `rolling_sharpe_3y: pd.Series`) and `backtest(pos, returns, spread_pnl=None, cost_bps=2.0) -> BacktestResult`. `stats` keys: `ann_return`, `ann_vol`, `sharpe`, `max_drawdown`, `calmar`, `hit_rate`, `turnover_ann`. Specs 20, 24, 25, 26 and 27 all import this.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core_backtest.py
import numpy as np
import pandas as pd
import pytest

from core import backtest as bt


def _idx(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2020-01-01", periods=n)


def _returns(n: int = 500, seed: int = 7) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(0.0002, 0.02, n), index=_idx(n))


def test_constant_long_at_zero_cost_reproduces_buy_and_hold_exactly() -> None:
    r = _returns()
    pos = pd.Series(1.0, index=r.index)
    result = bt.backtest(pos, r, cost_bps=0.0)
    assert result.daily_pnl.sum() == pytest.approx(r.iloc[1:].sum(), abs=1e-12)


def test_positions_are_lagged_so_same_day_returns_cannot_be_traded() -> None:
    r = _returns()
    perfect = np.sign(r)
    cheating = bt.backtest(perfect, r, cost_bps=0.0).daily_pnl.sum()
    honest = bt.backtest(perfect.shift(-1).fillna(0.0), r, cost_bps=0.0).daily_pnl.sum()
    assert honest > cheating


def test_costs_reduce_pnl_only_when_the_position_moves() -> None:
    r = _returns()
    still = pd.Series(1.0, index=r.index)
    assert bt.backtest(still, r, cost_bps=0.0).daily_pnl.sum() == pytest.approx(
        bt.backtest(still, r, cost_bps=50.0).daily_pnl.sum()
    )
    flipping = pd.Series(
        np.where(np.arange(len(r)) % 2 == 0, 1.0, -1.0), index=r.index
    )
    assert (
        bt.backtest(flipping, r, cost_bps=50.0).daily_pnl.sum()
        < bt.backtest(flipping, r, cost_bps=0.0).daily_pnl.sum()
    )


def test_stats_carry_every_key_the_spec_requires() -> None:
    r = _returns()
    result = bt.backtest(pd.Series(1.0, index=r.index), r)
    assert set(result.stats) == {
        "ann_return",
        "ann_vol",
        "sharpe",
        "max_drawdown",
        "calmar",
        "hit_rate",
        "turnover_ann",
    }
    assert result.stats["max_drawdown"] <= 0.0
    assert 0.0 <= result.stats["hit_rate"] <= 1.0


def test_worst_five_are_the_five_worst_days_in_ascending_order() -> None:
    r = _returns()
    result = bt.backtest(pd.Series(1.0, index=r.index), r, cost_bps=0.0)
    assert len(result.worst_5) == 5
    assert result.worst_5.is_monotonic_increasing
    assert result.worst_5.iloc[0] == result.daily_pnl.min()


def test_spread_pnl_is_added_on_the_same_lagged_position() -> None:
    r = _returns(100)
    spread = pd.Series(0.001, index=r.index)
    plain = bt.backtest(pd.Series(1.0, index=r.index), r, cost_bps=0.0)
    withspread = bt.backtest(
        pd.Series(1.0, index=r.index), r, spread_pnl=spread, cost_bps=0.0
    )
    assert withspread.daily_pnl.sum() == pytest.approx(
        plain.daily_pnl.sum() + 0.001 * len(plain.daily_pnl)
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core_backtest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.backtest'`

- [ ] **Step 3: Write the implementation**

```python
# core/backtest.py
"""Spec 21 — vectorised backtester shared by Specs 20, 24, 25, 26 and 27.

Positions are lagged one day inside `backtest`. Callers pass the position as of the
signal date and must not pre-lag it, or the look-ahead guard is applied twice.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252
_ROLLING_3Y = 756


@dataclass(frozen=True)
class BacktestResult:
    daily_pnl: pd.Series
    equity: pd.Series
    stats: dict[str, float]
    worst_5: pd.Series
    rolling_sharpe_3y: pd.Series


def backtest(
    pos: pd.Series,
    returns: pd.Series,
    spread_pnl: pd.Series | None = None,
    cost_bps: float = 2.0,
) -> BacktestResult:
    """Run a position series against log returns. Costs charged on position change."""
    lagged = pos.astype("float64").shift(1)
    gross = lagged * returns.astype("float64")
    if spread_pnl is not None:
        gross = gross + lagged * spread_pnl.astype("float64")

    turnover = lagged.diff().abs()
    cost = turnover.fillna(0.0) * (cost_bps / 10_000.0)
    daily = (gross - cost).dropna()

    equity = daily.cumsum()
    drawdown = equity - equity.cummax()
    ann_return = float(daily.mean() * TRADING_DAYS)
    ann_vol = float(daily.std(ddof=0) * np.sqrt(TRADING_DAYS))
    max_drawdown = float(drawdown.min()) if len(drawdown) else 0.0

    stats: dict[str, float] = {
        "ann_return": ann_return,
        "ann_vol": ann_vol,
        "sharpe": ann_return / ann_vol if ann_vol > 0 else float("nan"),
        "max_drawdown": max_drawdown,
        "calmar": ann_return / abs(max_drawdown) if max_drawdown < 0 else float("nan"),
        "hit_rate": float((daily > 0).mean()),
        "turnover_ann": float(turnover.reindex(daily.index).mean() * TRADING_DAYS),
    }

    rolling = daily.rolling(_ROLLING_3Y, min_periods=_ROLLING_3Y)
    rolling_sd = rolling.std(ddof=0)
    rolling_sharpe = (
        rolling.mean() * TRADING_DAYS / (rolling_sd.where(rolling_sd > 0) * np.sqrt(TRADING_DAYS))
    ).astype("float64")

    return BacktestResult(
        daily_pnl=daily,
        equity=equity,
        stats=stats,
        worst_5=daily.nsmallest(5).sort_values(),
        rolling_sharpe_3y=rolling_sharpe,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core_backtest.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Lint, type-check and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy core
git add core/backtest.py tests/test_core_backtest.py
git commit -m "feat(backtest): Spec 21 Session B -- vectorised backtester with look-ahead guard"
```

---

### Task 5: Fractionation and the inventory-predictability test

**Files:**
- Modify: `core/backtest.py`
- Test: `tests/test_core_backtest.py`

**Interfaces:**
- Consumes: `BacktestResult.daily_pnl` from Task 4.
- Produces: `fractionate(daily_pnl, conditioners: dict[str, pd.Series], bins: int | dict[str, int] = 5) -> pd.DataFrame` with columns `condition, bin, n, mean, sharpe, share_of_total`; `inventory_predictability_test(s12, inventory) -> dict` with keys `inv_to_spread_t`, `inv_to_spread_r2`, `spread_to_inv_t`, `spread_to_inv_r2`, `spreads_lead_inventories`.

The second function exists to make a specific point permanently visible on the page: spreads predict inventories more than inventories predict spreads (Bouchouev). It guards against the naive inventory-to-spread causal story.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_core_backtest.py

def test_fractionation_shares_sum_to_one_within_each_condition() -> None:
    r = _returns(1000)
    pnl = bt.backtest(pd.Series(1.0, index=r.index), r, cost_bps=0.0).daily_pnl
    rng = np.random.default_rng(3)
    conditioners = {
        "regime": pd.Series(rng.integers(0, 3, len(pnl)), index=pnl.index),
        "util": pd.Series(rng.random(len(pnl)), index=pnl.index),
    }
    table = bt.fractionate(pnl, conditioners, bins=5)
    for _, group in table.groupby("condition"):
        assert group["share_of_total"].sum() == pytest.approx(1.0, abs=1e-6)


def test_fractionation_counts_add_up_to_the_pnl_length() -> None:
    r = _returns(300)
    pnl = bt.backtest(pd.Series(1.0, index=r.index), r, cost_bps=0.0).daily_pnl
    cond = {"half": pd.Series([0] * 150 + [1] * (len(pnl) - 150), index=pnl.index)}
    table = bt.fractionate(pnl, cond, bins=2)
    assert int(table["n"].sum()) == len(pnl)


def test_inventory_predictability_reports_both_directions() -> None:
    rng = np.random.default_rng(11)
    n = 400
    idx = _idx(n)
    spread = pd.Series(rng.normal(0, 1, n), index=idx).cumsum()
    inventory = pd.Series(spread.diff().shift(1).fillna(0.0).cumsum(), index=idx)
    got = bt.inventory_predictability_test(spread, inventory)
    assert set(got) == {
        "inv_to_spread_t",
        "inv_to_spread_r2",
        "spread_to_inv_t",
        "spread_to_inv_r2",
        "spreads_lead_inventories",
    }
    assert isinstance(got["spreads_lead_inventories"], bool)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core_backtest.py -v -k "fractionation or inventory"`
Expected: FAIL — `AttributeError: module 'core.backtest' has no attribute 'fractionate'`

- [ ] **Step 3: Write the implementation**

```python
# add to core/backtest.py -- add `import statsmodels.api as sm` at the top

def fractionate(
    daily_pnl: pd.Series,
    conditioners: dict[str, pd.Series],
    bins: int | dict[str, int] = 5,
) -> pd.DataFrame:
    """Split P&L by conditioning variable, one block of rows per conditioner.

    `share_of_total` is a share of the conditioner's own total P&L, so it sums to 1
    within each `condition` block. It is NaN when that total is zero.
    """
    rows: list[dict[str, object]] = []
    total_pnl = float(daily_pnl.sum())
    for name, raw in conditioners.items():
        aligned = raw.reindex(daily_pnl.index)
        n_bins = bins[name] if isinstance(bins, dict) else bins
        if aligned.dtype.kind in "iub" or aligned.nunique(dropna=True) <= n_bins:
            labels = aligned
        else:
            labels = pd.qcut(aligned, n_bins, duplicates="drop")
        for label, group in daily_pnl.groupby(labels, observed=True):
            sd = float(group.std(ddof=0))
            rows.append(
                {
                    "condition": name,
                    "bin": str(label),
                    "n": int(len(group)),
                    "mean": float(group.mean()),
                    "sharpe": (
                        float(group.mean() * TRADING_DAYS / (sd * np.sqrt(TRADING_DAYS)))
                        if sd > 0
                        else float("nan")
                    ),
                    "share_of_total": (
                        float(group.sum() / total_pnl) if total_pnl != 0 else float("nan")
                    ),
                }
            )
    return pd.DataFrame(rows)


def _ols_t_and_r2(y: pd.Series, x: pd.Series) -> tuple[float, float]:
    frame = pd.concat({"y": y, "x": x}, axis=1).dropna()
    if len(frame) < 3:
        return float("nan"), float("nan")
    fit = sm.OLS(frame["y"], sm.add_constant(frame["x"])).fit()
    return float(fit.tvalues.iloc[1]), float(fit.rsquared)


def inventory_predictability_test(
    s12: pd.Series, inventory: pd.Series
) -> dict[str, float | bool]:
    """Regress each series on the other's lag, both ways.

    Bouchouev's point: spreads predict inventories more strongly than the reverse.
    The page prints this permanently, so a naive inventory-to-spread story cannot be
    told without the counter-evidence sitting beside it.
    """
    d_s12 = s12.astype("float64").diff()
    inv = inventory.astype("float64")
    inv_t, inv_r2 = _ols_t_and_r2(d_s12, inv.shift(1))
    spread_t, spread_r2 = _ols_t_and_r2(inv.diff(), d_s12.shift(1))
    return {
        "inv_to_spread_t": inv_t,
        "inv_to_spread_r2": inv_r2,
        "spread_to_inv_t": spread_t,
        "spread_to_inv_r2": spread_r2,
        "spreads_lead_inventories": bool(spread_r2 > inv_r2),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core_backtest.py -v`
Expected: PASS, 9 tests

- [ ] **Step 5: Lint, type-check and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy core
git add core/backtest.py tests/test_core_backtest.py
git commit -m "feat(backtest): Spec 21 Session B -- fractionation and the inventory-predictability test"
```

---

### Task 6: The strategy registry

**Files:**
- Create: `core/strategies.py`
- Test: `tests/test_strategies.py`

**Interfaces:**
- Consumes: every public function from `core/systematic.py`, `core.curve.time_spreads`.
- Produces: `Strategy` (frozen dataclass: `name: str`, `roots: tuple[str, ...]`, `build: Callable[[StrategyInputs], pd.Series]`, `benchmark: Benchmark | None`), `StrategyInputs` (frozen dataclass carrying `unadj: pd.DataFrame`, `f01_adj: pd.Series`, `returns: pd.Series`, `util_decile: pd.Series`, `cot_pct: pd.Series`), `REGISTRY: dict[str, Strategy]` with exactly the eight keys `CARRY_1_13`, `CARRY_REACT`, `MOM_100`, `CARRY_MOM`, `CONVEX_SPREAD`, `SHORT_SPREAD_STATIC`, `FWD_SPREAD_MR`, `VALUE_OVERLAY`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_strategies.py
import numpy as np
import pandas as pd
import pytest

from core import curve, strategies


def _inputs(n: int = 400, seed: int = 5) -> strategies.StrategyInputs:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n)
    f01 = pd.Series(60.0 + rng.normal(0, 1, n).cumsum(), index=idx)
    unadj = pd.DataFrame(
        {curve.rank_col(i): f01 - 0.4 * (i - 1) for i in range(1, 14)}
    )
    return strategies.StrategyInputs(
        unadj=unadj,
        f01_adj=f01,
        returns=np.log(f01 / f01.shift(1)).fillna(0.0),
        util_decile=pd.Series(5, index=idx),
        cot_pct=pd.Series(0.5, index=idx),
    )


def test_registry_holds_exactly_the_eight_specced_strategies() -> None:
    assert set(strategies.REGISTRY) == {
        "CARRY_1_13",
        "CARRY_REACT",
        "MOM_100",
        "CARRY_MOM",
        "CONVEX_SPREAD",
        "SHORT_SPREAD_STATIC",
        "FWD_SPREAD_MR",
        "VALUE_OVERLAY",
    }


@pytest.mark.parametrize("name", sorted(strategies.REGISTRY))
def test_every_strategy_returns_a_bounded_position_on_the_input_index(name: str) -> None:
    data = _inputs()
    pos = strategies.REGISTRY[name].build(data)
    assert isinstance(pos, pd.Series)
    assert pos.index.equals(data.f01_adj.index)
    assert pos.dropna().abs().max() <= 1.0 + 1e-12


def test_short_spread_static_is_the_flat_minus_one_benchmark() -> None:
    pos = strategies.REGISTRY["SHORT_SPREAD_STATIC"].build(_inputs())
    assert (pos.dropna() == -1.0).all()


def test_carry_1_13_carries_its_published_anchor() -> None:
    bench = strategies.REGISTRY["CARRY_1_13"].benchmark
    assert bench is not None
    assert bench.ann_return == pytest.approx(0.203)
    assert bench.sharpe == pytest.approx(0.53)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_strategies.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.strategies'`

- [ ] **Step 3: Write the implementation**

```python
# core/strategies.py
"""Spec 21 — the strategy registry.

Each entry maps a bundle of lake-derived inputs to a position series in [-1, 1].
Nothing here reads the lake: `pipelines/derived/systematic.py` assembles the inputs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core import curve, systematic


@dataclass(frozen=True)
class Benchmark:
    """A published figure shown beside the repo estimate, with its source."""

    ann_return: float
    sharpe: float
    source: str


@dataclass(frozen=True)
class StrategyInputs:
    unadj: pd.DataFrame
    f01_adj: pd.Series
    returns: pd.Series
    util_decile: pd.Series
    cot_pct: pd.Series


@dataclass(frozen=True)
class Strategy:
    name: str
    roots: tuple[str, ...]
    build: Callable[[StrategyInputs], pd.Series]
    benchmark: Benchmark | None = None


_BOUCHOUEV = "Bouchouev, Virtual Barrels, ch. 5-6 (1992-2022, unleveraged)"


def _guard(pos: pd.Series, data: StrategyInputs) -> pd.Series:
    return systematic.apply_guardrails(pos, data.util_decile, data.cot_pct)


def _carry_sign(data: StrategyInputs) -> pd.Series:
    return np.sign(systematic.carry(data.unadj)).astype("float64")


def _carry_react(data: StrategyInputs) -> pd.Series:
    z = systematic.zscore(systematic.carry_pct(data.unadj))
    sized = systematic.position(z) * systematic.vol_target(data.returns)
    return _guard(sized.clip(-1.0, 1.0), data)


def _mom_100(data: StrategyInputs) -> pd.Series:
    z = systematic.zscore(systematic.momentum_ma(data.f01_adj, n=100))
    return _guard(systematic.position(z), data)


def _carry_mom(data: StrategyInputs) -> pd.Series:
    blended = systematic.blend(
        {
            "carry": systematic.zscore(systematic.carry_pct(data.unadj)),
            "momentum": systematic.zscore(systematic.momentum_ma(data.f01_adj, n=100)),
        },
        {"carry": 0.5, "momentum": 0.5},
    )
    return _guard(systematic.position(blended), data)


def _convex_spread(data: StrategyInputs) -> pd.Series:
    return _guard(systematic.convexity_signal(data.unadj), data)


def _short_spread_static(data: StrategyInputs) -> pd.Series:
    return pd.Series(-1.0, index=data.f01_adj.index)


def _fwd_spread_mr(data: StrategyInputs) -> pd.Series:
    """Long S(k, k+1) when it sits below s12, short when above, for k in {3, 6}."""
    s12 = data.unadj[curve.rank_col(1)] - data.unadj[curve.rank_col(2)]
    legs = []
    for k in (3, 6):
        leg = data.unadj[curve.rank_col(k)] - data.unadj[curve.rank_col(k + 1)]
        legs.append(np.sign(s12 - leg).astype("float64"))
    return _guard((sum(legs) / len(legs)).clip(-1.0, 1.0), data)


def _value_overlay(data: StrategyInputs) -> pd.Series:
    base = _carry_mom(data)
    value_z = systematic.zscore(systematic.value(data.f01_adj, n=1260))
    overlay = 1.0 + 0.5 * np.sign(value_z).where(value_z.abs() > 1.5, 0.0)
    return (base * overlay).clip(-1.0, 1.0).astype("float64")


REGISTRY: dict[str, Strategy] = {
    "CARRY_1_13": Strategy(
        "CARRY_1_13", ("cl",), _carry_sign, Benchmark(0.203, 0.53, _BOUCHOUEV)
    ),
    "CARRY_REACT": Strategy("CARRY_REACT", ("cl",), _carry_react),
    "MOM_100": Strategy("MOM_100", ("cl",), _mom_100),
    "CARRY_MOM": Strategy(
        "CARRY_MOM", ("cl",), _carry_mom, Benchmark(0.247, 0.64, _BOUCHOUEV)
    ),
    "CONVEX_SPREAD": Strategy("CONVEX_SPREAD", ("cl",), _convex_spread),
    "SHORT_SPREAD_STATIC": Strategy(
        "SHORT_SPREAD_STATIC",
        ("cl",),
        _short_spread_static,
        Benchmark(float("nan"), 0.50, _BOUCHOUEV + " -- IR 0.50"),
    ),
    "FWD_SPREAD_MR": Strategy("FWD_SPREAD_MR", ("cl",), _fwd_spread_mr),
    "VALUE_OVERLAY": Strategy("VALUE_OVERLAY", ("cl",), _value_overlay),
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_strategies.py -v`
Expected: PASS, 12 tests (4 plus the 8-way parametrise)

- [ ] **Step 5: Lint, type-check and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy core
git add core/strategies.py tests/test_strategies.py
git commit -m "feat(strategies): Spec 21 Session B -- eight-strategy registry with published anchors"
```

---

### Task 7: Daily positions entrypoint and orchestration

**Files:**
- Create: `pipelines/derived/systematic.py`
- Modify: `infra/run_scheduled.py:31-45` — add to the `daily` group, **after** `derived_curve`
- Test: `tests/test_derived_systematic.py`

**Interfaces:**
- Consumes: `core.strategies.REGISTRY`, `core.storage.read_ts_long`, `core.storage.write_ts_long`, `core.curve.nearby_panel`, and — reused rather than reimplemented — `pipelines.derived.curve.contract_panel_for(root, meta)` and `pipelines.futures.series_meta.read_series_meta()`.
- Produces: `build_positions(root: str, meta: pd.DataFrame) -> pd.DataFrame` returning a `ts_long`-conformant frame, and `main() -> None`. Series IDs: `derived.pos.<strategy_lowercase>.<root>`, written under source `derived`.

Note the real `nearby_panel` signature — it takes a contract panel and an expiry Series, **not** a root, and returns a three-tuple:

```python
def nearby_panel(
    contract_panel: pd.DataFrame,
    expiries: pd.Series,
    roll_days_before_expiry: int = 5,
    adjust: str = "ratio",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:  # (adjusted, unadjusted, roll_dates)
```

Its first return value is already ratio-adjusted, so `back_adjust_from_ranks` is not needed here. `pipelines/derived/curve.py:76-81` shows the exact calling pattern to copy.

Ordering is load-bearing and already commented in `run_scheduled.py`: this entrypoint reads what `pipelines.derived.curve` writes in the same run, so it must sit after it in the list.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_derived_systematic.py
import pandas as pd
import pytest

from core import schemas, strategies
from pipelines.derived import systematic as derived_systematic
from pipelines.futures.series_meta import read_series_meta


def test_every_registry_strategy_yields_a_ts_long_conformant_block(monkeypatch) -> None:
    frame = derived_systematic.build_positions("cl", read_series_meta())
    schemas.validate_ts_long(frame)
    produced = set(frame["series_id"].unique())
    expected = {f"derived.pos.{name.lower()}.cl" for name in strategies.REGISTRY}
    assert produced == expected


def test_positions_stay_within_plus_minus_one() -> None:
    frame = derived_systematic.build_positions("cl", read_series_meta())
    assert frame["value"].abs().max() <= 1.0 + 1e-12


def test_entrypoint_is_registered_in_the_daily_cadence_after_derived_curve() -> None:
    from infra.run_scheduled import CADENCE_GROUPS

    names = [name for name, _ in CADENCE_GROUPS["daily"]]
    assert "derived_systematic" in names
    assert names.index("derived_systematic") > names.index("derived_curve")
```

The first two tests need lake data. Follow the precedent in `tests/test_derived_curve_ranks.py` for how that suite fixtures the lake, and reuse it rather than inventing a second approach — read that file before writing this one.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_derived_systematic.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipelines.derived.systematic'`

- [ ] **Step 3: Write the entrypoint**

```python
# pipelines/derived/systematic.py
"""Spec 21 — daily systematic positions.

Reads the Spec 18 curve panel and Spec 19 COT percentiles from the lake, runs every
strategy in the registry, writes `derived.pos.<strategy>.<root>` back.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core import curve, storage, strategies
from pipelines.derived.curve import contract_panel_for
from pipelines.futures.series_meta import read_series_meta

ROOTS = ("cl",)
SOURCE = "derived"

# Written by pipelines/derived/cushing.py and pipelines/derived/fundamentals.py
# respectively -- both confirmed against the live lake, not assumed.
UTIL_DECILE_SERIES = "derived.cushing.util_decile"


def build_positions(root: str, meta: pd.DataFrame) -> pd.DataFrame:
    contract_panel, expiries = contract_panel_for(root, meta)
    if contract_panel.empty or len(expiries) < 2:
        return pd.DataFrame()
    adjusted, unadj, _roll_dates = curve.nearby_panel(contract_panel, expiries)

    f01_adj = adjusted[curve.rank_col(1)]
    returns = np.log(f01_adj / f01_adj.shift(1))
    util = storage.read_ts_long([UTIL_DECILE_SERIES])
    cot = storage.read_ts_long([f"derived.cot.{root}.mm_pct_3y"])

    data = strategies.StrategyInputs(
        unadj=unadj,
        f01_adj=f01_adj,
        returns=returns,
        util_decile=util.set_index("ts")["value"].reindex(unadj.index).ffill(),
        cot_pct=cot.set_index("ts")["value"].reindex(unadj.index).ffill(),
    )

    blocks = []
    for name, strategy in strategies.REGISTRY.items():
        pos = strategy.build(data).dropna()
        blocks.append(
            pd.DataFrame(
                {
                    "series_id": f"derived.pos.{name.lower()}.{root}",
                    "source": SOURCE,
                    "ts": pos.index,
                    "value": pos.to_numpy(),
                    "unit": "position",
                    "geo": "us",
                    "freq": "daily",
                    "revision_date": pd.Timestamp.utcnow().normalize(),
                }
            )
        )
    return pd.concat(blocks, ignore_index=True)


def main() -> None:
    meta = read_series_meta()
    for root in ROOTS:
        frame = build_positions(root, meta)
        if not frame.empty:
            storage.write_ts_long(frame, source=SOURCE)
```

`derived.cushing.util_decile` is confirmed — `pipelines/derived/cushing.py` documents writing `derived.cushing.util` and `derived.cushing.util_decile`. Confirm `derived.cot.<root>.mm_pct_3y` against the live lake before the first run: it is written by `pipelines/derived/fundamentals.py` on the `weekly_fri` cadence, so on a fresh lake it may not exist yet, in which case `read_ts_long` returns an empty frame and every guardrailed strategy silently produces all-NaN positions. Fail loudly on an empty read rather than writing a lake full of NaN.

- [ ] **Step 4: Register the entrypoint**

In `infra/run_scheduled.py`, inside the `"daily"` list, immediately after the `("derived_curve", "pipelines.derived.curve")` entry:

```python
        # Must run after "derived_curve" above -- reads the rank panel and spreads that
        # entry just wrote. Same load-bearing ordering as the futures -> curve pair.
        ("derived_systematic", "pipelines.derived.systematic"),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_derived_systematic.py tests/test_run_scheduled.py -v`
Expected: PASS

- [ ] **Step 6: Lint, type-check and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy core pipelines infra
git add pipelines/derived/systematic.py infra/run_scheduled.py tests/test_derived_systematic.py
git commit -m "feat(systematic): Spec 21 Session B -- daily positions entrypoint on the daily cadence"
```

**Session B DoD:** [x] backtester, [x] registry, [x] daily positions in lake, benchmark comparison card lands in Task 9.

---

## Session C — the page

> Tasks 8 and 9 are deliberately specified as "read the existing pattern, then match it" rather than as literal code. `core/theme.py` and `apps/dashboard/pages/20_cracks.py` are the house style, and a chart primitive written from a plan instead of from the neighbouring functions is exactly how ad-hoc styling gets in — which `CLAUDE.md` rule 5 forbids. Each task names the file to read first and the assertions to make; write the code from that file, not from here.

### Task 8: Theme primitives

**Files:**
- Modify: `core/theme.py`
- Test: `tests/test_theme_model_charts.py` (extend the existing suite; do not create a parallel one)

**Interfaces:**
- Consumes: the module's existing `NAVY`, `LIGHT_BLUE`, `RED`, `ORANGE`, `GREY`, `BAND`, `GRID` constants and the `"kardamow"` template.
- Produces: `signal_board_table(df) -> go.Figure`; `equity_drawdown_chart(equity, drawdown, title, benchmark=None) -> go.Figure`; `reaction_curve_chart(current_z, title) -> go.Figure`; `fractionation_heatmap(table, title) -> go.Figure`; `crowding_quadrant_scatter(cot_pct, signal_z, title) -> go.Figure`.

- [ ] **Step 1: Read the existing suite and module first**

Run: `sed -n '1,60p' tests/test_theme_model_charts.py` and `grep -n '^def ' core/theme.py`

Match the assertion style already used there (these tests check figure structure, not pixels) and reuse the existing template rather than setting layout properties by hand.

- [ ] **Step 2: Write the failing tests**

One test per new function, asserting: the returned object is a `go.Figure`; its `layout.template` is the Kardamow template; the trace count matches the inputs; and for `reaction_curve_chart`, that the marked current-z point sits on the curve (`y == systematic.reaction(pd.Series([z])).iloc[0]`).

- [ ] **Step 3: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_theme_model_charts.py -v`
Expected: FAIL — `AttributeError` on each new name

- [ ] **Step 4: Implement the five primitives**

Follow the house style in `CLAUDE.md`: navy primary, light blue secondary, red accents, orange seasonal median, grey band, horizontal legend top-left, direct annotations near the last point rather than legend-only labelling. `equity_drawdown_chart` uses a two-row subplot (log equity above, drawdown below) with the benchmark line in grey. `fractionation_heatmap` may reuse the existing `category_time_heatmap` colour scale.

- [ ] **Step 5: Run to verify they pass, then commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_theme_model_charts.py -v
.venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy core
git add core/theme.py tests/test_theme_model_charts.py
git commit -m "feat(theme): Spec 21 Session C -- signal board, equity/drawdown and fractionation charts"
```

---

### Task 9: Page `21_systematic.py`

**Files:**
- Create: `apps/dashboard/pages/21_systematic.py`
- Test: `tests/test_pages_smoke.py`, `tests/test_pages_browser.py` (both are parametrised over pages — confirm the new page is picked up rather than adding a bespoke case)

**Interfaces:**
- Consumes: `core.storage.read_ts_long`, `core.strategies.REGISTRY`, `core.backtest.backtest`, `core.backtest.fractionate`, `core.backtest.inventory_predictability_test`, the five Task 8 primitives, `apps.dashboard.components.card.card`.
- Produces: no importable API.

- [ ] **Step 1: Read a built page for the layout contract**

Run: `sed -n '1,80p' apps/dashboard/pages/20_cracks.py`

Copy its structure exactly: `st.subheader` to group, one `card(...)` per individual chart, all data from `read_ts_long`, no API calls.

- [ ] **Step 2: Confirm the smoke and browser tests fail for the new page**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pages_smoke.py -v`
Expected: the parametrised case for `21_systematic` fails or is absent

- [ ] **Step 3: Build the page**

Sections, in order, each in its own `card(...)`:

1. **Signal board** — `signal_board_table` per root: z, position, guardrail state.
2. **Equity curves** — `equity_drawdown_chart` for every registry entry, with the published anchor drawn as a grey line and the deviation printed in the caption. Where `benchmark` is `None`, say so rather than showing a blank.
3. **Reaction function** — `reaction_curve_chart` with the live z marked.
4. **Fractionation** — `fractionation_heatmap` over regime, utilisation decile, COT quintile, roll window and month, plus share-of-total bars.
5. **Crowding monitor** — `crowding_quadrant_scatter`, COT percentile against signal z, inflection quadrant shaded.
6. **Inventory predictability** — the `inventory_predictability_test` result as a permanent caption, stating in words which direction dominates.

- [ ] **Step 4: Run the app and look at it**

```bash
.venv/Scripts/python.exe -m streamlit run apps/dashboard/app.py
```

Check every card renders with data, not an empty frame. A page that loads but shows nothing is exactly what `tests/test_pages_browser.py` was added to catch (commit `8197ff9`).

- [ ] **Step 5: Full green, then commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy core pipelines infra
.venv/Scripts/python.exe -m pytest
git add apps/dashboard/pages/21_systematic.py
git commit -m "feat(systematic): Spec 21 Session C -- page 21 (spec complete)"
```

- [ ] **Step 6: Close the spec**

Update `specs/00_INDEX.md` and `CHANGELOG.md`, tick the Definition of Done boxes in `specs/21_systematic-engine.md`, and commit.

---

## Definition of Done (Spec 21)

- [ ] Sessions A–C complete.
- [ ] `core/backtest.py` importable by Specs 20, 24, 25, 26 and 27.
- [ ] Daily positions entrypoint registered in `infra/run_scheduled.py`, after `derived_curve`.
- [ ] Published-versus-repo deviation displayed for `CARRY_1_13`, `CARRY_MOM` and `SHORT_SPREAD_STATIC`.
- [ ] `ruff check .`, `mypy core pipelines infra`, `pytest` all green.
- [ ] `specs/00_INDEX.md` and `CHANGELOG.md` updated.

## Deferred to Phase 2

The CARRY_1_13 accuracy check against real 1993–2022 history (within ±4 pp of 20.3% and Sharpe ±0.15 of 0.53) is specced as **xfail when history is absent**, and this repo's futures history does not yet reach 1993. Write the test as `xfail` now; when Spec 18's history deepens, flip it. On a miss the page must print the roll-rule and cost diagnostic rather than passing silently — that requirement belongs to Task 9's equity-curve card.
