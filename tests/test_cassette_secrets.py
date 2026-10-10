"""Secret-scan meta-test: reuses README.md's own documented pre-commit check
(`git grep -iE "api_key.*=.*[A-Za-z0-9]{20}"`) so a real API key can never land
in a committed cassette without failing CI, not just a human's memory of running
the check by hand before committing."""

from __future__ import annotations

import re
from pathlib import Path

CASSETTES_DIR = Path(__file__).parent / "cassettes"

# Verbatim from README.md's own pre-commit check.
_SECRET_PATTERN = re.compile((
    # A literal api_key=<value>, which is how EIA and friends pass a key.
    r"api_key.*=.*[A-Za-z0-9]{20}"
    # A bearer token or a JWT. The old single pattern could not see either: neither
    # contains the substring "api_key", so a recorded Authorization header would have
    # passed this guard silently.
    r"|[Aa]uthorization:\s*[Bb]earer\s+\S{20}"
    r"|eyJ(?:hbGciOi|0eXAiOi|pc3MiOi)"
    # A session cookie, and a signed/presigned URL.
    # vcrpy writes headers as a YAML block -- the name on one line, each value on its
    # own "- " line beneath it -- so a pattern anchored to "Set-Cookie: <value>" on one
    # line can never fire. This matches the value line instead.
    r"|^\s*-\s*\w+=\S{16,}.*(?:path=|domain=|expires=|max-age=)"
    r"|[?&](?:sig|signature|X-Amz-Signature)=[A-Za-z0-9%_-]{20}"
), re.IGNORECASE | re.MULTILINE)


def test_no_cassette_contains_a_real_looking_api_key() -> None:
    offenders = []
    for path in CASSETTES_DIR.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _SECRET_PATTERN.search(text):
            offenders.append(str(path.relative_to(CASSETTES_DIR)))

    assert not offenders, f"possible API key found in cassette(s): {offenders}"
