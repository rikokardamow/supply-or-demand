"""Real NYMEX futures settlements from EIA's own API -- the historical backfill that
finally gives Spec 18 real `fut.*` rows without an IBKR Gateway.

**This route is discontinued.** `petroleum/pri/fut` stopped updating on **2024-04-05**
(confirmed live against the route's own metadata, while `petroleum/pri/spt` runs to the
present). It is therefore a *history* source, not a live feed: it cannot drive a current
crack board's m1/m2 tenors, and Spec 20's `crack_board` will still show `NaN` there until
an IBKR pull or a manual CSV lands. What it does give is real crude and product futures
back to the 1980s, which spans Murat & Tokat's own 1993-2008 sample -- so the Spec 20
Session B VECM can finally be estimated on crack *futures* rather than the spot proxy that
failed.

**Ranks, not contracts.** EIA publishes "Contract 1..4" -- already rank-labelled, with no
contract code, expiry, open interest or volume. So this bypasses `core/curve.py`'s
`nearby_panel` (which builds ranks *from* contract codes plus expiries) and writes the
conventions' unadjusted rank series ids directly. Consequences: no Dec-Dec spreads, no roll
calendar, no `series_meta` rows, and nothing beyond rank 4 -- `s12`/`s13`/`cv123` are
computable, `m6` is not.

`source="eia"`, not `"futures"`, so a later IBKR or manual-CSV pull of the same
`series_id` is still distinguishable by provenance -- the multi-source-per-series_id
design `specs/00_TRADING_CONVENTIONS.md` describes.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

ROUTE = "petroleum/pri/fut"
MAX_RANK = 4
"""EIA only ever published contracts 1-4."""


@dataclass(frozen=True)
class EIAFutureSeries:
    """One EIA futures series and the lake series it becomes."""

    eia_id: str
    root: str
    rank: int
    unit: str
    geo: str


def _ranks(template: str, root: str, unit: str, geo: str) -> tuple[EIAFutureSeries, ...]:
    return tuple(
        EIAFutureSeries(template.format(rank=rank), root, rank, unit, geo)
        for rank in range(1, MAX_RANK + 1)
    )


EIA_FUTURES: tuple[EIAFutureSeries, ...] = (
    # Cushing WTI crude, $/bbl, from 1983-04-04.
    *_ranks("RCLC{rank}", "cl", "USD/bbl", "US"),
    # NY Harbor RBOB gasoline, $/gal, from 2005-10-03.
    *_ranks("EER_EPMRR_PE{rank}_Y35NY_DPG", "rb", "USD/gal", "PADD1"),
    # NY Harbor *regular* (pre-RBOB, NYMEX "HU") gasoline, $/gal, 1985-01-02 to
    # 2006-12-29. Deliberately its own root -- see rows_to_ts_long's docstring.
    *_ranks("EER_EPMR_PE{rank}_Y35NY_DPG", "hu", "USD/gal", "PADD1"),
    # NY Harbor No. 2 heating oil, $/gal, from 1980-01-02.
    *_ranks("EER_EPD2F_PE{rank}_Y35NY_DPG", "ho", "USD/gal", "PADD1"),
)

_BY_EIA_ID = {spec.eia_id: spec for spec in EIA_FUTURES}


def eia_series_ids() -> list[str]:
    """Every EIA series id this pipeline asks the API for."""
    return [spec.eia_id for spec in EIA_FUTURES]


def lake_series_id(root: str, rank: int) -> str:
    """The conventions' unadjusted nearby rank id: `fut.<root>.f01.settle`."""
    return f"fut.{root}.f{rank:02d}.settle"


def rows_to_ts_long(rows: pd.DataFrame) -> pd.DataFrame:
    """EIA client rows -> `ts_long` rows keyed by the conventions' rank series ids.

    RBOB and pre-2006 regular gasoline are kept as **separate roots** (`rb` and `hu`).
    They are two different NYMEX contracts with different specifications, and splicing
    them into a single `rb` history at ingestion would bake an analytical decision into
    the lake. The splice stays a downstream choice, which is exactly what
    `core.cracks.rbob_splice_flag` exists to flag.

    An EIA series this module does not map (e.g. Mont Belvieu propane, which is not a
    Spec 18 root) is dropped rather than guessed at.
    """
    if rows.empty:
        return pd.DataFrame()

    known = rows[rows["series_id"].isin(_BY_EIA_ID)].copy()
    if known.empty:
        return pd.DataFrame()

    specs = known["series_id"].map(_BY_EIA_ID)
    known["series_id"] = [lake_series_id(s.root, s.rank) for s in specs]
    known["source"] = "eia"
    known["unit"] = [s.unit for s in specs]
    known["geo"] = [s.geo for s in specs]
    known["freq"] = "D"
    known["value"] = known["value"].astype("float64")
    return known.reset_index(drop=True)
