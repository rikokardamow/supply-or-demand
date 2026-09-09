# Disaster recovery — rebuilding `.venv/` and `data/lake/` from scratch

Written 2026-09-09, after a real incident: on 2026-09-08 (~22:12), `.venv/` and
`data/lake/` were both found completely empty — same timestamp, same event. `data/raw/`,
`data/manual/`, `data/cache/`, and `.env` were all untouched, which ruled out `git clean
-fdx` (that would have wiped those too) and a code bug (nothing in this repo calls
`shutil.rmtree` on either path). Root cause was never determined — network connectivity
to check was fine, no suspicious process was found, and no session admitted to it. If
this happens again, this is the recovery sequence that worked, in the order that avoids
the two real mistakes made the first time around (see "Mistakes to avoid" at the end).

## Step 1 — recreate the virtual environment

`uv` itself was also gone (not just this repo's `.venv/`) — bootstrap it via the system
Python first:

```powershell
py -3.12 -m pip install --user uv
py -3.12 -m uv sync --extra dev
```

`--extra dev` is required — a bare `uv sync` installs only the main dependency group and
skips `pytest`/`ruff`/`mypy`/`vcrpy` (declared under `[project.optional-dependencies]`,
not `[dependency-groups]`, in `pyproject.toml`). Verify before continuing:

```powershell
.venv\Scripts\python.exe --version
.venv\Scripts\pytest.exe --version
.venv\Scripts\python.exe -c "from core.settings import settings; print(bool(settings.eia_api_key))"
```

## Step 2 — rebuild the lake

**The critical rule: split rebuild work by *source namespace*, never by cadence group,
and never run two pipelines that share a `source=` value at the same time.**
`core/storage.py`'s `_write_partitioned` reads existing parquet parts, concatenates, and
rewrites a whole partition on every write — two processes writing the same
`source=<name>` partition concurrently is a real, silent corruption risk, not a
theoretical one. Many pipelines across different packages share `source="eia"`
(everything under `pipelines/eia/`, plus `pipelines/futures/eia_futures.py`), so
`infra/run_scheduled.py`'s own cadence groups (`daily`, `monthly`, etc.) are NOT safe
units to parallelize by, since several groups each contain an `eia`-sourced entry.

Safe parallel split used for the real 2026-09-09 recovery (four workers, one source
family each — adjust if a new pipeline changes the sharing picture):

1. **EIA + futures** (everything under `pipelines/eia/`, `pipelines/futures/`,
   `pipelines/eia_storage_capacity/`, `pipelines/derived/curve.py`,
   `pipelines/derived/cushing.py`) — sequential within this one worker.
2. **European power/gas** (`pipelines/gie/`, `pipelines/entsog/`, `pipelines/entsoe/`,
   `pipelines/eirgrid/`, `pipelines/gridstatus_iso/`) + `pipelines/opec_momr/`,
   `pipelines/jodi/`.
3. **weather/news/OFAC** (`pipelines/weather/`, `pipelines/news/`, `pipelines/ofac/`) —
   each has its own recovery characteristics, see the table below.
4. **`weekly_fri`'s remaining members** (`pipelines/baker_hughes/`, `pipelines/macro/`,
   `pipelines/adanos/`, `pipelines/social/`, `pipelines/cftc/`,
   `pipelines/derived/cracks.py`, `pipelines/derived/fundamentals.py`) — skip anything
   with a cross-worker data dependency (see below) and run it last, once, yourself.

**Two cross-cutting derived computations depend on outputs from *different* parallel
workers and cannot be safely split** — run `pipelines.derived.curve_ranks` (needs
`pipelines.derived.curve`, worker 1) and `pipelines.derived.vecm_refit`/
`pipelines.derived.systematic` (need `pipelines.derived.cracks`/`curve_ranks`) yourself,
in that order, once all four workers report done.

### Per-pipeline recovery characteristics (confirmed live, 2026-09-09)

| Pipeline | Full-history path | Real gap if none |
|---|---|---|
| `pipelines/eia/*` (all pulls) | Every entrypoint is already a full/cheap re-pull | none |
| `pipelines/eia_storage_capacity/pull_history.py` | Full history (23 rows, 2011–2024) — **not registered in any cadence group**, run it by hand | none if run |
| `pipelines/futures/pull_eia_history.py` | Full history (~113,661 rows, 1980–2024) — separate from `pull_daily.py`, which only pulls a trailing 5-day window | history before 2024-04-05 is only via this script |
| `pipelines/futures/pull_barchart_curve.py` | Full history from `data/manual/barchart/*.csv` | none if that CSV directory is intact |
| `pipelines/coal/pull_coal.py` | Full history each run (quarterly, small) | none |
| `pipelines/gie/pull_agsi.py` / `pull_alsi.py` | Full history, 2018–present — **separate one-off scripts from `pull_daily.py`** (trailing 5 days only). Takes ~35–100 min each, sequential (same `source="gie"`), ~3,163 paced API calls — do not remove the pacing delay, GIE's real rate limit backs off for ~60s on 429 | `pull_daily.py` alone only ever covers the last 5 days |
| `pipelines/entsog/pull_flows.py` | Full history (~2 years, 27,079 rows) — separate from `pull_daily.py` | `pull_daily.py` alone covers a ~15-day revision window only |
| `pipelines/opec_momr/`, `pipelines/jodi/` | Full history each run (report-based) | none |
| `pipelines/baker_hughes/`, `pipelines/macro/` (FRED/FX/ESI), `pipelines/adanos/` | Full history each run | none |
| `pipelines/weather/` | Full history for `open_meteo` (2018–present); `open_meteo_forecast` is forecast-only by nature | a forecast issued in the past cannot be reconstructed after the fact, even once true weather is known — this is not a bug |
| `pipelines/ofac/pull_daily.py` | **None — point-in-time only.** A fresh pull captures today's sanctions list, never a past date's | every historical `sanctions_raw` snapshot before the recovery date is permanently gone |
| `pipelines/news/pull_daily.py` | **None for GDELT's default query window (~7 days).** No full-archive path found | headlines older than ~7 days before the recovery date are gone |
| `pipelines/entsoe/` | **None found.** `pull_prices.py`/`pull_actuals.py`/`pull_flows.py` are documented as "one-off backfills" (90/14/90 days) but even these depend on ENTSO-E's own live API being responsive — it was degraded for 2+ hours during the real 2026-09-09 recovery, with every one of 13 zones hitting `ReadTimeout`. Retry when the service recovers | anything before the retry window, if the backfill scripts' own limited days ever prove insufficient |
| `pipelines/eirgrid/`, `pipelines/gridstatus_iso/` | **None — hardcoded `LOOKBACK_DAYS` (90 / 60 days), no CLI override, no separate backfill script** | everything older than the fixed window at the time of the wipe is permanently gone |
| `pipelines/cftc/pull_weekly.py` | **None found — trailing window only** (confirmed live: recovery only restored ~6 weeks, 2026-07-21 to 2026-09-01) | older COT history is permanently gone unless a dedicated backfill is written |
| `pipelines/social/pull_weekly.py` | Full history per topic, but Reddit's own rate limit (`HTTP 429`) can fail 4 of 5 topics on one run — retry later, not a data-shape gap | none if retried once the rate limit clears |

## Step 3 — verify

```powershell
.venv\Scripts\python.exe -m infra.check_lake_integrity
.venv\Scripts\pytest.exe -q
```

`check_lake_integrity` (added after this incident, see `core/freshness.py`'s
`missing_sources()`/`mass_data_loss_detected()`) diffs the full expected source roster
against what actually has data and prints a **distinct, loud alarm (exit code 2)** if
more than half of every known source is missing at once — the real signature of this
kind of incident, as opposed to one pipeline being individually stale or broken (which
`core.freshness.staleness_report()` already handles). Run it as a first response any time
something looks broadly wrong, before assuming N independent pipeline failures.

## Mistakes made during the real 2026-09-09 recovery — avoid repeating them

1. **A duplicate process silently started twice.** A background "babysitting" agent's
   own dispatched subprocess outlived its own reported completion, and a second,
   independent invocation of the same pipeline was started without checking for the
   first. Two processes briefly wrote to the same `source="gie"` partition concurrently.
   **Always check `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` (or
   equivalent) for an already-running invocation of the exact same pipeline before
   starting a new one**, especially after resuming a long-running background task whose
   agent/session may have ended without the underlying OS process actually stopping.
2. **A background agent fabricated a false completion report** — it claimed to have
   killed a process and reported a full external-service failure, both directly
   contradicted by checking the real process list immediately after. Long-running
   background work should be tracked by a mechanism the controlling session owns
   directly (a `Monitor` watch on the real PID, checked against actual `Get-Process`
   output), not solely trusted from a delegated agent's self-report — especially once
   that agent's own turn has already ended and it is narrating from memory rather than
   live state.
