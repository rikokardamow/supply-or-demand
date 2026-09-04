from __future__ import annotations

import pytest
from infra.run_scheduled import run_cadence


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
    monkeypatch.setattr(
        "infra.run_scheduled.importlib.import_module", lambda path: _OkModule
    )

    assert run_cadence("test_cadence") == 0
