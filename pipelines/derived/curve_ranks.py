"""Derived curve series from EIA's **rank-published** futures, not contract-coded ones.

`pipelines/derived/curve.py` builds ranks from contract codes plus expiries via
`core.curve.nearby_panel`, reading `pipelines/futures/series_meta.py`. EIA's futures route
publishes "Contract 1..4" directly and writes no `series_meta` rows at all, so that
pipeline silently skips every EIA root — which is why `derived.spread.*` and
`derived.curve.*` were empty despite 113,661 real futures rows sitting in the lake.

This module is the missing path. It reads the rank series straight out of the lake and
writes what four ranks can actually support:

- `derived.spread.<root>.s12` / `.s13` / `.s23`
- `derived.curve.<root>.cv123` (convexity) and `.regime`
- `derived.curve.<root>.f01_adj` — the ratio back-adjusted front month Spec 21's
  momentum, value and return signals need, and which nothing in the lake provided

`pipelines/derived/curve.py` writes the same `derived.spread.*`/`derived.curve.*` ids from
contract-coded data. The two cannot currently collide because that path has no data at all
(no `series_meta` rows exist), but if a real IBKR or manual-CSV pull ever lands, decide
explicitly which source owns a given root rather than letting both write the same key.

Roll dates come from each root's **published exchange expiry rule**
(`core.curve.nymex_expiry`), not inferred from prices. An earlier price-based heuristic
fired 88 times a year against a true ~12 and *raised* realised volatility instead of
lowering it -- WTI's f01-f02 spread is routinely narrower than one day's move, so
"correcting" a non-roll day injects the spread as a spurious return. Validated on the real
lake: 11.9 rolls/year, median roll on the 22nd, and adjusted vol 38.9% against raw 39.9%.

**What four ranks cannot support**, and which is therefore deliberately absent rather than
approximated: `s16` and `s1_12` (need ranks 6 and 12), Dec-Dec spreads and the roll
calendar (need real contract codes and expiries), and Bouchouev's own C(1,13) carry
anchor. EIA published ranks 1-4 only.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from core.curve import REGIME_CODES, back_adjust_from_ranks, convexity, curve_regime
from core.storage import read_ts_long, write_ts_long

RANK_ROOTS = ("cl", "rb", "ho", "hu")
"""The roots EIA publishes NYMEX ranks for. No Brent, gasoil or TTF from this source."""

RANKS = ("f01", "f02", "f03", "f04")
ADJUSTED_SUFFIX = "f01_adj"

# Only the spreads four ranks can actually express. s16/s1_12 need ranks 6 and 12.
_SPREADS = {"s12": (1, 2), "s13": (1, 3), "s23": (2, 3)}

UNIT = "USD/bbl"
_GAL_ROOTS = {"rb", "ho", "hu"}


def rank_series_ids(root: str) -> list[str]:
    return [f"fut.{root}.{rank}.settle" for rank in RANKS]


def read_rank_legs() -> pd.DataFrame:
    wanted = [sid for root in RANK_ROOTS for sid in rank_series_ids(root)]
    return read_ts_long(series_ids=wanted)


def rank_panel_for(long_df: pd.DataFrame, root: str) -> pd.DataFrame:
    """Lake rows -> wide panel with f01..f04 columns for one root."""
    prefix = f"fut.{root}."
    rows = long_df[long_df["series_id"].str.startswith(prefix)]
    if rows.empty:
        return pd.DataFrame()

    panel = rows.pivot_table(index="ts", columns="series_id", values="value")
    panel.columns = [str(c).split(".")[2] for c in panel.columns]
    present = [r for r in RANKS if r in panel.columns]
    return panel[present].sort_index()


def _rows(series_id: str, values: pd.Series, root: str, ingested_at: pd.Timestamp) -> pd.DataFrame:
    values = values.dropna()
    if values.empty:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "series_id": series_id,
            "source": "derived",
            "ts": values.index,
            "value": values.to_numpy(dtype="float64"),
            "unit": "USD/gal" if root in _GAL_ROOTS else UNIT,
            "geo": "US",
            "freq": "D",
            "revision_date": ingested_at,
        }
    )


def derived_rows_for_root(
    long_df: pd.DataFrame, root: str, ingested_at: pd.Timestamp
) -> pd.DataFrame:
    """Every derived series computable for one root from its rank panel."""
    panel = rank_panel_for(long_df, root)
    if panel.empty or "f01" not in panel.columns or "f02" not in panel.columns:
        return pd.DataFrame()

    frames = []
    for name, (near, far) in _SPREADS.items():
        near_col, far_col = f"f{near:02d}", f"f{far:02d}"
        if near_col in panel.columns and far_col in panel.columns:
            spread = panel[near_col] - panel[far_col]
            frames.append(_rows(f"derived.spread.{root}.{name}", spread, root, ingested_at))

    if all(c in panel.columns for c in ("f01", "f02", "f03")):
        frames.append(
            _rows(f"derived.curve.{root}.cv123", convexity(panel), root, ingested_at)
        )
        regime = curve_regime(panel)["state"].map(REGIME_CODES).astype(float)
        frames.append(_rows(f"derived.curve.{root}.regime", regime, root, ingested_at))

    # Back-adjusted front month -- returns only, never spreads (conventions' own rule).
    frames.append(
        _rows(
            f"derived.curve.{root}.{ADJUSTED_SUFFIX}",
            back_adjust_from_ranks(panel, root),
            root,
            ingested_at,
        )
    )

    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main() -> None:
    ingested_at = pd.Timestamp(datetime.now())
    long_df = read_rank_legs()
    if long_df.empty:
        print("derived.curve_ranks: no rank series in the lake", flush=True)
        return

    total = 0
    for root in RANK_ROOTS:
        try:
            rows = derived_rows_for_root(long_df, root, ingested_at)
            if rows.empty:
                print(f"{root}: no rank data", flush=True)
                continue
            write_ts_long(rows, source="derived")
            total += len(rows)
            print(
                f"{root}: wrote {len(rows)} rows across "
                f"{rows['series_id'].nunique()} series",
                flush=True,
            )
        except Exception as exc:
            print(f"{root}: FAILED ({type(exc).__name__}: {exc})", flush=True)

    print(f"derived.curve_ranks: {total} total rows written", flush=True)


if __name__ == "__main__":
    main()
