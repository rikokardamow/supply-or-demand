"""Daily incremental entrypoint for orchestration (Spec 13): re-pulls only the trailing
window (both AGSI and ALSI, EU + all countries), not the full 2018-present history.

GIE revises a gas-day's figures for a few days after publication (see
pipelines/gie/CLAUDE.md's revision_date note — updatedAt is a real per-row revision
timestamp). Re-fetching the trailing days on every run and relying on write_ts_long's
revision-based de-dup (keeps the row with the latest revision_date per series_id+ts) is
how those late revisions get picked up without a full re-pull."""

from __future__ import annotations

from datetime import date, timedelta

from core.storage import write_ts_long

from pipelines.gie.client import GIEClient

TRAILING_DAYS = 5


def main() -> None:
    client = GIEClient()
    end = date.today()
    start = end - timedelta(days=TRAILING_DAYS - 1)

    agsi_df = client.get_agsi_eu_tree_history(start, end)
    write_ts_long(agsi_df, source="gie")
    print(f"AGSI: wrote {len(agsi_df)} rows across {agsi_df['geo'].nunique()} geos")

    alsi_df = client.get_alsi_eu_tree_history(start, end)
    write_ts_long(alsi_df, source="gie")
    print(f"ALSI: wrote {len(alsi_df)} rows across {alsi_df['geo'].nunique()} geos")


if __name__ == "__main__":
    main()
