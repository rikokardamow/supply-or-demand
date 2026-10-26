"""EU-27 gas balance by supply route: pure arithmetic, no I/O.

The method is this repo's own, built on Eurostat's monthly data. A Bloomberg Intelligence
TTF calculator was read as an example of the layout; nothing is taken from it. See
`docs/superpowers/specs/2026-10-26-eu-uk-gas-model-mapping.md`.

Three rules shape everything here, each found in the data, not assumed:

1. **Net, not gross.** Gas in transit leaves and re-enters the EU: TAP gas goes Greece ->
   Albania -> Italy, and TurkStream gas goes Bulgaria -> Serbia -> Hungary. Gross imports
   count it twice. A route is therefore a sum of *net* imports (imports minus exports) by
   partner.
2. **Intra-EU trade is excluded.** The EU-27 aggregate lists member states as partners, and
   its ``TOTAL`` includes them.
3. **"Natural gas" includes LNG.** Eurostat's ``G3000`` is all gas. Pipeline is ``G3000``
   minus ``G3200`` (LNG).

Units: million m3 (``mcm``) in, as Eurostat publishes. Converting to bcm is the caller's job.
"""

from __future__ import annotations

import pandas as pd

EU27: frozenset[str] = frozenset(
    {
        "at", "be", "bg", "cy", "cz", "de", "dk", "ee", "el", "es", "fi", "fr", "hr", "hu",
        "ie", "it", "lt", "lu", "lv", "mt", "nl", "pl", "pt", "ro", "se", "si", "sk",
    }
)  # fmt: skip
TOTAL_PARTNER = "total"
PRODUCTS = ("pipeline", "lng")
WILDCARD = "*"

# Display order and labels. A route not listed here is a mapping error and raises.
ROUTES: dict[str, str] = {
    "norway_pipeline": "Norway pipeline",
    "russia_pipeline": "Russia pipeline (direct, Belarus, Ukraine transit)",
    "southeast_corridor": "South-east corridor (TurkStream and TAP, Russian and Azeri gas mixed)",
    "north_africa_pipeline": "North Africa pipeline",
    "uk": "United Kingdom",
    "neighbour_exports": "Net exports to neighbours (Ukraine, Switzerland, Moldova…)",
    "other_pipeline": "Other and unspecified pipeline",
    "lng_us": "LNG: United States",
    "lng_qatar": "LNG: Qatar",
    "lng_russia": "LNG: Russia",
    "lng_other": "LNG: other origins",
    "lng_unspecified": "LNG: origin not specified",
}

# Balance lines (Eurostat nrg_bal codes, lower-case) and what this model calls them.
BALANCE_LINES: dict[str, str] = {
    "iprd": "production",
    "imp": "imports",
    "exp": "exports",
    "stk_chg_mg": "stock_build",  # positive = injection into storage (checked against GIE)
    "ic_obs": "consumption",
    "ti_ehg_map": "power",
    "fc_ind": "industry",
    "fc_oth": "other_final",
    "statdiff": "statdiff",
}
TJ_PER_TWH = 3600.0


def _sum_wide(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """Month x ``column`` sums where an all-blank group stays blank. ``pivot_table`` with
    ``aggfunc="sum"`` turns it into 0, which here would be invented data."""
    wide: pd.DataFrame = frame.groupby(["ts", column])["value"].sum(min_count=1).unstack(column)
    return wide


def net_by_partner(trade: pd.DataFrame) -> pd.DataFrame:
    """Net pipeline and LNG imports per partner and month.

    ``trade`` has columns ``flow`` (imports/exports), ``product`` (gas/lng), ``partner``,
    ``ts``, ``value``. Only :func:`complete_months` are used. Within such a month a partner
    with no cell has traded nothing, so it counts as 0, because Eurostat lists only partners
    with trade. Any other month yields no rows: no data is not zero.

    Returns ``ts``, ``partner``, ``product`` (pipeline/lng), ``value`` (net mcm).
    """
    frame = trade[trade["ts"].isin(complete_months(trade)) & (trade["partner"] != TOTAL_PARTNER)]
    if frame.empty:
        return pd.DataFrame(columns=["ts", "partner", "product", "value"])
    wide = frame.pivot_table(
        index=["ts", "partner"], columns=["flow", "product"], values="value", aggfunc="sum"
    )
    for col in [("imports", "gas"), ("imports", "lng"), ("exports", "gas"), ("exports", "lng")]:
        if col not in wide.columns:
            wide[col] = 0.0
    wide = wide.fillna(0.0)
    lng = wide[("imports", "lng")] - wide[("exports", "lng")]
    gas = wide[("imports", "gas")] - wide[("exports", "gas")]
    out = pd.concat({"pipeline": gas - lng, "lng": lng}, names=["product"]).rename("value")
    result: pd.DataFrame = out.reset_index()[["ts", "partner", "product", "value"]]
    return result


PARTNER_SUM_TOLERANCE = 0.02


def complete_months(
    trade: pd.DataFrame, tolerance: float = PARTNER_SUM_TOLERANCE
) -> list[pd.Timestamp]:
    """Months whose partner cells add up to the published total, for imports and exports of
    all gas. Eurostat sometimes publishes a month's total with most partners still blank
    (March 2024 is one), and counting those blanks as zero would drop most of the month's
    supply. A month needs an imports total. An exports total, where one exists, must match too."""
    gas = trade[trade["product"] == "gas"]

    def check(flow: str) -> pd.DataFrame:
        rows = gas[gas["flow"] == flow]
        is_total = rows["partner"] == TOTAL_PARTNER
        frame = pd.concat(
            {
                "total": rows[is_total].groupby("ts")["value"].sum(),
                "parts": rows[~is_total].groupby("ts")["value"].sum(),
            },
            axis=1,
            sort=True,
        )
        gap = (frame["parts"].fillna(0.0) - frame["total"]).abs()
        frame["ok"] = gap <= tolerance * frame["total"].abs()
        return frame

    imports = check("imports")
    exports = check("exports").reindex(imports.index)
    exports_ok = exports["total"].isna() | exports["ok"].eq(True)
    good = imports["ok"] & imports["total"].notna() & exports_ok
    return [pd.Timestamp(ts) for ts in good[good].index]


def assign_routes(net: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    """Attach a route to every extra-EU (partner, product, month); drop intra-EU partners.

    ``mapping`` has ``partner``, ``product``, ``route``, ``valid_from``, ``valid_to`` (month
    starts; NaT = open). Specific partners win over the ``*`` wildcard for their product.
    Raises if a row matches no rule or two rules, or names an unknown route: a silent
    gap would drop gas from the balance.
    """
    unknown = set(mapping["route"]) - set(ROUTES)
    if unknown:
        raise ValueError(f"unknown route(s) in mapping: {sorted(unknown)}")
    rows = net[~net["partner"].isin(EU27)].copy()
    rows["route"] = None
    for wildcard in (False, True):
        rules = mapping[(mapping["partner"] == WILDCARD) == wildcard]
        for rule in rules.itertuples(index=False):
            hit = rows["product"] == rule.product
            if not wildcard:
                hit &= rows["partner"] == rule.partner
            if pd.notna(rule.valid_from):
                hit &= rows["ts"] >= rule.valid_from
            if pd.notna(rule.valid_to):
                hit &= rows["ts"] <= rule.valid_to
            if wildcard:
                hit &= rows["route"].isna()
            elif (hit & rows["route"].notna()).any():
                raise ValueError(f"overlapping rules for {rule.partner}/{rule.product}")
            rows.loc[hit, "route"] = rule.route
    missing = rows[rows["route"].isna()]
    if not missing.empty:
        pairs = sorted(set(zip(missing["partner"], missing["product"], strict=True)))
        raise ValueError(f"no route for {pairs[:10]}")
    return rows


def route_totals(routed: pd.DataFrame) -> pd.DataFrame:
    """Month x route net imports (mcm), every route in ``ROUTES`` order.

    ``routed`` holds only published months (see :func:`net_by_partner`), so a route with no
    partner trading in such a month is 0, not missing.
    """
    table = _sum_wide(routed, "route")
    return table.reindex(columns=list(ROUTES)).fillna(0.0).sort_index()


def balance_table(balance: pd.DataFrame) -> pd.DataFrame:
    """Month x named balance line (mcm) from long Eurostat rows (``line``, ``ts``, ``value``).

    Adds ``other_uses``: consumption minus power, industry and other final use (own use,
    losses, non-energy). It is computed, not published, and NaN wherever a part is absent.
    """
    wide = (
        _sum_wide(balance, "line")
        .reindex(columns=list(BALANCE_LINES))
        .rename(columns=BALANCE_LINES)
    )
    wide["other_uses"] = wide["consumption"] - wide[["power", "industry", "other_final"]].sum(
        axis=1, min_count=3
    )
    return wide.sort_index()


def reconcile(routes: pd.DataFrame, balance: pd.DataFrame) -> pd.DataFrame:
    """The model's checks, month by month (mcm).

    - ``extra_eu_net``: sum of routes. ``balance_net``: Eurostat's imports minus exports,
      where intra-EU trade should cancel. Their gap, ``intra_eu_asymmetry``, measures how
      far member states' reports of the same flows disagree.
    - ``implied_stock_build``: production + extra-EU net imports - consumption. Set against
      Eurostat's reported stock build, its gap is ``unexplained``.
    """
    joined = pd.DataFrame(
        {
            "extra_eu_net": routes.sum(axis=1, min_count=1),
            "balance_net": balance["imports"] - balance["exports"],
            "production": balance["production"],
            "consumption": balance["consumption"],
            "stock_build": balance["stock_build"],
        }
    ).dropna()
    joined["intra_eu_asymmetry"] = joined["balance_net"] - joined["extra_eu_net"]
    joined["implied_stock_build"] = (
        joined["production"] + joined["extra_eu_net"] - joined["consumption"]
    )
    joined["unexplained"] = joined["implied_stock_build"] - joined["stock_build"]
    return joined


def storage_check(stock_build_tj: pd.Series, gie_storage_twh: pd.Series) -> pd.DataFrame:
    """Eurostat's monthly stock build against GIE's change in gas in storage, both in TWh.

    ``gie_storage_twh`` is daily EU gas in storage. Its month-end level minus the previous
    month-end level is the observed build. A month is compared only when both month ends
    are present. A missing day is never filled.
    """
    daily = gie_storage_twh.dropna().sort_index()
    month_end = daily.groupby(pd.DatetimeIndex(daily.index).to_period("M")).last()
    month_end.index = pd.PeriodIndex(month_end.index).to_timestamp()
    consecutive = month_end.index.to_series().diff().dt.days.between(28, 31)
    gie_build = month_end.diff()[consecutive]
    out = pd.DataFrame({"eurostat_twh": stock_build_tj / TJ_PER_TWH, "gie_twh": gie_build}).dropna()
    out["gap_twh"] = out["eurostat_twh"] - out["gie_twh"]
    return out


MEMBER_COVERAGE = 0.99


def fill_from_members(
    eu: pd.DataFrame, members: pd.DataFrame, threshold: float = MEMBER_COVERAGE
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fill blank EU-27 cells (month x line) with the sum of member states.

    Eurostat leaves an EU-27 cell blank when any member's cell is missing, even a member
    that produces nothing. ``members`` is long (``line``, ``geo``, ``ts``, ``value``). A
    member's weight in a line is its share of the line's absolute volume over the members'
    whole history. A blank month is filled only if the reporting members' weights sum to at
    least ``threshold``; otherwise it stays blank.

    Returns ``(filled, from_members)``, where ``from_members`` is a boolean mask of the cells
    that were filled.
    """
    filled = eu.copy()
    mask = pd.DataFrame(False, index=eu.index, columns=eu.columns)
    for line in eu.columns:
        rows = members[members["line"] == line]
        if rows.empty:
            continue
        wide = _sum_wide(rows, "geo")
        weight = wide.abs().sum() / wide.abs().sum().sum()
        coverage = wide.notna().mul(weight, axis=1).sum(axis=1)
        member_sum = wide.sum(axis=1, min_count=1).where(coverage >= threshold)
        blank = filled[line].isna()
        candidates = member_sum.reindex(filled.index)
        use = blank & candidates.notna()
        filled.loc[use, line] = candidates[use]
        mask.loc[use, line] = True
    return filled, mask
