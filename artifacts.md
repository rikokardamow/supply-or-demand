# Published artifacts and exports

The publishing layer (`apps/artifacts/`) turns the local lake into three claude.ai
artifact pages and two Office files. **Republish to the URLs below — never create new
pages.** From a new session, pass the URL as `url` to the Artifact tool (read it first);
the build step itself does not publish.

Build: `python -m apps.artifacts.build` · Refresh everything: `/refresh-artifacts`

## Artifact pages (all private)

| Page | URL | Built file | Template | Data |
|---|---|---|---|---|
| Energy Desk Dashboard | https://claude.ai/artifact/Y5mfMCmGkpxdKMiYdxEZWG | `apps/artifacts/dist/dashboard.html` | `apps/artifacts/templates/dashboard.html` | `apps/artifacts/dist/dashboard.json` |
| Energy Desk Briefing | https://claude.ai/artifact/Vxs8Hkk75AGW47LyYin2EE | `apps/artifacts/dist/briefing.html` | `apps/artifacts/templates/briefing.html` | `apps/artifacts/dist/briefing.json` |
| EU Gas Storage in Motion | https://claude.ai/artifact/UUaVSoR2wr2etkFZmzqtMM | `apps/artifacts/dist/motion.html` | `apps/artifacts/templates/motion.html` | `apps/artifacts/dist/motion.json` |

Shared by all three: `apps/artifacts/static/charts.js`, `apps/artifacts/static/base.css`,
and the exhibit definitions in `apps/artifacts/exhibits.py`. Sharing is managed by hand
from each page's Share menu; the build and the skill never change it.

## Office exports (git-ignored)

| File | Contents |
|---|---|
| `exports/kardamow_data.xlsx` | README sheet (source, units, rows, data-through and as-of per sheet) plus `series_long`, `seasonal`, `wpsr_lines`, `curve_settles`, `flows`, `storage_by_country`, `freshness`. Real Excel dates and numbers, no merged cells. |
| `exports/kardamow_briefing.pptx` | Cover plus one slide per briefing exhibit, each a native PowerPoint chart with embedded data. Seasonal bands are min/max lines and dual-axis exhibits are two stacked charts (see "Design system" in `NOTES.md`). |

## In the Streamlit app

| Surface | Source file | Notes |
|---|---|---|
| Briefing page (`/briefing`, Overview menu) | `apps/dashboard/pages/22_briefing.py` | Every exhibit, grouped under the dashboard page's tabs. Reads the lake live (cached one hour), so it needs no republish. |
| `exhibit(spec)` component | `apps/dashboard/components/exhibit.py` | Drop one exhibit into any page. Charts come from `apps/artifacts/figures.py`, the Python twin of `static/charts.js`. |

## Constraints the pages are built to

Self-contained static HTML: data is inlined at build time, the only external script is
Plotly from cdnjs (pinned, with an integrity hash), no fonts or tiles are fetched, and the
build fails if a page exceeds 4 MiB or any output contains a `.env` value.

## Publish log

| Date | What | Lake state |
|---|---|---|
| 2026-10-10 | First publish of all three pages and both exports | Most sources last pulled 2026-09-09; 16 of 18 exhibits flagged stale |
