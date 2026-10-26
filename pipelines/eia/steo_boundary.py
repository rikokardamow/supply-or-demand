"""Where STEO's measured history ends and its 18-month model output begins.

STEO rows carry no forecast flag, the route metadata carries no vintage, and the only hint
anywhere is the route description's "Monthly short term (18 month) projections". Writing the
series unlabelled would put EIA's model output into the lake wearing the same clothes as
measured history -- and 2027-12 gasoline demand is not an observation.

The boundary is therefore read from a different, authoritative EIA route: the monthly
supply-and-disposition actuals. Confirmed live 2026-10-10: `MGFUPUS1`'s last monthly period
was 2026-07, so STEO 2026-08 onward is model output.

Deliberately NOT derived from today's date (the STEO vintage lags the calendar by a variable
amount) and NOT from the STEO series maximum (that is the forecast horizon, the opposite end).
"""

from __future__ import annotations

import pandas as pd

from pipelines.eia.client import EIAClient

ACTUALS_ROUTE = "petroleum/sum/snd"
ACTUALS_SERIES = "MGFUPUS1"
"""US Product Supplied of Finished Motor Gasoline, monthly, MBBL. Gasoline is the right
bellwether: it is the largest RFS denominator component and EIA publishes it on the same
monthly cadence as every other product in this pull."""


def history_end(client: EIAClient) -> pd.Timestamp:
    """Last month for which EIA publishes a measured value. Raises if the route returns
    nothing -- a boundary that cannot be established must stop the pull, not be guessed."""
    actuals = client.get_series(ACTUALS_ROUTE, [ACTUALS_SERIES], "monthly")
    if actuals.empty:
        raise ValueError(
            f"{ACTUALS_ROUTE}/{ACTUALS_SERIES} returned no rows, so STEO's history boundary "
            "cannot be established; refusing to label model output as observed"
        )
    boundary = pd.Timestamp(actuals["ts"].max())
    if pd.isna(boundary):
        raise ValueError(
            f"{ACTUALS_ROUTE}/{ACTUALS_SERIES} returned no usable period, so STEO's history "
            "boundary cannot be established; refusing to label model output as observed"
        )
    return boundary


def split_observed_projected(df: pd.DataFrame, boundary: pd.Timestamp) -> pd.DataFrame:
    """Suffixes every `series_id` with `.observed` or `.projected`. Every row gets one or the
    other; there is no unlabelled path out of this function."""
    if not isinstance(boundary, pd.Timestamp) or pd.isna(boundary):
        raise ValueError(
            f"boundary must be a real Timestamp, got {boundary!r} -- defaulting it "
            "would relabel EIA's model output as measured history"
        )
    out = df.copy()
    suffix = out["ts"].le(boundary).map({True: ".observed", False: ".projected"})
    out["series_id"] = out["series_id"].astype(str) + suffix
    return out
