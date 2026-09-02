"""Daily scheduled entrypoint for orchestration (Spec 13). Unlike
pipelines/weather|entsoe|entsog's own pull_daily.py, there's no separate
backfill-vs-daily distinction needed here: pull_news.py's GDELT/Guardian queries are
already windowed to the last 7 days each (per-query `timespan`), so pull_news.py is
already exactly the daily-safe, idempotent pull Spec 13's scheduler needs. This file
exists only so Spec 13 can find a consistently-named pull_daily.py in every pipeline
directory, matching pipelines/weather|entsoe|entsog's own convention."""

from __future__ import annotations

from pipelines.news.pull_news import main

if __name__ == "__main__":
    main()
