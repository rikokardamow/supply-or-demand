from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import pytest
from core.schemas import validate_flows
from pipelines.eia import pull_rto_interchange
from pipelines.eia.rto import ERCOT


@pytest.fixture(scope="module")
def vcr_config(vcr_config: dict[str, object]) -> dict[str, object]:
    """`_hour_bounds` stamps start/end from `datetime.now(UTC)`, so the recorded
    request's query string carries a fixed timestamp that will not match a later
    replay's freshly-computed one. Relaxed match_on (method+path only, dropping the
    query string) rather than freezing time -- same fix as tests/test_eia_rto_fuel_mix.py
    and tests/test_eia_rto_demand.py."""
    return {**vcr_config, "match_on": ["method", "path"]}


@pytest.mark.vcr
def test_interchange_returns_valid_flows_rows() -> None:
    df = pull_rto_interchange.pull_interchange(pull_rto_interchange.EIAClient(), days=2)

    validate_flows(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    assert set(df["mode"]) == {"grid_interchange"}
    # Corridors are read off each row's own fromba/toba, so from and to must differ.
    assert not (df["from_node"] == df["to_node"]).any()


@pytest.mark.vcr
def test_ercot_appears_as_a_real_corridor_endpoint() -> None:
    df = pull_rto_interchange.pull_interchange(pull_rto_interchange.EIAClient(), days=2)
    assert ERCOT in set(df["from_node"]) | set(df["to_node"])


def test_run_passes_a_replace_window_to_write_flows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The load-bearing test of this task. flows has no revision_date, so a re-pulled
    # trailing window that does NOT replace its old rows keeps both the old and the
    # revised value -- they differ, so de-dup keeps both -- and every downstream sum
    # double-counts, with nothing raised anywhere. Assert the window is actually passed.
    captured: dict[str, Any] = {}

    def _fake_write(df: pd.DataFrame, source: str, replace_window: Any = None) -> None:
        captured["source"] = source
        captured["replace_window"] = replace_window

    monkeypatch.setattr(pull_rto_interchange, "write_flows", _fake_write)
    monkeypatch.setattr(
        pull_rto_interchange,
        "pull_interchange",
        lambda client, days: pd.DataFrame(
            {
                "source": ["eia"],
                "from_node": ["ERCO"],
                "to_node": ["SWPP"],
                "value": [120.0],
                "unit": ["megawatthours"],
                "ts": pd.to_datetime([datetime.now(UTC).replace(tzinfo=None)]),
                "mode": ["grid_interchange"],
            }
        ),
    )

    pull_rto_interchange.run(days=3)

    assert captured["source"] == "eia"
    window = captured["replace_window"]
    assert window is not None, "a flows re-pull without a replace_window double-counts"
    start, end = window
    assert end - start >= timedelta(days=3)
