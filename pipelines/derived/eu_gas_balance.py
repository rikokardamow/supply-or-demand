"""EU-27 gas balance by supply route, observed and projected, written as ``derived.eu_gas.*``.

    python -m pipelines.derived.eu_gas_balance        (after pipelines.eurostat_gas.pull)

Inputs:
- the lake's ``estat.gas.*`` rows from ``pipelines/eurostat_gas``
- ``eu_gas/routes.csv``, the committed partner-to-route mapping
- ``eu_gas/assumptions.csv``, the committed year-on-year assumptions with author and date
- GIE ``agsi.EU.gas_in_storage``, the starting level for the storage path

Series written (``source="derived"``, monthly, ``geo="EU"``):

- ``derived.eu_gas.route.<route>.<observed|projected>`` in bcm, net imports. Read only via
  :func:`latest_run`.
- ``derived.eu_gas.balance.<line>.<observed|projected>`` in bcm
- ``derived.eu_gas.check.<name>.observed`` in bcm, the model's own reconciliation residuals
- ``derived.eu_gas.member_sum.<line>.observed``, a flag of 1 where the EU-27 cell was blank
  at Eurostat and was rebuilt from member states
- ``derived.eu_gas.storage.<level|fill_pct>.projected`` in TWh and %

Not scheduled. Run by hand after the monthly Eurostat pull, or after editing an assumption.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from core import eu_gas_balance as egb
from core import gas_projection as gp
from core.failures import fails_loudly, record_failure
from core.storage import read_ts_long, write_ts_long

HERE = Path(__file__).parent / "eu_gas"
ROUTES_CSV = HERE / "routes.csv"
ASSUMPTIONS_CSV = HERE / "assumptions.csv"
PROJECTION_END = pd.Timestamp("2027-12-01")
PROJECTED_LINES = ("production", "consumption")
_PREFIX = "derived.eu_gas"
_LABELS = ("observed", "projected")


def load_routes(path: Path = ROUTES_CSV) -> pd.DataFrame:
    mapping = pd.read_csv(path, dtype={"partner": str, "product": str, "route": str})
    for col in ("valid_from", "valid_to"):
        mapping[col] = pd.to_datetime(mapping[col])
    return mapping


def load_assumptions(path: Path = ASSUMPTIONS_CSV) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"line", "year", "yoy_pct", "author", "as_of"}
    if not required <= set(frame.columns):
        raise ValueError(f"{path.name}: needs columns {sorted(required)}")
    if frame[["author", "as_of"]].isna().any().any():
        raise ValueError(f"{path.name}: every assumption needs an author and a date")
    return frame


def read_trade() -> pd.DataFrame:
    rows = read_ts_long(series_prefix="estat.gas.", source="eurostat_gas")
    rows = rows[rows["series_id"].str.match(r"estat\.gas\.(imports|exports)\.")]
    parts = rows["series_id"].str.split(".", expand=True)
    return pd.DataFrame(
        {
            "flow": parts[2],
            "product": parts[3],
            "partner": parts[4],
            "ts": rows["ts"],
            "value": rows["value"],
            "revision_date": rows["revision_date"],
        }
    ).pipe(_latest)


def read_balance(prefix: str = "balance") -> pd.DataFrame:
    """Long balance rows (``line``, ``geo``, ``ts``, ``value``), ``geo`` lower-case Eurostat
    codes with ``eu`` for the aggregate."""
    rows = read_ts_long(series_prefix=f"estat.gas.{prefix}.", source="eurostat_gas")
    parts = rows["series_id"].str.split(".")
    return pd.DataFrame(
        {
            "line": parts.str[3],
            "geo": parts.str[4],
            "ts": rows["ts"],
            "value": rows["value"],
            "revision_date": rows["revision_date"],
        }
    ).pipe(_latest)


def _latest(frame: pd.DataFrame) -> pd.DataFrame:
    """Eurostat revises recent months and the lake keeps every pull: the latest revision of
    each cell wins."""
    keys = [c for c in frame.columns if c not in ("value", "revision_date")]
    ordered = frame.sort_values("revision_date")
    return ordered.drop_duplicates(keys, keep="last").drop(columns="revision_date")


def gcv_twh_per_mcm(balance_mcm: pd.DataFrame, balance_tj: pd.DataFrame) -> float:
    """Energy content of a million m3 in TWh (GCV), from Eurostat's own consumption in both
    units over the latest twelve months. It is not a textbook constant."""
    mcm = balance_mcm.query("line == 'ic_obs' and geo == 'eu'").set_index("ts")["value"]
    tj = balance_tj.query("line == 'ic_obs' and geo == 'eu'").set_index("ts")["value"]
    both = pd.concat({"mcm": mcm, "tj": tj}, axis=1, sort=True).dropna().sort_index().tail(12)
    if len(both) < 12:
        raise ValueError("fewer than twelve months with consumption in both units")
    return float(both["tj"].sum() / both["mcm"].sum() / egb.TJ_PER_TWH)


def eu_balance(balance_mcm: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The EU-27 balance table, blank EU cells filled from member states where they cover
    the line (``core.eu_gas_balance.fill_from_members``). Returns ``(table, filled_mask)``
    with columns named as in ``BALANCE_LINES``; ``other_uses`` is recomputed after filling."""
    eu = (
        balance_mcm[balance_mcm["geo"] == "eu"]
        .pivot(index="ts", columns="line", values="value")
        .reindex(columns=list(egb.BALANCE_LINES))
    )
    members = balance_mcm[balance_mcm["geo"] != "eu"]
    filled, mask = egb.fill_from_members(eu, members)
    long = filled.rename_axis("ts").reset_index().melt(id_vars="ts", var_name="line").dropna()
    table = egb.balance_table(long)
    return table, mask.rename(columns=egb.BALANCE_LINES)


def _rows(
    table: pd.DataFrame, kind: str, label: str, unit: str, ingested_at: pd.Timestamp
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
            "freq": "M",
            "revision_date": ingested_at,
        }
    )


def build_rows(
    trade: pd.DataFrame,
    balance_mcm: pd.DataFrame,
    balance_tj: pd.DataFrame,
    mapping: pd.DataFrame,
    assumptions: pd.DataFrame,
    gie_storage_twh: pd.Series,
    gie_capacity_twh: float | None,
    ingested_at: pd.Timestamp,
) -> pd.DataFrame:
    """Everything this module writes, as ``ts_long`` rows."""
    routes = egb.route_totals(egb.assign_routes(egb.net_by_partner(trade), mapping))
    balance, from_members = eu_balance(balance_mcm)
    checks = egb.reconcile(routes, balance)[["intra_eu_asymmetry", "unexplained"]]

    frames = [
        _rows(routes / 1000, "route", "observed", "bcm", ingested_at),
        _rows(balance / 1000, "balance", "observed", "bcm", ingested_at),
        _rows(checks / 1000, "check", "observed", "bcm", ingested_at),
        _rows(
            from_members.astype("float64").where(from_members),
            "member_sum",
            "observed",
            "flag",
            ingested_at,
        ),
    ]

    history = pd.concat([routes, balance[list(PROJECTED_LINES)]], axis=1, sort=True).dropna()
    projected = gp.project(history, assumptions, PROJECTION_END)
    if not projected.empty and projected.notna().any().any():
        frames.append(
            _rows(projected[routes.columns] / 1000, "route", "projected", "bcm", ingested_at)
        )
        frames.append(
            _rows(
                projected[list(PROJECTED_LINES)] / 1000, "balance", "projected", "bcm", ingested_at
            )
        )
        build_mcm = (
            projected["production"]
            + projected[routes.columns].sum(axis=1, min_count=len(routes.columns))
            - projected["consumption"]
        )
        build_twh = build_mcm * gcv_twh_per_mcm(balance_mcm, balance_tj)
        start = gie_storage_twh.dropna().sort_index()
        start = start[start.index < build_twh.index.min()]
        if not start.empty:
            level = gp.storage_path(float(start.iloc[-1]), build_twh)
            storage = pd.DataFrame({"level": level})
            if gie_capacity_twh:
                storage["fill_pct"] = level / gie_capacity_twh * 100
            frames.append(_rows(storage[["level"]], "storage", "projected", "TWh", ingested_at))
            if "fill_pct" in storage:
                frames.append(
                    _rows(storage[["fill_pct"]], "storage", "projected", "%", ingested_at)
                )
    return pd.concat(frames, ignore_index=True)


def latest_run(rows: pd.DataFrame) -> pd.DataFrame:
    """READ ``derived.eu_gas.*`` THROUGH THIS. Each run writes the whole model at once and
    the lake has no delete path, so rows from an older run (a month later found incomplete,
    a projection since overtaken by data) would otherwise linger. Only the latest run's
    rows are kept. Adds ``kind``, ``name`` and ``label`` columns."""
    if rows.empty:
        return rows.assign(kind=[], name=[], label=[])
    frame = rows[rows["revision_date"] == rows["revision_date"].max()]
    parts = frame["series_id"].str.split(".", expand=True)
    frame = frame.assign(kind=parts[2], name=parts[3], label=parts[4])
    result: pd.DataFrame = frame[frame["label"].isin(_LABELS)]
    return result


@fails_loudly("derived.eu_gas")
def main() -> None:
    trade = read_trade()
    balance_mcm = read_balance("balance")
    balance_tj = read_balance("balance_tj")
    if trade.empty or balance_mcm.empty:
        record_failure(
            "derived.eu_gas",
            RuntimeError("no Eurostat gas rows: run python -m pipelines.eurostat_gas.pull"),
        )
        return
    gie = read_ts_long(
        series_ids=["agsi.EU.gas_in_storage", "agsi.EU.working_gas_volume"], source="gie"
    )
    level = gie[gie["series_id"] == "agsi.EU.gas_in_storage"].set_index("ts")["value"]
    capacity = gie[gie["series_id"] == "agsi.EU.working_gas_volume"].sort_values("ts")["value"]

    rows = build_rows(
        trade,
        balance_mcm,
        balance_tj,
        load_routes(),
        load_assumptions(),
        level,
        float(capacity.iloc[-1]) if not capacity.empty else None,
        pd.Timestamp(datetime.now(UTC)).tz_localize(None),
    )
    write_ts_long(rows, source="derived")
    labels = rows["series_id"].str.rsplit(".", n=1).str[-1].value_counts()
    print(
        f"derived.eu_gas: wrote {len(rows)} rows across {rows['series_id'].nunique()} series "
        f"({int(labels.get('observed', 0))} observed, {int(labels.get('projected', 0))} "
        "projected)",
        flush=True,
    )


if __name__ == "__main__":
    main()
