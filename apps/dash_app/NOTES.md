# apps/dash_app — notes

A Plotly Dash version of the four supply-demand model pages (EU gas, UK gas, EU carbon, LNG).

    uv run python apps/dash_app/app.py
    DASHBOARD_LAKE=/path/to/data/lake uv run python apps/dash_app/app.py   # lake elsewhere

Serves http://127.0.0.1:8050 (`PORT` overrides). Routes: `/eu_gas_balance`, `/uk_gas_balance`,
`/eu_carbon`, `/lng`. Every navigation reads the lake fresh.

## One source of content

Both apps draw the same `PageView` objects from `apps/dashboard/views/sd.py`. Streamlit
pages 25–28 render them through `views/render_streamlit.py`, and this app through
`render.py`. A caption, figure or table changes in one place and appears in both.
`tests/test_dash_app.py` seeds the same synthetic lake as the Streamlit page tests and
checks for the same words.

## Why the folder is not called `dash`

`apps/` goes on `sys.path` (the `artifacts` precedent), and a folder named `dash` would
shadow the Dash library itself. A test checks that the real library loads.

## What it does not do

There is no authentication and no serving-layer publish. It reads the private lake. EEX-derived
series (carbon prices and balance) are licence-restricted and must not be exposed publicly
(see `core.publish.LICENCE_RESTRICTED_PREFIXES` and `pipelines/carbon/NOTES.md`). Run it
locally, not on a public host.
