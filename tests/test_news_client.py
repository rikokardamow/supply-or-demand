from __future__ import annotations

import pandas as pd
import pytest
from pipelines.news.client import GDELTClient


@pytest.mark.vcr
def test_search_returns_real_tagged_rows_for_a_crude_outage_query() -> None:
    df = GDELTClient().search(
        '("refinery" OR "pipeline") AND (outage OR fire OR explosion OR "force majeure")',
        timespan="7d",
        maxrecords=10,
    )

    assert {"url", "title", "seendate", "domain", "language", "sourcecountry"}.issubset(df.columns)
    assert not df.empty
    assert pd.api.types.is_datetime64_any_dtype(df["seendate"])
