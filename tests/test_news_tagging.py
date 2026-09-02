from __future__ import annotations

from pipelines.news.tagging import extract_geo, extract_severity, extract_tags


def test_refinery_fire_rotterdam_acceptance_case() -> None:
    """specs/09_news-events.md's own Session B acceptance criterion: a "refinery fire
    Rotterdam" test headline tags (crude, outage, NL, severity 2+). commodity="crude"
    is a query-dictionary concern, not this module's -- only tags/geo/severity checked
    here."""
    headline = "Refinery fire forces shutdown near Rotterdam"

    assert "outage" in extract_tags(headline)
    assert extract_geo(headline) == "NL"
    assert extract_severity(headline) >= 2


def test_extract_tags_can_match_multiple_tags() -> None:
    headline = "OPEC weighs sanctions after tanker seized near Hormuz"

    tags = extract_tags(headline)

    assert "opec" in tags
    assert "sanctions" in tags
    assert "geopolitics" in tags


def test_extract_tags_returns_empty_for_no_keyword_match() -> None:
    assert extract_tags("Oil prices little changed in quiet trading") == []


def test_extract_severity_tier_3_beats_tier_2() -> None:
    assert extract_severity("Pipeline explosion halts flows") == 3


def test_extract_severity_tier_2_when_no_tier_3_keyword() -> None:
    assert extract_severity("Workers strike at refinery") == 2


def test_extract_severity_defaults_to_1() -> None:
    assert extract_severity("OPEC meeting scheduled for next month") == 1


def test_extract_geo_falls_back_when_no_keyword_found() -> None:
    assert extract_geo("Prices steady in Asian trading", fallback="Singapore") == "Singapore"


def test_extract_geo_prefers_headline_keyword_over_fallback() -> None:
    # The whole point of headline-derived geo: a US-published wire story about a
    # Rotterdam event should still resolve to NL, not the publisher's own country.
    assert extract_geo("Reuters: Rotterdam refinery halted", fallback="United States") == "NL"


def test_extract_tags_uses_word_boundaries_not_bare_substrings() -> None:
    # "halt" must not match inside an unrelated longer word.
    assert extract_tags("Asphalt prices rise on refinery upgrade") == []
