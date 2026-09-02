"""Weekly scheduled entrypoint for orchestration (Spec 13), per the spec's own
Session C scope. pull_macro.py's own full-history pulls are already cheap and
idempotent (the largest series, DGS10, is ~16,870 points -- confirmed live a full
re-pull completes in well under a minute per source), so there's no separate
narrower-window entrypoint needed -- this file exists only so Spec 13 can find a
consistently-named pull_weekly.py here, matching pipelines/news/pull_daily.py's
identical reasoning for its own daily cadence."""

from __future__ import annotations

from pipelines.macro.pull_macro import main

if __name__ == "__main__":
    main()
