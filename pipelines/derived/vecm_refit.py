"""Monthly refit of the Spec 20 crack VECM (Murat & Tokat 2009).

Reads the lake, calls `core/vecm.py`'s pure functions, and writes a model card as a
plain Parquet manifest -- following `pipelines/futures/series_meta.py`'s precedent, since
`core/storage.py` still has no persisted-table mechanism and a model card is not a
`ts_long` series.

Registered in `infra/run_scheduled.py`'s `monthly` cadence group, per the spec's "refit
monthly". The spec's other two triggers -- an annual break test, and a forced refit when
the rolling 12-month OOS RMSE ratio against the random walk exceeds 1.05 -- are carried on
the card itself (`refit_triggered`), so a breach is visible on the page rather than only
in a log.

**The model is estimated on spot legs, not crack futures.** See `core/vecm.py`'s module
docstring: this is a weaker claim than the paper's and must never be presented as a
replication. The caveat travels on the card itself, in `deviation`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from core.storage import read_ts_long
from core.vecm import (
    forecast_eval,
    granger,
    johansen,
    select_lag_order,
    structural_break,
    to_monthly,
    unit_root_tests,
)

WTI_SERIES = "fred.dcoilwtico"
CRACK_SERIES = "derived.crack.us321.spot"

CARD_DIR = Path("data/lake/vecm")
CARD_PATH = CARD_DIR / "model_card.parquet"

MIN_POST_BREAK = 60
"""Months. Below this the post-break sample is too short to estimate a VECM on, and the
refit falls back to the full sample rather than fitting something meaningless."""

CARD_COLUMNS = [
    "model",
    "as_of",
    "sample",
    "estimation_start",
    "estimation_end",
    "post_break_start",
    "n_obs",
    "k_ar_diff",
    "rank",
    "beta_crack",
    "break_date",
    "sup_f",
    "sup_f_date",
    "wti_i1",
    "crack_i1",
    "granger_crack_to_spot_p",
    "granger_spot_to_crack_p",
    "rmse_vecm",
    "rmse_rw",
    "theil_u",
    "dm_stat",
    "dm_p",
    "exceptions",
    "n_forecasts",
    "oos_status",
    "benchmark",
    "refit_triggered",
    "deviation",
]

DEVIATION = (
    "Legs are spot (FRED WTI + NYH product spots), not the crack futures Murat & Tokat "
    "use -- a weaker, different claim, not a replication."
)


def read_legs() -> pd.DataFrame:
    """Wide panel of the two lake series this model needs."""
    long_df = read_ts_long(series_ids=[WTI_SERIES, CRACK_SERIES])
    if long_df.empty:
        return pd.DataFrame()
    return long_df.pivot_table(index="ts", columns="series_id", values="value")


def build_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Wide daily lake panel -> the spec's monthly two-variable frame.

    log(WTI spot) and the 3:2:1 crack **in levels** -- the crack is not logged, both
    because the spec says levels and because a crack can legitimately go negative.
    """
    wti = to_monthly(panel[WTI_SERIES].dropna())
    crack = to_monthly(panel[CRACK_SERIES].dropna())
    return pd.DataFrame({"log_wti": np.log(wti), "crack321": crack}).dropna()


def refit(
    panel: pd.DataFrame,
    test_size: int = 60,
    as_of: pd.Timestamp | None = None,
    min_post_break: int = MIN_POST_BREAK,
    rmse_ratio_trigger: float = 1.05,
) -> dict[str, Any]:
    """Full diagnostic pass: unit roots, break, Johansen, Granger, rolling-origin OOS.

    Estimated on the post-break sample where one is long enough, with the full sample's
    own span still reported beside it, per the spec.
    """
    data = panel.dropna()
    brk = structural_break(data)

    post_break = data.loc[brk["break_date"] :] if brk["break_date"] is not None else data
    use_post_break = len(post_break) >= min_post_break and len(post_break) > test_size + 10
    estimation = post_break if use_post_break else data

    lags = select_lag_order(estimation)["chosen"]
    joh = johansen(estimation, k_ar_diff=lags)
    causality = granger(estimation, maxlag=lags).set_index("direction")["p_value"]
    evaluation = forecast_eval(estimation, test_size=test_size, k_ar_diff=lags)

    theil_u = evaluation["theil_u"]
    return {
        "model": "crack_vecm_murat_tokat",
        "as_of": pd.Timestamp(as_of) if as_of is not None else pd.Timestamp(datetime.now()),
        "sample": "post_break" if use_post_break else "full",
        "estimation_start": data.index[0],
        "estimation_end": data.index[-1],
        "post_break_start": estimation.index[0],
        "n_obs": len(estimation),
        "k_ar_diff": lags,
        "rank": joh["rank"],
        "beta_crack": joh["beta_y2"],
        "break_date": brk["break_date"],
        "sup_f": brk["sup_f"],
        "sup_f_date": brk["sup_f_date"],
        "wti_i1": unit_root_tests(estimation["log_wti"])["i1"],
        "crack_i1": unit_root_tests(estimation["crack321"])["i1"],
        "granger_crack_to_spot_p": float(causality.get("crack321->log_wti", float("nan"))),
        "granger_spot_to_crack_p": float(causality.get("log_wti->crack321", float("nan"))),
        "rmse_vecm": evaluation["rmse_vecm"],
        "rmse_rw": evaluation["rmse_rw"],
        "theil_u": theil_u,
        "dm_stat": evaluation["dm_stat"],
        "dm_p": evaluation["dm_p"],
        "exceptions": evaluation["exceptions"],
        "n_forecasts": evaluation["n_forecasts"],
        "oos_status": "fail" if theil_u > rmse_ratio_trigger else "pass",
        "benchmark": "random walk (qualitative vs Murat & Tokat -- their own RMSE/Theil "
        "figures are not in open sources)",
        "refit_triggered": bool(theil_u > rmse_ratio_trigger),
        "deviation": DEVIATION,
    }


def card_to_row(card: dict[str, Any]) -> pd.DataFrame:
    """Card -> a single flat, Parquet-safe row in CARD_COLUMNS order."""
    return pd.DataFrame([{column: card[column] for column in CARD_COLUMNS}])


def write_model_card(row: pd.DataFrame) -> None:
    """Append + keep the latest row per (model, as_of) -- the series_meta manifest
    pattern, so a re-run on the same day corrects rather than duplicates."""
    CARD_DIR.mkdir(parents=True, exist_ok=True)
    if CARD_PATH.exists():
        combined = pd.concat([pd.read_parquet(CARD_PATH), row[CARD_COLUMNS]], ignore_index=True)
    else:
        combined = row[CARD_COLUMNS]
    combined = combined.drop_duplicates(subset=["model", "as_of"], keep="last")
    combined.to_parquet(CARD_PATH, index=False)


def read_model_card() -> pd.DataFrame:
    if not CARD_PATH.exists():
        return pd.DataFrame(columns=CARD_COLUMNS)
    return pd.read_parquet(CARD_PATH)


def main() -> None:
    legs = read_legs()
    if legs.empty or WTI_SERIES not in legs.columns or CRACK_SERIES not in legs.columns:
        print("vecm_refit: crack or WTI legs missing from the lake", flush=True)
        return

    panel = build_panel(legs)
    if len(panel) < MIN_POST_BREAK:
        print(f"vecm_refit: only {len(panel)} months available, need {MIN_POST_BREAK}", flush=True)
        return

    card = refit(panel)
    write_model_card(card_to_row(card))
    print(
        f"vecm_refit: {card['sample']} sample, n={card['n_obs']}, rank={card['rank']}, "
        f"beta={card['beta_crack']:.4f}, Theil U={card['theil_u']:.4f} "
        f"({card['oos_status']}), break={card['break_date'].date()}",
        flush=True,
    )


if __name__ == "__main__":
    main()
