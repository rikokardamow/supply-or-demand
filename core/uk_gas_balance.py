"""UK gas balance by supply route and the call on LNG: pure arithmetic, no I/O.

This repo's own model on DESNZ Energy Trends (ET 4.2 monthly balance, ET 4.3 trade by
pipeline and LNG origin). A Bloomberg Intelligence NBP calculator was read as a layout
example only. Spec: `docs/superpowers/specs/2026-10-26-eu-uk-gas-model-mapping.md`.

The UK has little storage, so the question is not how full storage will be. It is how much
LNG the UK must import once production, Norway and the continent are counted. Every term is
in mcm, as DESNZ publishes it.

Conventions from DESNZ, checked against the published rows:
- ``stock_change`` is positive for a WITHDRAWAL, the opposite of Eurostat.
- ``net_supply`` = production + net imports + stock change + biomethane. Synthetic coke
  oven gas is NOT in it: the published rows add up exactly without it (March 2026, to the
  hundredth of an mcm).
- ``net_supply - demand`` is losses and the statistical difference.
"""

from __future__ import annotations

import pandas as pd

WILDCARD = "*"
TOTAL_TYPES = frozenset({"total_imports", "total_exports", "net_imports"})
TOTAL_COUNTRIES = frozenset({"total_lng", "total_pipeline"})
TOTAL_PIPELINES = frozenset({"total_norwegian_pipeline", "total_pipeline"})

UK_ROUTES: dict[str, str] = {
    "norway_pipeline": "Norway pipeline",
    "continent_pipeline": "Continent pipeline (IUK and BBL), net",
    "ireland_exports": "Exports to Ireland",
    "isle_of_man_exports": "Exports to the Isle of Man",
    "lng_us": "LNG: United States",
    "lng_qatar": "LNG: Qatar",
    "lng_other": "LNG: other origins, net of reloads",
}
LNG_ROUTES = ("lng_us", "lng_qatar", "lng_other")
PIPELINE_ROUTES = (
    "norway_pipeline",
    "continent_pipeline",
    "ireland_exports",
    "isle_of_man_exports",
)

DEMAND_GROUPS: dict[str, tuple[str, ...]] = {
    "power": ("power",),
    "domestic": ("domestic",),
    "industrial": ("industrial",),
    "services": ("services",),
    "own_use": ("producer_own_use", "operator_own_use", "lng_own_use", "storage_own_use"),
    "other": ("other",),
}


def _is_total(trade: pd.DataFrame) -> pd.Series:
    return (
        trade["type"].isin(TOTAL_TYPES)
        | trade["country"].isin(TOTAL_COUNTRIES)
        | trade["pipeline"].isin(TOTAL_PIPELINES)
    )


def route_table(trade: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    """Month x route net imports (mcm): imports count positive, exports negative.

    ``trade`` has ``flow`` (imports/exports/net), ``type``, ``country``, ``pipeline``,
    ``ts``, ``value``. Totals and the net rows are not routes. They are left out here, and
    checked separately by :func:`route_gaps`. ``mapping`` has ``type``, ``country`` and
    ``route``, where a ``*`` country catches the rest of its type. An unmapped row raises.
    """
    unknown = set(mapping["route"]) - set(UK_ROUTES)
    if unknown:
        raise ValueError(f"unknown route(s): {sorted(unknown)}")
    rows = trade[(trade["flow"] != "net") & ~_is_total(trade)].copy()
    rows["signed"] = rows["value"].where(rows["flow"] == "imports", -rows["value"])
    specific = mapping[mapping["country"] != WILDCARD].set_index(["type", "country"])["route"]
    wildcard = mapping[mapping["country"] == WILDCARD].set_index("type")["route"]
    keys = pd.MultiIndex.from_frame(rows[["type", "country"]])
    route = pd.Series(specific.reindex(keys).to_numpy(), index=rows.index)
    route = route.fillna(rows["type"].map(wildcard))
    if route.isna().any():
        missing = sorted(set(zip(rows.loc[route.isna(), "type"], rows.loc[route.isna(), "country"],
                                 strict=True)))  # fmt: skip
        raise ValueError(f"no route for {missing[:10]}")
    rows["route"] = route
    table = rows.groupby(["ts", "route"])["signed"].sum().unstack("route")
    return table.reindex(columns=list(UK_ROUTES)).fillna(0.0).sort_index()


def route_gaps(trade: pd.DataFrame, routes: pd.DataFrame) -> pd.Series:
    """Published net imports minus the sum of routes, per month (mcm). Any gap means a
    route lost or double counted a flow."""
    net = trade[trade["flow"] == "net"].groupby("ts")["value"].sum()
    return (net - routes.sum(axis=1)).dropna()


def balance_table(balance: pd.DataFrame) -> pd.DataFrame:
    """Month x line (mcm) from long ET 4.2 rows (``line``, ``ts``, ``value``). Adds the
    demand groups (NaN unless every part is present), ``losses_statdiff`` (net supply minus
    demand) and ``supply_gap`` (the net-supply identity's residual, ~0 when the parts add up)."""
    wide = balance.groupby(["ts", "line"])["value"].sum(min_count=1).unstack("line")
    out = wide.copy()
    for group, parts in DEMAND_GROUPS.items():
        present = [p for p in parts if p in wide.columns]
        out[f"demand_{group}"] = (
            wide[present].sum(axis=1, min_count=len(parts)) if len(present) == len(parts)
            else float("nan")
        )  # fmt: skip
    out["losses_statdiff"] = wide["net_supply"] - wide["demand"]
    out["supply_gap"] = (
        wide["production"] + wide["net_imports"] + wide["stock_change"] + wide["biomethane"]
        - wide["net_supply"]
    )  # fmt: skip
    return out.sort_index()


def lng_call(lines: pd.DataFrame) -> pd.Series:
    """LNG the UK needs, month by month (mcm): demand plus losses minus every other source.

    ``lines`` needs ``demand``, ``production``, ``biomethane``, ``stock_change``
    and the four pipeline routes. ``losses_statdiff`` is used where present, and treated as
    zero otherwise (in a projection). On history this equals net LNG imports exactly, which
    the tests pin. NaN wherever an input is missing.
    """
    losses = lines.get("losses_statdiff", 0.0)
    other_sources = (
        lines["production"] + lines["biomethane"] + lines["stock_change"]
        + lines[list(PIPELINE_ROUTES)].sum(axis=1, min_count=len(PIPELINE_ROUTES))
    )  # fmt: skip
    return lines["demand"] + losses - other_sources


def eu_mirror(routes: pd.DataFrame) -> pd.Series:
    """The UK's net pipeline exports to EU members (mcm), as the EU model should see them:
    to Belgium and the Netherlands net, plus Ireland. The Isle of Man is not in the EU."""
    return -(routes["continent_pipeline"] + routes["ireland_exports"])
