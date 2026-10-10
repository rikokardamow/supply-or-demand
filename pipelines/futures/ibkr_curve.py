"""Parse an archived IBKR MCP curve capture into lake rows.

The connector is an MCP tool, not a Python library, so nothing here fetches anything:
the capture is archived by an agent session under data/raw/ibkr/ and this module parses
it. See docs/superpowers/specs/2026-10-10-ibkr-curve-design.md.

Prices from this source are LAST TRADE, not exchange settlement -- the response reports
its own price source as "Last". Series are therefore `.close`, never `.settle`. See
pipelines/futures/CLAUDE.md for what that difference is worth, measured.
"""

from __future__ import annotations

import re
from typing import Final

MONTH_CODES: Final[dict[int, str]] = {
    1: "f", 2: "g", 3: "h", 4: "j", 5: "k", 6: "m",
    7: "n", 8: "q", 9: "u", 10: "v", 11: "x", 12: "z",
}
"""Standard exchange delivery-month letters, January to December."""

_MONTH_RE: Final = re.compile(r"\d{6}")


def contract_code_from_month(contract_month: str) -> str:
    """IBKR's `contract_month` ("202612") -> this lake's contract code ("z2026").

    The year is deliberately four digits. A two-digit year collides with the nearby-rank
    namespace (January is "f", so "f27" is indistinguishable from rank 27) -- see
    client.looks_like_rank_code, which this module's callers assert against.
    """
    if not _MONTH_RE.fullmatch(contract_month):
        raise ValueError(f"contract_month must be YYYYMM, got {contract_month!r}")
    year = int(contract_month[:4])
    month = int(contract_month[4:])
    if month not in MONTH_CODES:
        raise ValueError(f"contract_month names no real month: {contract_month!r}")
    return f"{MONTH_CODES[month]}{year}"
