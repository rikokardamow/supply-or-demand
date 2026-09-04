# infra/ — scheduled pulls (Spec 13)

## The lake-on-laptop decision

This project runs on the operator's own Windows laptop, not a server. GitHub
Actions runners are ephemeral cloud VMs with no access to this machine's real
`data/` lake or `.env` secrets — mirroring every secret into GitHub Actions just
so a cloud runner could pull data, then somehow getting the resulting parquet
back onto this laptop, is real complexity for zero benefit over just running the
pull where the human analyst and the lake already live.

**Decision**: `.github/workflows/ci.yml` stays exactly as it is — CI only
(ruff/mypy/pytest against recorded cassettes, no live API calls, no real
secrets). Every scheduled *data pull* runs locally, via **Windows Task
Scheduler** (this is Windows, not Linux — no cron here).

## How it works

`infra/run_scheduled.py` is the single orchestrator. Every real pipeline
entrypoint (`pipelines/*/pull_daily.py`, `pull_weekly.py`, or a named script like
`pull_wpsr.py`) is grouped by cadence in `CADENCE_GROUPS`. Running:

```powershell
.venv\Scripts\python.exe -m infra.run_scheduled --cadence daily
```

calls every daily pipeline's own `main()` in turn, catching each one's own
exceptions so a single flaky source (GDELT's own well-documented flakiness, say)
never blocks the rest — prints a clear `OK`/`FAILED` per pipeline, and exits
non-zero if anything failed, so Task Scheduler's own "Last Run Result" column
reflects real status at a glance.

Cadences: `daily`, `wpsr` (Wed), `ng_storage` (Thu), `weekly_fri` (Fri),
`monthly` (13th & 21st).

## Registering the scheduled tasks

```powershell
.\infra\register_tasks.ps1
```

Registers 6 tasks under the `EnergyDashboard\` folder (idempotent — re-run any
time after editing the script). Verify one:

```powershell
schtasks /Query /TN EnergyDashboard\PullDaily /V /FO LIST
```

Remove one:

```powershell
schtasks /Delete /TN EnergyDashboard\PullDaily /F
```

**Known limitation**: Task Scheduler triggers on local time, and the registered
times are a UTC target translated once at registration time — they'll drift by
~1h across a DST transition. Acceptable for a solo analyst's own evening/
afternoon pull; not engineered away here. Re-run `register_tasks.ps1` after a DST
change if exact timing starts to matter.

## What's deliberately NOT scheduled

- `pipelines/opec_momr/pull_doc_crude.py` — needs a manually-provided MOMR PDF
  path (automated download 403s, confirmed live in an earlier session). Run it
  by hand when you have a fresh PDF saved under `data/raw/opec/`.
- `pipelines/news/newsapi_client.py` — Spec 16's own manual-only design (NewsAPI's
  free tier's ToS bans scheduled/production use). Triggered from page 09's own
  "Search NewsAPI" control, never from here.

See root `README.md`'s "Orchestration & scheduling" section for the short
version of this page.
