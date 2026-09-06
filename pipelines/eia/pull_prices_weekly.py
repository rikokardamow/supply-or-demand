"""Thin re-export so infra/run_scheduled.py can address the weekly cadence by the same
pull_<cadence> convention every other pipeline uses -- the precedent is
pipelines/adanos/pull_weekly.py."""

from __future__ import annotations

from pipelines.eia.pull_prices import main_weekly as main

__all__ = ["main"]
