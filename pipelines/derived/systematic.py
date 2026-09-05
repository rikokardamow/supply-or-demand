"""Daily systematic positions: reads the lake, runs `core/strategies.py`, writes
`derived.pos.<strategy>.<root>` (Spec 21 Session B).

A strategy whose required ranks are absent is **skipped with a reason**, never written as
a flat series. Writing zeros would be the worst outcome available: a flat position is a
real trading decision, and storing one because data was missing would silently corrupt
every downstream attribution. The skips and their reasons are printed on every run and
returned by `rows_for_root` so the page can display them.

On the lake's current futures data (EIA ranks 1-4) that means `CARRY_1_13` (needs rank 13)
and `FWD_SPREAD_MR` (needs rank 7) are always skipped.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from core.storage import read_ts_long, write_ts_long
from core.strategies import (
    REGISTRY,
    StrategyInputs,
    available_strategies,
    build_positions,
    missing_ranks,
)

from pipelines.derived.curve_ranks import ADJUSTED_SUFFIX, RANK_ROOTS, RANKS

POSITION_ROOTS = RANK_ROOTS
UTIL_SERIES = "derived.cushing.util_decile"
UNIT = "position"


def _cot_series(root: str) -> str:
    return f"derived.cot.{root}.mm_pct_3y"


def read_legs() -> pd.DataFrame:
    wanted = [f"fut.{r}.{rank}.settle" for r in POSITION_ROOTS for rank in RANKS]
    wanted += [f"derived.curve.{r}.{ADJUSTED_SUFFIX}" for r in POSITION_ROOTS]
    wanted += [_cot_series(r) for r in POSITION_ROOTS]
    wanted.append(UTIL_SERIES)
    return read_ts_long(series_ids=wanted)


def _wide(long_df: pd.DataFrame, series_ids: list[str]) -> pd.DataFrame:
    rows = long_df[long_df["series_id"].isin(series_ids)]
    if rows.empty:
        return pd.DataFrame()
    return rows.pivot_table(index="ts", columns="series_id", values="value")


def inputs_for_root(long_df: pd.DataFrame, root: str) -> StrategyInputs | None:
    """Assemble every leg the registry can draw on for one root, or None if the root has
    no rank data at all."""
    rank_ids = [f"fut.{root}.{rank}.settle" for rank in RANKS]
    panel = _wide(long_df, rank_ids)
    if panel.empty:
        return None
    panel.columns = [str(c).split(".")[2] for c in panel.columns]
    panel = panel[[r for r in RANKS if r in panel.columns]].sort_index()

    adjusted = _wide(long_df, [f"derived.curve.{root}.{ADJUSTED_SUFFIX}"])
    f01_adj = (
        adjusted.iloc[:, 0].reindex(panel.index)
        if not adjusted.empty
        else panel["f01"]
    )

    util = _wide(long_df, [UTIL_SERIES])
    cot = _wide(long_df, [_cot_series(root)])
    return StrategyInputs(
        unadj=panel,
        f01_adj=f01_adj,
        util_decile=util.iloc[:, 0].reindex(panel.index).ffill() if not util.empty else None,
        cot_pct=cot.iloc[:, 0].reindex(panel.index).ffill() if not cot.empty else None,
    )


def position_rows(
    strategy: str, root: str, pos: pd.Series, ingested_at: pd.Timestamp
) -> pd.DataFrame:
    """One strategy's positions -> `ts_long` rows at `derived.pos.<strategy>.<root>`."""
    pos = pos.dropna()
    if pos.empty:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "series_id": f"derived.pos.{strategy}.{root}",
            "source": "derived",
            "ts": pos.index,
            "value": pos.to_numpy(dtype="float64"),
            "unit": UNIT,
            "geo": "US",
            "freq": "D",
            "revision_date": ingested_at,
        }
    )


def rows_for_root(
    long_df: pd.DataFrame, root: str, ingested_at: pd.Timestamp
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Positions for every runnable strategy, plus `{strategy: reason}` for the skips."""
    data = inputs_for_root(long_df, root)
    if data is None:
        return pd.DataFrame(), {}

    runnable = set(available_strategies(data.unadj))
    skipped = {
        name: (
            f"needs rank(s) {', '.join(f'f{r:02d}' for r in missing_ranks(strategy, data.unadj))}"
            f" -- {strategy.note}"
        )
        for name, strategy in REGISTRY.items()
        if name not in runnable
    }

    frames = []
    for name in runnable:
        try:
            frames.append(position_rows(name, root, build_positions(name, data), ingested_at))
        except Exception as exc:
            skipped[name] = f"{type(exc).__name__}: {exc}"

    frames = [f for f in frames if not f.empty]
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), skipped


def main() -> None:
    ingested_at = pd.Timestamp(datetime.now())
    long_df = read_legs()
    if long_df.empty:
        print("derived.pos: no futures legs in the lake", flush=True)
        return

    total = 0
    for root in POSITION_ROOTS:
        rows, skipped = rows_for_root(long_df, root, ingested_at)
        if rows.empty and not skipped:
            print(f"{root}: no rank data", flush=True)
            continue
        if not rows.empty:
            write_ts_long(rows, source="derived")
            total += len(rows)
            print(
                f"{root}: wrote {len(rows)} rows across "
                f"{rows['series_id'].nunique()} strategies",
                flush=True,
            )
        for name, reason in sorted(skipped.items()):
            print(f"  {root}/{name}: SKIPPED -- {reason}", flush=True)

    print(f"derived.pos: {total} total rows written", flush=True)


if __name__ == "__main__":
    main()
