"""The README and docs must not claim what the code does not do (I-03).

Each assertion is a claim that was false when this test was written, or a pointer that
has to stay true: revisions replace the earlier row, the terms were not "checked per
pipeline", and the API example must not teach a class d series.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from core.rights import RIGHTS

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
DOCS_README = (ROOT / "docs" / "README.md").read_text()


def test_the_readme_does_not_say_a_revision_is_a_new_row() -> None:
    # core/storage.py de-duplicates on (series_id, ts) and keeps the last write, so a
    # corrected number replaces the first print. Keeping first prints is I-05, parked.
    assert "a corrected number is a new row" not in README
    assert "replaces the earlier one" in README
    assert "First prints are not retained yet" in README


def test_the_readme_does_not_claim_terms_were_checked_per_pipeline() -> None:
    assert "Checked per pipeline" not in README
    assert "no attribution requirement found in each provider's own documents" not in README


def test_the_api_example_uses_a_public_domain_series() -> None:
    assert "fut.cl.f01.close" not in README
    assert "series_id=eq.WCESTUS1" in README


def test_the_readme_and_docs_point_at_rights_md() -> None:
    assert "RIGHTS.md" in README
    assert "RIGHTS.md" in DOCS_README
    assert (ROOT / "RIGHTS.md").exists()


def test_the_docs_do_not_say_the_notes_files_record_terms() -> None:
    assert "and its terms" not in DOCS_README


def test_the_readme_names_yahoo_as_kept_off_the_serving_layer() -> None:
    row = next(line for line in README.splitlines() if line.startswith("| Yahoo Finance"))
    assert "serving layer" in row


@pytest.mark.parametrize("source", sorted(s for s, r in RIGHTS.items() if r.cls == "d"))
def test_no_readme_licence_row_calls_a_class_d_source_free(source: str) -> None:
    """A class d source may be named in the README, but not in a row that says free
    public data with no attribution."""
    name = RIGHTS[source].name
    for line in README.splitlines():
        if line.startswith("|") and name.lower() in line.lower():
            assert "no attribution requirement" not in line, line


def test_the_readme_licence_table_lists_the_disputed_sources_as_pending() -> None:
    row = next(line for line in README.splitlines() if "GIE AGSI+" in line and line.startswith("|"))
    assert re.search(r"RIGHTS\.md", row)
    assert "pending" in row.lower()


def test_the_readme_shows_no_screenshot_of_class_d_data() -> None:
    # The dashboard capture showed Yahoo front-month closes, class d (core/rights.py):
    # a picture of class d data is the data (PROJECT-STARTER section 6, rule 10).
    assert "data-overview.png" not in README
    assert "screenshots/" not in README
    assert not (ROOT / "docs" / "screenshots" / "data-overview.png").exists()
