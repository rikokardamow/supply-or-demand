"""Entrypoint: load a Barchart futures-spreads export into the lake as a full outright
curve for its as-of date.

Manual drop, so **not** registered in `infra/run_scheduled.py` -- it runs when a new
export is placed in `data/manual/barchart/`. Filenames carry the product and date, e.g.
`futures-spreads-qax26-09-05-2026.csv`.

See `barchart_curve.py` for why the settles are reconstructed rather than quoted.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from core.failures import fails_loudly, record_failure
from core.storage import write_ts_long

from pipelines.futures.barchart_curve import (
    curve_to_ts_long,
    load_spreads,
    reconstruct_curve,
)

BARCHART_DIR = Path("data/manual/barchart")

# Barchart's product symbol -> the lake root it belongs to. Confirmed with the user
# rather than inferred from the price level: QA is Crude Oil Brent Financial (NYMEX),
# which is this project's `lco` root.
PRODUCT_ROOTS = {"QA": "lco"}


def as_of_from_quotes(spreads: pd.DataFrame) -> pd.Timestamp:
    """The export's own quote date. Barchart stamps a trade date in `Time` on settled
    rows and a clock time ("16:40 CT") on the live one, so only the parseable dates
    count -- and the latest of them is the session being quoted."""
    dates = pd.to_datetime(spreads["Time"], errors="coerce", format="%Y-%m-%d").dropna()
    if dates.empty:
        raise ValueError("no parseable quote date in the export's Time column")
    return pd.Timestamp(dates.max())


def pull_file(path: Path) -> int:
    spreads = load_spreads(path)
    product = str(spreads["Leg1"].iloc[0])[:2].upper()
    root = PRODUCT_ROOTS.get(product)
    if root is None:
        print(f"{path.name}: unknown product {product!r} -- skipping", flush=True)
        return 0

    as_of = as_of_from_quotes(spreads)
    curve = reconstruct_curve(spreads, as_of_year=int(as_of.year))
    rows = curve_to_ts_long(curve, as_of=as_of, root=root)
    write_ts_long(rows, source="manual")

    print(
        f"{path.name}: {root} curve for {as_of.date()} -- {len(curve)} contracts "
        f"{curve.index[0]} {curve.iloc[0]:.2f} -> {curve.index[-1]} {curve.iloc[-1]:.2f}",
        flush=True,
    )
    return len(rows)


@fails_loudly("futures.pull_barchart_curve")
def main() -> None:
    paths = [Path(a) for a in sys.argv[1:]] or sorted(BARCHART_DIR.glob("*.csv"))
    if not paths:
        print(f"barchart: no exports in {BARCHART_DIR}", flush=True)
        return

    total = 0
    for path in paths:
        try:
            total += pull_file(path)
        except (ValueError, KeyError, OSError) as exc:
            record_failure(f"{path.name}", exc)

    print(f"barchart: wrote {total} rows", flush=True)


if __name__ == "__main__":
    main()
