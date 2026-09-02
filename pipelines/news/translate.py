"""Headline translation for the news-map redesign (Spec 09 amendment). Uses MyMemory
(`api.mymemory.translated.net`) -- confirmed live, free, no key required. Two
confirmed-dead alternatives ruled out first: `libretranslate.com`'s public instance now
requires a paid key; Google's unofficial no-key `translate_a/single` endpoint returned a
live HTTP 429 (rate-limited) from this environment.

Real, confirmed-live gotcha: MyMemory's `langpair` param does NOT accept `auto` as a
source language (`400: "'AUTO' IS AN INVALID SOURCE LANGUAGE"`) -- an explicit ISO
639-1 source code is required, which is exactly why `events.language` (a GDELT/
Guardian-reported language *name*, e.g. "Spanish") needed to exist as a schema field
before this module could work at all. `LANGUAGE_TO_ISO` bridges that name to the code
MyMemory expects.

Response shape confirmed live: `{"responseData": {"translatedText": "..."}, ...}`.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://api.mymemory.translated.net/get"
REQUEST_TIMEOUT_SECONDS = 15
CACHE_PATH = Path("data/cache/translations.parquet")

# GDELT-observed language *names* (confirmed live examples from this project's own
# lake/session history: Spanish, Chinese, Arabic, Portuguese, Russian, Ukrainian,
# Vietnamese, Korean, French) mapped to MyMemory's expected ISO 639-1 codes. Not
# exhaustive -- an unmapped language name means `translate_headline` no-ops rather
# than guessing a code.
LANGUAGE_TO_ISO: dict[str, str] = {
    "english": "en",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "portuguese": "pt",
    "russian": "ru",
    "ukrainian": "uk",
    "chinese": "zh",
    "japanese": "ja",
    "korean": "ko",
    "arabic": "ar",
    "vietnamese": "vi",
    "turkish": "tr",
    "polish": "pl",
    "dutch": "nl",
    "greek": "el",
    "hebrew": "he",
    "hindi": "hi",
    "indonesian": "id",
    "thai": "th",
    "persian": "fa",
    "farsi": "fa",
    "romanian": "ro",
    "swedish": "sv",
    "czech": "cs",
    "hungarian": "hu",
    "danish": "da",
    "finnish": "fi",
    "norwegian": "no",
}


def _load_cache() -> pd.DataFrame:
    if not CACHE_PATH.exists():
        return pd.DataFrame(columns=["event_id", "translated_headline"])
    return pd.read_parquet(CACHE_PATH)


def _save_cache(df: pd.DataFrame) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE_PATH, index=False)


def _call_mymemory(headline: str, source_code: str) -> str:
    response = requests.get(
        BASE_URL,
        params={"q": headline, "langpair": f"{source_code}|en"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    translated: str = payload["responseData"]["translatedText"]
    return translated


def translate_headline(event_id: str, headline: str, source_language: str) -> str:
    """No-ops (returns `headline` unchanged) when `source_language` is already English
    or isn't in `LANGUAGE_TO_ISO` -- never guesses a code. Cached on disk keyed by
    `event_id`, both to respect MyMemory's real 5,000-words/day anonymous quota and to
    keep a repeat click on the same event instant."""
    normalised = source_language.strip().lower()
    if normalised in ("", "english"):
        return headline

    source_code = LANGUAGE_TO_ISO.get(normalised)
    if source_code is None:
        return headline

    cache = _load_cache()
    cached_row = cache[cache["event_id"] == event_id]
    if not cached_row.empty:
        return str(cached_row.iloc[0]["translated_headline"])

    translated = _call_mymemory(headline, source_code)

    cache = pd.concat(
        [cache, pd.DataFrame([{"event_id": event_id, "translated_headline": translated}])],
        ignore_index=True,
    )
    _save_cache(cache)
    return translated
