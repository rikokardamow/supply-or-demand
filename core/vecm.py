"""Crack-spread VECM after Murat & Tokat (2009), *Energy Economics* 31:85-90.

Pure maths only -- never touches DuckDB (root NOTES.md rule 2). `pipelines/derived/
vecm_refit.py` reads the lake, calls these functions, and writes the model card back.

**Deviation from the paper, to be shown on the page and never presented as a
replication.** Murat & Tokat regress WTI spot on the 3:2:1 crack *futures*; their whole
result is about the forecasting content of the futures. The lake holds no `fut.*` rows at
all (Spec 18 has never ingested a real settlement), so the crack here is the **spot**
crack from `pipelines/derived/cracks.py`. A spot-crack VECM is a weaker, different claim.
The paper's own RMSE/Theil figures are not in open sources either, so the page benchmark
is qualitative, per the spec.

Spec 20 Session B's own model specification: variables log(WTI spot) and the 3:2:1 crack
in levels; lag order by AIC/SIC over p=1..4; constant in the cointegration space
(`det_order=0` / `deterministic="ci"`); estimated on the post-break sample with the
full-sample fit shown beside it.
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd
import ruptures as rpt
from arch.unitroot import PhillipsPerron
from statsmodels.tools.sm_exceptions import InterpolationWarning
from statsmodels.tsa.stattools import adfuller, grangercausalitytests, kpss
from statsmodels.tsa.vector_ar.vecm import VECM, VECMResults, coint_johansen

MONTHLY_FREQ = "BME"
"""Business month end -- the spec fixes monthly aggregation at the last business day."""

MAX_LAGS = 4
"""The spec's own p=1..4 grid."""

ANDREWS_TRIM = 0.15
"""Standard Andrews (1993) trimming: candidate breaks only in the middle 70%."""

BENCHMARK = "random walk"


def to_monthly(series: pd.Series) -> pd.Series:
    """Daily series -> last business-day observation of each month.

    Weekend-dated rows are dropped before resampling rather than resampled with
    everything else. A Saturday-dated print is not a business-day observation, and left
    in place `resample("BME")` would push it past the month's business-month-end anchor
    and into the *next* month's bucket. The FRED legs this runs on are business-day only,
    so this is a guard rather than a live correction.
    """
    clean = series.dropna()
    index = pd.DatetimeIndex(clean.index)
    weekday: pd.Series = clean[index.dayofweek < 5]
    return weekday.resample(MONTHLY_FREQ).last().dropna()


# --- unit roots -------------------------------------------------------------------


def _level_tests(y: np.ndarray) -> dict[str, float]:
    # result_object=True is statsmodels 0.15's forward-compatible form here too.
    adf = adfuller(y, autolag="AIC", result_object=True)
    adf_stat, adf_p, adf_lags = adf.statistic, adf.pvalue, adf.lags
    pp = PhillipsPerron(y)
    with warnings.catch_warnings():
        # KPSS's p-value look-up table is bounded at 0.01/0.10; statsmodels warns when
        # the statistic falls outside it. That is expected on a clear (non-)stationary
        # series, not a problem -- the bound is reported as the p-value.
        warnings.simplefilter("ignore", InterpolationWarning)
        # result_object=True is statsmodels 0.15's forward-compatible form; the plain
        # tuple it replaces is deprecated from 0.16.
        kpss_result = kpss(y, regression="c", nlags="auto", result_object=True)
    kpss_stat, kpss_p = kpss_result.statistic, kpss_result.pvalue
    return {
        "adf_stat": float(adf_stat),
        "adf_p": float(adf_p),
        "adf_lags": int(adf_lags),
        "pp_stat": float(pp.stat),
        "pp_p": float(pp.pvalue),
        "kpss_stat": float(kpss_stat),
        "kpss_p": float(kpss_p),
    }


def unit_root_tests(y: pd.Series, alpha: float = 0.05) -> dict[str, Any]:
    """ADF (AIC lag choice), Phillips-Perron and KPSS on the level and the difference.

    The I(1) verdict is the standard confirmatory pattern: a unit root cannot be
    rejected in the level (ADF **and** PP fail to reject) but is rejected in the first
    difference. KPSS runs with the opposite null and is reported alongside rather than
    folded into the verdict, so a disagreement between the two families stays visible
    instead of being silently resolved.
    """
    values = y.dropna().to_numpy(dtype=float)
    level = _level_tests(values)
    diff = _level_tests(np.diff(values))

    i1 = bool(level["adf_p"] > alpha and level["pp_p"] > alpha and diff["adf_p"] < alpha)
    return {"level": level, "diff": diff, "i1": i1, "alpha": alpha}


# --- lag order --------------------------------------------------------------------


def select_lag_order(df: pd.DataFrame, max_lags: int = MAX_LAGS) -> dict[str, int]:
    """Lag order for the VECM's differenced terms, chosen over the spec's p=1..4 grid.

    statsmodels' own `select_order` reports the VAR-level order; the VECM takes
    `k_ar_diff = p - 1`, so a VAR order of 1 is not representable. The grid is therefore
    searched directly on the VECM's own AIC/SIC, which is what the spec's "lag order by
    AIC/SIC over p=1..4" actually means for this model.
    """
    values = df.dropna().to_numpy(dtype=float)
    aic: dict[int, float] = {}
    sic: dict[int, float] = {}
    for p in range(1, max_lags + 1):
        try:
            fitted = VECM(values, k_ar_diff=p, coint_rank=1, deterministic="ci").fit()
        except (ValueError, np.linalg.LinAlgError):
            continue
        n_params = fitted.alpha.size + fitted.beta.size + fitted.gamma.size
        resid = np.asarray(fitted.resid, dtype=float)
        n_obs = resid.shape[0]
        sigma = np.cov(resid, rowvar=False)
        _sign, log_det = np.linalg.slogdet(np.atleast_2d(sigma))
        aic[p] = log_det + 2.0 * n_params / n_obs
        sic[p] = log_det + np.log(n_obs) * n_params / n_obs

    if not aic:
        return {"aic": 1, "sic": 1, "chosen": 1}

    best_aic = min(aic, key=lambda k: aic[k])
    best_sic = min(sic, key=lambda k: sic[k])
    # The spec estimates on AIC; SIC is reported beside it as the more parsimonious
    # second opinion, not used to override.
    return {"aic": best_aic, "sic": best_sic, "chosen": best_aic}


# --- structural break -------------------------------------------------------------


def _andrews_sup_f(df: pd.DataFrame, trim: float) -> tuple[float, int]:
    """Andrews (1993) sup-F for a break in the regression of column 0 on the rest.

    Returns (sup-F statistic, index). With a single column there is no relationship to
    break, so this returns (nan, -1) and the caller falls back on Bai-Perron alone.
    """
    if df.shape[1] < 2:
        return float("nan"), -1

    y = df.iloc[:, 0].to_numpy(dtype=float)
    x = df.iloc[:, 1:].to_numpy(dtype=float)
    n = len(y)
    design = np.column_stack([np.ones(n), x])
    k = design.shape[1]

    def _ssr(yy: np.ndarray, xx: np.ndarray) -> float:
        beta, *_ = np.linalg.lstsq(xx, yy, rcond=None)
        resid = yy - xx @ beta
        return float(resid @ resid)

    ssr_pooled = _ssr(y, design)
    lo, hi = int(np.floor(trim * n)), int(np.ceil((1 - trim) * n))
    best_f, best_i = float("-inf"), -1
    for i in range(max(lo, k + 1), min(hi, n - k - 1)):
        ssr_split = _ssr(y[:i], design[:i]) + _ssr(y[i:], design[i:])
        if ssr_split <= 0:
            continue
        f_stat = ((ssr_pooled - ssr_split) / k) / (ssr_split / (n - 2 * k))
        if f_stat > best_f:
            best_f, best_i = f_stat, i
    return best_f, best_i


def structural_break(
    df: pd.DataFrame, n_breaks: int = 1, trim: float = ANDREWS_TRIM
) -> dict[str, Any]:
    """Bai-Perron (via `ruptures`) plus Andrews sup-F.

    The two answer different questions and are both reported. Bai-Perron's l2 cost finds
    shifts in the *level* of the series; Andrews sup-F finds a break in the *relationship*
    between them. A regime change can show up in one and not the other, so neither is
    allowed to stand in for the other. `break_index` is Bai-Perron's, which is the one the
    spec's own April-2003 target refers to.
    """
    data = df.dropna()
    signal = data.to_numpy(dtype=float)
    if signal.ndim == 1:
        signal = signal.reshape(-1, 1)

    algo = rpt.Dynp(model="l2", min_size=max(10, int(trim * len(data))), jump=1)
    try:
        breaks = algo.fit(signal).predict(n_bkps=n_breaks)
    except rpt.exceptions.BadSegmentationParameters:
        # The sample is too short to hold n_breaks+1 segments of the minimum size.
        # "No break found" is the honest answer; raising would abort a refit that can
        # still legitimately run on the full sample.
        breaks = []
    # ruptures always terminates the list with the sample length itself; that sentinel
    # is not a break.
    break_indices = [b for b in breaks if b < len(data)]

    sup_f, sup_f_index = _andrews_sup_f(data, trim)

    break_index = break_indices[0] if break_indices else -1
    return {
        "break_index": break_index,
        "break_date": data.index[break_index] if break_index >= 0 else None,
        "bai_perron_indices": break_indices,
        "bai_perron_dates": [data.index[i] for i in break_indices],
        "sup_f": sup_f,
        "sup_f_index": sup_f_index,
        "sup_f_date": data.index[sup_f_index] if sup_f_index >= 0 else None,
    }


# --- Johansen ---------------------------------------------------------------------


def johansen(df: pd.DataFrame, det_order: int = 0, k_ar_diff: int = 1) -> dict[str, Any]:
    """Johansen trace and maximum-eigenvalue tests. `det_order=0` puts a constant in the
    cointegration space, per the spec.

    Rank is read off the trace statistic against its own 5% critical value -- the first
    r whose statistic fails to exceed the critical value. `beta_y2` is the cointegrating
    coefficient with the relation normalised to `y1 - beta_y2*y2`, which is the sign
    convention the spec's own beta=0.16 acceptance test uses.
    """
    data = df.dropna()
    with warnings.catch_warnings():
        # statsmodels' own coint_johansen casts complex eigenvalues to real internally
        # (vecm.py's lr1/lr2 accumulation) and warns while doing it. The imaginary parts
        # are numerically zero for a real-valued system; the warning is theirs, not a
        # signal about this data.
        warnings.simplefilter("ignore", np.exceptions.ComplexWarning)
        result = coint_johansen(data.to_numpy(dtype=float), det_order, k_ar_diff)

    trace_stat = np.asarray(result.lr1, dtype=float)
    max_eig_stat = np.asarray(result.lr2, dtype=float)
    trace_cv = np.asarray(result.cvt, dtype=float)[:, 1]  # column 1 == 5%
    max_eig_cv = np.asarray(result.cvm, dtype=float)[:, 1]

    def _rank(stats: np.ndarray, cvs: np.ndarray) -> int:
        for r, (stat, cv) in enumerate(zip(stats, cvs, strict=True)):
            if stat <= cv:
                return r
        return len(stats)

    rank_trace = _rank(trace_stat, trace_cv)
    # `evec` comes back complex; the imaginary parts are numerically zero here.
    evec = np.asarray(result.evec, dtype=float).real if np.isrealobj(
        result.evec
    ) else np.real(result.evec)
    beta = evec[:, 0] / evec[0, 0]

    return {
        "trace_stat": trace_stat,
        "trace_cv_5pct": trace_cv,
        "max_eig_stat": max_eig_stat,
        "max_eig_cv_5pct": max_eig_cv,
        "rank_trace": rank_trace,
        "rank_max_eig": _rank(max_eig_stat, max_eig_cv),
        "rank": rank_trace,
        "beta": beta,
        "beta_y2": float(-beta[1]) if len(beta) > 1 else float("nan"),
    }


def fit_vecm(df: pd.DataFrame, rank: int = 1, k_ar_diff: int = 1) -> VECMResults:
    """statsmodels VECM with a constant in the cointegration space. `alpha`, `beta` and
    `gamma` are read straight off the returned results object."""
    data = df.dropna()
    return VECM(
        data.to_numpy(dtype=float),
        k_ar_diff=k_ar_diff,
        coint_rank=rank,
        deterministic="ci",
    ).fit()


def granger(df: pd.DataFrame, maxlag: int = 1) -> pd.DataFrame:
    """Granger causality in both directions. Murat & Tokat find it unidirectional --
    crack -> spot -- so testing only the direction of interest would beg the question."""
    data = df.dropna()
    first, second = data.columns[0], data.columns[1]
    rows = []
    for cause, effect in ((second, first), (first, second)):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pair = data[[effect, cause]].to_numpy(dtype=float)
            tests = grangercausalitytests(pair, maxlag=maxlag)
        f_stat, p_value = tests[maxlag][0]["ssr_ftest"][:2]
        rows.append(
            {
                "direction": f"{cause}->{effect}",
                "maxlag": maxlag,
                "f_stat": float(f_stat),
                "p_value": float(p_value),
            }
        )
    return pd.DataFrame(rows)


# --- forecast evaluation ----------------------------------------------------------


def _newey_west_dm(d: np.ndarray, h: int) -> tuple[float, float]:
    """Diebold-Mariano statistic on a loss differential, Newey-West corrected to h-1
    lags. Negative statistic == the first model (the VECM) has the lower loss."""
    from scipy import stats

    n = len(d)
    d_bar = float(d.mean())
    demeaned = d - d_bar
    gamma0 = float(demeaned @ demeaned) / n
    var = gamma0
    for lag in range(1, h):
        cov = float(demeaned[lag:] @ demeaned[:-lag]) / n
        var += 2.0 * (1.0 - lag / h) * cov
    if var <= 0 or n == 0:
        return float("nan"), float("nan")
    dm = d_bar / np.sqrt(var / n)
    p_value = 2.0 * (1.0 - stats.norm.cdf(abs(dm)))
    return float(dm), float(p_value)


def forecast_eval(
    df: pd.DataFrame,
    test_size: int = 60,
    rank: int = 1,
    k_ar_diff: int = 1,
    h: int = 1,
    target: str | None = None,
) -> dict[str, Any]:
    """Rolling-origin out-of-sample evaluation of the VECM against a random walk.

    At each origin the model is refit on **only** the data up to that origin, so nothing
    after the forecast date can influence it. RMSE, Theil's U (the RMSE ratio against the
    random walk, so <1 means the VECM wins) and a Diebold-Mariano test on the squared-
    error differential are returned.

    The spec also asks for a DM test against a *crude-futures* VECM. That benchmark
    cannot be built: it needs Spec 18's futures settlements, of which the lake holds
    none. `dm_vs_futures_vecm` is reported as None rather than silently omitted.
    """
    data = df.dropna()
    target_col = target or data.columns[0]
    target_pos = list(data.columns).index(target_col)

    n = len(data)
    start = n - test_size
    if start <= k_ar_diff + 2:
        raise ValueError("test_size leaves too little data to estimate the VECM")

    values = data.to_numpy(dtype=float)
    target_values = values[:, target_pos]

    errors_vecm, errors_rw = [], []
    for origin in range(start, n):
        train = values[:origin]
        actual = float(target_values[origin])
        try:
            fitted = VECM(
                train, k_ar_diff=k_ar_diff, coint_rank=rank, deterministic="ci"
            ).fit()
            prediction = float(fitted.predict(steps=h)[h - 1, target_pos])
        except (ValueError, np.linalg.LinAlgError):
            prediction = float(target_values[origin - 1])
        # A random walk's h-step forecast is simply the last observed value.
        naive = float(target_values[origin - 1])
        errors_vecm.append(actual - prediction)
        errors_rw.append(actual - naive)

    e_vecm = np.asarray(errors_vecm, dtype=float)
    e_rw = np.asarray(errors_rw, dtype=float)
    rmse_vecm = float(np.sqrt(np.mean(e_vecm**2)))
    rmse_rw = float(np.sqrt(np.mean(e_rw**2)))
    dm_stat, dm_p = _newey_west_dm(e_vecm**2 - e_rw**2, h)

    return {
        "rmse_vecm": rmse_vecm,
        "rmse_rw": rmse_rw,
        "theil_u": rmse_vecm / rmse_rw if rmse_rw else float("nan"),
        "dm_stat": dm_stat,
        "dm_p": dm_p,
        "dm_vs_futures_vecm": None,
        # Months where the VECM did worse than doing nothing -- the model card's
        # "exception count" per 00_TRADING_CONVENTIONS.md.
        "exceptions": int(np.sum(np.abs(e_vecm) > np.abs(e_rw))),
        "n_forecasts": len(e_vecm),
        # Per-origin errors, in origin order. Exposed so the no-look-ahead guard can
        # compare the overlapping prefix of two runs over different sample lengths --
        # aggregate RMSE alone cannot show that.
        "errors_vecm": e_vecm,
        "errors_rw": e_rw,
        "target": target_col,
        "h": h,
    }


# --- model card -------------------------------------------------------------------


def model_card(
    df: pd.DataFrame,
    test_size: int = 60,
    rank: int = 1,
    k_ar_diff: int | None = None,
    as_of: pd.Timestamp | None = None,
    rmse_ratio_trigger: float = 1.05,
) -> dict[str, Any]:
    """Every field `00_TRADING_CONVENTIONS.md` requires of a model card, plus the refit
    trigger the spec defines (rolling OOS RMSE ratio vs the random walk > 1.05).

    `exceptions` counts out-of-sample months where the VECM's absolute error exceeded the
    random walk's -- the "how often was this model worse than doing nothing" count.
    """
    data = df.dropna()
    lags = k_ar_diff if k_ar_diff is not None else select_lag_order(data)["chosen"]
    joh = johansen(data, k_ar_diff=lags)
    brk = structural_break(data)
    evaluation = forecast_eval(data, test_size=test_size, rank=rank, k_ar_diff=lags)

    theil_u = evaluation["theil_u"]
    breached = bool(theil_u > rmse_ratio_trigger)

    return {
        "estimation_start": data.index[0],
        "estimation_end": data.index[-1],
        "last_refit": pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.now(),
        "oos_status": "fail" if breached else "pass",
        "benchmark": BENCHMARK,
        "benchmark_note": (
            "Murat & Tokat's own RMSE/Theil figures are not in open sources -- the "
            "published comparison is qualitative only."
        ),
        "exceptions": evaluation["exceptions"],
        "break_date": brk["break_date"],
        "break_index": brk["break_index"],
        "sup_f": brk["sup_f"],
        "sup_f_date": brk["sup_f_date"],
        "rank": joh["rank"],
        "beta_y2": joh["beta_y2"],
        "k_ar_diff": lags,
        "theil_u": theil_u,
        "rmse_vecm": evaluation["rmse_vecm"],
        "rmse_rw": evaluation["rmse_rw"],
        "dm_stat": evaluation["dm_stat"],
        "dm_p": evaluation["dm_p"],
        "refit_triggered": breached,
        "rmse_ratio_trigger": rmse_ratio_trigger,
        "n_forecasts": evaluation["n_forecasts"],
        "spot_crack_deviation": (
            "Legs are spot, not crack futures -- a weaker claim than the paper's."
        ),
    }
