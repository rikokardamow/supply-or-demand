"""Implied Renewable Fuel Standard mandate, month by month, from the EIA STEO baseline.

Reads the non-renewable gasoline and distillate demand series from the lake, applies EPA's
percentage standards (the committed reference file), and writes the implied mandate in billions
of RINs back to the lake. The arithmetic is `core.rin`; this module only joins, labels and
writes.

Series ids
----------
    derived.rin.mandate.<category>.<observed|projected>.<final|proposed>

* ``<category>``: ``cellulosic``, ``biomass_based_diesel``, ``advanced`` or ``total``.
* ``observed`` or ``projected``: ``projected`` if EITHER demand input for that month is a STEO
  projection, ``observed`` only if both are measured. A mandate is only as measured as the
  demand under it.
* ``final`` or ``proposed``: the ``status`` of the EPA percentage-standard row used, read from
  the reference, never assumed.

Unit: ``billion RINs``. Monthly (``freq="M"``), ``geo="US"``, ``source="derived"``.

Rules
-----
* Observed beats projected. The lake has no delete path, so when STEO's history boundary moves
  a month can sit under both ``.observed`` and ``.projected``; :func:`prefer_observed` keeps
  the observed value.
* The denominator is the registered non-renewable pair (``RFS_DENOMINATOR_CODES``, the ``_P``
  series), never the headline ``MGTCPUSX`` / ``DFTCPUS``, which include blended renewables.
* The day count is the calendar length of each row's own month (leap years included).
* No data is not zero: a month missing either demand input, or in a year with no standard for
  a category, gets no row. Nothing is filled, carried forward or zeroed.
* Standards are an argument, not discovered by path (the hormuz lesson).

No volume comparison is made, so the ``requirement`` / ``applicable`` basis of EPA's volume
targets does not arise here. A caller that compares these figures with a volume target should
use the ``applicable`` basis where both exist, because EPA's percentage standards are
computed on the total applicable volume.

Not scheduled: run ``python -m pipelines.derived.rin`` by hand after a STEO pull.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from core.failures import fails_loudly, record_failure
from core.rin import implied_mandate_billion_rins, rfs_denominator_gallons
from core.storage import read_ts_long, write_ts_long

from pipelines.eia.steo_series import RFS_DENOMINATOR_CODES
from pipelines.epa.reference import load_percentage_standards

ID_PREFIX = "derived.rin.mandate"
UNIT = "billion RINs"
GASOLINE_CODE, DISTILLATE_CODE = RFS_DENOMINATOR_CODES
# Lake ids are `steo.<lowercased code>.<label>` (pipelines/eia/pull_steo.py).
GASOLINE_SERIES, DISTILLATE_SERIES = (f"steo.{code.lower()}" for code in RFS_DENOMINATOR_CODES)
DENOMINATOR_SERIES = (GASOLINE_SERIES, DISTILLATE_SERIES)
_LABELS = ("observed", "projected")


def days_in_period(period_start: pd.Timestamp) -> int:
    """Calendar length of the month starting at ``period_start`` (29 for February 2028)."""
    return int(period_start.days_in_month)


def prefer_observed(steo: pd.DataFrame) -> pd.DataFrame:
    """One row per (series, month): the observed value wherever a month exists under both.

    ``steo`` holds lake rows with ids ``steo.<code>.<observed|projected>``. Rows whose id has
    another shape are dropped. Within one (series, month, label) the latest ``revision_date``
    wins. Returns ``series`` (id without label), ``label``, ``ts``, ``value`` and the original
    ``series_id``.
    """
    if steo.empty:
        return pd.DataFrame(columns=["series_id", "series", "label", "ts", "value"])
    split = steo["series_id"].str.rsplit(".", n=1, expand=True)
    frame = steo.assign(series=split[0], label=split[1])
    frame = frame[frame["label"].isin(_LABELS)]
    frame = frame.sort_values("revision_date").drop_duplicates(
        ["series", "label", "ts"], keep="last"
    )
    frame = frame.assign(_rank=frame["label"].map({"observed": 0, "projected": 1}))
    frame = frame.sort_values("_rank").drop_duplicates(["series", "ts"], keep="first")
    return frame[["series_id", "series", "label", "ts", "value"]].reset_index(drop=True)


def build_mandate_rows(
    steo: pd.DataFrame, standards: pd.DataFrame, ingested_at: pd.Timestamp
) -> pd.DataFrame:
    """STEO demand rows plus percentage standards -> ``ts_long`` mandate rows.

    ``steo`` is the lake frame for the two denominator series (any other series is ignored);
    ``standards`` is ``load_percentage_standards()``-shaped (``year``, ``category``, ``pct``,
    ``status``). Empty frame when nothing can be derived.
    """
    if standards.duplicated(["year", "category"]).any():
        raise ValueError("standards: duplicate year/category")
    chosen = prefer_observed(steo)
    chosen = chosen[chosen["series"].isin(DENOMINATOR_SERIES)]

    values = chosen.pivot(index="ts", columns="series", values="value")
    labels = chosen.pivot(index="ts", columns="series", values="label")
    if not set(DENOMINATOR_SERIES) <= set(values.columns):
        return pd.DataFrame()
    both = values[list(DENOMINATOR_SERIES)].dropna()  # a missing leg is not a denominator
    if both.empty:
        return pd.DataFrame()

    months = pd.DataFrame(
        {
            "ts": both.index,
            "gasoline": both[GASOLINE_SERIES].to_numpy(),
            "distillate": both[DISTILLATE_SERIES].to_numpy(),
            "label": [
                "projected"
                if "projected" in labels.loc[ts, list(DENOMINATOR_SERIES)].tolist()
                else "observed"
                for ts in both.index
            ],
        }
    )
    months["year"] = months["ts"].dt.year
    months["gallons"] = [
        rfs_denominator_gallons(g, d, days_in_period(ts))
        for g, d, ts in zip(months["gasoline"], months["distillate"], months["ts"], strict=True)
    ]
    joined = months.merge(standards[["year", "category", "pct", "status"]], on="year")
    if joined.empty:
        return pd.DataFrame()

    joined["value"] = [
        implied_mandate_billion_rins(gal, pct)
        for gal, pct in zip(joined["gallons"], joined["pct"], strict=True)
    ]
    joined = joined.dropna(subset=["value"])
    if joined.empty:
        return pd.DataFrame()

    return pd.DataFrame(
        {
            "series_id": (
                f"{ID_PREFIX}."
                + joined["category"]
                + "."
                + joined["label"]
                + "."
                + joined["status"]
            ),
            "source": "derived",
            "ts": joined["ts"],
            "value": joined["value"].to_numpy(dtype="float64"),
            "unit": UNIT,
            "geo": "US",
            "freq": "M",
            "revision_date": ingested_at,
        }
    ).reset_index(drop=True)


@fails_loudly("derived.rin")
def main() -> None:
    steo = read_ts_long(
        series_ids=[f"{s}.{label}" for s in DENOMINATOR_SERIES for label in _LABELS]
    )
    if steo.empty:
        record_failure("derived.rin", RuntimeError("no STEO denominator rows in the lake"))
        return

    rows = build_mandate_rows(steo, load_percentage_standards(), pd.Timestamp(datetime.now()))
    if rows.empty:
        record_failure(
            "derived.rin", RuntimeError("no month has both demand inputs and a standard")
        )
        return

    write_ts_long(rows, source="derived")
    counts = rows["series_id"].str.split(".").str[-2].value_counts()
    print(
        f"derived.rin: wrote {len(rows)} rows across {rows['series_id'].nunique()} series "
        f"({int(counts.get('observed', 0))} observed, {int(counts.get('projected', 0))} projected)",
        flush=True,
    )


if __name__ == "__main__":
    main()
