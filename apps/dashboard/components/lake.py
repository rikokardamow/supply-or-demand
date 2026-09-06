"""Cached lake reads for the dashboard.

Streamlit reruns a page's entire script on every interaction -- every widget change,
every tab switch, every map click -- so an uncached `read_ts_long` re-queries the parquet
lake each time. `19_fundamentals.py` alone made seven such reads per rerun.

These wrappers keep `core.storage`'s own names and signatures, so a page swaps one import
line and no call site changes. The caching lives here rather than in `core/storage.py`
because that module is imported by every pipeline and must not depend on Streamlit.

**A page that writes to the lake must clear the matching reader afterwards** --
`read_events.clear()` -- or its own `st.rerun()` will show it the pre-write cache and the
write will look like it did nothing for a full TTL. `09_events.py`'s manual NewsAPI search
is the one place in this app that writes, and it does exactly that.

Reads stay uncached in `20_cracks.py` and `21_systematic.py`: both already wrap their lake
access in their own `@st.cache_data` functions, alongside the expensive model fits those
reads feed, so routing them through here as well would just cache the same frames twice.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st
from core import storage

# One hour, matching the ttl 20_cracks.py and 21_systematic.py already use. Every source
# in this lake refreshes daily at fastest (see infra/run_scheduled.py's cadence groups),
# so an hour is well inside a single pull cycle. The home page's own lake-status panel
# deliberately uses a much shorter ttl -- see apps/dashboard/app.py for why.
CACHE_TTL_SECONDS = 3600


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def read_ts_long(
    series_ids: list[str] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame:
    return storage.read_ts_long(series_ids=series_ids, start=start, end=end)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def read_flows(
    source: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame:
    return storage.read_flows(source=source, start=start, end=end)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def read_events(
    start: datetime | None = None,
    end: datetime | None = None,
    commodity: str | None = None,
) -> pd.DataFrame:
    return storage.read_events(start=start, end=end, commodity=commodity)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def read_sanctions_current() -> pd.DataFrame:
    return storage.read_sanctions_current()
