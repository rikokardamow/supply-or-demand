from __future__ import annotations

import pytest
import requests
from core.failures import fails_loudly, record_failure
from infra.run_scheduled import CADENCE_GROUPS, run_cadence


def test_derived_systematic_is_registered_after_its_own_dependency() -> None:
    """Spec 21's daily-positions entrypoint reads what `derived_curve_ranks` writes
    (the rank panel's back-adjusted front month and convexity/regime series), so it must
    run after it. It lives in `weekly_fri`, not `daily`, alongside `derived_curve_ranks`
    itself -- both only need re-running when new futures land."""
    names = [name for name, _ in CADENCE_GROUPS["weekly_fri"]]
    assert "derived_systematic" in names
    assert "derived_curve_ranks" in names
    assert names.index("derived_systematic") > names.index("derived_curve_ranks")


def test_run_cadence_returns_1_for_an_unknown_label() -> None:
    assert run_cadence("not-a-real-cadence") == 1


def test_run_cadence_isolates_one_failing_pipeline_from_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class _OkModule:
        @staticmethod
        def main() -> None:
            calls.append("ok")

    class _BrokenModule:
        @staticmethod
        def main() -> None:
            raise RuntimeError("simulated pipeline failure")

    def fake_import_module(path: str) -> object:
        return _BrokenModule if path == "broken.module" else _OkModule

    test_group = [("first", "ok.module"), ("broken", "broken.module"), ("last", "ok.module")]
    monkeypatch.setattr("infra.run_scheduled.CADENCE_GROUPS", {"test_cadence": test_group})
    monkeypatch.setattr("infra.run_scheduled.importlib.import_module", fake_import_module)

    exit_code = run_cadence("test_cadence")

    assert exit_code == 1  # the group had a real failure
    assert calls == ["ok", "ok"]  # both "ok" entries still ran despite "broken" failing


def test_run_cadence_returns_0_when_everything_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    class _OkModule:
        @staticmethod
        def main() -> None:
            pass

    monkeypatch.setattr(
        "infra.run_scheduled.CADENCE_GROUPS", {"test_cadence": [("first", "ok.module")]}
    )
    monkeypatch.setattr("infra.run_scheduled.importlib.import_module", lambda path: _OkModule)

    assert run_cadence("test_cadence") == 0


def test_run_cadence_fails_when_every_item_inside_a_pipeline_failed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The regression this whole mechanism exists for. A pull script catches each item's
    exception so one bad contract can't cost the other twenty -- but before @fails_loudly
    it then returned normally, so this loop printed "OK" and the cadence exited 0 for a
    run that ingested precisely nothing. Task Scheduler showed green."""

    class _AllItemsFailedModule:
        @staticmethod
        @fails_loudly("futures.pull_daily")
        def main() -> None:
            for root in ("cl", "ng", "lco"):
                try:
                    raise RuntimeError("IBKR gateway not connected")
                except RuntimeError as exc:
                    record_failure(root, exc)
            print("pull_daily: 0 total rows written", flush=True)

    monkeypatch.setattr("infra.run_scheduled.CADENCE_GROUPS", {"test_cadence": [("futures", "x")]})
    monkeypatch.setattr(
        "infra.run_scheduled.importlib.import_module", lambda path: _AllItemsFailedModule
    )

    exit_code = run_cadence("test_cadence")

    assert exit_code == 1
    printed = capsys.readouterr().out
    assert "futures: FAILED" in printed
    assert "3 item(s) failed" in printed
    assert "futures: OK" not in printed


def test_run_cadence_still_succeeds_when_a_pipeline_had_no_item_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _HealthyModule:
        @staticmethod
        @fails_loudly("futures.pull_daily")
        def main() -> None:
            pass

    monkeypatch.setattr("infra.run_scheduled.CADENCE_GROUPS", {"test_cadence": [("futures", "x")]})
    monkeypatch.setattr("infra.run_scheduled.importlib.import_module", lambda path: _HealthyModule)

    assert run_cadence("test_cadence") == 0


def test_run_cadence_never_prints_a_credential_from_a_pipeline_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Golden rule 1, at the exact line that leaked. A pipeline that lets a raw
    requests.HTTPError escape must not put the key in Task Scheduler's log."""
    key = "REALKEY0123456789"

    class _LeakyModule:
        @staticmethod
        def main() -> None:
            response = requests.Response()
            response.status_code = 403
            response.reason = "Forbidden"
            response.url = f"https://api.eia.gov/v2/x/data/?api_key={key}"
            response.raise_for_status()

    monkeypatch.setattr("infra.run_scheduled.CADENCE_GROUPS", {"test_cadence": [("eia_wpsr", "x")]})
    monkeypatch.setattr("infra.run_scheduled.importlib.import_module", lambda path: _LeakyModule)

    assert run_cadence("test_cadence") == 1
    printed = capsys.readouterr().out
    assert key not in printed
    assert "eia_wpsr: FAILED" in printed
