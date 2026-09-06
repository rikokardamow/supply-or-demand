from __future__ import annotations

from pipelines.social.queries import TICKER_QUERIES, TOPIC_QUERIES, slugify


def test_slugify_follows_the_fixed_permanent_rule() -> None:
    assert slugify("Strait of Hormuz") == "strait_of_hormuz"
    assert slugify("Bab el-Mandeb") == "bab_el_mandeb"
    assert slugify("  Urals discount!! ") == "urals_discount"
    assert slugify("JKM") == "jkm"


def test_topic_slugs_are_stored_not_derived_and_are_unique() -> None:
    slugs = [q["slug"] for q in TOPIC_QUERIES]
    assert len(slugs) == len(set(slugs)), "series IDs are permanent; slugs must be unique"
    for q in TOPIC_QUERIES:
        assert q["slug"] == slugify(q["slug"]), "stored slug must already be canonical"


def test_ticker_set_is_frozen_at_twelve() -> None:
    assert len(TICKER_QUERIES) == 12
    assert [t.upper() for t in TICKER_QUERIES] == TICKER_QUERIES
    assert len(set(TICKER_QUERIES)) == 12
