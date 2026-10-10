"""EPA Renewable Fuel Standard reference tables: volume targets and percentage standards.

Pure file readers: no network at import or at call time. The CSVs sit beside this module and
are rulemaking figures, so they change when a rule changes, not on a clock.

Units
-----
``billion_rins`` is a volume in billions of RINs (one RIN = one ethanol-equivalent gallon).
``basis`` says which volume it is: ``requirement`` is EPA's volume requirement; ``applicable``
is EPA's *total applicable volume*, the basis EPA states it uses to calculate the percentage
standards, i.e. the requirement plus the reallocated small-refinery-exemption volume. Do not
read the step between the two bases as policy. 2023-2025 carry ``requirement`` only (no
reallocation then); 2026 and 2027 carry both. 2025 cellulosic is the post-waiver 1.21; only
cellulosic was waived, so 2025 advanced and total stand as in the 2023 rule.

``pct`` is a FRACTION in [0, 1] (EPA publishes 15.50 per cent; the file holds 0.155). In EPA's
terms it is the percentage standard "applicable to producers and importers of gasoline and
diesel": the obligated RINs per unit of projected gasoline plus diesel volume in the covered
location, net of exempt volumes (40 CFR 80.1405).

Status
------
Every row is ``final`` or ``proposed``. Where a final rule exists it is used and named in
``source``. Where a later action revised a figure (2024 cellulosic, 2025 cellulosic) the
revised final figure is used.

Not sourced (rows deliberately absent; nothing was estimated)
-------------------------------------------------------------
* biomass_based_diesel volume, 2023, 2024, 2025: the 2023 rule states BBD in physical
  gallons (2.82, 3.04, 3.35 billion), not RINs, and no opened EPA text gives the RIN figure.
  Converting would be our arithmetic, not a published number.
* The 2023 supplemental standard (0.25 billion RINs; 0.14 per cent) is outside CATEGORIES.
* All years before 2023: no pre-2023 rule text was opened.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

CATEGORIES: tuple[str, ...] = ("cellulosic", "biomass_based_diesel", "advanced", "total")
STATUSES: tuple[str, str] = ("final", "proposed")
BASES: tuple[str, str] = ("requirement", "applicable")

_HERE = Path(__file__).parent
_VOLUME_COLUMNS = ("year", "category", "billion_rins", "basis", "status", "source", "as_of")
_PCT_COLUMNS = ("year", "category", "pct", "status", "source", "as_of")


def _load(path: Path, columns: tuple[str, ...], value: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"source": str, "category": str, "status": str})
    if set(df.columns) != set(columns):
        raise ValueError(f"{path.name}: columns {sorted(df.columns)} != {sorted(columns)}")
    df = df[list(columns)]
    if df.isna().any().any():
        raise ValueError(f"{path.name}: blank cell in column(s) "
                         f"{sorted(df.columns[df.isna().any()])}")
    if not df["status"].isin(STATUSES).all():
        raise ValueError(f"{path.name}: status must be one of {STATUSES}")
    if not df["category"].isin(CATEGORIES).all():
        raise ValueError(f"{path.name}: category must be one of {CATEGORIES}")
    if not df["source"].str.strip().str.len().gt(0).all():
        raise ValueError(f"{path.name}: source must be non-empty")
    try:
        df["as_of"] = pd.to_datetime(df["as_of"], format="%Y-%m-%d")
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{path.name}: as_of must be an ISO date") from exc
    key = ["year", "category"]
    if value == "billion_rins":
        if not df["basis"].isin(BASES).all():
            raise ValueError(f"{path.name}: basis must be one of {BASES}")
        key.append("basis")
    if df.duplicated(key).any():
        raise ValueError(f"{path.name}: duplicate {'/'.join(key)}")
    if value == "pct":
        if not df["pct"].between(0, 1).all():
            raise ValueError(f"{path.name}: pct must lie in [0, 1] (a fraction, not per cent)")
    elif not df["billion_rins"].gt(0).all():
        raise ValueError(f"{path.name}: billion_rins must be strictly positive")
    return df.reset_index(drop=True)


def load_volume_targets(path: Path | None = None) -> pd.DataFrame:
    """Annual RFS volumes in billion RINs (see ``basis``); one row per year/category/basis."""
    return _load(path or _HERE / "volume_targets.csv", _VOLUME_COLUMNS, "billion_rins")


def load_percentage_standards(path: Path | None = None) -> pd.DataFrame:
    """Annual RFS percentage standards. ``pct`` is a fraction of 1 (0.155), not per cent (15.5)."""
    return _load(path or _HERE / "percentage_standards.csv", _PCT_COLUMNS, "pct")
