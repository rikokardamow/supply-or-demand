"""Pull AGSI+ daily storage history (2018-present): EU aggregate + every EU member
country, via GIEClient.get_agsi_eu_tree_history (one /api/eu call per day, EU + all
member countries nested inside — see pipelines/gie/CLAUDE.md for why this superseded
Session A's per-country-only approach)."""

from __future__ import annotations

from datetime import date

from core.storage import write_ts_long

from pipelines.gie.client import GIEClient

START = date(2018, 1, 1)


def main() -> None:
    client = GIEClient()
    df = client.get_agsi_eu_tree_history(START, date.today())
    write_ts_long(df, source="gie")
    print(f"wrote {len(df)} rows across {df['geo'].nunique()} geos")


if __name__ == "__main__":
    main()
