"""IBKR MCP curve parsing. No cassettes exist for this source and none can: vcrpy records
HTTP made from Python, and this data arrives through an MCP tool, never through Python's
HTTP stack. The fixture under tests/fixtures/futures/ is a trimmed real response instead."""

from __future__ import annotations

import pytest
from pipelines.futures.client import looks_like_rank_code
from pipelines.futures.ibkr_curve import contract_code_from_month


def test_contract_code_from_month_covers_every_month_letter() -> None:
    codes = [contract_code_from_month(f"2026{month:02d}") for month in range(1, 13)]
    assert codes == [
        "f2026", "g2026", "h2026", "j2026", "k2026", "m2026",
        "n2026", "q2026", "u2026", "v2026", "x2026", "z2026",
    ]


def test_every_derived_code_clears_the_rank_namespace_guard() -> None:
    """A two-digit year would collide: January is "f", so f27 reads as rank 27. Eight such
    series were live in the lake before that was caught."""
    for year in (2026, 2027, 2030, 2036):
        for month in range(1, 13):
            code = contract_code_from_month(f"{year}{month:02d}")
            assert not looks_like_rank_code(code), code


def test_contract_code_rejects_a_malformed_month() -> None:
    with pytest.raises(ValueError, match="contract_month"):
        contract_code_from_month("2026-12")


def test_contract_code_rejects_an_impossible_month() -> None:
    with pytest.raises(ValueError, match="contract_month"):
        contract_code_from_month("202613")
