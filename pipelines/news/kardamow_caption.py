"""Phase 2 of the news-map redesign: an LLM-generated "Kardamow take" one-liner
explaining what a translated headline could mean for the energy complex (crude,
power, natgas). Uses the official `anthropic` Python SDK (added as a project
dependency for this feature, per explicit approval -- this project's CLAUDE.md asks
before adding any dependency).

Needs a real `ANTHROPIC_API_KEY` in `.env` (via `core.settings`, never printed/logged)
-- unset until the user provides one, same pattern as `pipelines/news/guardian_client.py`
staying gracefully unverified until `GUARDIAN_KEY` existed. `generate_kardamow_caption`
raises a clear `RuntimeError` rather than crashing obscurely when the key is absent;
the caller (the page) is expected to catch this and show an explanatory message
instead of a stack trace.

Cached on disk keyed by `event_id`, both to control real per-call cost (a live
Anthropic API call has a real dollar cost per click) and to keep a repeat click on
the same event instant -- same pattern as `pipelines/news/translate.py`'s cache."""

from __future__ import annotations

from pathlib import Path

import anthropic
import pandas as pd
from core.settings import settings

MODEL_ID = "claude-haiku-4-5-20251001"
MAX_TOKENS = 300
CACHE_PATH = Path("data/cache/kardamow_captions.parquet")

# Real "Kardamow take" one-liners already shipped on other pages of this dashboard
# (apps/dashboard/pages/01_us_padd.py, 02_gas_storage.py, 08_weather.py, 10_macro.py,
# 015_us_oil_overview.py) -- embedded as style references so the model matches the
# house voice actually in use, rather than inventing a tone from scratch.
_STYLE_EXAMPLES = [
    "A stronger dollar is a headwind for dollar-priced crude almost mechanically — "
    "this is the chart that separates a real demand story from a currency one before "
    "either gets treated as the explanation.",
    "Cracks lead runs by roughly one to two months: strong margins today are next "
    "month's crude demand and the month after's product supply.",
    "Europe's storage is well behind its own median, and the current injection pace "
    "gets it full past 1 November — the date the market actually prices, which is "
    "why this chart is doing more for TTF than the flat price admits.",
    "Colder-than-normal EU weather shows up in storage draws within days, not weeks — "
    "this is the fastest-moving read on whether a cold snap is actually pulling gas "
    "out of the ground or just making headlines.",
    "This is the price refiners are actually responding to once inflation's stripped "
    "out — the nominal quote alone overstates how attractive the crack spread really "
    "is versus five years ago.",
]


def _build_prompt(
    headline_en: str, commodity: str, tags: list[str], severity: int, geo: str
) -> str:
    examples = "\n".join(f'- "{e}"' for e in _STYLE_EXAMPLES)
    tags_str = ", ".join(tags) if tags else "none"
    return (
        "You write one-sentence \"Kardamow take\" captions for an energy/macro "
        "research dashboard (publication: Kardamow). Style: direct, analytical, no "
        "hedging filler, ties the fact to a concrete consequence rather than "
        "restating it. Real examples of the house voice, already published:\n"
        f"{examples}\n\n"
        f'Headline (already translated to English): "{headline_en}"\n'
        f"Commodity: {commodity} | Tags: {tags_str} | Severity: {severity}/3 | "
        f"Location: {geo or 'unspecified'}\n\n"
        "Write exactly one sentence, in the house voice above, explaining what this "
        "could mean for the energy complex (crude, power, natgas). No preamble, no "
        "quotation marks -- just the sentence."
    )


def _load_cache() -> pd.DataFrame:
    if not CACHE_PATH.exists():
        return pd.DataFrame(columns=["event_id", "caption"])
    return pd.read_parquet(CACHE_PATH)


def _save_cache(df: pd.DataFrame) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE_PATH, index=False)


def generate_kardamow_caption(
    event_id: str,
    headline_en: str,
    commodity: str,
    tags: list[str],
    severity: int,
    geo: str,
) -> str:
    cache = _load_cache()
    cached_row = cache[cache["event_id"] == event_id]
    if not cached_row.empty:
        return str(cached_row.iloc[0]["caption"])

    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set -- Phase 2 Kardamow-take captions are "
            "unavailable until a key is added to .env."
        )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=MODEL_ID,
        max_tokens=MAX_TOKENS,
        messages=[
            {
                "role": "user",
                "content": _build_prompt(headline_en, commodity, tags, severity, geo),
            }
        ],
    )
    caption = next((b.text for b in response.content if b.type == "text"), "").strip()

    cache = pd.concat(
        [cache, pd.DataFrame([{"event_id": event_id, "caption": caption}])],
        ignore_index=True,
    )
    _save_cache(cache)
    return caption
