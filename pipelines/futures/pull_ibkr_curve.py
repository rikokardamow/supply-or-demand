"""Ingest archived IBKR MCP curve captures into the lake.

Deliberately NOT registered in infra/run_scheduled.py. The fetch half is an MCP tool that
only exists inside an AI-assistant session, so this cannot run headless; registering the parser
alone would rewrite identical rows from an unchanged archive. pipelines/manual_physical and
pipelines/ais are unscheduled for the same kind of reason.

Capture ritual: see docs/superpowers/plans/2026-10-10-ibkr-curve.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.failures import failure_scope, record_failure
from core.storage import write_ts_long

from pipelines.futures.client import load_contract_specs
from pipelines.futures.ibkr_curve import parse_envelope
from pipelines.futures.series_meta import write_series_meta

ARCHIVE_DIR = Path("data/raw/ibkr")


def load_envelope(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not hold a capture envelope")
    return payload


def main() -> None:
    envelopes = sorted(ARCHIVE_DIR.glob("*.json"))
    if not envelopes:
        print(f"no captures under {ARCHIVE_DIR} -- nothing to ingest", flush=True)
        return

    specs = load_contract_specs()
    with failure_scope("futures.pull_ibkr_curve"):
        for path in envelopes:
            try:
                rows, meta, rejections, skipped = parse_envelope(load_envelope(path), specs=specs)
            except Exception as exc:
                record_failure(path.name, exc)
                continue

            if not meta.empty:
                write_series_meta(meta)
            if not rows.empty:
                write_ts_long(rows, source="ibkr")

            refused = {
                contract: {reason: n for reason, n in counts.items() if n}
                for contract, counts in rejections.items()
                if any(counts.values())
            }
            # `meta` is the whole ladder, written or not, so it overstates coverage: the
            # real 2026-10-10 run printed "across 36 contracts" for captures that wrote 35
            # and 34. Count the contracts actually present in the rows instead, and state
            # the ladder, the skips (ragged arrays) and the contracts whose every bar
            # failed the liquidity gate as the three separate things they are.
            contracts_written = rows["series_id"].str.split(".").str[2] if not rows.empty else None
            written = 0 if contracts_written is None else int(contracts_written.nunique())
            no_bars_kept = len(meta) - written - len(skipped)
            print(
                f"{path.name}: wrote {len(rows)} rows across {written} contract(s) -- "
                f"{len(meta)} in the ladder, {len(skipped)} skipped, "
                f"{no_bars_kept} with no bars kept",
                flush=True,
            )
            for contract, counts in sorted(refused.items()):
                print(f"  {contract}: refused {counts}", flush=True)
            # A ragged/unparseable contract is a recorded skip, never a reason to lose the
            # other contracts in this capture -- printed as a distinct "FAILED" line (never
            # "refused {...}", which means something else: a contract that parsed fine but
            # whose bars didn't pass the liquidity gate) and fed into the same failure log
            # as a whole-file failure, so the run still exits non-zero overall.
            for contract, failure in sorted(skipped.items()):
                record_failure(f"{path.name}:{contract}", failure)


if __name__ == "__main__":
    main()
