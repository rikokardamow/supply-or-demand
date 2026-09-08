from __future__ import annotations

import pytest
from core.schemas import validate_ts_long
from pipelines.eia import pull_rto_demand
from pipelines.eia.rto import ERCOT, PJM


@pytest.fixture(scope="module")
def vcr_config(vcr_config: dict[str, object]) -> dict[str, object]:
    """`_hour_bounds` stamps start/end from `datetime.now(UTC)`, so the recorded
    request's query string carries a fixed timestamp that will not match a later
    replay's freshly-computed one. Relaxed match_on (method+path only, dropping the
    query string) rather than freezing time: freezegun isn't already a dependency here,
    and the pull module deliberately takes no clock parameter to satisfy a cassette (see
    pull_rto_demand.py's docstring) -- a test-local match_on relaxation is the narrower
    fix and needs no new dependency."""
    return {**vcr_config, "match_on": ["method", "path"]}


@pytest.mark.vcr
def test_demand_returns_valid_ts_long_for_the_two_blocked_markets() -> None:
    df = pull_rto_demand.pull_demand(pull_rto_demand.EIAClient(), days=2)

    validate_ts_long(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    assert set(df["freq"]) == {"hourly"}
    # ERCOT and PJM are the entire justification for this pipeline -- gridstatus cannot
    # reach either. If they come back empty the pull is pointless, and an empty frame
    # would otherwise pass every other assertion here.
    assert ERCOT in set(df["geo"])
    assert PJM in set(df["geo"])


@pytest.mark.vcr
def test_series_ids_are_minted_from_the_row_not_guessed() -> None:
    df = pull_rto_demand.pull_demand(pull_rto_demand.EIAClient(), days=2)

    assert all(sid.startswith("RTO.REGION.") for sid in df["series_id"])
    # Every row's id must be reconstructible from its own geo -- proving the id was
    # minted from the row and not from a positional guess.
    for _, row in df.head(50).iterrows():
        assert row["series_id"].split(".")[2] == row["geo"]


def test_trailing_window_is_bounded() -> None:
    # Hourly routes have no monthly rollup to fall back on, so an unbounded pull is the
    # row-volume problem plan 31B's Decision A exists to prevent. main() must never
    # request full history.
    assert pull_rto_demand.TRAILING_DAYS <= 7
