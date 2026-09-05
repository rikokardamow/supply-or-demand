"""Reads Spec 10's FRED spot legs from the lake, computes the crack boards via
core/cracks.py, and writes `derived.crack.<name>.<tenor>` series back.

Registered as a Spec 13 orchestration step alongside pipelines/derived/curve.py, run
after pipelines.macro.pull_macro. Per-crack failure isolation, matching every other
pipeline's own loop.

**Tenor is `spot` for every series here.** Spec 20's own series template is
`derived.crack.<name>.<tenor>`, with the tenors coming from Spec 18's futures curve --
but the lake holds no `fut.*` rows at all yet (Spec 18 has never ingested a real
settlement), so the only tenor that can be computed today is the spot crack. The m1/m2/m6
board columns stay NaN until that lands; see core/cracks.py's own module docstring.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import pandas as pd
from core.cracks import Leg, crack_211, crack_321, crack_ho, crack_rbob
from core.storage import read_ts_long, write_ts_long

TENOR = "spot"
UNIT = "USD/bbl"

WTI = "fred.dcoilwtico"
NYH_GASOLINE = "fred.dgasnyh"
NYH_HEATING_OIL = "fred.dhoilnyh"
GULF_GASOLINE = "fred.dgasusgulf"
GULF_ULSD = "fred.ddfuelusgulf"


@dataclass(frozen=True)
class CrackDef:
    """One crack: the lake series it needs, the function that computes it, and the
    geography tag that lands in the `ts_long` row."""

    legs: tuple[str, ...]
    fn: Callable[..., Leg]
    geo: str
    label: str


CRACK_DEFS: dict[str, CrackDef] = {
    "us321": CrackDef(
        (WTI, NYH_GASOLINE, NYH_HEATING_OIL), crack_321, "PADD1", "NYH 3:2:1 (spot)"
    ),
    "us211": CrackDef(
        (WTI, NYH_GASOLINE, NYH_HEATING_OIL), crack_211, "PADD1", "NYH 2:1:1 (spot)"
    ),
    "gulf321": CrackDef(
        (WTI, GULF_GASOLINE, GULF_ULSD), crack_321, "PADD3", "US Gulf 3:2:1 (spot)"
    ),
    "nyh_gasoline": CrackDef((WTI, NYH_GASOLINE), crack_rbob, "PADD1", "NYH gasoline crack"),
    "nyh_distillate": CrackDef(
        (WTI, NYH_HEATING_OIL), crack_ho, "PADD1", "NYH heating oil crack"
    ),
}


def build_cracks(panel: pd.DataFrame) -> pd.DataFrame:
    """Wide panel of lake series -> wide panel of cracks in $/bbl.

    A crack whose legs are not all present is omitted entirely rather than emitted as a
    column of NaN -- the ICE gasoil and Singapore gasoil cracks Spec 20 also names have
    no legs in the lake at all.
    """
    columns: dict[str, pd.Series] = {}
    for name, spec in CRACK_DEFS.items():
        if not all(leg in panel.columns for leg in spec.legs):
            continue
        # Every leg here is a Series, so the crack is one too -- pd.Series() makes that
        # explicit for the type checker rather than widening CrackDef.fn to Any.
        columns[name] = pd.Series(spec.fn(*(panel[leg] for leg in spec.legs)))

    if not columns:
        return pd.DataFrame(index=panel.index)
    return pd.DataFrame(columns)


def derived_rows(name: str, values: pd.Series, ingested_at: pd.Timestamp) -> pd.DataFrame:
    """One crack series -> `ts_long` rows. `value` is forced to float64 explicitly here
    as well as in write_ts_long, so the dtype holds even for callers that inspect the
    frame before writing (the v0.11 sub-dollar lesson)."""
    values = values.dropna()
    if values.empty:
        return pd.DataFrame()

    spec = CRACK_DEFS[name]
    return pd.DataFrame(
        {
            "series_id": f"derived.crack.{name}.{TENOR}",
            "source": "derived",
            "ts": values.index,
            "value": values.to_numpy(dtype="float64"),
            "unit": UNIT,
            "geo": spec.geo,
            "freq": "D",
            "revision_date": ingested_at,
        }
    )


def read_legs() -> pd.DataFrame:
    """Every leg any crack needs, pivoted wide on series_id."""
    wanted = sorted({leg for spec in CRACK_DEFS.values() for leg in spec.legs})
    long_df = read_ts_long(series_ids=wanted)
    if long_df.empty:
        return pd.DataFrame()
    return long_df.pivot_table(index="ts", columns="series_id", values="value")


def main() -> None:
    ingested_at = pd.Timestamp(datetime.now())
    panel = read_legs()
    if panel.empty:
        print("derived.crack: no spot legs in the lake", flush=True)
        return

    cracks = build_cracks(panel)
    total = 0
    for name in cracks.columns:
        try:
            rows = derived_rows(name, cracks[name], ingested_at)
            if rows.empty:
                print(f"{name}: no rows", flush=True)
                continue
            write_ts_long(rows, source="derived")
            total += len(rows)
            print(f"{name}: wrote {len(rows)} rows", flush=True)
        except Exception as exc:
            print(f"{name}: FAILED ({type(exc).__name__}: {exc})", flush=True)

    print(f"derived.crack: {total} total rows written", flush=True)


if __name__ == "__main__":
    main()
