"""Rights register and publish guard (I-01).

PROJECT-STARTER section 6 sorts every source into a rights class:

* **a** may publish derived numbers, no attribution burden;
* **b** the same, with attribution;
* **c** research or non-commercial only; may be shown with the licence named and no ads;
* **d** no, or terms not read; private only.

A source's class above d needs its terms read at source, with the date and who read it.
This module holds that register (`RIGHTS`), the lookups the publish step uses
(`SOURCE_CLASS`, `series_class`, `drop_restricted`) and the renderer for `RIGHTS.md` at
the repo root, so the file and the code cannot disagree (`tests/test_rights.py` compares
them byte for byte). Edit this module, then run `uv run python -m core.rights`.

**What the guard does.** `core.publish.publish()` calls `drop_restricted()` before any
SQL: rows of a class d source, and rows whose `series_id` matches `RESTRICTED_SERIES`,
are not published. A source that is not in the register raises
`UnregisteredSourceError`: unknown means unread, and unread means d, but a sweep should
fail loudly rather than quietly publish less.

**The six disputed sources (I-06, parked).** GIE, ENTSO-E, ENTSOG, FRED, OPEC MOMR and
Baker Hughes are held at the class this repo's README gave them (`a`, "no attribution
requirement found"). The owner's registers (`~/Projects/_runs/desk-core/RIGHTS.md`,
`oil-gas-desk/RIGHTS.md`) class them `d`, and nobody has read their terms at source in
this repo. They are the one named exception to the rule above, they carry no read date,
and the owner decides: read the terms, ask for consent, or change the class here, which
takes the source off the serving layer at the next publish.

The reading of each terms page was done on 2026-11-21 by "improve run-01" with a plain
`curl` request. A page that refused the request, or that held no re-use statement, left
its source at d, "terms not read".
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pandas as pd

RESTRICTED_CLASSES: Final = frozenset({"d"})
"""Classes the serving layer must not carry."""

_CLASS_RANK: Final = {"a": 0, "b": 1, "c": 2, "d": 3}

READ_BY: Final = "improve run-01"
READ_ON: Final = "2026-11-21"


class UnregisteredSourceError(ValueError):
    """A source (or a publish label) with no row in the rights register.

    Unknown means unread, and unread means class d. The publish step raises rather than
    guessing, so a new source cannot reach the public layer by being forgotten here.
    """


@dataclass(frozen=True)
class SourceRight:
    """One source's row in `RIGHTS.md`."""

    name: str
    used: str
    terms: str
    cls: str
    surfaces: str
    credit: str = ""
    terms_url: str = ""
    read_on: str = ""
    read_by: str = ""
    owner_class: str = ""
    """The class in the owner's registers where it differs; empty when it agrees."""


def _read(
    name: str, used: str, terms: str, cls: str, surfaces: str, url: str, credit: str = "",
    owner_class: str = "",
) -> SourceRight:
    """A source whose terms page was read at source on READ_ON."""
    return SourceRight(
        name=name, used=used, terms=terms, cls=cls, surfaces=surfaces, credit=credit,
        terms_url=url, read_on=READ_ON, read_by=READ_BY, owner_class=owner_class,
    )


def _unread(name: str, used: str, terms: str, surfaces: str, owner_class: str = "") -> SourceRight:
    """A source left at class d because its terms were not read, or could not be."""
    return SourceRight(
        name=name, used=used, terms=terms, cls="d", surfaces=surfaces, owner_class=owner_class
    )


def _disputed(name: str, used: str, surfaces: str, credit: str = "") -> SourceRight:
    """One of the six I-06 sources: README class `a`, owner's register `d`, not read."""
    return SourceRight(
        name=name,
        used=used,
        terms=(
            "README reading kept pending I-06: free public data, no attribution requirement"
            " found. Not read at source by this run. The owner's register reads it as d"
        ),
        cls="a",
        surfaces=surfaces,
        credit=credit,
        owner_class="d",
    )


_API = "serving API"

RIGHTS: Final[Mapping[str, SourceRight]] = {
    "adanos": _unread(
        "Adanos sentiment API",
        "daily buzz and sentiment scores by ticker and platform",
        "terms not read",
        f"{_API} (series_long)",
    ),
    "ais": _unread(
        "aisstream.io",
        "live AIS positions, compacted to the latest per vessel",
        "terms not read",
        f"{_API} (vessel_latest)",
    ),
    "baker_hughes": _disputed(
        "Baker Hughes rig count", "North America rig counts", f"{_API} (series_long)"
    ),
    "cftc": _read(
        "CFTC Commitments of Traders",
        "disaggregated futures-only positions",
        "CFTC web policy, Copyright: government information on the CFTC website is in the"
        " public domain; appropriate acknowledgement requested",
        "b",
        f"README chart, {_API} (series_long)",
        "https://www.cftc.gov/WebPolicy/index.htm",
        "Source: CFTC Commitments of Traders",
    ),
    "coal": _read(
        "U.S. EIA coal, consumption and quality",
        "power-sector coal receipts, stocks, price and heat content",
        "EIA Copyrights and Reuse: U.S. government publications are in the public domain;"
        " an acknowledgment with the publication date is requested",
        "b",
        f"{_API} (series_long)",
        "https://www.eia.gov/about/copyrights_reuse.php",
        "Source: U.S. Energy Information Administration",
    ),
    "derived": SourceRight(
        name="Series computed in this repo",
        used="cracks, spreads, positions, moving averages, Cushing utilisation, z-scores",
        terms="inherits the worst class among its inputs; see the derived table below",
        cls="inherit",
        surfaces=f"web, {_API} (series_long)",
    ),
    "ecmwf": _read(
        "ECMWF open data",
        "IFS forecast runs for the weather anomaly maps",
        "ECMWF open data page: use is governed by CC-BY-4.0 and the ECMWF Terms of Use;"
        " the data may be redistributed and used commercially, subject to attribution",
        "b",
        "weather maps",
        "https://www.ecmwf.int/en/forecasts/datasets/open-data",
        "Contains modified ECMWF open data (CC BY 4.0)",
    ),
    "eia": _read(
        "U.S. Energy Information Administration, open data API v2",
        "WPSR, gas storage, EIA-930, prices, NYMEX ranks 1 to 4 to 2024-04-05",
        "EIA Copyrights and Reuse: U.S. government publications are in the public domain;"
        " an acknowledgment with the publication date is requested",
        "b",
        f"README charts, web, {_API} (series_long, seasonal, flows, wpsr_lines, spreads)",
        "https://www.eia.gov/about/copyrights_reuse.php",
        "Source: U.S. Energy Information Administration",
    ),
    "eirgrid": _read(
        "EirGrid Smart Grid Dashboard",
        "Irish and all-island demand, wind and interconnection",
        "EirGrid Group Open Data Licence: free to copy, adapt and use commercially;"
        " the attribution statement is required",
        "b",
        f"{_API} (series_long)",
        "https://www.smartgriddashboard.com/all/open-data-license/",
        "Supported by EirGrid Group Data",
        owner_class="d",
    ),
    "entsoe": _disputed(
        "ENTSO-E Transparency Platform",
        "power prices, load, generation and cross-border flows",
        f"{_API} (series_long, flows)",
        "Source: ENTSO-E Transparency Platform",
    ),
    "entsog": _disputed(
        "ENTSOG Transparency Platform", "gas flows and nominations", f"{_API} (flows)"
    ),
    "eurostat": _read(
        "Eurostat",
        "economic sentiment indicator",
        "Eurostat copyright notice: re-use of statistical data for commercial or"
        " non-commercial purposes is authorised with the source acknowledged; data"
        " identified as belonging to sources other than Eurostat may not be reused"
        " commercially. The sentiment survey is a DG ECFIN series, so held at c",
        "c",
        f"{_API} (series_long)",
        "https://ec.europa.eu/eurostat/help/copyright-notice",
        "Source: Eurostat",
        owner_class="d",
    ),
    "fred": _disputed(
        "FRED, Federal Reserve Bank of St. Louis",
        "spot prices, rates and macro series",
        f"{_API} (series_long)",
    ),
    "frankfurter": _unread(
        "Frankfurter exchange rates",
        "daily reference rates",
        "frankfurter.dev says the API is free and open source, blends central-bank"
        " providers and needs no key; it states no data licence or terms, so not read",
        f"{_API} (series_long)",
        owner_class="d",
    ),
    "gdelt": _read(
        "GDELT Project",
        "news article events",
        "GDELT Terms of Use: unlimited and unrestricted use, including commercial;"
        " redistribution allowed with a citation to the GDELT Project and a link",
        "b",
        f"web, {_API} (events)",
        "https://www.gdeltproject.org/about.html",
        "Source: The GDELT Project, https://www.gdeltproject.org/",
    ),
    "gfs": _read(
        "NOAA GFS via NOMADS",
        "2 m temperature forecasts for degree days",
        "NWS disclaimer: NWS information is in the public domain; the data must not be"
        " presented as official government material. The NOMADS page itself states no"
        " terms, so the NWS disclaimer is what was read",
        "b",
        f"web, {_API} (series_long)",
        "https://www.weather.gov/disclaimer",
        "Source: NOAA/NCEP Global Forecast System",
    ),
    "gie": _disputed(
        "GIE AGSI+ and ALSI+",
        "EU gas storage and LNG terminals",
        f"README chart (EU gas storage), web front page, {_API} (series_long, seasonal)",
        "GIE AGSI+/ALSI+",
    ),
    "gridstatus": _unread(
        "GridStatus",
        "U.S. ISO prices and load",
        "terms page refused a plain request (HTTP 403), so not read",
        f"{_API} (series_long)",
        owner_class="d",
    ),
    "guardian": _read(
        "The Guardian Open Platform",
        "news headlines (no key set yet)",
        "Open Platform terms: content for end users' personal and non-commercial use"
        " only, and any advertisement supplied with it must be displayed; a no-ads"
        " page cannot comply",
        "d",
        f"{_API} (events)",
        "https://www.theguardian.com/open-platform/terms-and-conditions",
    ),
    "ibkr": _unread(
        "Interactive Brokers gateway",
        "futures curves when FUTURES_SOURCE=ibkr",
        "private use only; market-data subscriptions are not redistributable",
        f"{_API} (series_long)",
    ),
    "jodi": _unread(
        "JODI-Oil World Database",
        "production, demand and stocks by country",
        "no terms page found on jodidata.org; the footer carries a copyright line only",
        f"{_API} (series_long)",
        owner_class="d",
    ),
    "manual": _unread(
        "Manual drops: vendor exports and paid commercial data",
        "reconstructed Brent forward curve, physical differentials",
        "paid commercial licences (pipelines/manual_physical/NOTES.md:32); the curve is"
        " reconstructed from a vendor export (pipelines/futures/NOTES.md:199)",
        f"web /curves, {_API} (series_long, curve_settles)",
    ),
    "newsapi": _read(
        "NewsAPI",
        "headline search, on demand",
        "NewsAPI terms: the free Developer plan is for development and testing only,"
        " never staging or production; production use needs a paid plan",
        "d",
        f"{_API} (events)",
        "https://newsapi.org/terms",
    ),
    "ofac": _unread(
        "OFAC sanctions lists",
        "Specially Designated Nationals list",
        "the Treasury site-policies page carries no re-use statement for list data, so"
        " not read as permission",
        f"web, {_API} (sanctions, events)",
    ),
    "opec_momr": _disputed(
        "OPEC Monthly Oil Market Report",
        "secondary-source output tables",
        f"{_API} (series_long)",
        "Source: OPEC Monthly Oil Market Report",
    ),
    "open_meteo": _read(
        "Open-Meteo",
        "observed weather and degree days",
        "Terms of Use: the free API is for non-commercial use only, under 10,000 calls a"
        " day; data under CC BY 4.0",
        "c",
        f"web, {_API} (series_long)",
        "https://open-meteo.com/en/terms",
        "Weather data by Open-Meteo.com (CC BY 4.0)",
    ),
    "open_meteo_forecast": _read(
        "Open-Meteo forecasts",
        "forecast weather, degree days and wind",
        "Terms of Use: the free API is for non-commercial use only, under 10,000 calls a"
        " day; data under CC BY 4.0",
        "c",
        f"web, {_API} (series_long)",
        "https://open-meteo.com/en/terms",
        "Weather data by Open-Meteo.com (CC BY 4.0)",
    ),
    "polymarket": _unread(
        "Polymarket",
        "event market quotes",
        "terms not read here; the owner's register reads the Terms of Use as barring"
        " redistribution",
        f"{_API} (events, series_long)",
        owner_class="d",
    ),
    "reddit": _unread(
        "Reddit",
        "post counts and sentiment",
        "terms not read",
        f"{_API} (events, series_long)",
    ),
    "stocktwits": _unread(
        "StockTwits", "post counts and sentiment", "terms not read", f"{_API} (events, series_long)"
    ),
    "yfinance": _unread(
        "Yahoo Finance",
        "continuous front-month closes for five roots",
        "Yahoo's terms restrict redistribution (pipelines/futures/NOTES.md:330), and the"
        " question for the public site was never answered",
        f"web front page, /prices and /curves, {_API} (series_long, seasonal)",
    ),
}

DISPUTED_SOURCES: Final = frozenset(
    {"gie", "entsoe", "entsog", "fred", "opec_momr", "baker_hughes"}
)
"""The six sources parked as I-06: held at the README class, `d` in the owner's register."""

SOURCE_CLASS: Final[Mapping[str, str]] = {source: row.cls for source, row in RIGHTS.items()}
"""Source id to class. `derived` is `inherit`: see `series_class`."""


# --- series-level rules -------------------------------------------------------------

RESTRICTED_SERIES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"^fut\.[a-z0-9]+\.f\d{2}\.close$"),  # Yahoo front-month closes
    re.compile(r"^derived\.ma\."),  # moving averages of those closes
    re.compile(r"^eex\."),  # EEX, licence-restricted (2ba04f3 on feat/lng)
    re.compile(r"^derived\.eu_carbon\.(price|balance)\."),  # pre-seeded for feat/sd-models
)
"""Series that stay off the serving layer whatever their `source` column says."""

DERIVED_INPUTS: Final[tuple[tuple[re.Pattern[str], tuple[str, ...]], ...]] = (
    (re.compile(r"^derived\.ma\."), ("yfinance",)),
    (re.compile(r"^derived\.cushing\."), ("eia",)),
    (re.compile(r"^derived\.inv\."), ("eia",)),
    (re.compile(r"^derived\.cot\."), ("cftc",)),
    (re.compile(r"^derived\.crack\..+\.spot$"), ("fred",)),
    (re.compile(r"^derived\.crack\..+\.m\d$"), ("eia",)),
    # pipelines/derived/curve_ranks.py reads the EIA rank series. curve.py would read
    # contract-coded manual settles, but writes nothing today (no series_meta rows).
    (re.compile(r"^derived\.(spread|curve)\."), ("eia",)),
    (re.compile(r"^derived\.pos\."), ("eia", "cftc")),
)
"""`derived` series id to the sources its inputs come from. An id that matches none is
class d: no mapping means the inputs were not traced."""


def _worst(classes: list[str]) -> str:
    return max(classes, key=lambda c: _CLASS_RANK[c])


def series_class(source: str, series_id: str) -> str:
    """The class that governs one series.

    Equal to the source's class, except for `derived`, which takes the worst class among
    the sources its inputs come from (`DERIVED_INPUTS`), and d when no mapping matches.
    """
    if source not in SOURCE_CLASS:
        raise UnregisteredSourceError(
            f"source {source!r} is not in core/rights.py's register; add it with its terms"
            " read at source, or it stays unpublished"
        )
    cls = SOURCE_CLASS[source]
    if cls != "inherit":
        return cls
    for pattern, inputs in DERIVED_INPUTS:
        if pattern.search(series_id):
            return _worst([SOURCE_CLASS[i] for i in inputs])
    return "d"


# --- the guard ----------------------------------------------------------------------

PIPELINE_SOURCES: Final[Mapping[str, str]] = {
    "wpsr": "eia",
    "yfinance": "yfinance",
    "ais": "ais",
}
"""`publish(..., pipeline=)` labels that are not themselves source ids. Any label that is
a source id (the sweep passes one) needs no entry."""

TABLE_PIPELINE_SOURCES: Final[Mapping[tuple[str, str], str]] = {
    ("curve", "curve_settles"): "manual",  # contract-coded, reconstructed from a vendor export
    ("curve", "spreads"): "eia",  # rank-based NYMEX settles
}

NEUTRAL_PIPELINES: Final = frozenset({"events", "flows"})
"""Labels for tables whose rows carry their own `source` column."""


def _pipeline_source(pipeline: str | None, table: str) -> str:
    if pipeline is None:
        raise UnregisteredSourceError(
            f"cannot tell which source feeds serving.{table}: the frame has no `source`"
            " column and no pipeline label was given"
        )
    if (pipeline, table) in TABLE_PIPELINE_SOURCES:
        return TABLE_PIPELINE_SOURCES[(pipeline, table)]
    if pipeline in PIPELINE_SOURCES:
        return PIPELINE_SOURCES[pipeline]
    if pipeline in SOURCE_CLASS:
        return pipeline
    if pipeline in NEUTRAL_PIPELINES:
        raise UnregisteredSourceError(
            f"pipeline {pipeline!r} does not name a source, and serving.{table} rows have"
            " no `source` column to say which one"
        )
    raise UnregisteredSourceError(
        f"pipeline label {pipeline!r} is not a known source or label in core/rights.py"
    )


def drop_restricted(
    df: pd.DataFrame, table: str, *, pipeline: str | None
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Rows of `df` that may be published, and what was dropped.

    A row goes when its source is class d (by the `source` column, else by the pipeline
    label), when `derived` inputs trace to class d, or when its `series_id` matches
    `RESTRICTED_SERIES`. The dict maps what was dropped (a series id, or `source=<x>`
    for a frame with no series ids) to a row count.

    Raises `UnregisteredSourceError` before returning anything if a source or label is
    unknown or missing.
    """
    if df.empty:
        return df, {}

    has_series = "series_id" in df.columns
    if "source" in df.columns:
        sources = df["source"]
        if sources.isna().any():
            raise UnregisteredSourceError(
                f"serving.{table}: {int(sources.isna().sum())} row(s) with no source"
            )
        unknown = sorted(set(sources) - set(SOURCE_CLASS))
        if unknown:
            raise UnregisteredSourceError(
                f"serving.{table}: source(s) {unknown} are not in core/rights.py's register;"
                " add them with their terms read at source, or they stay unpublished"
            )
    else:
        sources = pd.Series(_pipeline_source(pipeline, table), index=df.index)

    series = df["series_id"].astype(str) if has_series else None
    restricted = pd.Series(False, index=df.index)
    for source in sources.unique():
        mask = sources == source
        cls = SOURCE_CLASS[source]
        if cls == "inherit":
            if series is None:
                raise UnregisteredSourceError(
                    f"serving.{table}: {source!r} rows need a series_id to inherit a class"
                )
            by_id = {sid: series_class(source, sid) for sid in series[mask].unique()}
            restricted |= mask & series.map(by_id).isin(RESTRICTED_CLASSES)
        elif cls in RESTRICTED_CLASSES:
            restricted |= mask
    if series is not None:
        flagged = {
            sid: any(p.search(sid) for p in RESTRICTED_SERIES) for sid in series.unique()
        }
        restricted |= series.map(flagged).astype(bool)

    if not restricted.any():
        return df, {}
    labels = series[restricted] if series is not None else "source=" + sources[restricted]
    dropped = {str(k): int(v) for k, v in labels.value_counts(sort=False).items()}
    return df.loc[~restricted], dict(sorted(dropped.items()))


# --- RIGHTS.md ----------------------------------------------------------------------

RIGHTS_MD: Final = Path(__file__).resolve().parent.parent / "RIGHTS.md"

_HEADER: Final = """# RIGHTS.md

Every source this repo pulls, its terms as read, and the class that decides what the
serving layer may carry. Written from `core/rights.py` by `uv run python -m core.rights`;
edit that module, not this file (`tests/test_rights.py` checks they agree).

Classes (PROJECT-STARTER section 6): **a** may publish derived numbers, no attribution
burden. **b** the same, with attribution. **c** research or non-commercial only; may be
shown with the licence named and no ads. **d** no, or terms not read; private only.
`core/publish.py` drops class d rows before any SQL runs, and refuses a source that is
not in this table.

A class above d needs its terms read at source. "Read on" and "read by" say when and by
whom; the terms pages were fetched with a plain request and read in full. A page that
refused the request, or that held no re-use statement, leaves the source at d, "terms not
read". The six sources parked as I-06 are the one exception: they are held at class a,
the reading the README gave them, with no read date, until the owner decides. The owner's
register (`~/Projects/_runs/desk-core/RIGHTS.md`) classes all six d. Marking one d in
`core/rights.py` takes it off the serving layer at the next publish.

"""


def _cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ")


def render_markdown() -> str:
    """The text of `RIGHTS.md`."""
    lines = [_HEADER]
    lines.append(
        "| source | name | what is used | terms as read here | class | owner register |"
        " public surfaces reached | credit line | terms page | read on | read by |"
    )
    lines.append("|" + "---|" * 11)
    for source in sorted(RIGHTS):
        r = RIGHTS[source]
        lines.append(
            "| "
            + " | ".join(
                _cell(c)
                for c in (
                    f"`{source}`",
                    r.name,
                    r.used,
                    r.terms,
                    r.cls,
                    r.owner_class or "same",
                    r.surfaces,
                    r.credit,
                    r.terms_url,
                    r.read_on,
                    r.read_by or "not read",
                )
            )
            + " |"
        )
    lines.append("")
    lines.append("## Derived series")
    lines.append("")
    lines.append(
        "A `derived` series takes the worst class among the sources its inputs come from."
        " An id that matches no row here is class d."
    )
    lines.append("")
    lines.append("| series id pattern | inputs | class |")
    lines.append("|---|---|---|")
    for pattern, inputs in DERIVED_INPUTS:
        cls = _worst([SOURCE_CLASS[i] for i in inputs])
        lines.append(f"| `{pattern.pattern}` | {', '.join(inputs)} | {cls} |")
    lines.append("")
    lines.append("## Series kept off the serving layer whatever their source")
    lines.append("")
    for pattern in RESTRICTED_SERIES:
        lines.append(f"- `{pattern.pattern}`")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    RIGHTS_MD.write_text(render_markdown())
    print(f"wrote {RIGHTS_MD}")


if __name__ == "__main__":
    main()
