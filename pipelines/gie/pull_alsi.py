"""Pull ALSI+ daily LNG history (2018-present): EU aggregate + every LNG-terminal
country, via GIEClient.get_alsi_eu_tree_history. Landlocked countries (e.g. Austria)
have no LNG data and are silently skipped (all fields are "-")."""

from __future__ import annotations

from datetime import date

from core.storage import write_ts_long

from pipelines.gie.client import GIEClient

START = date(2018, 1, 1)


def main() -> None:
    client = GIEClient()
    df = client.get_alsi_eu_tree_history(START, date.today())
    write_ts_long(df, source="gie")
    print(f"wrote {len(df)} rows across {df['geo'].nunique()} geos")


if __name__ == "__main__":
    main()
