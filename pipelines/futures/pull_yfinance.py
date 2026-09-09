"""Pull front-month futures closes from Yahoo Finance into the lake.

See `pipelines/futures/yfinance_front.py` for why this is `.close` and not `.settle`,
and why it is a front-month gap-filler rather than a curve source.

`--period` maps straight onto yfinance's own argument: `max` for a one-off backfill
(~26 years for CL), `1mo` for the scheduled daily run, which is a comfortable margin over
a long weekend while keeping the request small. Re-running is idempotent -- `write_ts_long`
dedups on `(series_id, ts)` keeping the latest `revision_date`, so an overlapping window
refreshes rows rather than duplicating them.
"""

from __future__ import annotations

import argparse
from datetime import UTC

import yfinance as yf
from core.failures import failure_scope, record_failure
from core.publish import publish
from core.storage import read_ts_long, write_ts_long

from pipelines.futures.yfinance_front import SOURCE, YAHOO_FUTURES, history_to_ts_long

DEFAULT_PERIOD = "1mo"


def main(period: str = DEFAULT_PERIOD) -> None:
    total = 0
    # One flaky symbol must not cost the other four, but a run where every symbol failed
    # has to exit non-zero rather than report success -- core/failures.py's own rule.
    with failure_scope("yfinance front month"):
        for future in YAHOO_FUTURES:
            try:
                history = yf.Ticker(future.symbol).history(period=period, auto_adjust=False)
                rows = history_to_ts_long(history, future)
                if rows.empty:
                    # Yahoo answering with nothing is a real failure, not an empty
                    # market: these are the most heavily traded futures in the world.
                    raise ValueError(f"{future.symbol}: no rows returned for period={period!r}")
                write_ts_long(rows, source=SOURCE)
                total += len(rows)
                print(f"{future.symbol} -> {rows['series_id'].iloc[0]}: {len(rows)} rows")
            except Exception as exc:
                record_failure(future.symbol, exc)

    print(f"wrote {total} yfinance front-month rows across {len(YAHOO_FUTURES)} roots")

    # Publish the whole lake history, not `total` -- the scheduled run only pulls a
    # trailing month, and publishing that alone would leave serving.series_long holding
    # a month of prices with no history behind them (the same trap pipelines/gie's
    # publish avoids by reading the lake). Spec 32 §2: as_of is the data's own latest
    # timestamp, never wall-clock, so a Yahoo outage shows up as a stale panel.
    history = read_ts_long(source=SOURCE)
    if history.empty:
        raise RuntimeError(f"read 0 rows for source={SOURCE!r} after writing {total}")

    published = publish(
        "series_long",
        history,
        as_of=history["ts"].max().to_pydatetime().replace(tzinfo=UTC),
        source_note=(
            "Yahoo Finance continuous front-month daily closes"
            " (not exchange settlements -- see pipelines/futures/yfinance_front.py)"
        ),
        key=["series_id", "ts"],
        pipeline=SOURCE,
    )
    print(f"published {published} yfinance rows to the serving layer")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--period",
        default=DEFAULT_PERIOD,
        help="yfinance period, e.g. 1mo (default, scheduled runs) or max (backfill)",
    )
    main(parser.parse_args().period)
