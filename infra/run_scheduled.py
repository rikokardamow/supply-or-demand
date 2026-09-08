"""Local orchestrator for every scheduled pull (Spec 13). This project's own real
per-pipeline entrypoints (each already independently idempotent/resilient) are
just never *called* on a schedule until now. Run via
`.venv\\Scripts\\python.exe -m infra.run_scheduled --cadence <label>` -- registered
against Windows Task Scheduler by `infra/register_tasks.ps1`, per this project's
own lake-on-laptop decision (see infra/README.md): GitHub Actions stays CI-only
(`.github/workflows/ci.yml`), since a cloud runner has no access to this laptop's
real `data/` lake or `.env` secrets.

Every cadence group entry is `(label, "pipelines.pkg.module")` rather than a
direct callable -- `main` is imported lazily inside `run_cadence`, not at module
load time, so one pipeline's own import-time failure (a missing dependency, a
broken settings field) can't take down the whole orchestrator before it even
starts the per-pipeline try/except loop below.

Confirmed live: pipelines whose own `pull_daily.py`/`pull_weekly.py` is a thin
re-export (`from pipelines.X.pull_Y import main`), not a locally-defined
`def main()` -- e.g. `pipelines.news.pull_daily`, `pipelines.ofac.pull_daily`,
`pipelines.macro.pull_weekly`, `pipelines.adanos.pull_weekly` -- still expose a
real, callable `main` attribute via that re-export, so every cadence-group entry
below can be treated uniformly with no special-casing for which file actually
defines `main` versus just imports it."""

from __future__ import annotations

import argparse
import importlib
import sys

from core.failures import describe_exception

# (label, module path). `main` is resolved from each module at call time.
CADENCE_GROUPS: dict[str, list[tuple[str, str]]] = {
    "daily": [
        ("gie", "pipelines.gie.pull_daily"),
        ("entsog", "pipelines.entsog.pull_daily"),
        ("entsoe", "pipelines.entsoe.pull_daily"),
        ("eirgrid", "pipelines.eirgrid.pull_ireland"),
        ("gridstatus_iso", "pipelines.gridstatus_iso.pull_iso"),
        ("weather", "pipelines.weather.pull_daily"),
        ("news", "pipelines.news.pull_daily"),
        ("ofac", "pipelines.ofac.pull_daily"),
        ("futures", "pipelines.futures.pull_daily"),
        # Must run after "futures" above -- reads settle data that entry just wrote. A
        # dict preserves insertion order in Python 3.7+, and run_cadence iterates this
        # list in order, so this ordering is load-bearing, not incidental.
        ("derived_curve", "pipelines.derived.curve"),
    ],
    "wpsr": [
        ("eia_wpsr", "pipelines.eia.pull_wpsr"),
        # Must run after "eia_wpsr" above -- reads the Cushing stocks row it just wrote.
        ("derived_cushing", "pipelines.derived.cushing"),
    ],
    "ng_storage": [
        ("eia_gas_storage", "pipelines.eia.pull_gas_storage"),
    ],
    "weekly_fri": [
        ("baker_hughes", "pipelines.baker_hughes.pull_rigs"),
        ("macro", "pipelines.macro.pull_weekly"),
        # Must run after "macro" above -- reads the FRED crude/product spot legs that
        # pull just wrote. Spec 20 calls the crack series "written daily"; the series is
        # daily-*frequency*, but its legs only refresh on this weekly FRED cadence, so
        # recomputing it in the "daily" group would just rewrite identical rows from
        # unchanged inputs.
        ("derived_cracks", "pipelines.derived.cracks"),
        # Spec 21's daily positions. Reads the rank panel and the derived curve series,
        # so it must follow "derived_curve_ranks" -- which itself only needs re-running
        # when new futures land, hence its place in this same weekly group.
        ("derived_curve_ranks", "pipelines.derived.curve_ranks"),
        ("derived_systematic", "pipelines.derived.systematic"),
        ("adanos", "pipelines.adanos.pull_weekly"),
        ("social", "pipelines.social.pull_weekly"),
        ("cftc", "pipelines.cftc.pull_weekly"),
        # Must run after "cftc" above -- reads the COT data that pull just wrote.
        ("derived_fundamentals", "pipelines.derived.fundamentals"),
        ("eia_prices_weekly", "pipelines.eia.pull_prices_weekly"),
    ],
    "monthly": [
        ("opec_momr", "pipelines.opec_momr.pull_momr"),
        ("jodi", "pipelines.jodi.pull_jodi"),
        ("eia_padd_flows", "pipelines.eia.pull_padd_flows"),
        ("eia_production_exports", "pipelines.eia.pull_production_exports"),
        ("eia_prices", "pipelines.eia.pull_prices"),
        # Spec 20's "refit monthly". Reads the crack series pipelines.derived.cracks
        # writes on the weekly cadence, so it needs no ordering constraint inside this
        # group -- but it must not run before that pipeline has ever run at all.
        ("vecm_refit", "pipelines.derived.vecm_refit"),
    ],
}


def run_cadence(label: str) -> int:
    """Returns 0 if every pipeline in the group succeeded, 1 if any failed -- so
    Windows Task Scheduler's own "Last Run Result" column reflects real status.
    One flaky pipeline never blocks the rest, matching the same per-source
    resilience pattern already established inside every individual pipeline's own
    pull script, applied here at the cross-pipeline level too.

    "Succeeded" means the pipeline's own items succeeded, not merely that `main()`
    returned. Each pull script's per-item `except` records to a `core.failures`
    scope and its `main()` carries `@fails_loudly`, so a run where every contract
    failed raises PartialFailureError here instead of returning quietly -- before
    that, this loop printed "OK" and exited 0 for a run that ingested nothing."""
    group = CADENCE_GROUPS.get(label)
    if group is None:
        print(f"unknown cadence {label!r} -- choices: {sorted(CADENCE_GROUPS)}", flush=True)
        return 1

    results: list[tuple[str, bool]] = []
    for name, module_path in group:
        try:
            module = importlib.import_module(module_path)
            module.main()
        except Exception as exc:
            # Deliberately broad: one pipeline's own exception type is never
            # predictable in advance, and the whole point of this loop is that no
            # single pipeline's failure mode may abort the rest.
            #
            # describe_exception, not f"{exc}": this is the exact line that printed a
            # real EIA api_key into the log, because requests puts the full request URL
            # in HTTPError's message. The clients now sanitise at source; this is the
            # backstop for every exception type that reaches here from anywhere else.
            print(f"{name}: FAILED ({describe_exception(exc)})", flush=True)
            results.append((name, False))
        else:
            print(f"{name}: OK", flush=True)
            results.append((name, True))

    failed = [name for name, ok in results if not ok]
    print(
        f"cadence={label}: {len(results) - len(failed)}/{len(results)} succeeded"
        + (f", failed: {failed}" if failed else ""),
        flush=True,
    )
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cadence", required=True, choices=sorted(CADENCE_GROUPS))
    args = parser.parse_args()
    return run_cadence(args.cadence)


if __name__ == "__main__":
    sys.exit(main())
