"""Entrypoint: UK monthly gas balance and trade from DESNZ Energy Trends into the lake.

    python -m pipelines.desnz_gas.pull

Writes ``ts_long`` under ``source="desnz"``, monthly, ``geo="GB"``, in mcm:

- ``desnz.gas.balance.<line>.gb``: ET 4.2 lines, named in ``client.BALANCE_COLUMNS``.
  ``stock_change`` is positive for a WITHDRAWAL from storage, which is the opposite of
  Eurostat's ``stk_chg_mg``.
- ``desnz.gas.<imports|exports|net>.<type>.<country>.<pipeline>.gb``: ET 4.3 flat rows,
  slugged (``imports.pipeline.norway.langeled_to_easington``). Totals are kept.
- ``desnz.gas.provisional.gb``: 1 for each month DESNZ marks provisional.

Full history every run: DESNZ revises the latest quarters.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pandas as pd
import requests
from core.failures import fails_loudly, record_failure
from core.storage import write_ts_long

from pipelines.desnz_gas.client import DesnzGasClient, parse_monthly_balance, parse_trade

SOURCE = "desnz"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "na"


def _ts_long(ids: pd.Series, frame: pd.DataFrame, unit: str, at: pd.Timestamp) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": ids,
            "source": SOURCE,
            "ts": frame["ts"],
            "value": frame["value"].astype("float64"),
            "unit": unit,
            "geo": "GB",
            "freq": "M",
            "revision_date": at,
        }
    )


def balance_rows(balance: pd.DataFrame, at: pd.Timestamp) -> pd.DataFrame:
    values = _ts_long("desnz.gas.balance." + balance["line"] + ".gb", balance, "mcm", at)
    months = balance.loc[balance["provisional"], ["ts"]].drop_duplicates().assign(value=1.0)
    flags = _ts_long(pd.Series("desnz.gas.provisional.gb", index=months.index), months, "flag", at)
    return pd.concat([values, flags], ignore_index=True)


def trade_rows(trade: pd.DataFrame, at: pd.Timestamp) -> pd.DataFrame:
    ids = (
        "desnz.gas."
        + trade["flow"]
        + "."
        + trade["type"].map(slug)
        + "."
        + trade["country"].map(slug)
        + "."
        + trade["pipeline"].map(slug)
        + ".gb"
    )
    return _ts_long(ids, trade, "mcm", at)


@fails_loudly("desnz")
def main() -> None:
    client = DesnzGasClient()
    at = pd.Timestamp(datetime.now(UTC)).tz_localize(None)
    try:
        links = client.links()
    except (requests.RequestException, ValueError) as exc:
        record_failure("desnz links", exc)
        return

    frames = []
    for table, parse, to_rows in (
        ("4.2", parse_monthly_balance, balance_rows),
        ("4.3", parse_trade, trade_rows),
    ):
        try:
            frames.append(to_rows(parse(client.workbook(links[table])), at))
        except (requests.RequestException, ValueError, KeyError, StopIteration) as exc:
            record_failure(f"desnz ET {table}", exc)

    frames = [f for f in frames if not f.empty]
    if not frames:
        record_failure("desnz", RuntimeError("no table returned any row"))
        return
    rows = pd.concat(frames, ignore_index=True)
    write_ts_long(rows, source=SOURCE)
    print(
        f"desnz: wrote {len(rows)} rows across {rows['series_id'].nunique()} series, "
        f"{rows['ts'].min():%Y-%m} to {rows['ts'].max():%Y-%m} "
        f"({', '.join(sorted(links))} from {links['4.2'].rsplit('/', 1)[-1]})",
        flush=True,
    )


if __name__ == "__main__":
    main()
