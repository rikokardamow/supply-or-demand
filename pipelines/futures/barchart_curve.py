"""Rebuild a full outright forward curve from a Barchart futures-spreads export.

The EIA backfill (`eia_futures.py`) gives deep history but only ranks 1-4 and stops in
2024. This gives the opposite: a single recent date, but the **whole** curve -- which is
what Spec 18's Dec-Dec spreads, convexity and roll calendar actually need.

**The settles here are reconstructed, not quoted.** A Barchart spreads export carries no
outright prices, only relationships between contracts:

- `SP` (two legs): `leg1 - leg2`
- `SA` (strip average): the mean of its legs
- `BF` (butterfly, three legs): ignored here

`SA` and `SP` on the same pair together pin both outrights (`a = SA + SP/2`,
`b = SA - SP/2`); every remaining contract then follows from a spread against an already
known one. Spreads alone fix only the curve's *shape*, so without at least one `SA` anchor
this raises rather than returning a curve that is silently wrong by a constant.

Validated against a real quote: rebuilt from spread rows alone, the 2026-09-04 Brent
Financial front month comes out at **96.280** against Barchart's own published
**96.28s** settlement, and the over-determined anchors agree to half a cent.

`source="manual"` -- these rows are a manual drop derived from a vendor export, not an
exchange settlement feed, and must not pose as one.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

MONTH_CODES: dict[str, int] = {
    "F": 1,
    "G": 2,
    "H": 3,
    "J": 4,
    "K": 5,
    "M": 6,
    "N": 7,
    "Q": 8,
    "U": 9,
    "V": 10,
    "X": 11,
    "Z": 12,
}

BARCHART_FOOTER = "Downloaded from Barchart.com"


def contract_code(barchart_symbol: str, as_of_year: int) -> str:
    """`QAX6` -> `x26`, the lake's lowercase two-digit contract convention.

    Barchart writes a single-digit year, so `4` on a curve struck in 2026 is 2034, not
    2024 -- the digit resolves to the first year at or after `as_of_year`.
    """
    month_letter = barchart_symbol[-2].upper()
    year_digit = int(barchart_symbol[-1])

    year = (as_of_year // 10) * 10 + year_digit
    if year < as_of_year:
        year += 10
    return f"{month_letter.lower()}{year % 100:02d}"


def _delivery_key(code: str, as_of_year: int) -> tuple[int, int]:
    year = 2000 + int(code[1:])
    if year < as_of_year:
        year += 100
    return year, MONTH_CODES[code[0].upper()]


def load_spreads(path: Path | str) -> pd.DataFrame:
    """Read a Barchart export, dropping its trailing attribution line."""
    raw = pd.read_csv(path)
    return raw[~raw["Leg1"].astype(str).str.startswith(BARCHART_FOOTER)].copy()


def reconstruct_curve(spreads: pd.DataFrame, as_of_year: int) -> pd.Series:
    """Spread quotes -> outright settles, indexed by lake contract code in delivery order.

    Raises ValueError if no `SA` row gives the curve a level to hang on.
    """
    two_leg = spreads[spreads["Leg3"].isna()]
    sa = two_leg[two_leg["Type"] == "SA"]
    sp = two_leg[two_leg["Type"] == "SP"]

    spread_by_pair: dict[tuple[str, str], float] = {
        (str(row.Leg1), str(row.Leg2)): float(str(row.Latest)) for row in sp.itertuples()
    }

    outrights: dict[str, float] = {}
    for row in sa.itertuples():
        leg1, leg2 = str(row.Leg1), str(row.Leg2)
        spread = spread_by_pair.get((leg1, leg2))
        if spread is None:
            continue
        average = float(str(row.Latest))
        outrights[leg1] = average + spread / 2.0
        outrights[leg2] = average - spread / 2.0

    if not outrights:
        raise ValueError(
            "no SA (strip average) row pairs with an SP row -- spreads alone fix the "
            "curve's shape but not its level, so it cannot be anchored"
        )

    # Walk the spread graph out from the anchored contracts until nothing new resolves.
    changed = True
    while changed:
        changed = False
        for (leg1, leg2), spread in spread_by_pair.items():
            if leg1 in outrights and leg2 not in outrights:
                outrights[leg2] = outrights[leg1] - spread
                changed = True
            elif leg2 in outrights and leg1 not in outrights:
                outrights[leg1] = outrights[leg2] + spread
                changed = True

    by_code = {
        contract_code(symbol, as_of_year): value for symbol, value in outrights.items()
    }
    ordered = sorted(by_code, key=lambda code: _delivery_key(code, as_of_year))
    return pd.Series([by_code[c] for c in ordered], index=ordered, dtype="float64")


def curve_to_ts_long(
    curve: pd.Series, as_of: pd.Timestamp, root: str, unit: str = "USD/bbl"
) -> pd.DataFrame:
    """Reconstructed curve -> `ts_long` rows at `fut.<root>.<contract>.settle`."""
    return pd.DataFrame(
        {
            "series_id": [f"fut.{root}.{code}.settle" for code in curve.index],
            "source": "manual",
            "ts": as_of,
            "value": curve.to_numpy(dtype="float64"),
            "unit": unit,
            "geo": "GLOBAL",
            "freq": "D",
            "revision_date": pd.Timestamp.now(),
        }
    )
