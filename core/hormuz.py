"""Strait of Hormuz closure overlay -- scenario supply for the Gulf producers.

Ported from the `Hormuz Scenarios` sheet of a Bloomberg Intelligence supply-demand
workbook. The mechanism is the workbook's own (its cell F25), kept verbatim so the port
can be checked against its published figures:

    scenario = disrupted + (undisrupted - disrupted) * open_share * recovery_ceiling

`recovery_ceiling` is a cap on how much of the lost rate a producer ever regains, not a
speed: at a fully reopened strait a producer with a ceiling of 0.8 is still 20% of its
loss short. The workbook labels it "Ramp (Recovery) Factor", which reads like a rate; the
formula is a ceiling, and the name here says so.

**This is a scenario, not a forecast.** Every value is conditional on an assumed flow
share. Anything that displays these numbers states the assumption beside them and does not
share an axis with a base case undistinguished.

Pure transforms -- no lake I/O. Writing lives in pipelines/derived/hormuz.py.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ProducerDisruption:
    """One producer's two bounding rates and its recovery cap, all in mb/d."""

    producer: str
    undisrupted_mbd: float
    disrupted_mbd: float
    recovery_ceiling: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.recovery_ceiling <= 1.0:
            raise ValueError(
                f"{self.producer}: recovery_ceiling must lie in [0, 1], "
                f"got {self.recovery_ceiling}"
            )
        if self.disrupted_mbd > self.undisrupted_mbd:
            raise ValueError(
                f"{self.producer}: disrupted_mbd ({self.disrupted_mbd}) exceeds "
                f"undisrupted_mbd ({self.undisrupted_mbd}) -- a floor above the ceiling "
                f"would make supply rise as the strait closes"
            )


def scenario_supply(producer: ProducerDisruption, open_share: float | None) -> float:
    """Supply for one producer at an assumed share of normal Hormuz flows.

    `open_share` of None (or NaN) means *not known*, and returns NaN. The source workbook
    writes its first quarter as "-" for exactly this reason; reading that as 0.0 would
    assert a total closure, which is the opposite of what it says.
    """
    if open_share is None or (isinstance(open_share, float) and math.isnan(open_share)):
        return float("nan")
    if not 0.0 <= open_share <= 1.0:
        raise ValueError(f"flow share must lie in [0, 1], got {open_share}")

    lost = producer.undisrupted_mbd - producer.disrupted_mbd
    return producer.disrupted_mbd + lost * open_share * producer.recovery_ceiling


def scenario_path(
    producers: Sequence[ProducerDisruption],
    open_share_by_quarter: Mapping[pd.Timestamp, float | None],
) -> pd.DataFrame:
    """One row per producer per quarter, carrying the assumption that produced it."""
    rows = [
        {
            "ts": ts,
            "producer": producer.producer,
            "supply_mbd": scenario_supply(producer, open_share),
            "open_share": open_share,
        }
        for ts, open_share in open_share_by_quarter.items()
        for producer in producers
    ]
    return pd.DataFrame(rows, columns=["ts", "producer", "supply_mbd", "open_share"])


def total_supply(path: pd.DataFrame) -> pd.Series:
    """Gulf total per quarter, NaN wherever any producer is unknown.

    Summing around a missing producer would publish a number that looks like a regional
    total and is not one -- the degenerate-input rule in specs/00_TRADING_CONVENTIONS.md.
    """
    grouped = path.groupby("ts")["supply_mbd"]
    return grouped.apply(lambda values: values.sum(min_count=len(values)))
