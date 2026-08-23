# Spec 13 — Orchestration, Testing Hardening & CI/CD

**Weeks 19–20 · Est. 10 h · Prereq: all pipelines you intend to automate.**

## Objective
Every pipeline runs itself on the release calendar; failures are visible within a day; CI blocks
regressions; the dashboard always states data freshness. Keep it boring: **GitHub Actions cron +
local scheduler for AIS — no Prefect until this demonstrably breaks.**

## Scheduled workflows (`.github/workflows/`)
All jobs: checkout → uv sync → run entrypoint → commit/push lake deltas OR upload to storage
(decide in Session A: simplest = lake lives on your machine and Actions only run CI; pragmatic
alternative = a `data` branch or object storage. If lake-on-laptop, scheduled pulls run on the
laptop via cron and Actions do CI only — choose and document).
- `pull_daily.yml` — 19:45 UTC: GIE, ENTSOG, ENTSO-E, weather (+maps), news, flights hourly handled locally.
- `pull_wpsr.yml` — Wed 15:45 UTC (EIA WPSR after 10:30 ET; holiday-shift note in run log).
- `pull_ng_storage.yml` — Thu 15:45 UTC (EIA gas storage).
- `pull_weekly_fri.yml` — Fri 19:00 UTC (Baker Hughes; CFTC COT stretch).
- `pull_monthly.yml` — 13th & 21st 09:00 UTC (MOMR attempt with retry-next-day; JODI).
- `ci.yml` — push/PR: ruff, mypy, pytest (cassettes only).
Secrets via GitHub Actions secrets mirroring `.env` names — never echoed.

## Freshness & failure visibility
- `core/freshness.py`: expected-cadence table per source; `staleness_report()` → DuckDB.
- Home page: freshness table with green/amber/red vs expected cadence.
- Failure alert: workflow-failure → GitHub notification is enough; stretch = ntfy.sh push.

## Testing hardening
- Cassette coverage audit: every client has ≥1 cassette; keys/tokens filtered (assert in a meta-test scanning cassettes for secret-shaped strings).
- Transform test audit: cracks, HDD/CDD, seasonal-excl-2020, transit/storage synthetic tracks, dedup — all hand-checked values.
- Schema drift guards: every pipeline validates against `core.schemas` before writing; a failing
  validation writes nothing and exits non-zero.
- Smoke test: `tests/test_pages_import.py` imports every dashboard page headlessly.

## Sessions

### Session A (weekend, 3 h) — scheduler decision + workflows
> Read NOTES.md, specs/13_orchestration-tests.md. Decide and document lake location strategy
> (laptop-cron vs Actions-writes). Implement all workflow files + local crontab file
> `infra/crontab.example` for anything running on the laptop (AIS ingester supervision, hourly
> flights, daily pulls if laptop-strategy). Acceptance: one scheduled workflow triggered manually
> end-to-end.

### Session B (weekend, 3 h) — freshness + audits
> core/freshness.py + home-page table; cassette secret-scan meta-test; pages smoke test;
> fix every gap the audits reveal.

### Session C (weekday, 1 h) — docs
> Rewrite README.md: what this is, architecture diagram, how to run, how to add a pipeline,
> data-source credits/licences table (CC-BY for ECMWF, non-commercial note for Open-Meteo,
> GDELT/Guardian attribution), and the key-rotation policy.

### Session D (weekday, 1 h) — release
> Version sweep, tag v1.0, write `CHANGELOG.md`. Open issues for every stretch item you skipped —
> the backlog is the v1.1 plan.

## Definition of Done
- All pulls scheduled and observed green across one full week; freshness table live; audits pass;
- README + licence credits complete; v1.0 tagged.

## Post-v1.0 backlog seeds
- Prefect migration trigger: >2 silent pipeline failures in a month.
- VPS move for AIS + daily pulls. — TTF/EUA additions. — Event-study module. — Kardamow chart-export
  helper (PNG at publication size with source footers) for Substack/X posts.
