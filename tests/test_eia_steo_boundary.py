from __future__ import annotations

import pandas as pd
import pytest


def _steo_frame(periods: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": "MGTCPUSX",
            "source": "eia_steo",
            "ts": pd.to_datetime(periods),
            "value": range(len(periods)),
            "unit": "million barrels per day",
            "geo": "US",
            "freq": "monthly",
            "revision_date": pd.Timestamp("2026-10-10"),
        }
    )


class _FakeClient:
    """Records the call it receives and returns a canned actuals frame."""

    def __init__(self, periods: list[str]) -> None:
        self._periods = periods
        self.calls: list[tuple[str, list[str], str]] = []

    def get_series(self, route: str, series: list[str], frequency: str) -> pd.DataFrame:
        self.calls.append((route, series, frequency))
        return pd.DataFrame({"ts": pd.to_datetime(self._periods), "value": 1.0})


def test_rows_at_or_before_the_boundary_are_observed_and_later_rows_are_projected() -> None:
    from pipelines.eia.steo_boundary import split_observed_projected

    df = _steo_frame(["2026-06", "2026-07", "2026-08", "2027-12"])
    out = split_observed_projected(df, pd.Timestamp("2026-07-01"))

    by_ts = dict(zip(out["ts"], out["series_id"], strict=True))
    assert by_ts[pd.Timestamp("2026-06-01")] == "MGTCPUSX.observed"
    assert by_ts[pd.Timestamp("2026-07-01")] == "MGTCPUSX.observed"
    assert by_ts[pd.Timestamp("2026-08-01")] == "MGTCPUSX.projected"
    assert by_ts[pd.Timestamp("2027-12-01")] == "MGTCPUSX.projected"


def test_no_row_keeps_an_unlabelled_series_id() -> None:
    """The whole point. An id that does not say observed or projected must not reach the lake."""
    from pipelines.eia.steo_boundary import split_observed_projected

    out = split_observed_projected(_steo_frame(["2026-06", "2026-08"]), pd.Timestamp("2026-07-01"))
    assert out["series_id"].str.endswith((".observed", ".projected")).all()


def test_the_split_does_not_mutate_its_input() -> None:
    from pipelines.eia.steo_boundary import split_observed_projected

    df = _steo_frame(["2026-06", "2026-08"])
    split_observed_projected(df, pd.Timestamp("2026-07-01"))
    assert (df["series_id"] == "MGTCPUSX").all()


@pytest.mark.parametrize("bad", [None, pd.NaT, "2026-07-01"])
def test_a_missing_boundary_is_refused_rather_than_defaulted(bad: object) -> None:
    """A missing boundary must fail loudly. Defaulting it -- to today, or to the series max --
    silently relabels EIA's model output as measured history, which is the one error this
    module exists to prevent."""
    from pipelines.eia.steo_boundary import split_observed_projected

    with pytest.raises(ValueError, match="boundary"):
        split_observed_projected(_steo_frame(["2026-06"]), bad)  # type: ignore[arg-type]


def test_history_end_is_the_latest_actual_period_whatever_the_row_order() -> None:
    """Hand-computed: the actuals arrive newest-first (the client sorts desc) and the latest
    period is 2026-07, so that is the boundary -- not the first row, not a later STEO month."""
    from pipelines.eia.steo_boundary import history_end

    client = _FakeClient(["2026-07", "2026-06", "2025-12", "2026-05"])
    assert history_end(client) == pd.Timestamp("2026-07-01")  # type: ignore[arg-type]
    assert client.calls == [("petroleum/sum/snd", ["MGFUPUS1"], "monthly")]


def test_history_end_on_an_empty_route_fails_loudly_rather_than_guessing_a_date() -> None:
    """No data is not zero: an empty actuals frame must stop the pull, never yield a date."""
    from pipelines.eia.steo_boundary import history_end

    with pytest.raises(ValueError, match="boundary"):
        history_end(_FakeClient([]))  # type: ignore[arg-type]


def test_the_boundary_and_the_split_agree_end_to_end_on_synthetic_inputs() -> None:
    """Actuals end 2026-07; STEO runs to 2027-12. Of 6 STEO months, hand-count: 2026-06 and
    2026-07 observed (2), 2026-08, 2026-12, 2027-06, 2027-12 projected (4)."""
    from pipelines.eia.steo_boundary import history_end, split_observed_projected

    boundary = history_end(_FakeClient(["2026-06", "2026-07"]))  # type: ignore[arg-type]
    out = split_observed_projected(
        _steo_frame(["2026-06", "2026-07", "2026-08", "2026-12", "2027-06", "2027-12"]), boundary
    )
    assert out["series_id"].str.endswith(".observed").sum() == 2
    assert out["series_id"].str.endswith(".projected").sum() == 4


@pytest.mark.vcr
def test_history_end_comes_from_eias_own_monthly_actuals() -> None:
    """Not from today's date, not from the STEO series max. Confirmed live 2026-10-10:
    MGFUPUS1's last monthly period was 2026-07."""
    from pipelines.eia.client import EIAClient
    from pipelines.eia.steo_boundary import history_end

    boundary = history_end(EIAClient())

    assert isinstance(boundary, pd.Timestamp)
    assert boundary >= pd.Timestamp("2026-07-01")
    assert boundary < pd.Timestamp("2027-01-01"), "a boundary inside STEO's forecast is wrong"
