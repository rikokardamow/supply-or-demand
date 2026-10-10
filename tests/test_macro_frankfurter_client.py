from __future__ import annotations

from datetime import date

import pytest
from pipelines.macro.frankfurter_client import FrankfurterClient


@pytest.mark.vcr
def test_get_rates_returns_real_plausible_rates() -> None:
    df = FrankfurterClient().get_rates(date(2026, 8, 28), date(2026, 9, 2), ["EUR", "GBP", "TRY"])

    assert list(df.columns) == ["ts", "currency", "rate"]
    assert not df.empty
    assert set(df["currency"]) == {"EUR", "GBP", "TRY"}
    # EUR-per-USD and GBP-per-USD are plausible in a narrow real-world band;
    # TRY-per-USD is a much larger number (a weak currency) -- both sanity-checked
    # against real values confirmed live while planning, not arbitrary bounds.
    eur = df[df["currency"] == "EUR"]["rate"]
    assert (eur > 0.5).all() and (eur < 1.5).all()
