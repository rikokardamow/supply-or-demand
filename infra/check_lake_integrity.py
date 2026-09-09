"""Early-warning check for a whole-lake wipe (Spec 13 follow-up, 2026-09-09).

Prompted by a real incident: on 2026-09-08, `data/lake/` and `.venv/` were both
emptied by an out-of-band event (cause never determined -- ruled out `git clean`,
a code bug, and a network outage). Nothing in this project would have noticed until
a dashboard page broke, hours or days later. `core.freshness.staleness_report()`
already tracks per-source staleness, but a source with zero rows anywhere never
appears in that report at all -- it looks identical to "never configured", not
"just lost everything". This script diffs the full expected roster
(`core.freshness.EXPECTED_CADENCE_DAYS`) against what's actually present and raises
a loud, distinct alarm when a large fraction vanish at once, rather than treating it
as N unrelated single-pipeline staleness issues.

Run manually (`.venv/Scripts/python.exe -m infra.check_lake_integrity`) or wire into
a scheduled task alongside `infra/run_scheduled.py` -- exit code 2 is reserved for
this specific alarm so it can be distinguished from a normal pipeline failure (exit 1)
or a clean run (exit 0)."""

from __future__ import annotations

import sys

from core.freshness import mass_data_loss_detected, missing_sources


def main() -> int:
    missing = missing_sources()
    if mass_data_loss_detected():
        print(
            "MASS DATA LOSS suspected: "
            f"{len(missing)} of every known source have zero rows in the lake at once "
            f"-- {sorted(missing)}. This is the signature of a whole-lake wipe, not "
            "independent pipeline failures. Check data/lake/ and .venv/ directly "
            "before assuming this is N separate broken pipelines.",
            flush=True,
        )
        return 2
    if missing:
        print(f"OK -- {len(missing)} source(s) missing (normal): {sorted(missing)}", flush=True)
    else:
        print("OK -- every expected source has data.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
