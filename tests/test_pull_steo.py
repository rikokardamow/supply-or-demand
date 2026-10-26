from __future__ import annotations

import pandas as pd
import pytest

CODES = ["MGTCPUSX", "DFTCPUS"]


def _frame(codes: list[str] = CODES) -> pd.DataFrame:
    frames = [
        pd.DataFrame(
            {
                "series_id": code,
                "source": "eia_steo",
                "ts": pd.to_datetime(["2026-06-01", "2026-07-01", "2026-08-01"]),
                "value": [8.1, 8.2, 8.3],
                "unit": "million barrels per day",
                "geo": "US",
                "freq": "monthly",
                "revision_date": pd.Timestamp("2026-10-10"),
            }
        )
        for code in codes
    ]
    return pd.concat(frames, ignore_index=True)


def _client(steo: pd.DataFrame, actuals_ts: list[str] | None = None):
    ts = ["2026-07-01"] if actuals_ts is None else actuals_ts

    class FakeClient:
        def get_steo_series(self, codes, frequency):
            return steo.copy()

        def get_series(self, route, series, frequency):
            return pd.DataFrame({"ts": pd.to_datetime(ts), "value": [277320.0] * len(ts)})

    return FakeClient()


@pytest.fixture
def lake(tmp_path, monkeypatch):
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")
    return storage


def _run(monkeypatch, client) -> None:
    from pipelines.eia import pull_steo

    monkeypatch.setattr(pull_steo, "EIAClient", lambda *a, **k: client)
    pull_steo.main()


def test_main_writes_both_labelled_variants_and_reports_the_boundary(
    lake, monkeypatch, capsys
) -> None:
    _run(monkeypatch, _client(_frame()))

    written = lake.read_ts_long(source="eia_steo")
    assert set(written["series_id"]) == {
        "steo.mgtcpusx.observed",
        "steo.mgtcpusx.projected",
        "steo.dftcpus.observed",
        "steo.dftcpus.projected",
    }
    for code in ("mgtcpusx", "dftcpus"):
        obs = written[written["series_id"] == f"steo.{code}.observed"]
        proj = written[written["series_id"] == f"steo.{code}.projected"]
        assert sorted(obs["ts"].dt.strftime("%Y-%m")) == ["2026-06", "2026-07"]
        assert list(proj["ts"].dt.strftime("%Y-%m")) == ["2026-08"]
    assert (written["source"] == "eia_steo").all()
    assert (written["unit"] == "million barrels per day").all()
    assert len(written) == 6

    assert "2026-07" in capsys.readouterr().out, "the run log must state the history boundary"


def test_main_writes_nothing_when_the_boundary_cannot_be_established(lake, monkeypatch) -> None:
    class NoBoundaryClient:
        def get_steo_series(self, codes, frequency):
            raise AssertionError("STEO must not be fetched before the boundary is known")

        def get_series(self, route, series, frequency):
            return pd.DataFrame(columns=["ts", "value"])

    with pytest.raises(ValueError, match="boundary"):
        _run(monkeypatch, NoBoundaryClient())

    assert lake.read_ts_long(source="eia_steo").empty


def test_empty_steo_pull_exits_non_zero_and_writes_nothing(lake, monkeypatch) -> None:
    from core.failures import PartialFailureError

    with pytest.raises(PartialFailureError, match="pull_steo"):
        _run(monkeypatch, _client(_frame().iloc[0:0]))

    assert lake.read_ts_long(source="eia_steo").empty


def test_nat_period_fails_loudly_and_writes_nothing(lake, monkeypatch) -> None:
    bad = _frame()
    bad.loc[0, "ts"] = pd.NaT

    with pytest.raises(ValueError, match="NaT"):
        _run(monkeypatch, _client(bad))

    assert lake.read_ts_long(source="eia_steo").empty


def test_boundary_month_is_observed_and_the_next_is_projected(lake, monkeypatch) -> None:
    """The boundary month itself is measured; only strictly later months are projected."""
    _run(monkeypatch, _client(_frame(["MGTCPUSX"]), actuals_ts=["2026-06-01"]))

    written = lake.read_ts_long(source="eia_steo")
    by_id = {
        sid: sorted(g["ts"].dt.strftime("%Y-%m")) for sid, g in written.groupby("series_id")
    }
    assert by_id == {
        "steo.mgtcpusx.observed": ["2026-06"],
        "steo.mgtcpusx.projected": ["2026-07", "2026-08"],
    }
