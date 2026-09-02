"""FRED client -- thin wrapper around `fredapi.Fred`, same "wrap a third-party SDK"
precedent as pipelines/entsoe/client.py's ENTSOEClient around EntsoePandasClient.

Confirmed live (reading fredapi's own source, fred.py): it builds its request URL with
the literal query param `&api_key=...`, and FRED's raw JSON response never echoes it
back anywhere (checked a real response body directly -- no request/params section
like EIA's does). tests/conftest.py's existing filter_query_parameters already covers
this exactly -- no new cassette scrub needed."""

from __future__ import annotations

import pandas as pd
from core.settings import settings
from fredapi import Fred


class FREDClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._client = Fred(api_key=api_key or settings.fred_api_key)

    def get_series(self, series_id: str) -> pd.DataFrame:
        """Returns columns: ts, value -- fredapi's own get_series returns a bare
        value Series (DatetimeIndex) with no unit/frequency/geo metadata attached;
        pipelines/macro/fred_series.py's FRED_SERIES table supplies those separately."""
        series = self._client.get_series(series_id)
        return pd.DataFrame({"ts": series.index, "value": series.to_numpy()})
