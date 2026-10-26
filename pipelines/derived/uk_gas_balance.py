"""UK gas balance by route and the call on LNG, observed and projected: ``derived.uk_gas.*``.

    python -m pipelines.derived.uk_gas_balance      (after pipelines.desnz_gas.pull, and
                                                     after pipelines.derived.eu_gas_balance
                                                     for the cross-check)

Inputs: the lake's ``desnz.gas.*`` rows, the committed ``uk_gas/routes.csv`` and
``uk_gas/assumptions.csv``, and, if present, ``derived.eu_gas.route.uk`` for the mirror check.

Series written (``source="derived"``, monthly, ``geo="GB"``, bcm unless stated):

- ``derived.uk_gas.route.<route>.<observed|projected>``: net imports by route. LNG routes
  are observed only, because the projection solves for LNG as a single total.
- ``derived.uk_gas.balance.<line>.<observed|projected>``
- ``derived.uk_gas.lng_call.total.<observed|projected>``: observed is net LNG imports. The
  projection is what LNG must supply once everything else is assumed.
- ``derived.uk_gas.check.<route_gap|supply_gap|eu_mirror_gap>.observed``
- ``derived.uk_gas.mirror.<uk_view|eu_view>.observed``: UK net exports to the EU as each
  side's statistics record them.

Read through ``pipelines.derived.eu_gas_balance.latest_run``, which keeps only the latest run.
Not scheduled: run it by hand after the monthly DESNZ pull, or after editing an assumption.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from core import gas_projection as gp
from core import uk_gas_balance as uk
from core.failures import fails_loudly, record_failure
from core.storage import read_ts_long, write_ts_long

from pipelines.derived.eu_gas_balance import latest_run, load_assumptions

HERE = Path(__file__).parent / "uk_gas"
ROUTES_CSV = HERE / "routes.csv"
ASSUMPTIONS_CSV = HERE / "assumptions.csv"
PROJECTION_END = pd.Timestamp("2027-12-01")
PROJECTED_LINES = ("production", "demand", "biomethane", "stock_change")
OBSERVED_LINES = (
    "production", "imports", "exports", "net_imports", "stock_change", "biomethane", "demand",
    *(f"demand_{g}" for g in uk.DEMAND_GROUPS), "losses_statdiff",
)  # fmt: skip
_PREFIX = "derived.uk_gas"


def _latest(rows: pd.DataFrame) -> pd.DataFrame:
    return rows.sort_values("revision_date").drop_duplicates(["series_id", "ts"], keep="last")


def read_trade() -> pd.DataFrame:
    rows = _latest(read_ts_long(series_prefix="desnz.gas.", source="desnz"))
    rows = rows[rows["series_id"].str.match(r"desnz\.gas\.(imports|exports|net)\.")]
    parts = rows["series_id"].str.split(".", expand=True)
    return pd.DataFrame(
        {"flow": parts[2], "type": parts[3], "country": parts[4], "pipeline": parts[5],
         "ts": rows["ts"], "value": rows["value"]}
    )  # fmt: skip


def read_balance() -> pd.DataFrame:
    rows = _latest(read_ts_long(series_prefix="desnz.gas.balance.", source="desnz"))
    return pd.DataFrame(
        {"line": rows["series_id"].str.split(".").str[3], "ts": rows["ts"], "value": rows["value"]}
    )


def read_eu_view() -> pd.Series:
    """The EU model's UK route in mcm, or empty if the EU model has not run."""
    eu = latest_run(read_ts_long(series_prefix="derived.eu_gas.route.uk.", source="derived"))
    eu = eu[eu["label"] == "observed"]
    return eu.set_index("ts")["value"] * 1000


def _rows(table: pd.DataFrame, kind: str, label: str, unit: str, at: pd.Timestamp) -> pd.DataFrame:
    long = table.rename_axis("ts").reset_index().melt(id_vars="ts", var_name="name").dropna()
    return pd.DataFrame(
        {
            "series_id": f"{_PREFIX}.{kind}." + long["name"] + f".{label}",
            "source": "derived",
            "ts": long["ts"],
            "value": long["value"].astype("float64"),
            "unit": unit,
            "geo": "GB",
            "freq": "M",
            "revision_date": at,
        }
    )


def build_rows(
    trade: pd.DataFrame,
    balance: pd.DataFrame,
    mapping: pd.DataFrame,
    assumptions: pd.DataFrame,
    eu_view: pd.Series,
    at: pd.Timestamp,
) -> pd.DataFrame:
    routes = uk.route_table(trade, mapping)
    bal = uk.balance_table(balance)
    lng = routes[list(uk.LNG_ROUTES)].sum(axis=1)
    checks = pd.DataFrame(
        {"route_gap": uk.route_gaps(trade, routes), "supply_gap": bal["supply_gap"]}
    )
    frames = [
        _rows(routes / 1000, "route", "observed", "bcm", at),
        _rows(
            bal[[c for c in OBSERVED_LINES if c in bal]] / 1000, "balance", "observed", "bcm", at
        ),
        _rows(pd.DataFrame({"total": lng}) / 1000, "lng_call", "observed", "bcm", at),
    ]
    if not eu_view.empty:
        mirror = pd.concat({"uk_view": uk.eu_mirror(routes), "eu_view": eu_view}, axis=1).dropna()
        checks["eu_mirror_gap"] = mirror["eu_view"] - mirror["uk_view"]
        frames.append(_rows(mirror / 1000, "mirror", "observed", "bcm", at))
    frames.append(_rows(checks / 1000, "check", "observed", "bcm", at))

    history = pd.concat(
        [bal[list(PROJECTED_LINES)], routes[list(uk.PIPELINE_ROUTES)]], axis=1, sort=True
    ).dropna()
    projected = gp.project(history, assumptions, PROJECTION_END)
    if not projected.empty and projected.notna().any().any():
        call = uk.lng_call(projected)
        frames += [
            _rows(projected[list(uk.PIPELINE_ROUTES)] / 1000, "route", "projected", "bcm", at),
            _rows(projected[list(PROJECTED_LINES)] / 1000, "balance", "projected", "bcm", at),
            _rows(pd.DataFrame({"total": call}) / 1000, "lng_call", "projected", "bcm", at),
        ]
    return pd.concat(frames, ignore_index=True)


@fails_loudly("derived.uk_gas")
def main() -> None:
    trade, balance = read_trade(), read_balance()
    if trade.empty or balance.empty:
        record_failure(
            "derived.uk_gas", RuntimeError("no DESNZ rows: run python -m pipelines.desnz_gas.pull")
        )
        return
    rows = build_rows(
        trade,
        balance,
        pd.read_csv(ROUTES_CSV),
        load_assumptions(ASSUMPTIONS_CSV),
        read_eu_view(),
        pd.Timestamp(datetime.now(UTC)).tz_localize(None),
    )
    write_ts_long(rows, source="derived")
    labels = rows["series_id"].str.rsplit(".", n=1).str[-1].value_counts()
    print(
        f"derived.uk_gas: wrote {len(rows)} rows across {rows['series_id'].nunique()} series "
        f"({int(labels.get('observed', 0))} observed, {int(labels.get('projected', 0))} "
        "projected)",
        flush=True,
    )


if __name__ == "__main__":
    main()
