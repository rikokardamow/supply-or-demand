"""Publish the lake's directional flows into `serving.flows` (Spec 32 §2).

Cross-source by nature -- `serving.flows` is one table carrying every corridor this
project tracks, and `source` is part of its primary key, so each source's rows coexist
without collision. Lives under `pipelines/derived/` for the same reason
`fundamentals.py` does: it reads several sources rather than owning one.

**`period` is measured, not taken from the spec.** Spec 32 §2 annotates the column
`-- 'weekly','monthly'`, but neither value describes what this lake actually holds.
Measured live 2026-09-09 from the median gap between consecutive observations on a single
corridor:

| Source | Mode | Median gap | Period |
|---|---|---|---|
| eia | `grid_interchange` | 1 hour | `hourly` |
| eia | `pipeline`/`rail`/`tanker_barge` | 31 days | `monthly` |
| entsog | `pipeline`/`nomination` | 1 day | `daily` |

Publishing all three as `'weekly'` or `'monthly'` would put a false cadence in the column
the UI filters on, and would collapse hourly grid interchange onto the monthly PADD
movements' primary key. The real cadence is used instead, and this note is the spec
correction.
"""

from __future__ import annotations

from datetime import UTC
from typing import Final, cast

import pandas as pd
from core.publish import publish
from core.storage import read_flows

SOURCES: Final = ("eia", "entsog")

SERVING_FLOWS_COLUMNS: Final[list[str]] = [
    "source",
    "from_node",
    "to_node",
    "ts",
    "period",
    "value",
    "unit",
    "mode",
]

# Measured from the lake, not assumed -- see the module docstring. Keyed by the `mode`
# each pipeline writes, since that is what actually distinguishes the cadences here.
PERIOD_BY_MODE: Final[dict[str, str]] = {
    "grid_interchange": "hourly",
    "pipeline": "daily",
    "nomination": "daily",
    "rail": "monthly",
    "tanker_barge": "monthly",
}

# `pipeline` means different cadences in different pipelines: ENTSOG publishes daily gas
# flows, EIA publishes monthly inter-PADD crude movements. Mode alone cannot separate
# them, so source wins where the two disagree.
PERIOD_BY_SOURCE_AND_MODE: Final[dict[tuple[str, str], str]] = {
    ("eia", "pipeline"): "monthly",
}


def period_for(source: str, mode: str) -> str:
    """The real observation cadence for a flows row.

    An unrecognised mode raises rather than defaulting: `period` is part of
    `serving.flows`' primary key, so guessing it wrong would silently overwrite one
    corridor's rows with another's.
    """
    override = PERIOD_BY_SOURCE_AND_MODE.get((source, mode))
    if override is not None:
        return override
    try:
        return PERIOD_BY_MODE[mode]
    except KeyError:
        raise ValueError(
            f"no known cadence for source={source!r} mode={mode!r} -- measure it and add"
            " it to PERIOD_BY_MODE rather than letting it default"
        ) from None


def to_serving_flows(df: pd.DataFrame) -> pd.DataFrame:
    """A lake `flows` frame as `serving.flows` rows."""
    if df.empty:
        return pd.DataFrame(columns=SERVING_FLOWS_COLUMNS)

    out = df.copy()
    out["period"] = [period_for(s, m) for s, m in zip(out["source"], out["mode"], strict=True)]

    # Sum across the physical points feeding one corridor. ENTSOG maps 21 interconnection
    # points onto 8 corridors (pipelines/entsog/CLAUDE.md), and the lake's `flows` schema
    # carries no point dimension -- so LNG->FR, NO->DE and NO->GB each arrive as two rows
    # per timestamp, distinguishable only by value. Confirmed live 2026-09-09: 4,365 such
    # groups, always exactly two rows, and no other corridor affected.
    #
    # Summing is what a corridor total means; letting publish() dedup them instead would
    # report a single terminal's send-out as the whole corridor, roughly halving it. The
    # grouping keeps `mode`, so a corridor genuinely carrying both a pipeline and a
    # tanker/barge movement on one date stays two rows rather than being merged.
    key = ["source", "from_node", "to_node", "ts", "period", "mode"]
    # cast: with as_index=False this returns a DataFrame at runtime, but pandas-stubs
    # types the ["value"].sum() chain as a Series.
    summed = cast(
        pd.DataFrame, out.groupby([*key, "unit"], as_index=False, sort=False)["value"].sum()
    )
    return summed[SERVING_FLOWS_COLUMNS].reset_index(drop=True)


def main() -> None:
    frames = [read_flows(source=source) for source in SOURCES]
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    if df.empty:
        raise RuntimeError(
            f"read 0 flows rows across sources {SOURCES} -- the lake is empty or"
            " unreadable; refusing to report success."
        )

    rows = to_serving_flows(df)
    published = publish(
        "flows",
        rows,
        # Spec 32 §2: as_of is the data's own latest timestamp, never wall-clock.
        as_of=rows["ts"].max().to_pydatetime().replace(tzinfo=UTC),
        source_note=(
            "Directional flows: EIA inter-PADD crude movements (monthly) and RTO grid"
            " interchange (hourly), ENTSOG EU gas (daily)"
        ),
        # `mode` is part of the key: a corridor genuinely carries several transport
        # modes at the same timestamp (PADD1->PADD2 in Feb 1986 has both a pipeline and
        # a tanker/barge movement). The spec's original key omitted it and silently
        # dropped ~15% of the rows -- see the migration
        # 20260909160000_flows_key_includes_mode.sql.
        key=["source", "from_node", "to_node", "ts", "period", "mode"],
        pipeline="flows",
    )
    corridors = rows.groupby(["from_node", "to_node"]).ngroups
    print(f"published {published} flows rows across {corridors} corridors")


if __name__ == "__main__":
    main()
