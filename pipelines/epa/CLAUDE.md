# pipelines/epa — Claude Code Guide

First EPA package in the repo. It holds two hand-maintained reference tables of published
Renewable Fuel Standard figures and their loaders (`reference.py`). Not a feed: the CSVs
change when EPA publishes or revises a rule, not on a clock, so nothing here is scheduled.

- **EMTS is deliberately absent.** Its pages serve JavaScript tables and the route shape was
  unconfirmed as of 2026-10-10. Do not guess a scrape; confirm the route first.
- **Every row has `status` (`final` or `proposed`), `source` and `as_of`.** Use the final
  rule where one exists and say so in `source`. A figure with no opened public source is left
  out, never estimated; the gaps are listed in `reference.py`'s docstring.
- `pct` is a fraction (0.155, not 15.5). The loaders refuse anything outside [0, 1].
- Never copy a figure from the licensed RIN workbook or from memory.
- As of 2026-10-10 EPA has finalised 2026 and 2027 (rule of 1 Apr 2026), so no row is
  currently `proposed`. The brief's expectation that those years are proposed was out of date.
