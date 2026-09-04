"""Daily scheduled entrypoint for orchestration (Spec 13). OFAC publishes a fresh
full snapshot on each pull (not deltas), and pull_ofac.py's own diff logic is
already idempotent/daily-safe -- this file exists only so Spec 13 can find a
consistently-named pull_daily.py here, matching pipelines/news|weather|entsoe's own
convention."""

from __future__ import annotations

from pipelines.ofac.pull_ofac import main

if __name__ == "__main__":
    main()
