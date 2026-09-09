from __future__ import annotations

import pytest
from infra.check_lake_integrity import main


def test_main_returns_0_and_prints_ok_when_nothing_is_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("infra.check_lake_integrity.missing_sources", lambda: set())
    monkeypatch.setattr("infra.check_lake_integrity.mass_data_loss_detected", lambda: False)

    assert main() == 0
    assert "OK" in capsys.readouterr().out


def test_main_returns_0_for_a_single_missing_source_but_still_names_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A single missing source is normal (never run yet, or one genuinely broken
    # pipeline) -- worth printing so it's not silent, but not the loud alarm below.
    monkeypatch.setattr("infra.check_lake_integrity.missing_sources", lambda: {"gie"})
    monkeypatch.setattr("infra.check_lake_integrity.mass_data_loss_detected", lambda: False)

    assert main() == 0
    out = capsys.readouterr().out
    assert "gie" in out


def test_main_returns_2_and_prints_a_loud_alarm_on_mass_data_loss(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # This is the real, confirmed-live signature of the 2026-09-08 incident: most of
    # the lake's known sources vanishing at once. A distinct, non-zero exit code
    # (never the same as a single-pipeline gap) lets this be wired into a scheduled
    # task or CI step that pages someone, rather than scrolling past in a log.
    missing = {"gie", "entsog", "entsoe", "eirgrid", "gridstatus", "eia", "fred"}
    monkeypatch.setattr("infra.check_lake_integrity.missing_sources", lambda: missing)
    monkeypatch.setattr("infra.check_lake_integrity.mass_data_loss_detected", lambda: True)

    assert main() == 2
    out = capsys.readouterr().out
    assert "MASS DATA LOSS" in out
    for source in missing:
        assert source in out
