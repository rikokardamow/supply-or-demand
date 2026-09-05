"""Hand-maintained FRED series reference table -- same small-reference-table precedent
as pipelines/weather/cities.py / pipelines/opec_momr/quotas.csv. Every (unit, freq)
pair here was read from that series' own live `Fred.get_series_info(...)` response,
not guessed from the series id/title -- see CLAUDE.md for the two substitutions this
caught (a stale/wrong-kind-of-series swap, a flat-wrong ID guess) and the two series
dropped for being stale/non-existent before ever reaching this table.

Deliberately goes well beyond specs/10_macro-fx.md's own 5-series list, per explicit
user request for "much more around energy and inflation... micro and macro level" --
organised into MACRO_SERIES (broad economy/inflation/rates) and ENERGY_SERIES
(crude/product prices, energy-specific inflation, energy-sector labour/sentiment)."""

from __future__ import annotations

from typing import NamedTuple


class SeriesMeta(NamedTuple):
    unit: str
    freq: str
    geo: str


MACRO_SERIES: dict[str, SeriesMeta] = {
    "CPIAUCSL": SeriesMeta("Index 1982-1984=100", "M", "US"),
    "CPILFESL": SeriesMeta("Index 1982-1984=100", "M", "US"),
    "PCEPI": SeriesMeta("Index 2017=100", "M", "US"),
    "PCEPILFE": SeriesMeta("Index 2017=100", "M", "US"),
    "CP0000EZ19M086NEST": SeriesMeta("Index 2025=100", "M", "EA"),
    "PPIACO": SeriesMeta("Index 1982=100", "M", "US"),
    "DTWEXBGS": SeriesMeta("Index Jan 2006=100", "D", "US"),
    "DTWEXAFEGS": SeriesMeta("Index Jan 2006=100", "D", "US"),
    "DGS10": SeriesMeta("Percent", "D", "US"),
    "DFII10": SeriesMeta("Percent", "D", "US"),
    "T5YIE": SeriesMeta("Percent", "D", "US"),
    "T10YIE": SeriesMeta("Percent", "D", "US"),
    "MICH": SeriesMeta("Percent", "M", "US"),
    "INDPRO": SeriesMeta("Index 2017=100", "M", "US"),
    "GDPC1": SeriesMeta("Billions of Chained 2017 Dollars", "Q", "US"),
    "UNRATE": SeriesMeta("Percent", "M", "US"),
    "FEDFUNDS": SeriesMeta("Percent", "M", "US"),
    "M2SL": SeriesMeta("Billions of Dollars", "M", "US"),
}

ENERGY_SERIES: dict[str, SeriesMeta] = {
    "DCOILWTICO": SeriesMeta("Dollars per Barrel", "D", "US"),
    "DCOILBRENTEU": SeriesMeta("Dollars per Barrel", "D", "US"),
    "DHHNGSP": SeriesMeta("Dollars per Million BTU", "D", "US"),
    "GASREGW": SeriesMeta("Dollars per Gallon", "W", "US"),
    "GASREGECW": SeriesMeta("Dollars per Gallon", "W", "PADD1"),
    "GASREGMWW": SeriesMeta("Dollars per Gallon", "W", "PADD2"),
    "GASREGGCW": SeriesMeta("Dollars per Gallon", "W", "PADD3"),
    "GASREGRMW": SeriesMeta("Dollars per Gallon", "W", "PADD4"),
    "GASREGWCW": SeriesMeta("Dollars per Gallon", "W", "PADD5"),
    "DDFUELUSGULF": SeriesMeta("Dollars per Gallon", "D", "PADD3"),
    "DJFUELUSGULF": SeriesMeta("Dollars per Gallon", "D", "PADD3"),
    # Spot product legs for the Spec 20 crack boards. Daily back to 1986-06-02, so the
    # crack history spans Murat & Tokat's own 1993-2008 sample. These are *spot* legs, not
    # the crack futures the paper uses -- see specs/20_refining-crack-vecm.md.
    "DGASNYH": SeriesMeta("Dollars per Gallon", "D", "PADD1"),
    "DGASUSGULF": SeriesMeta("Dollars per Gallon", "D", "PADD3"),
    "DHOILNYH": SeriesMeta("Dollars per Gallon", "D", "PADD1"),
    "WPU0561": SeriesMeta("Index 1982=100", "M", "US"),
    "PPIENG": SeriesMeta("Index 1982=100", "M", "US"),
    "CPIENGSL": SeriesMeta("Index 1982-1984=100", "M", "US"),
    "IR100": SeriesMeta("Index 2000=100", "M", "US"),
    "CES1021100001": SeriesMeta("Thousands of Persons", "M", "US"),
    "DALENGINDEXQQ04": SeriesMeta("Index", "Q", "US"),
}

FRED_SERIES: dict[str, SeriesMeta] = {**MACRO_SERIES, **ENERGY_SERIES}
