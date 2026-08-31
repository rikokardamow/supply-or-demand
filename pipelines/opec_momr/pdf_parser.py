"""Parses per-country DoC crude production (Table 5-7, "based on secondary
sources") straight out of the MOMR PDF's own embedded text layer. This is the one
target table genuinely missing from the Excel appendix (confirmed in Session A --
Excel only has the OPEC-wide aggregate, not per-country breakdown).

Session B's spec text calls for a Camelot lattice-mode parse as the fallback here.
Tried it first, live: the auto-download endpoint (momr.opec.org/pdf-download/) is
blocked (403), and Camelot's lattice mode needs a system Ghostscript install --
installed successfully but the underlying question is moot, because the MOMR PDF
turns out to have a full, clean, digitally-native text layer (not a scan), so a
much simpler and more reliable approach was available: read the embedded text
directly and regex the rows, no Ghostscript/Camelot/image-based table detection
needed at all. Verified live: summing every OPEC member row from this parser
against the PDF's own printed "Total OPEC" line for the same month matched to
within 1 unit (23,633 vs 23,632 -- OPEC's own "totals may not add up due to
independent rounding" disclaimer, not a parsing error).

Table 5-8 ("based on direct communication") exists on the same page but is
visibly messier (missing-data ".." cells, footnoted alternate figures for Saudi
Arabia) and isn't the metric the spec's own example series_id
(`momr.prod.saudi.secondary`) points at -- only Table 5-7 is parsed here."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pypdfium2 as pdfium

# Table 5-7's real column order, confirmed live (August 2026 issue) -- annual x2,
# quarterly x3, then the latest 3 actual months, then a Jul/Jun-style change
# column (skipped, it's a delta not a period value). The two trailing-month
# columns' actual calendar months shift by one each issue (this issue: May/Jun/Jul
# 2026) -- inferred from the sheet's own header row rather than hardcoded, since
# "the latest 1-2 actual months" already proved variable in the Excel appendix
# (Session A, Table 11-5).
_ROW_RE = re.compile(
    r"^(?P<country>[A-Za-z][A-Za-z .]*?)\s+(?P<values>[\d,.\-]+(?:\s+[\d,.*\-]+|\s+\.\.)*)$"
)


def _parse_header_periods(
    header_line: str, latest_months: list[pd.Timestamp]
) -> list[tuple[pd.Timestamp, str]]:
    """header_line is e.g. "2024 2025 4Q25 1Q26 2Q26 May 26 Jun 26 Jul 26
    Jul/Jun" -- but month names and years are space-separated (unlike the
    Excel appendix's own tokens), so this can't be split on whitespace alone.
    `latest_months` (found separately, see `_find_table_5_7`) supplies the
    actual calendar months for the trailing "May 26"-style columns in order."""
    periods: list[tuple[pd.Timestamp, str]] = []
    tokens = header_line.split()
    i = 0
    month_idx = 0
    while i < len(tokens):
        tok = tokens[i]
        if re.match(r"^(19|20)\d{2}$", tok):
            periods.append((pd.Timestamp(int(tok), 1, 1), "A"))
            i += 1
        elif re.match(r"^[1-4]Q\d{2}$", tok):
            quarter, yy = int(tok[0]), int(tok[2:])
            month = (quarter - 1) * 3 + 1
            periods.append((pd.Timestamp(2000 + yy, month, 1), "Q"))
            i += 1
        elif re.match(r"^[A-Z][a-z]{2}$", tok) and i + 1 < len(tokens) and tokens[i + 1].isdigit():
            # "May 26" style two-token month header -- use the pre-resolved
            # calendar month rather than re-deriving it (the header alone is
            # ambiguous about which year "26" means without more context, and
            # we already know the real months from the page's own narrative).
            periods.append((latest_months[month_idx], "M"))
            month_idx += 1
            i += 2
        else:
            i += 1  # "Change", "Jul/Jun" etc -- not a period column, skip
    return periods


def _find_table_5_7(pdf: pdfium.PdfDocument) -> tuple[list[str], list[tuple[pd.Timestamp, str]]]:
    """Returns (data_lines, periods). Searches every page for the table rather
    than assuming a fixed page number -- confirmed live it moves issue to issue
    (page 66 in the August 2026 PDF, a physical position, not a MOMR-numbered
    page)."""
    for page_idx in range(len(pdf)):
        text = pdf[page_idx].get_textpage().get_text_range()
        if "Table 5 - 7" not in text or "secondary sources" not in text.lower():
            continue

        lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]

        # The narrative names the actual trailing months (e.g. "averaged ...
        # in July 2026, ... m-o-m" and the table intro sentence) -- but the
        # cleanest anchor is the "Secondary" / "sources <periods>" header pair
        # that precedes the real data block (confirmed live: this appears
        # *after* both tables' titles and the intro paragraph in reading
        # order, a two-column PDF layout quirk, not a bug in this scan).
        try:
            header_idx = next(i for i, line in enumerate(lines) if line == "Secondary Change")
        except StopIteration as exc:
            raise ValueError(
                f"Page {page_idx + 1}: found Table 5-7's title but not its "
                f"'Secondary Change' header row — layout may have changed"
            ) from exc

        period_line = lines[header_idx + 1]
        latest_months = _infer_latest_months(lines)
        periods = _parse_header_periods(period_line, latest_months)
        if len(periods) < 5:
            raise ValueError(
                f"Page {page_idx + 1}: only parsed {len(periods)} period columns "
                f"from {period_line!r} — expected at least 5"
            )

        data_lines = []
        for line in lines[header_idx + 2 :]:
            if line.startswith(("Notes:", "Source:")):
                break
            data_lines.append(line)
        return data_lines, periods

    raise ValueError(
        "Table 5-7 (DoC crude oil production, secondary sources) not found in this PDF"
    )


def _infer_latest_months(lines: list[str]) -> list[pd.Timestamp]:
    """The page's own narrative sentence names the real calendar year for the
    trailing month columns (e.g. "averaged 37.66 mb/d in July 2026") -- used to
    anchor the two-token "May 26"/"Jun 26"/"Jul 26" header cells to real dates
    rather than guessing the century from "26" alone."""
    narrative = next(
        (line for line in lines if line.startswith("Total DoC crude oil production")), None
    )
    if narrative is None:
        raise ValueError(
            "Could not find the DoC crude oil production narrative sentence to anchor months"
        )
    match = re.search(r"in (\w+) (\d{4})", narrative)
    if not match:
        raise ValueError(f"Could not parse a month/year out of narrative: {narrative!r}")
    latest_month_name, year = match.group(1), int(match.group(2))
    latest = pd.Timestamp(f"{latest_month_name} 1, {year}")
    return [latest - pd.DateOffset(months=2), latest - pd.DateOffset(months=1), latest]


def parse_doc_crude_secondary(path: Path, revision_date: pd.Timestamp) -> pd.DataFrame:
    """Returns a ts_long-shaped DataFrame of per-country DoC crude production
    (secondary sources), unit tb/d -- geo is the actual country here (unlike the
    Excel appendix parser's "WORLD" simplification), since this table's whole
    point is per-country compliance."""
    pdf = pdfium.PdfDocument(path)
    data_lines, periods = _find_table_5_7(pdf)

    rows: list[dict[str, object]] = []
    for line in data_lines:
        match = _ROW_RE.match(line)
        if not match:
            continue
        country = match.group("country").strip()
        if country.startswith("Total"):
            continue  # subtotal rows -- not a single country
        tokens = match.group("values").split()
        # The row's last token is a trailing "Jul/Jun"-style change value with
        # no corresponding period column (confirmed live: the header's own
        # last column, e.g. "Jul/Jun", is a delta and deliberately not counted
        # as a period by `_parse_header_periods`) -- so there's always exactly
        # one more value token than period columns.
        if len(tokens) != len(periods) + 1:
            raise ValueError(
                f"Row {line!r}: found {len(tokens)} value tokens, expected "
                f"{len(periods) + 1} ({len(periods)} periods + 1 change column) "
                f"— layout may have changed"
            )
        for token, (ts, freq) in zip(tokens[: len(periods)], periods, strict=True):
            if token in ("..", "."):
                continue  # confirmed live: OPEC's own "not available" marker
            clean_token = token.rstrip("*")  # confirmed footnote marker (Table 5-8 only, harmless)
            value = float(clean_token.replace(",", ""))
            rows.append(
                {
                    "series_id": f"momr.doc_crude_secondary.{_slug(country)}.{_freq_word(freq)}",
                    "source": "opec_momr",
                    "ts": ts,
                    "value": value,
                    "unit": "tb/d",
                    "geo": country,
                    "freq": freq,
                    "revision_date": revision_date,
                }
            )

    if not rows:
        raise ValueError("Parsed zero data rows from Table 5-7 — layout may have changed")
    return pd.DataFrame(rows)[
        ["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]
    ]


def find_issue_month(path: Path) -> pd.Timestamp:
    """The MOMR's own publication date, read from the front page (e.g. "12
    August 2026") -- confirmed live as more reliable than trusting a filename
    convention, and consistent with the running header on every other page
    ("OPEC Monthly Oil Market Report — August 2026")."""
    pdf = pdfium.PdfDocument(path)
    text = pdf[0].get_textpage().get_text_range()
    match = re.search(r"\d{1,2} (\w+) (\d{4})", text)
    if not match:
        raise ValueError(f"Could not find a publication date on {path.name}'s front page")
    return pd.Timestamp(f"{match.group(1)} 1, {match.group(2)}")


def _slug(label: str) -> str:
    cleaned = re.sub(r"[^\w\s]", "", label).strip().lower()
    return re.sub(r"\s+", "_", cleaned)


def _freq_word(freq: str) -> str:
    return {"A": "annual", "Q": "quarterly", "M": "monthly"}[freq]
