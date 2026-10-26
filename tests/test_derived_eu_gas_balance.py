"""pipelines/derived/eu_gas_balance.py and its committed mapping and assumptions files.
All figures synthetic."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from core import eu_gas_balance as egb
from pipelines.derived import eu_gas_balance as d

AT = pd.Timestamp("2026-10-26")


def test_the_committed_mapping_is_valid_and_non_overlapping() -> None:
    mapping = d.load_routes()

    assert set(mapping["route"]) <= set(egb.ROUTES)
    for product in egb.PRODUCTS:
        assert ((mapping["partner"] == egb.WILDCARD) & (mapping["product"] == product)).sum() == 1
    # Every partner/product pair whose rules are dated must not overlap in time.
    for (_, _), rules in mapping[mapping["partner"] != "*"].groupby(["partner", "product"]):
        rules = rules.sort_values("valid_from", na_position="first")
        ends = rules["valid_to"].iloc[:-1].to_numpy()
        starts = rules["valid_from"].iloc[1:].to_numpy()
        assert all(e < s for e, s in zip(ends, starts, strict=True))
    assert not set(mapping["partner"]) & egb.EU27  # intra-EU is excluded, never mapped


def test_the_committed_assumptions_name_an_author_and_date() -> None:
    assumptions = d.load_assumptions()

    assert assumptions[["author", "as_of"]].notna().all().all()
    assert set(assumptions["line"]) <= set(egb.ROUTES) | set(d.PROJECTED_LINES)


def test_an_assumption_without_an_author_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "assumptions.csv"
    path.write_text("line,year,yoy_pct,author,as_of\nlng_us,2026,5,,2026-10-26\n")

    with pytest.raises(ValueError, match="author"):
        d.load_assumptions(path)


def test_only_the_latest_run_is_read() -> None:
    def row(series: str, ts: str, run: str, value: float) -> dict[str, object]:
        return {"series_id": series, "ts": pd.Timestamp(ts), "value": value,
                "revision_date": pd.Timestamp(run)}  # fmt: skip

    rows = pd.DataFrame(
        [
            row("derived.eu_gas.route.uk.observed", "2024-03-01", "2026-10-01", 9.0),
            row("derived.eu_gas.route.uk.observed", "2024-04-01", "2026-10-26", 1.0),
        ]
    )

    latest = d.latest_run(rows)

    assert list(latest["ts"]) == [pd.Timestamp("2024-04-01")]  # the stale March row is gone
    assert list(latest[["kind", "name", "label"]].iloc[0]) == ["route", "uk", "observed"]


def _inputs():
    months = pd.date_range("2025-01-01", "2025-12-01", freq="MS")
    trade = []
    for ts in months:
        trade += [
            ("imports", "gas", "no", ts, 7000.0),
            ("imports", "gas", "us", ts, 4000.0),
            ("imports", "lng", "us", ts, 4000.0),
        ]
    trade = pd.DataFrame(trade, columns=["flow", "product", "partner", "ts", "value"])
    totals = trade.groupby(["flow", "product", "ts"], as_index=False)["value"].sum()
    trade = pd.concat([trade, totals.assign(partner="total")[trade.columns]])

    def bal(line: str, value: float, geo: str = "eu") -> pd.DataFrame:
        return pd.DataFrame({"line": line, "geo": geo, "ts": months, "value": value})

    balance_mcm = pd.concat(
        [bal("iprd", 3000.0), bal("imp", 11000.0), bal("exp", 0.0), bal("ic_obs", 13000.0),
         bal("stk_chg_mg", 1000.0)]
    )  # fmt: skip
    balance_tj = pd.concat([bal("ic_obs", 13000.0 * 38.0)])  # 38 TJ per mcm
    mapping = d.load_routes()
    assumptions = pd.DataFrame(
        {"line": [*egb.ROUTES, *d.PROJECTED_LINES], "year": 2026, "yoy_pct": 0.0,
         "author": "test", "as_of": "2026-10-26"}
    )  # fmt: skip
    gie = pd.Series([500.0], index=[pd.Timestamp("2025-12-31")])
    return trade, balance_mcm, balance_tj, mapping, assumptions, gie


def test_build_rows_writes_observed_and_projected_series() -> None:
    trade, balance_mcm, balance_tj, mapping, assumptions, gie = _inputs()

    rows = d.build_rows(trade, balance_mcm, balance_tj, mapping, assumptions, gie, 1000.0, AT)

    ids = set(rows["series_id"])
    assert "derived.eu_gas.route.norway_pipeline.observed" in ids
    assert "derived.eu_gas.route.lng_us.projected" in ids
    assert "derived.eu_gas.storage.fill_pct.projected" in ids
    obs = rows[rows["series_id"] == "derived.eu_gas.route.norway_pipeline.observed"]
    assert (obs["value"] == 7.0).all() and set(obs["unit"]) == {"bcm"}
    level = rows[rows["series_id"] == "derived.eu_gas.storage.level.projected"].sort_values("ts")
    # 3 + 7 + 4 - 13 = +1 bcm a month, at 38 TJ per mcm = 10.56 TWh a month.
    assert level["value"].iloc[0] == pytest.approx(500.0 + 1000 * 38.0 / 3600)


def test_no_projection_without_assumptions() -> None:
    trade, balance_mcm, balance_tj, mapping, _, gie = _inputs()
    empty = pd.DataFrame(columns=["line", "year", "yoy_pct", "author", "as_of"])

    rows = d.build_rows(trade, balance_mcm, balance_tj, mapping, empty, gie, 1000.0, AT)

    assert not rows["series_id"].str.endswith(".projected").any()
