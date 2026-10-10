# tests/test_eia_biofuels.py
from __future__ import annotations

import pandas as pd
import pytest
import requests
from core.failures import PartialFailureError
from core.schemas import validate_ts_long
from pipelines.eia import pull_biofuels


@pytest.mark.vcr
def test_capacity_returns_valid_ts_long_for_every_fuel() -> None:
    df = pull_biofuels.pull_capacity(pull_biofuels.EIAClient())

    validate_ts_long(df)
    assert not df.empty
    assert set(df["source"]) == {"eia"}
    assert set(df["geo"]) == {"US"}
    assert set(df["series_id"]) == set(pull_biofuels.CAPACITY)


@pytest.mark.vcr
def test_renewable_diesel_capacity_is_present_and_named() -> None:
    # Renewable diesel capacity displacing petroleum diesel demand is the signal the
    # spec names for this item. Selected by name, never by index.
    df = pull_biofuels.pull_capacity(pull_biofuels.EIAClient())
    assert pull_biofuels.RENEWABLE_DIESEL in set(df["series_id"])


@pytest.mark.vcr
def test_feedstocks_return_valid_ts_long_for_every_series() -> None:
    df = pull_biofuels.pull_feedstocks(pull_biofuels.EIAClient())

    validate_ts_long(df)
    assert not df.empty
    # A feedstock that silently returns nothing would understate feedstock competition,
    # which is the entire point of ingesting 26 series rather than a headline number.
    #
    # Real, live-confirmed exception (Task 2, 2026-09-09): 4 of the 26 feedstocks --
    # dedicated energy crops, biogas, municipal solid waste, yard/food waste -- report a
    # literal null value for every one of their recorded periods (2021-01 to 2026-06,
    # confirmed via a direct, unfiltered fetch of each series in isolation). EIAClient's
    # existing null-skip (client.py) therefore drops them to zero rows -- this is EIA
    # publishing no real data for these categories, not a bug in this pull or a truncated
    # FEEDSTOCKS list. See pipelines/eia/CLAUDE.md's Task 2 (31C) entry.
    assert (
        set(df["series_id"]) == set(pull_biofuels.FEEDSTOCKS) - pull_biofuels.ALWAYS_NULL_FEEDSTOCKS
    )


def test_feedstock_list_is_the_full_set_and_has_no_duplicates() -> None:
    assert len(set(pull_biofuels.FEEDSTOCKS)) == len(pull_biofuels.FEEDSTOCKS)
    assert len(pull_biofuels.FEEDSTOCKS) == pull_biofuels.EXPECTED_FEEDSTOCK_COUNT


def _fake_row(series_id: str, frequency: str = "monthly") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": [series_id],
            "source": ["eia"],
            "ts": [pd.Timestamp("2026-01-01")],
            "value": [1.0],
            "unit": ["MMGL"],
            "geo": ["US"],
            "freq": [frequency],
            "revision_date": [pd.Timestamp("2026-01-02")],
        }
    )


def test_a_failing_capacity_route_does_not_abort_feedstocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Finding I2: failure_scope does not isolate an exception raised by its own body --
    # it only collects record_failure calls and raises once at the end. Two separate
    # failure_scope blocks (the previous shape) let a capacity exception propagate
    # straight out of main() before pull_feedstocks ever ran. This test proves the
    # fixed shape -- one scope, try/except per route -- actually isolates the two.
    calls: list[str] = []

    def fake_pull_capacity(client: object) -> pd.DataFrame:
        calls.append("capacity")
        raise requests.exceptions.ConnectionError("capbio down")

    def fake_pull_feedstocks(client: object) -> pd.DataFrame:
        calls.append("feedstocks")
        return pd.concat([_fake_row(sid) for sid in pull_biofuels.FEEDSTOCKS], ignore_index=True)

    monkeypatch.setattr(pull_biofuels, "pull_capacity", fake_pull_capacity)
    monkeypatch.setattr(pull_biofuels, "pull_feedstocks", fake_pull_feedstocks)
    written: list[pd.DataFrame] = []
    monkeypatch.setattr(pull_biofuels, "write_ts_long", lambda df, source: written.append(df))

    with pytest.raises(PartialFailureError):
        pull_biofuels.main()

    assert calls == ["capacity", "feedstocks"], "feedstocks must still run"
    assert len(written) == 1, "the surviving route's data must still be written"
    assert set(written[0]["series_id"]) == set(pull_biofuels.FEEDSTOCKS)


def test_a_failing_feedstocks_route_does_not_abort_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_pull_capacity(client: object) -> pd.DataFrame:
        calls.append("capacity")
        return pd.concat([_fake_row(sid) for sid in pull_biofuels.CAPACITY], ignore_index=True)

    def fake_pull_feedstocks(client: object) -> pd.DataFrame:
        calls.append("feedstocks")
        raise requests.exceptions.ConnectionError("feedbiofuel down")

    monkeypatch.setattr(pull_biofuels, "pull_capacity", fake_pull_capacity)
    monkeypatch.setattr(pull_biofuels, "pull_feedstocks", fake_pull_feedstocks)
    written: list[pd.DataFrame] = []
    monkeypatch.setattr(pull_biofuels, "write_ts_long", lambda df, source: written.append(df))

    with pytest.raises(PartialFailureError):
        pull_biofuels.main()

    assert calls == ["capacity", "feedstocks"]
    assert len(written) == 1, "the surviving route's data must still be written"
    assert set(written[0]["series_id"]) == set(pull_biofuels.CAPACITY)


def test_a_missing_series_in_a_healthy_route_still_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # I1: an empty/partial result (no exception at all) from either route must still
    # be recorded as a failure -- not just a wholly-thrown exception.
    def fake_pull_capacity(client: object) -> pd.DataFrame:
        missing = pull_biofuels.CAPACITY[0]
        return pd.concat(
            [_fake_row(sid) for sid in pull_biofuels.CAPACITY if sid != missing],
            ignore_index=True,
        )

    def fake_pull_feedstocks(client: object) -> pd.DataFrame:
        return pd.concat([_fake_row(sid) for sid in pull_biofuels.FEEDSTOCKS], ignore_index=True)

    monkeypatch.setattr(pull_biofuels, "pull_capacity", fake_pull_capacity)
    monkeypatch.setattr(pull_biofuels, "pull_feedstocks", fake_pull_feedstocks)
    monkeypatch.setattr(pull_biofuels, "write_ts_long", lambda df, source: None)

    with pytest.raises(PartialFailureError):
        pull_biofuels.main()


def test_always_null_feedstocks_are_not_flagged_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A healthy pull that correctly gets zero rows for the 4 always-null feedstocks
    # (Task 2's finding) must not be reported as a partial failure on every run.
    def fake_pull_capacity(client: object) -> pd.DataFrame:
        return pd.concat([_fake_row(sid) for sid in pull_biofuels.CAPACITY], ignore_index=True)

    def fake_pull_feedstocks(client: object) -> pd.DataFrame:
        present = set(pull_biofuels.FEEDSTOCKS) - pull_biofuels.ALWAYS_NULL_FEEDSTOCKS
        return pd.concat([_fake_row(sid) for sid in sorted(present)], ignore_index=True)

    monkeypatch.setattr(pull_biofuels, "pull_capacity", fake_pull_capacity)
    monkeypatch.setattr(pull_biofuels, "pull_feedstocks", fake_pull_feedstocks)
    monkeypatch.setattr(pull_biofuels, "write_ts_long", lambda df, source: None)

    pull_biofuels.main()  # must not raise
