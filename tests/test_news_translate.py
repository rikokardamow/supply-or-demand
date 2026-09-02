from __future__ import annotations

import pytest
from pipelines.news.translate import translate_headline


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_translate_headline_noops_for_english() -> None:
    result = translate_headline("e1", "Refinery fire in Rotterdam", "English")

    assert result == "Refinery fire in Rotterdam"


def test_translate_headline_noops_for_an_unmapped_language() -> None:
    result = translate_headline("e2", "Some headline", "Klingon")

    assert result == "Some headline"


@pytest.mark.vcr
def test_translate_headline_translates_a_real_spanish_headline() -> None:
    result = translate_headline("e3", "Hola mundo", "Spanish")

    assert result != "Hola mundo"
    assert "hello" in result.lower() or "world" in result.lower()


@pytest.mark.vcr
def test_translate_headline_is_cached_on_second_call() -> None:
    first = translate_headline("e4", "Buenos dias", "Spanish")
    # The cassette holds exactly one recorded response for this event_id's query --
    # a second call that hit the network again (instead of the on-disk cache) would
    # have no matching request left to play and raise, per vcrpy's own record-mode
    # enforcement (confirmed live while writing this test).
    second = translate_headline("e4", "Buenos dias", "Spanish")

    assert second == first
