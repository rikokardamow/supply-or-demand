"""Moving averages over the front-month closes, written to the lake and published.

Computed in Python and stored as real series rather than drawn in the browser: Spec 32 §1
keeps every derived number the UI shows on this side, so a chart and an article quoting it
cannot disagree, and so the figure is reproducible from the lake alone.

Series ids follow the lake's `derived.<topic>.<subject>.<detail>` convention, e.g.
`derived.ma.cl.50` -- the 50-session simple moving average of `fut.cl.f01.close`. Windows
are in *observations*, not calendar days: futures do not trade at weekends, and a
"200-day" average that counted calendar days would silently span ten months.

Also publishes a seasonal band per ticker, so a price panel can show the same
range/median exhibit the storage panels use.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import pandas as pd
from core.failures import failure_scope, record_failure
from core.indicators import MA_WINDOWS, moving_average
from core.publish import publish, seasonal_frame
from core.storage import read_ts_long, write_ts_long

from pipelines.futures.yfinance_front import YAHOO_FUTURES
from pipelines.futures.yfinance_front import series_id as close_series_id

SOURCE: Final = "derived"


def ma_series_id(root: str, window: int) -> str:
    return f"derived.ma.{root}.{window}"


def moving_average_rows(closes: pd.DataFrame, root: str) -> pd.DataFrame:
    """`ts_long` rows for every window in `MA_WINDOWS`, for one root.

    Rows where the window is not yet full are dropped rather than written as null: the
    lake's own convention is that an absent observation is absent, not a null row, and
    `write_ts_long` drops no-value rows anyway.
    """
    ordered = closes.sort_values("ts")
    frames: list[pd.DataFrame] = []

    for window in MA_WINDOWS:
        values = moving_average(ordered["value"], window)
        frame = pd.DataFrame(
            {
                "series_id": ma_series_id(root, window),
                "source": SOURCE,
                "ts": ordered["ts"].to_numpy(),
                "value": values.to_numpy(),
                "unit": ordered["unit"].iloc[0] if len(ordered) else None,
                "geo": ordered["geo"].iloc[0] if len(ordered) else None,
                "freq": "D",
                "revision_date": datetime.now(UTC).replace(tzinfo=None),
            }
        ).dropna(subset=["value"])
        if not frame.empty:
            frames.append(frame)

    if not frames:
        return pd.DataFrame(
            columns=["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]
        )
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    closes = read_ts_long(source="yfinance")
    if closes.empty:
        raise RuntimeError(
            "no yfinance closes in the lake -- run pipelines.futures.pull_yfinance first"
        )

    written = 0
    with failure_scope("moving averages"):
        for future in YAHOO_FUTURES:
            try:
                one = closes[closes["series_id"] == close_series_id(future.root)]
                if one.empty:
                    raise ValueError(f"{future.root}: no close series in the lake")
                rows = moving_average_rows(one, future.root)
                if rows.empty:
                    # Every window empty means under 50 observations, which for a series
                    # with 20+ years of history means something is wrong upstream.
                    raise ValueError(f"{future.root}: not enough history for any window")
                write_ts_long(rows, source=SOURCE)
                written += len(rows)
                print(f"{future.root}: {len(rows)} moving-average rows")
            except Exception as exc:
                record_failure(future.root, exc)

    print(f"wrote {written} moving-average rows")

    # Publish the closes' own seasonal bands alongside, so a price panel can show the
    # same range/median exhibit the storage panels use.
    bands = seasonal_frame(closes)
    as_of = closes["ts"].max().to_pydatetime().replace(tzinfo=UTC)
    published = publish(
        "seasonal",
        bands,
        as_of=as_of,
        source_note="Front-month close seasonal bands, 2020 excluded",
        key=["series_id", "doy"],
        pipeline="yfinance",
    )
    print(f"published {published} seasonal rows for {bands['series_id'].nunique()} tickers")


if __name__ == "__main__":
    main()
