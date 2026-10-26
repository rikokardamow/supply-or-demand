"""pipelines/derived/uk_gas_balance.py and its committed files. All figures synthetic."""

from __future__ import annotations

import pandas as pd
from core import uk_gas_balance as uk
from pipelines.derived import uk_gas_balance as d
from pipelines.derived.eu_gas_balance import load_assumptions

AT = pd.Timestamp("2026-10-26")


def test_the_committed_mapping_and_assumptions_are_valid() -> None:
    mapping = pd.read_csv(d.ROUTES_CSV)
    assumptions = load_assumptions(d.ASSUMPTIONS_CSV)

    assert set(mapping["route"]) <= set(uk.UK_ROUTES)
    assert not mapping.duplicated(["type", "country"]).any()
    assert set(assumptions["line"]) <= set(d.PROJECTED_LINES) | set(uk.PIPELINE_ROUTES)


def _inputs():
    months = pd.date_range("2025-01-01", "2025-12-01", freq="MS")
    trade = pd.concat(
        [
            pd.DataFrame({"flow": "imports", "type": "pipeline", "country": "norway",
                          "pipeline": "langeled", "ts": months, "value": 2000.0}),
            pd.DataFrame({"flow": "imports", "type": "lng", "country": "usa", "pipeline": "na",
                          "ts": months, "value": 500.0}),
            pd.DataFrame({"flow": "net", "type": "net_imports", "country": "net_imports",
                          "pipeline": "na", "ts": months, "value": 2500.0}),
        ]
    )  # fmt: skip
    lines = {
        "production": 2000.0,
        "net_imports": 2500.0,
        "stock_change": 0.0,
        "biomethane": 0.0,
        "synthetic": 0.0,
        "net_supply": 4500.0,
        "demand": 4500.0,
    }
    balance = pd.concat(
        [pd.DataFrame({"line": k, "ts": months, "value": v}) for k, v in lines.items()]
    )
    assumptions = pd.DataFrame(
        {"line": [*d.PROJECTED_LINES, *uk.PIPELINE_ROUTES], "year": 2026, "yoy_pct": 0.0,
         "author": "test", "as_of": "2026-10-26"}
    )  # fmt: skip
    return trade, balance, pd.read_csv(d.ROUTES_CSV), assumptions


def test_build_rows_solves_the_projection_for_lng() -> None:
    trade, balance, mapping, assumptions = _inputs()

    rows = d.build_rows(trade, balance, mapping, assumptions, pd.Series(dtype=float), AT)

    ids = set(rows["series_id"])
    assert "derived.uk_gas.lng_call.total.projected" in ids
    assert "derived.uk_gas.route.lng_us.projected" not in ids  # LNG is the solved total
    call = rows[rows["series_id"] == "derived.uk_gas.lng_call.total.projected"]
    assert (call["value"] == 0.5).all()  # 4.5 demand - 2.0 production - 2.0 Norway
    assert "derived.uk_gas.check.eu_mirror_gap.observed" not in ids  # no EU model: no check


def test_the_mirror_check_is_written_when_the_eu_view_exists() -> None:
    trade, balance, mapping, assumptions = _inputs()
    eu_view = pd.Series(0.0, index=pd.date_range("2025-01-01", "2025-12-01", freq="MS"))

    rows = d.build_rows(trade, balance, mapping, assumptions, eu_view, AT)

    assert "derived.uk_gas.mirror.uk_view.observed" in set(rows["series_id"])
