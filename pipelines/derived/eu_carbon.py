"""EU ETS allowance balance and auction prices, observed and projected: ``derived.eu_carbon.*``.

    python -m pipelines.derived.eu_carbon        (after pipelines.carbon.pull)

Inputs: ``eu_ets.*`` (Union Registry) and ``eex.*`` (EEX auctions) from the lake, the
committed ``pipelines/carbon/maritime_phase_in.csv`` and ``eu_carbon/assumptions.csv``.

Series written (``source="derived"``, ``geo="EU"``):

- ``derived.eu_carbon.ets.<column>.observed``: annual, Mt (``core.carbon_balance.annual_ets``).
- ``derived.eu_carbon.balance.<free_allocation|auctioned|supply|demand|surplus|
  cumulative_surplus>.<observed|projected>``: annual, Mt. Observed only for complete years.
- ``derived.eu_carbon.check.complete.observed``: 1 for a complete registry year, else 0.
- ``derived.eu_carbon.price.<monthly_mean|annual_vwap>.observed``: €/t, auction clearing
  prices for general allowances (EEX contract T3PA), not market prices.
- ``derived.eu_carbon.tnac.<tnac|msr_intake|rule_intake>.observed``: annual, Mt, ts = 1 January
  of the TNAC year. The published TNAC and MSR intake come from ``pipelines/carbon/tnac.csv``
  (each figure quoted with its source); ``rule_intake`` is ``core.carbon_balance.msr_intake``
  on the same TNAC, kept as a check.

Read through ``pipelines.derived.eu_gas_balance.latest_run``. Not scheduled.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from core import carbon_balance as cb
from core import gas_projection as gp
from core.failures import fails_loudly, record_failure
from core.storage import read_ts_long, write_ts_long

from pipelines.derived.eu_gas_balance import load_assumptions

HERE = Path(__file__).parent / "eu_carbon"
ASSUMPTIONS_CSV = HERE / "assumptions.csv"
PHASE_IN_CSV = Path(__file__).parent.parent / "carbon" / "maritime_phase_in.csv"
TNAC_CSV = Path(__file__).parent.parent / "carbon" / "tnac.csv"
PROJECTION_END = pd.Timestamp("2027-01-01")
PROJECTED_LINES = (
    "emissions_combustion",
    "emissions_industry",
    "emissions_aviation",
    "emissions_maritime",
    "free_allocation",
    "auctioned",
)
_PREFIX = "derived.eu_carbon"
MT = 1e6


def _latest(rows: pd.DataFrame) -> pd.DataFrame:
    return rows.sort_values("revision_date").drop_duplicates(["series_id", "ts"], keep="last")


def read_registry() -> pd.DataFrame:
    rows = _latest(read_ts_long(series_prefix="eu_ets.", source="eu_registry"))
    parts = rows["series_id"].str.split(".", expand=True)
    return pd.DataFrame(
        {
            "metric": parts[1],
            "sector": parts[2],
            "registry": parts[3],
            "year": pd.DatetimeIndex(rows["ts"]).year,
            "value": rows["value"],
        }
    )


def read_auctions() -> pd.DataFrame:
    """Daily ``ts``, ``product`` (eua/euaa), ``price``, ``volume``."""
    rows = _latest(read_ts_long(series_prefix="eex.", source="eex"))
    rows = rows[rows["series_id"].str.match(r"eex\.(eua|euaa)\.auction\.(price|volume)$")]
    parts = rows["series_id"].str.split(".", expand=True)
    long = rows.assign(product=parts[1], metric=parts[3])
    wide = long.pivot_table(index=["ts", "product"], columns="metric", values="value")
    return wide.reset_index().rename_axis(columns=None)


def _rows(
    table: pd.DataFrame, kind: str, label: str, unit: str, freq: str, at: pd.Timestamp
) -> pd.DataFrame:
    long = table.rename_axis("ts").reset_index().melt(id_vars="ts", var_name="name").dropna()
    return pd.DataFrame(
        {
            "series_id": f"{_PREFIX}.{kind}." + long["name"] + f".{label}",
            "source": "derived",
            "ts": long["ts"],
            "value": long["value"].astype("float64"),
            "unit": unit,
            "geo": "EU",
            "freq": freq,
            "revision_date": at,
        }
    )


def _balance_from(lines: pd.DataFrame, phase: pd.Series, carried: float = 0.0) -> pd.DataFrame:
    demand = cb.surrender_demand(lines, phase)
    return cb.balance(lines, lines["auctioned"], demand, carried)


def tnac_rows(tnac: pd.DataFrame, at: pd.Timestamp) -> pd.DataFrame:
    index = pd.to_datetime(tnac["tnac_year"].astype(str) + "-01-01")
    rule = [
        cb.msr_intake(int(y), float(v)) if y >= cb.FIRST_RULE_TNAC_YEAR else float("nan")
        for y, v in zip(tnac["tnac_year"], tnac["tnac"], strict=True)
    ]
    table = pd.DataFrame(
        {"tnac": tnac["tnac"].to_numpy(), "msr_intake": tnac["msr_intake"].to_numpy(),
         "rule_intake": rule},
        index=index,
    )  # fmt: skip
    return _rows(table / MT, "tnac", "observed", "Mt", "A", at)


def build_rows(
    registry: pd.DataFrame,
    auctions: pd.DataFrame,
    phase_in: pd.Series,
    assumptions: pd.DataFrame,
    at: pd.Timestamp,
    tnac: pd.DataFrame | None = None,
) -> pd.DataFrame:
    ets = cb.annual_ets(registry)
    complete = cb.complete_years(ets)
    auctioned = cb.auctioned_by_year(auctions)
    lines = ets.assign(auctioned=auctioned)[[*PROJECTED_LINES]].loc[complete[complete].index]
    # Before shipping entered the ETS it owed nothing: a real zero, not missing data.
    before = pd.DatetimeIndex(lines.index).year < cb.SHIPPING_FROM
    lines.loc[before, "emissions_maritime"] = 0.0
    observed = _balance_from(lines.dropna(subset=["free_allocation", "auctioned"]), phase_in)
    monthly, weighted = cb.price_summary(auctions[auctions["product"] == "eua"])

    frames = [
        _rows(
            ets.drop(columns=[c for c in ets.columns if str(c).startswith("reporting")]) / MT,
            "ets",
            "observed",
            "Mt",
            "A",
            at,
        ),
        _rows(observed / MT, "balance", "observed", "Mt", "A", at),
        _rows(
            pd.DataFrame({"complete": complete.astype(float)}), "check", "observed", "flag", "A", at
        ),
        _rows(pd.DataFrame({"monthly_mean": monthly}), "price", "observed", "EUR/t", "M", at),
        _rows(pd.DataFrame({"annual_vwap": weighted}), "price", "observed", "EUR/t", "A", at),
    ]
    history = lines.dropna()
    carried = float(observed["cumulative_surplus"].iloc[-1]) if not observed.empty else 0.0
    projected = gp.project(history, assumptions, PROJECTION_END, freq="YS")
    if not projected.empty and projected.notna().all(axis=1).any():
        frames.append(
            _rows(
                _balance_from(projected.dropna(), phase_in, carried) / MT,
                "balance",
                "projected",
                "Mt",
                "A",
                at,
            )
        )
    if tnac is not None and not tnac.empty:
        frames.append(tnac_rows(tnac, at))
    return pd.concat(frames, ignore_index=True)


@fails_loudly("derived.eu_carbon")
def main() -> None:
    registry, auctions = read_registry(), read_auctions()
    if registry.empty or auctions.empty:
        record_failure(
            "derived.eu_carbon",
            RuntimeError("no registry or EEX rows: run python -m pipelines.carbon.pull"),
        )
        return
    phase_in = pd.read_csv(PHASE_IN_CSV).set_index("year")["share"]
    rows = build_rows(
        registry,
        auctions,
        phase_in,
        load_assumptions(ASSUMPTIONS_CSV),
        pd.Timestamp(datetime.now(UTC)).tz_localize(None),
        pd.read_csv(TNAC_CSV),
    )
    write_ts_long(rows, source="derived")
    labels = rows["series_id"].str.rsplit(".", n=1).str[-1].value_counts()
    print(
        f"derived.eu_carbon: wrote {len(rows)} rows across {rows['series_id'].nunique()} "
        f"series ({int(labels.get('observed', 0))} observed, "
        f"{int(labels.get('projected', 0))} projected)",
        flush=True,
    )


if __name__ == "__main__":
    main()
