---
description: Scaffold a new Streamlit dashboard page under apps/dashboard/pages/
---

Scaffold a new dashboard page: $ARGUMENTS

Read `CLAUDE.md` and the relevant spec under `specs/` before writing anything. Follow the
pattern already established in `apps/dashboard/pages/01_us_padd.py`.

Create `apps/dashboard/pages/<NN>_<name>.py` (next available number prefix in that
directory) that:
- `import core.theme` before any charting call, so the `"kardamow"` Plotly template is
  registered.
- Reads data only via `core.storage.read_ts_long` / `read_flows` — pages never call APIs
  directly (golden rule 2 in `CLAUDE.md`).
- Uses `core.seasonal.seasonal_stats` / `yoy` for any seasonal maths — never reimplement,
  and never let 2020 back into a corridor calculation.
- Uses `core.theme.seasonal_range_chart` / `dual_axis_chart` for charts (add a new helper
  to `core/theme.py`, in the same house style, if neither fits — never ad-hoc colours).
- Handles the empty-lake case gracefully (an `st.info(...)` pointing at the relevant pull
  script), matching `01_us_padd.py`.

Plan first, then implement. Run `streamlit run apps/dashboard/app.py` yourself and check the
new page actually renders in a browser before considering this done.
