"""Parses per-country DoC crude production (secondary sources) from a manually
provided MOMR PDF into ts_long. Unlike pull_momr.py's Excel appendix, this has
no automated download -- confirmed live (Session B): momr.opec.org/pdf-download/
returns a 403, and there's no other public, stable PDF URL pattern the way
opec.org's Excel appendix has. Save the PDF under data/raw/opec/ yourself
(matching the Excel cache's own directory) and pass its path as an argument, or
rely on the default guess of the current month's conventional filename."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from core.storage import write_ts_long

from pipelines.opec_momr.pdf_parser import find_issue_month, parse_doc_crude_secondary

CACHE_DIR = Path("data/raw/opec")


def _default_pdf_path(today: date | None = None) -> Path:
    reference = today or date.today()
    return CACHE_DIR / f"momr-{reference.strftime('%B').lower()}-{reference.year}.pdf"


def main() -> None:
    pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _default_pdf_path()
    if not pdf_path.exists():
        raise SystemExit(
            f"MOMR PDF not found at {pdf_path} -- the auto-download endpoint is blocked "
            f"(confirmed live, see pipelines/opec_momr/NOTES.md). Save the PDF there "
            f"yourself, or pass its path as an argument."
        )

    revision_date = find_issue_month(pdf_path)
    df = parse_doc_crude_secondary(pdf_path, revision_date)
    write_ts_long(df, source="opec_momr")
    print(f"wrote {len(df)} rows across {df['geo'].nunique()} countries ({pdf_path.name})")


if __name__ == "__main__":
    main()
