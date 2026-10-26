"""pipelines/derived/eu_carbon.py and its committed files. All figures synthetic."""

from __future__ import annotations

import pandas as pd
from pipelines.derived import eu_carbon as d
from pipelines.derived.eu_gas_balance import load_assumptions

AT = pd.Timestamp("2026-10-26")


def test_the_committed_phase_in_and_assumptions_are_valid() -> None:
    phase = pd.read_csv(d.PHASE_IN_CSV)
    assumptions = load_assumptions(d.ASSUMPTIONS_CSV)

    assert phase["share"].between(0, 1).all() and phase["source"].notna().all()
    assert phase.set_index("year")["share"][2026] == 1.0
    assert set(assumptions["line"]) <= set(d.PROJECTED_LINES)


def _registry() -> pd.DataFrame:
    rows = []
    for year, reporting in ((2022, 100.0), (2023, 100.0), (2024, 50.0)):  # 2024 still reporting
        for sector, value in (("combustion", 600.0), ("industry", 300.0), ("aviation", 50.0)):
            rows += [
                ("verified_emissions", sector, "de", year, value * 1e6),
                ("reporting", sector, "de", year, reporting),
                ("free_allocation", sector, "de", year, value / 2 * 1e6),
            ]
    return pd.DataFrame(rows, columns=["metric", "sector", "registry", "year", "value"])


def _auctions() -> pd.DataFrame:
    days = pd.to_datetime(["2022-06-01", "2023-06-01", "2024-06-01"])
    return pd.DataFrame(
        {"ts": days, "product": "eua", "price": [80.0, 85.0, 65.0], "volume": [500e6] * 3}
    )


def test_an_incomplete_latest_year_is_kept_out_of_the_balance() -> None:
    assumptions = pd.DataFrame(
        {"line": list(d.PROJECTED_LINES), "year": 2024, "yoy_pct": 0.0, "author": "t",
         "as_of": "2026-10-26"}
    )  # fmt: skip

    rows = d.build_rows(_registry(), _auctions(), pd.Series({2024: 0.4}), assumptions, AT)

    observed = rows[rows["series_id"] == "derived.eu_carbon.balance.surplus.observed"]
    assert list(observed["ts"].dt.year) == [2022, 2023]
    # supply 475 + 500 = 975, demand 950: +25 a year
    assert (observed["value"] == 25.0).all()
    cumulative = rows[rows["series_id"] == "derived.eu_carbon.balance.cumulative_surplus.projected"]
    assert list(cumulative["value"]) == [75.0]  # carried 50, plus the projected 2024's 25
    flags = rows[rows["series_id"] == "derived.eu_carbon.check.complete.observed"]
    assert list(flags["value"]) == [1.0, 1.0, 0.0]
