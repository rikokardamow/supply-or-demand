"""OFAC Specially Designated Nationals (SDN) list client -- free, no key. Confirmed
live: `https://www.treasury.gov/ofac/downloads/sdn.csv` is a full snapshot (not
deltas) of 19,327 rows, no header row, 12 fixed positional columns:
`ent_num, sdn_name, sdn_type, program, title, call_sign, vess_type, tonnage, grt,
vess_flag, vess_owner, remarks`. `-0-` is OFAC's own literal null placeholder.

**Real `sdn_type` distinct values, confirmed live (4, not the 3 a prior session
guessed)**: blank/`-0-` (corporate entities, 9,926 rows -- mapped here to
`"entity"`), `individual` (7,518), `vessel` (1,540), `aircraft` (342).

**`program` is genuinely multi-valued for a real minority of rows -- confirmed
live, and a real correction of an earlier wrong assumption**: an initial check for
comma/semicolon delimiters found none and wrongly concluded the field was always
single-valued. The real delimiter is `"] ["` -- e.g. `"IRAN] [SDGT] [IRGC] [IFSR"`
is four distinct programs, not one string. 2,905 of 19,327 rows (15%) are
multi-program; 243 distinct individual program codes exist. Confirmed the split
logic: `[p.strip("[] ") for p in raw.split("] [")]` correctly turns
`"CUBA] [CUBA-EO14404"` into `["CUBA", "CUBA-EO14404"]` and a plain `"CUBA"` into
`["CUBA"]` (no-op when there is only one).

A trailing blank line (row length 1) exists at EOF -- confirmed live, dropped along
with any other malformed row rather than assumed away."""

from __future__ import annotations

import csv
import io

import pandas as pd
import requests

BASE_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"
REQUEST_TIMEOUT_SECONDS = 60
NULL_PLACEHOLDER = "-0-"

# Positional columns, confirmed live against the real CSV.
_RAW_COLUMNS = [
    "sanction_id",
    "name",
    "entity_type",
    "program",
    "title",
    "call_sign",
    "vess_type",
    "tonnage",
    "grt",
    "vess_flag",
    "vess_owner",
    "remarks",
]


def _clean(value: str) -> str | None:
    stripped = value.strip()
    return None if stripped == NULL_PLACEHOLDER or stripped == "" else stripped


def _split_programs(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [p.strip("[] ") for p in raw.split("] [") if p.strip("[] ")]


def fetch_sdn_csv() -> pd.DataFrame:
    """Returns columns: sanction_id, name, entity_type, programs (list[str]),
    call_sign, vess_type, vess_flag, vess_owner, remarks -- `title`/`tonnage`/`grt`
    are parsed but dropped here, matching specs/15_ofac-sanctions.md's own canonical
    field list."""
    response = requests.get(
        BASE_URL, timeout=REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": "Mozilla/5.0"}
    )
    response.raise_for_status()

    reader = csv.reader(io.StringIO(response.text))
    rows = [row for row in reader if len(row) == len(_RAW_COLUMNS)]

    df = pd.DataFrame(rows, columns=_RAW_COLUMNS)
    for col in df.columns:
        df[col] = df[col].map(_clean)

    df["entity_type"] = df["entity_type"].fillna("entity")
    df["programs"] = df["program"].map(_split_programs)

    return df[
        [
            "sanction_id",
            "name",
            "entity_type",
            "programs",
            "call_sign",
            "vess_type",
            "vess_flag",
            "vess_owner",
            "remarks",
        ]
    ]
