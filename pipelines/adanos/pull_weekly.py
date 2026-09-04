"""Weekly scheduled entrypoint for orchestration (Spec 13). Same reasoning as
pipelines/macro/pull_weekly.py: pull_adanos.py's own full pull is already the
right cadence (weekly, per the request-budget arithmetic in
specs/17_adanos-sentiment-overlay.md) -- this file exists only so Spec 13's
orchestration can find a consistently-named entrypoint here."""

from __future__ import annotations

from pipelines.adanos.pull_adanos import main

if __name__ == "__main__":
    main()
