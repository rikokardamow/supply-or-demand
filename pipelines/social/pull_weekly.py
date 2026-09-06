"""Thin re-export so infra/run_scheduled.py's cadence groups can address this
pipeline by the same pull_<cadence> convention every other pipeline uses (the
precedent is pipelines/macro/pull_weekly.py and pipelines/adanos/pull_weekly.py)."""

from __future__ import annotations

from pipelines.social.pull_social import main

if __name__ == "__main__":
    main()
