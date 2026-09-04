"""Secret-scan meta-test: reuses README.md's own documented pre-commit check
(`git grep -iE "api_key.*=.*[A-Za-z0-9]{20}"`) so a real API key can never land
in a committed cassette without failing CI, not just a human's memory of running
the check by hand before committing."""

from __future__ import annotations

import re
from pathlib import Path

CASSETTES_DIR = Path(__file__).parent / "cassettes"

# Verbatim from README.md's own pre-commit check.
_SECRET_PATTERN = re.compile(r"api_key.*=.*[A-Za-z0-9]{20}", re.IGNORECASE)


def test_no_cassette_contains_a_real_looking_api_key() -> None:
    offenders = []
    for path in CASSETTES_DIR.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _SECRET_PATTERN.search(text):
            offenders.append(str(path.relative_to(CASSETTES_DIR)))

    assert not offenders, f"possible API key found in cassette(s): {offenders}"
