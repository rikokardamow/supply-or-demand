from __future__ import annotations

import pandas as pd
import pytest
from pipelines.eurostat_gas.client import (
    BALANCE,
    IMPORTS,
    EurostatGasClient,
    parse_json_stat,
)
from pipelines.eurostat_gas.pull import balance_rows, trade_rows


def _payload() -> dict:
    """Two partners x two months, row-major over id order, one cell unpublished."""
    return {
        "id": ["partner", "time"],
        "size": [2, 2],
        "dimension": {
            "partner": {"category": {"index": {"NO": 0, "US": 1}}},
            "time": {"category": {"index": {"2026-07": 0, "2026-08": 1}}},
        },
        "value": {"0": 7.5, "1": 8.0, "3": 4.25},
    }


def test_parse_is_row_major_and_skips_unpublished_cells() -> None:
    frame = parse_json_stat(_payload())

    assert len(frame) == 3  # US 2026-07 is absent, not zero
    lookup = frame.set_index(["partner", "time"])["value"]
    assert lookup[("NO", "2026-08")] == 8.0
    assert lookup[("US", "2026-08")] == 4.25


def test_an_empty_dimension_parses_to_an_empty_frame() -> None:
    payload = _payload()
    payload["dimension"]["partner"]["category"]["index"] = {}

    assert parse_json_stat(payload).empty


def test_series_ids_name_the_flow_product_partner_and_geo() -> None:
    trade = pd.DataFrame(
        {"siec": ["G3000", "G3200", "G9999"], "partner": ["NO", "US", "XX"],
         "geo": "EU27_2020", "time": "2026-08", "value": [1.0, 2.0, 3.0]}
    )  # fmt: skip
    balance = pd.DataFrame(
        {"nrg_bal": ["IC_OBS", "IPRD"], "geo": ["EU27_2020", "NL"], "time": "2026-08",
         "value": [10.0, 2.0]}
    )  # fmt: skip
    at = pd.Timestamp("2026-10-26")

    ids = set(trade_rows(trade, IMPORTS, at)["series_id"])
    bal = balance_rows(balance, "MIO_M3", at)

    assert ids == {"estat.gas.imports.gas.no.eu", "estat.gas.imports.lng.us.eu"}
    assert set(bal["series_id"]) == {"estat.gas.balance.ic_obs.eu", "estat.gas.balance.iprd.nl"}
    assert set(bal["geo"]) == {"EU", "NL"}


@pytest.mark.vcr
def test_live_balance_and_imports_shapes() -> None:
    client = EurostatGasClient()

    balance = client.fetch(BALANCE, siec="G3000", unit="MIO_M3", nrg_bal="IC_OBS",
                           time=["2026-01", "2026-02"])  # fmt: skip
    imports = client.fetch(IMPORTS, unit="MIO_M3", partner=["NO", "TOTAL"], time="2026-01")

    assert set(balance["nrg_bal"]) == {"IC_OBS"} and len(balance) == 2
    assert (balance["value"] > 0).all()
    assert {"G3000", "G3200"} == set(imports["siec"])
    assert set(imports["partner"]) <= {"NO", "TOTAL"}


@pytest.mark.vcr
def test_a_bad_filter_raises_rather_than_returning_nothing() -> None:
    with pytest.raises(ValueError, match="no categories for \\['siec'\\]"):
        EurostatGasClient().fetch(BALANCE, siec="NOT_A_CODE", unit="MIO_M3", time="2026-01")
