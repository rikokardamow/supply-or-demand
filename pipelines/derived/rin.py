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
* Twins across runs. The lake has no delete path and the id carries the label and the status,
  so a month first written as ``...projected.final`` survives beside the ``...observed.final``
  a later run writes once STEO's boundary moves (likewise proposed then final). Read
  ``derived.rin.mandate.*`` through :func:`resolve_mandate_twins`, never raw.
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

from pipelines.eia.steo_series import RFS_DENOMINATOR_CODES, lake_series_id
from pipelines.epa.reference import load_percentage_standards

ID_PREFIX = "derived.rin.mandate"
UNIT = "billion RINs"
GASOLINE_CODE, DISTILLATE_CODE = RFS_DENOMINATOR_CODES
GASOLINE_SERIES, DISTILLATE_SERIES = (lake_series_id(code) for code in RFS_DENOMINATOR_CODES)
DENOMINATOR_SERIES = (GASOLINE_SERIES, DISTILLATE_SERIES)
_LABELS = ("observed", "projected")
_LABEL_RANK = {"observed": 0, "projected": 1}
_STATUSES = ("final", "proposed")
_STATUS_RANK = {"final": 0, "proposed": 1}


def days_in_period(period_start: pd.Timestamp) -> int:
    """Calendar length of the month starting at ``period_start`` (29 for February 2028)."""
    return int(period_start.days_in_month)


def _best_per(frame: pd.DataFrame, keys: list[str], ranks: list[pd.Series]) -> pd.DataFrame:
    """First row per ``keys`` after ordering by each rank (lower wins), then latest
    ``revision_date``. The one ranking both readers share."""
    cols = {f"_rank{i}": r for i, r in enumerate(ranks)}
    ordered = frame.assign(**cols).sort_values(
        [*cols, "revision_date"], ascending=[*[True] * len(cols), False], kind="stable"
    )
    return ordered.drop_duplicates(keys, keep="first").drop(columns=list(cols))


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
    frame = _best_per(frame, ["series", "ts"], [frame["label"].map(_LABEL_RANK)])
    return frame[["series_id", "series", "label", "ts", "value"]].reset_index(drop=True)


_MANDATE_COLUMNS = ["category", "ts", "value", "unit", "label", "status"]


def resolve_mandate_twins(rows: pd.DataFrame) -> pd.DataFrame:
    """One row per (category, month) from raw ``derived.rin.mandate.*`` lake rows.

    READ ``derived.rin.mandate.*`` THROUGH THIS FUNCTION, NEVER RAW. The id carries both the
    observed/projected label and the final/proposed status and the lake has no delete path, so
    once STEO's history boundary moves, or a standard moves from proposed to final, a later
    run writes the month under a new id and the old row stays: the same month then exists
    twice. This resolves each pair to the winner:

    1. ``observed`` beats ``projected``, FIRST. An observed-but-proposed row therefore beats a
       projected-but-final one: what the demand rests on outranks which standard was applied.
    2. Then ``final`` beats ``proposed``.
    3. Ties go to the latest ``revision_date``.

    Takes a ``ts_long`` frame (other series and malformed ids are ignored). Returns
    ``category``, ``ts``, ``value``, ``unit`` and the winner's own ``label`` (observed or
    projected) and ``status`` (final or proposed), so a caller can still show "projected" or
    "proposed".
    """
    if rows.empty:
        return pd.DataFrame(columns=_MANDATE_COLUMNS)
    frame = rows[rows["series_id"].str.startswith(f"{ID_PREFIX}.")]
    parts = frame["series_id"].str[len(ID_PREFIX) + 1 :].str.rsplit(".", n=2, expand=True)
    if frame.empty or parts.shape[1] != 3:
        return pd.DataFrame(columns=_MANDATE_COLUMNS)
    frame = frame.assign(category=parts[0], label=parts[1], status=parts[2])
    frame = frame[frame["label"].isin(_LABELS) & frame["status"].isin(_STATUSES)]
    frame = _best_per(
        frame,
        ["category", "ts"],
        [frame["label"].map(_LABEL_RANK), frame["status"].map(_STATUS_RANK)],
    )
    return frame[_MANDATE_COLUMNS].sort_values(["category", "ts"]).reset_index(drop=True)


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
