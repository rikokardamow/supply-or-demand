"""Atlantic LNG: where US LNG goes, and where Europe's LNG comes from. Pure arithmetic.

This repo's own model on public data: EIA US LNG exports by destination, Eurostat EU LNG
imports by partner and DESNZ UK LNG imports by origin. A Bloomberg Intelligence global LNG
calculator was read as a layout example only. Spec:
`docs/models/2026-10-26-lng-model-mapping.md`.

Asian demand is not here yet. JODI-Gas, the public route for it, needs an account (its API
is token-only, and its bulk file stops in 2018-08).

Units: mcm in, as Eurostat and DESNZ publish. EIA's MMcf convert at 0.0283168 mcm per MMcf.
The reference conditions differ slightly (EIA at 60°F and 14.73 psia, Eurostat at 15°C), by
well under 1%, so they are not adjusted.
"""

from __future__ import annotations

import pandas as pd

from core.eu_gas_balance import EU27

MCM_PER_MMCF = 0.0283168

REGIONS: dict[str, str] = {
    "europe": "Europe",
    "asia": "Asia",
    "middle_east_africa": "Middle East and Africa",
    "latin_america": "Latin America and Caribbean",
    "other": "Other",
    "unmapped": "Destination not mapped yet",
    "unallocated": "Not allocated to a destination by EIA",
}

# Origin groups for Europe's LNG imports. Keys are Eurostat partner codes and DESNZ slugs.
ORIGINS: dict[str, str] = {
    "united_states": "United States",
    "qatar": "Qatar",
    "russia": "Russia",
    "algeria": "Algeria",
    "nigeria": "Nigeria",
    "norway": "Norway",
    "other": "Other origins",
    "not_specified": "Origin not specified",
}
EUROSTAT_ORIGIN = {"us": "united_states", "qa": "qatar", "ru": "russia", "dz": "algeria",
                   "ng": "nigeria", "no": "norway", "nsp": "not_specified"}  # fmt: skip
DESNZ_ORIGIN = {"usa": "united_states", "qatar": "qatar", "russia": "russia",
                "algeria": "algeria", "nigeria": "nigeria", "norway": "norway"}  # fmt: skip
EU27_EUROSTAT = EU27  # Eurostat partner codes of the member states
EUROPE_DESNZ = frozenset(
    {"belgium", "france", "netherlands", "spain", "total_lng"}
)  # DESNZ origins that are other European terminals' re-exports, plus its total row


def us_exports_by(exports: pd.DataFrame, mapping: pd.DataFrame, column: str) -> pd.DataFrame:
    """Month x ``mapping[column]`` (region or bloc) of US LNG exports, in mcm.

    ``exports`` has ``kind`` (exports/truck/reexports), ``destination``, ``ts`` and ``value``
    (MMcf), including the ``exports``/``total`` row. Vessel exports plus trucks add up to the
    national total, which EIA does not include re-exports in. That is checked, not assumed:
    whatever the destinations leave out of the total becomes ``unallocated``. A destination
    missing from ``mapping`` becomes ``unmapped``, never dropped.
    """
    is_total = (exports["kind"] == "exports") & (exports["destination"] == "total")
    total = exports[is_total].groupby("ts")["value"].sum()
    parts = exports[exports["kind"].isin(["exports", "truck"]) & ~is_total]
    group = parts["destination"].map(mapping.set_index("destination")[column]).fillna("unmapped")
    table = parts.assign(group=group).groupby(["ts", "group"])["value"].sum().unstack("group")
    table = table.reindex(total.index).fillna(0.0)
    table["unallocated"] = (total - table.sum(axis=1)).clip(lower=0.0)
    return table * MCM_PER_MMCF


def europe_lng_imports(eu: pd.DataFrame, uk: pd.DataFrame) -> pd.DataFrame:
    """Month x origin group of LNG imported into the EU-27 and the UK from outside Europe, in mcm.

    ``eu``: Eurostat LNG imports by partner (``partner`` = lower-case code, ``ts``, ``value``).
    EU members and the UK are dropped, because they are re-exports inside Europe. ``uk``:
    DESNZ LNG imports by origin (``country`` = slug, ``ts``, ``value``), with EU terminals and
    the total row dropped. A month counts only where both sides publish it.
    """
    eu = eu[~eu["partner"].isin(EU27_EUROSTAT | {"uk", "total"})]
    eu = eu.assign(origin=eu["partner"].map(EUROSTAT_ORIGIN).fillna("other"))
    uk = uk[~uk["country"].isin(EUROPE_DESNZ)]
    uk = uk.assign(origin=uk["country"].map(DESNZ_ORIGIN).fillna("other"))
    sides = []
    for frame in (eu, uk):
        sides.append(frame.groupby(["ts", "origin"])["value"].sum().unstack("origin"))
    months = sides[0].index.intersection(sides[1].index)
    total = sides[0].reindex(months).fillna(0.0).add(sides[1].reindex(months).fillna(0.0),
                                                      fill_value=0.0)  # fmt: skip
    return total.reindex(columns=list(ORIGINS)).fillna(0.0).sort_index()


def mirror(us_side: pd.Series, europe_side: pd.Series) -> pd.DataFrame:
    """US-reported exports to a bloc against the bloc's reported imports from the US (mcm),
    for months both publish. Shipping takes two to three weeks, so a month can differ by a
    cargo in transit; compare years, not months."""
    out = pd.concat({"us_reported": us_side, "europe_reported": europe_side}, axis=1).dropna()
    out["gap"] = out["europe_reported"] - out["us_reported"]
    return out


# --- global view from JODI-Gas -----------------------------------------------------------

EXPORTER_GROUPS: dict[str, tuple[str, ...]] = {
    "united_states": ("us",), "qatar": ("qa",), "australia": ("au",), "malaysia": ("my",),
    "nigeria": ("ng",), "algeria": ("dz",), "trinidad_tobago": ("tt",),
}  # fmt: skip
IMPORTER_GROUPS: dict[str, tuple[str, ...]] = {
    "china": ("cn",), "japan": ("jp",), "south_korea": ("kr",), "india": ("in",),
    # JODI codes Greece "gr" where Eurostat uses "el".
    "europe": (*sorted((EU27 - {"el"}) | {"gr"}), "gb", "tr"),
    "other_asia": ("th", "sg", "bd", "pk", "ph", "my", "id", "vn", "hk", "lk", "mm"),
}  # fmt: skip
GROUP_LABELS: dict[str, str] = {
    "united_states": "United States", "qatar": "Qatar", "australia": "Australia",
    "malaysia": "Malaysia", "nigeria": "Nigeria", "algeria": "Algeria",
    "trinidad_tobago": "Trinidad and Tobago", "china": "China", "japan": "Japan",
    "south_korea": "South Korea", "india": "India",
    "europe": "Europe (EU-27, UK, Türkiye)", "other_asia": "Other Asia", "rest": "Rest of world",
}  # fmt: skip
# Taiwan (Chinese Taipei) files a zero for LNG imports in every month it reports to JODI
# (58 of 58, checked 2026-10-26), though it imports tens of bcm a year. A placeholder zero is
# not data: those cells are treated as unreported.
ZERO_IS_UNREPORTED: frozenset[tuple[str, str]] = frozenset({("implng", "tw")})
GLOBAL_COVERAGE = 0.98
COVERAGE_WINDOW_MONTHS = 24


def by_country(rows: pd.DataFrame, flow: str) -> pd.DataFrame:
    """Month x country (lower-case JODI code) for one flow, from long JODI rows
    (``flow``, ``country``, ``ts``, ``value``). A country that did not report is NaN."""
    part = rows[rows["flow"] == flow]
    placeholder = part["country"].map(lambda c: (flow, c) in ZERO_IS_UNREPORTED) & (
        part["value"] == 0
    )
    part = part[~placeholder]
    return part.groupby(["ts", "country"])["value"].sum(min_count=1).unstack("country").sort_index()


def coverage(table: pd.DataFrame, window: int = COVERAGE_WINDOW_MONTHS) -> pd.Series:
    """Share of typical volume reported, per month: each country weighs its share of the
    flow over the trailing ``window`` months before that month. A new month in which only
    early reporters have filed scores low and is not treated as a collapse."""
    filled = table.fillna(0.0).abs()
    out = {}
    for i, month in enumerate(table.index):
        past = filled.iloc[max(0, i - window) : i]
        if past.empty or past.to_numpy().sum() == 0:
            continue
        weight = past.sum() / past.to_numpy().sum()
        out[month] = float(weight[table.loc[month].notna()].sum())
    return pd.Series(out, dtype="float64")


def grouped(table: pd.DataFrame, groups: dict[str, tuple[str, ...]]) -> pd.DataFrame:
    """Month x group sums, with every other country in ``rest``."""
    out = pd.DataFrame(index=table.index)
    used: set[str] = set()
    for group, members in groups.items():
        present = [m for m in members if m in table.columns]
        used.update(present)
        out[group] = table[present].sum(axis=1, min_count=1) if present else float("nan")
    rest = [c for c in table.columns if c not in used]
    out["rest"] = table[rest].sum(axis=1, min_count=1)
    return out
