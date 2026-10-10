"""Ingests the EIA Short-Term Energy Outlook into the lake, labelled.

Writes `steo.<code>.observed` and `steo.<code>.projected` under `source="eia_steo"`. The split
is not cosmetic: STEO is an 18-month model outlook with no per-row forecast flag, so without
it the lake cannot distinguish EIA's projection of 2027 gasoline demand from a measurement of
2026's. See pipelines/eia/steo_boundary.py.

Stale-label residue: when a later release moves the boundary forward, a month first written as
`.projected` is rewritten as `.observed`, but the old `.projected` row stays, because
`write_ts_long` only merges and the lake has no delete path. Readers must prefer `.observed`
wherever a month exists under both ids.

Not scheduled. STEO releases monthly; run this by hand after a release."""

from __future__ import annotations

from core.failures import failure_scope, record_failure
from core.storage import write_ts_long

from pipelines.eia.client import EIAClient
from pipelines.eia.steo_boundary import history_end, split_observed_projected
from pipelines.eia.steo_series import STEO_SERIES, lake_series_id

SOURCE = "eia_steo"


def main() -> None:
    with failure_scope("eia.pull_steo"):
        client = EIAClient()

        # Boundary first: if it cannot be established there is nothing safe to write.
        boundary = history_end(client)
        print(f"steo: history ends {boundary.date()}; later periods are model output", flush=True)

        raw = client.get_steo_series(list(STEO_SERIES), "monthly")
        if raw.empty:
            # Recorded inside the scope, so the run exits non-zero and nothing is written.
            record_failure(SOURCE, RuntimeError("steo returned no rows"))
            return

        # Fail loudly rather than drop: a NaT period would compare False against the
        # boundary and be labelled `.projected`, and a silently shrunken pull is exactly
        # what this pipeline must not produce.
        if raw["ts"].isna().any():
            raise ValueError(f"steo: {int(raw['ts'].isna().sum())} row(s) have no period (NaT)")

        raw = raw.copy()
        raw["series_id"] = raw["series_id"].map(lake_series_id)
        labelled = split_observed_projected(raw, boundary)

        write_ts_long(labelled, source=SOURCE)

        counts = labelled["series_id"].str.rsplit(".", n=1).str[-1].value_counts()
        print(
            f"steo: wrote {len(labelled)} rows across {labelled['series_id'].nunique()} series "
            f"({int(counts.get('observed', 0))} observed, "
            f"{int(counts.get('projected', 0))} projected)",
            flush=True,
        )


if __name__ == "__main__":
    main()
