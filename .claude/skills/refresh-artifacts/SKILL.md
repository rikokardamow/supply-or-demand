---
name: refresh-artifacts
description: Refresh the published energy pages and Office exports end to end - run the pipelines against the local lake, rebuild the JSON and HTML, republish every page listed in artifacts.md to its existing URL, rebuild the Excel and PowerPoint files, and report what changed and what failed. Use when asked to refresh, rebuild, update or republish the dashboard, briefing, motion page or the kardamow exports.
---

# Refresh artifacts

Run from the repo root of the checkout that holds `data/lake/` and `.env`. Work through
the steps in order and keep going when one pipeline fails: a failed source becomes a
stale flag on the page, not a reason to stop.

## Guardrails

- Local lake only. Never write to Supabase or any remote database: every pipeline run
  below sets `SUPABASE_DB_URL` to empty, which makes `core.publish.publish` skip.
- Never print, log or commit `.env` values. Do not echo the environment.
- Do not change pipeline code to make a chart work. Report the gap instead.
- Do not re-enable scheduled tasks, workflows or deploys.
- Republish to the URLs in `artifacts.md`. Never create a new page, never change sharing.
- No pushes. Commit only if asked.

## 1. Record the starting point

Check for other sessions working in this repo (ListAgents) and tell them a lake refresh
is starting. Two series families are not produced by any scheduled pipeline and must
survive the run, so count them now and again after step 2:

```
.venv/Scripts/python.exe -c "from core.storage import read_ts_long as r; print(len(r(source='opec_momr', series_prefix='momr.doc_crude_secondary.')), len(r(source='derived', series_prefix='derived.hormuz.scenario.')))"
```

If either count drops, say so in the report; they are restored with
`python -m pipelines.opec_momr.pull_doc_crude <MOMR pdf>` and
`python -m pipelines.derived.hormuz`.

## 2. Run the pipelines

One cadence at a time, in this order (derived series read what earlier groups wrote):

```
for c in wpsr ng_storage daily monthly weekly_fri; do
  SUPABASE_DB_URL= .venv/Scripts/python.exe -m infra.run_scheduled --cadence "$c"
done
```

`weekly_fri` takes about an hour (Reddit is throttled to one request a minute); run it in
the background and carry on once the other four have finished if time is short. Each
cadence prints `name: OK` or `name: FAILED (reason)` per pipeline and a summary line.
Collect every FAILED line for the report. A non-zero exit from one cadence is expected
when a single source fails; continue with the next.

## 3. Rebuild

```
.venv/Scripts/python.exe -m apps.artifacts.build
```

This writes `apps/artifacts/dist/{dashboard,briefing,motion}.{json,html}`,
`exports/kardamow_data.xlsx` and `exports/kardamow_briefing.pptx`, and prints one
`changed:` line per page or exhibit whose data moved and one `issue:` line per data
problem it found. If it exits non-zero for any reason - a credential value in an
output, a page over 4 MiB, a crash, a traceback - it deletes everything it wrote. Stop
and report; do not republish or hand over any file from a failed build.

## 4. Republish

For each row of the "Artifact pages" table in `artifacts.md`: read the artifact at its
URL (Artifact tool, `action: "read"`), then publish the built file from the same row
with that `url`. Skip a page whose `changed:` line did not appear only if nothing else
about it changed. Add a row to the "Publish log" table in `artifacts.md`.

## 5. Report

Give the user, in this order:

1. The three artifact URLs and the two export paths.
2. **What changed** - the build's `changed:` lines, as plain sentences with the new
   data-through dates.
3. **What failed** - every pipeline FAILED line with its reason, every `issue:` line,
   and any exhibit still carrying a `No data since` flag after the refresh.
4. The before and after counts from step 1.
