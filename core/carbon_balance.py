"""EU ETS supply and demand for allowances: pure arithmetic, no I/O.

This repo's own model on public data: verified emissions and free allocation from the Union
Registry, auctioned volumes and clearing prices from EEX. A Bloomberg Intelligence EUA
calculator was read as a layout example only. Spec:
`docs/superpowers/specs/2026-10-26-eu-carbon-model-mapping.md`.

- **Demand** is what must be surrendered: verified emissions, with shipping scaled by its
  legislated phase-in (shipping emissions in the registry are reported before it).
- **Supply** is free allocation plus auctioned volume.
- **Surplus** is supply minus demand for the year. It is an annual flow, NOT the Total Number
  of Allowances in Circulation: the Market Stability Reserve and banking are outside it.
- **Scope** is today's EU ETS for every year: the registry file minus Great Britain, which
  left after 2020. Keeping the UK in for the early years would put a break in 2021.
"""

from __future__ import annotations

import pandas as pd

EXCLUDED_REGISTRIES = frozenset({"gb"})
SECTORS = ("combustion", "industry", "aviation", "maritime")
FIRST_COMPARABLE_YEAR = 2013  # the file's Read Me: pre-2013 is not comparable (phase III)
COMPLETE_SHARE = 0.98
# Shipping entered the EU ETS with its 2024 emissions (Directive (EU) 2023/959).
SHIPPING_FROM = 2024  # a year needs this share of the prior year's reporting accounts


def annual_ets(totals: pd.DataFrame) -> pd.DataFrame:
    """Year x column from long registry totals (``metric``, ``sector``, ``registry``,
    ``year``, ``value``): ``emissions_<sector>``, ``emissions_total``,
    ``free_allocation``, ``reporting_<sector>``. Only the in-scope registries, from 2013."""
    rows = totals[
        ~totals["registry"].str.lower().isin(EXCLUDED_REGISTRIES)
        & (totals["year"] >= FIRST_COMPARABLE_YEAR)
    ]
    by = (
        rows.groupby(["year", "metric", "sector"])["value"]
        .sum(min_count=1)
        .unstack(["metric", "sector"])
    )
    out = pd.DataFrame(index=by.index)
    for sector in SECTORS:
        out[f"emissions_{sector}"] = by.get(("verified_emissions", sector))
        out[f"reporting_{sector}"] = by.get(("reporting", sector))
    out["emissions_total"] = out[[f"emissions_{s}" for s in SECTORS]].sum(axis=1, min_count=1)
    allocation = [c for c in by.columns if c[0] == "free_allocation"]
    out["free_allocation"] = by[allocation].sum(axis=1, min_count=1) if allocation else None
    out.index = pd.to_datetime(out.index.astype(str) + "-01-01")
    return out.sort_index()


def complete_years(ets: pd.DataFrame, share: float = COMPLETE_SHARE) -> pd.Series:
    """True for every year except a latest year still being reported.

    The registry file is extracted soon after the reporting deadline for its latest year, so
    only that year can be incomplete. Every earlier year is final. The latest year counts as
    complete once its stationary and aviation reporting accounts reach ``share`` of the
    previous year's. Comparing every year this way would be wrong: account counts also
    fall for real reasons (closures, aviation in 2020), and a fall in a final year is data.
    """
    complete = pd.Series(True, index=ets.index)
    if len(ets) >= 2:
        cols = ["reporting_combustion", "reporting_industry", "reporting_aviation"]
        counts = ets[cols].sum(axis=1)
        complete.iloc[-1] = bool(counts.iloc[-1] >= share * counts.iloc[-2])
    return complete


def surrender_demand(ets: pd.DataFrame, maritime_phase_in: pd.Series) -> pd.Series:
    """Allowances to surrender per year: combustion + industry + aviation emissions, plus
    shipping emissions times the phase-in share for that year (``maritime_phase_in`` is
    indexed by year). Shipping is 0 before ``SHIPPING_FROM``. From then on, a year with no
    phase-in row, or with no shipping figure, is NaN, not zero."""
    years = pd.DatetimeIndex(ets.index).year
    phase = maritime_phase_in.reindex(years).to_numpy()
    maritime = pd.Series(ets["emissions_maritime"].astype("float64").to_numpy() * phase,
                         index=ets.index)  # fmt: skip
    maritime[years < SHIPPING_FROM] = 0.0  # not yet in the scheme: owes nothing
    rest = ets[["emissions_combustion", "emissions_industry", "emissions_aviation"]]
    return rest.sum(axis=1, min_count=3) + maritime


def auctioned_by_year(auctions: pd.DataFrame) -> pd.Series:
    """Allowances auctioned per calendar year (t) from daily rows (``ts``, ``volume``)."""
    years = pd.DatetimeIndex(auctions["ts"]).year
    totals = auctions.groupby(years)["volume"].sum(min_count=1)
    totals.index = pd.to_datetime(totals.index.astype(str) + "-01-01")
    return totals


def price_summary(auctions: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(monthly mean clearing price, annual volume-weighted price) from daily rows
    (``ts``, ``price``, ``volume``), both in €/t."""
    frame = auctions.dropna(subset=["price", "volume"]).set_index("ts").sort_index()
    index = pd.DatetimeIndex(frame.index)
    monthly = frame["price"].groupby(index.to_period("M")).mean()
    monthly.index = pd.PeriodIndex(monthly.index).to_timestamp()
    weighted = (frame["price"] * frame["volume"]).groupby(index.year).sum() / frame[
        "volume"
    ].groupby(index.year).sum()
    weighted.index = pd.to_datetime(weighted.index.astype(str) + "-01-01")
    return monthly, weighted


def balance(
    ets: pd.DataFrame, auctioned: pd.Series, demand: pd.Series, carried: float = 0.0
) -> pd.DataFrame:
    """Year x (free_allocation, auctioned, supply, demand, surplus, cumulative_surplus), in
    tonnes, for years with every term. The cumulative surplus is a running sum of flows from
    ``carried`` (0 for the first observed year; the last observed total for a projection),
    not a bank balance."""
    out = pd.DataFrame(
        {"free_allocation": ets["free_allocation"], "auctioned": auctioned, "demand": demand}
    ).dropna()
    out["supply"] = out["free_allocation"] + out["auctioned"]
    out["surplus"] = out["supply"] - out["demand"]
    out["cumulative_surplus"] = carried + out["surplus"].cumsum()
    return out
