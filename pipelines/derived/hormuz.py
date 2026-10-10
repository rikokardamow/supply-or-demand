"""Writes the Hormuz closure scenario into the lake as `derived.hormuz.scenario.*`.

Reads assumptions, calls core.hormuz's pure functions, writes `ts_long` rows back --
the same shape as every other module in this package.

**Assumptions are split on purpose.** `recovery_ceilings.csv` and `flow_share.csv` are
committed beside this file: they are the user's own scenario choices and belong in a diff,
following the `pipelines/opec_momr/quotas.csv` precedent for a hand-maintained reference
file. `baselines.csv` is read from the git-ignored `data/manual/hormuz/` drop instead,
because the undisrupted and disrupted rates derive from a licensed Bloomberg Intelligence
workbook and must not reach a remote.

Not registered in infra/run_scheduled.py. A scenario changes when its assumptions change,
not on a clock, so re-running it nightly would rewrite identical rows and imply the
numbers were refreshed from somewhere. Run it by hand after editing an assumption.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from core.hormuz import ProducerDisruption, scenario_path, total_supply
from core.storage import write_ts_long

ASSUMPTIONS_DIR = Path(__file__).parent / "hormuz"
BASELINES_DIR = Path("data/manual/hormuz")

UNIT_MBD = "mb/d"


def _slug(producer: str) -> str:
    return producer.strip().lower().replace(" ", "_")


def read_levers(directory: Path) -> tuple[dict[str, float], dict[pd.Timestamp, float | None]]:
    """The committed scenario levers: a recovery ceiling per producer, and the assumed
    share of normal Hormuz flows per quarter.

    A blank `open_share` reads as None, never 0.0 -- the source workbook writes its
    pre-disruption quarter as "-", and zero would assert a total closure instead.
    """
    ceilings_df = pd.read_csv(directory / "recovery_ceilings.csv")
    ceilings = {
        str(record["producer"]): float(record["recovery_ceiling"])
        for record in ceilings_df.to_dict("records")
    }

    flow_df = pd.read_csv(directory / "flow_share.csv")
    quarters = pd.to_datetime(flow_df["quarter"])
    shares = pd.to_numeric(flow_df["open_share"], errors="coerce")
    flow: dict[pd.Timestamp, float | None] = {
        pd.Timestamp(quarter): (None if pd.isna(share) else float(share))
        for quarter, share in zip(quarters, shares, strict=True)
    }
    return ceilings, flow


def read_baselines(directory: Path) -> pd.DataFrame:
    """The undisrupted and disrupted rates per producer per quarter."""
    path = directory / "baselines.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. The Hormuz baselines are a git-ignored drop -- see this "
            f"module's docstring for why, and pipelines/derived/hormuz/README.md for the "
            f"schema."
        )
    baselines = pd.read_csv(path)
    baselines["quarter"] = pd.to_datetime(baselines["quarter"])
    return baselines


def build_scenario_rows(
    levers_dir: Path, baselines_dir: Path, ingested_at: pd.Timestamp
) -> pd.DataFrame:
    """Assumptions -> `ts_long` rows. Quarters with no known flow share write nothing.

    Two directories, not one: the levers are committed beside this module, the baselines
    sit in the git-ignored drop. Collapsing them into a single argument is how this
    function first shipped, and it ran green in tests while failing on the real layout.
    """
    ceilings, flow = read_levers(levers_dir)
    baselines = read_baselines(baselines_dir)

    frames: list[pd.DataFrame] = []
    for quarter, open_share in flow.items():
        if open_share is None:
            continue
        quarter_rows = baselines[baselines["quarter"] == quarter]
        if quarter_rows.empty:
            continue

        producers = [
            ProducerDisruption(
                producer=str(record["producer"]),
                undisrupted_mbd=float(record["undisrupted_mbd"]),
                disrupted_mbd=float(record["disrupted_mbd"]),
                recovery_ceiling=ceilings[str(record["producer"])],
            )
            for record in quarter_rows.to_dict("records")
        ]
        path = scenario_path(producers, {quarter: open_share})
        totals = total_supply(path)

        per_producer = pd.DataFrame(
            {
                "series_id": [
                    f"derived.hormuz.scenario.{_slug(p)}.supply" for p in path["producer"]
                ],
                "ts": path["ts"],
                "value": path["supply_mbd"],
                "unit": UNIT_MBD,
            }
        )
        gulf_total = pd.DataFrame(
            {
                "series_id": "derived.hormuz.scenario.gulf_total.supply",
                "ts": totals.index,
                "value": totals.to_numpy(dtype="float64"),
                "unit": UNIT_MBD,
            }
        )
        assumed_share = pd.DataFrame(
            {
                "series_id": "derived.hormuz.scenario.open_share",
                "ts": [quarter],
                "value": [float(open_share)],
                "unit": "%",
            }
        )
        frames.extend([per_producer, gulf_total, assumed_share])

    if not frames:
        return pd.DataFrame(
            columns=["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]
        )

    rows = pd.concat(frames, ignore_index=True).dropna(subset=["value"])
    rows["source"] = "derived"
    rows["geo"] = "GULF"
    rows["freq"] = "Q"
    rows["revision_date"] = ingested_at
    rows["value"] = rows["value"].astype("float64")
    return rows[["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]]


def main() -> None:
    ingested_at = pd.Timestamp(datetime.now(UTC)).tz_localize(None)
    rows = build_scenario_rows(ASSUMPTIONS_DIR, BASELINES_DIR, ingested_at)
    if rows.empty:
        print("hormuz: no quarter has a known flow share -- nothing written", flush=True)
        return
    write_ts_long(rows, source="derived")
    print(
        f"hormuz: wrote {len(rows)} scenario rows across "
        f"{rows['series_id'].nunique()} series -- these are CONDITIONAL on the "
        f"assumptions in {ASSUMPTIONS_DIR} and {BASELINES_DIR}",
        flush=True,
    )


if __name__ == "__main__":
    main()
