from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import pytest
from core.schemas import validate_flows
from pipelines.eia import pull_rto_interchange
from pipelines.eia.rto import ERCOT, RTO_RESPONDENTS


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
    #
    # The window is derived from the pulled frame's own `ts` column (df["ts"].min()/
    # .max()), not a second `datetime.now(UTC)` call -- a second wall-clock read is
    # always a little later than pull_interchange's internal one (the API call happens
    # in between), which leaves the oldest pulled hour outside the window and unreplaced.
    # Every RTO_RESPONDENTS BA appears once as from_node, all sharing one timestamp, so
    # min() == max() still holds -- the invariant to check is that the window exactly
    # brackets the pulled rows' timestamps, not "at least 3 days wide", which was only
    # ever true of the old now()-derived window. Covering every respondent also keeps
    # this fake frame clear of run()'s own silent-partial-pull guard (Finding I1) -- a
    # frame missing a BA would otherwise fail this test with PartialFailureError for an
    # unrelated reason.
    captured: dict[str, Any] = {}

    def _fake_write(df: pd.DataFrame, source: str, replace_window: Any = None) -> None:
        captured["source"] = source
        captured["replace_window"] = replace_window

    ts = datetime.now(UTC).replace(tzinfo=None)
    monkeypatch.setattr(pull_rto_interchange, "write_flows", _fake_write)
    monkeypatch.setattr(
        pull_rto_interchange,
        "pull_interchange",
        lambda client, days: pd.DataFrame(
            {
                "source": ["eia"] * len(RTO_RESPONDENTS),
                "from_node": list(RTO_RESPONDENTS),
                "to_node": ["NEIGHBOR"] * len(RTO_RESPONDENTS),
                "value": [120.0] * len(RTO_RESPONDENTS),
                "unit": ["megawatthours"] * len(RTO_RESPONDENTS),
                "ts": pd.to_datetime([ts] * len(RTO_RESPONDENTS)),
                "mode": ["grid_interchange"] * len(RTO_RESPONDENTS),
            }
        ),
    )

    pull_rto_interchange.run(days=3)

    assert captured["source"] == "eia"
    window = captured["replace_window"]
    assert window is not None, "a flows re-pull without a replace_window double-counts"
    start, end = window
    assert start == ts
    assert end == ts


def test_pull_interchange_requests_the_bounded_window_and_correct_facets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The VCR tests above relax match_on to method+path, so a cassette replays
    # regardless of what was actually requested -- a bug that dropped start=/end=
    # (an unbounded pull) or narrowed facets to the wrong values would still pass every
    # one of them. This proves the request wiring itself, with no cassette involved.
    captured: dict[str, Any] = {}

    def _fake_get_facet_flows(self: object, **kwargs: Any) -> pd.DataFrame:
        captured.update(kwargs)
        return pd.DataFrame()

    monkeypatch.setattr(
        pull_rto_interchange.EIAClient, "get_facet_flows", _fake_get_facet_flows
    )

    pull_rto_interchange.pull_interchange(pull_rto_interchange.EIAClient(), days=3)

    assert captured["facets"] == {"fromba": pull_rto_interchange.RTO_RESPONDENTS}
    assert captured["frequency"] == pull_rto_interchange.HOURLY
    assert captured["mode"] == pull_rto_interchange.INTERCHANGE_MODE
    start, end = captured["start"], captured["end"]
    assert start is not None and end is not None
    span = datetime.strptime(end, "%Y-%m-%dT%H") - datetime.strptime(start, "%Y-%m-%dT%H")
    # Not exact equality against a freshly-computed timedelta(days=3) -- wall-clock
    # drift between window computation (inside pull_interchange) and this assertion is
    # real, if tiny. A generous tolerance still catches an unbounded or wrongly-sized
    # window.
    assert abs(span - timedelta(days=3)) < timedelta(hours=1)
