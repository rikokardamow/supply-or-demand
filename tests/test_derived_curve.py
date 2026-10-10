"""Tests for pipelines/derived/curve.py::contract_panel_for -- the per-contract
settle-vs-close metric choice. See pipelines/futures/CLAUDE.md for the measured
difference between a genuine settlement and an IBKR last trade."""

from __future__ import annotations

import pandas as pd


def test_contract_panel_for_reads_close_when_no_settle_exists(tmp_path, monkeypatch) -> None:
    """IBKR supplies .close, not .settle. Without this the whole derived curve chain sees
    nothing for a root that only has IBKR data."""
    from core import storage
    from pipelines.derived.curve import contract_panel_for

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)
    storage.write_ts_long(
        pd.DataFrame(
            {
                "series_id": ["fut.lco.z2026.close", "fut.lco.f2027.close"],
                "source": "ibkr",
                "ts": [pd.Timestamp("2026-10-09")] * 2,
                "value": [104.43, 103.80],
                "unit": "USD/1000 bbl", "geo": "LCO", "freq": "D",
                "revision_date": pd.Timestamp("2026-10-10"),
            }
        ),
        source="ibkr",
    )
    meta = pd.DataFrame(
        {
            "root": ["lco", "lco"],
            "contract": ["z2026", "f2027"],
            "expiry": [pd.Timestamp("2026-10-30"), pd.Timestamp("2026-11-30")],
        }
    )
    panel, expiries = contract_panel_for("lco", meta)
    assert sorted(panel.columns) == ["f2027", "z2026"]
    assert len(expiries) == 2


def test_contract_panel_for_prefers_settle_and_does_not_blend_within_a_contract(
    tmp_path, monkeypatch
) -> None:
    """A settlement and a last trade are different quantities. Mixing them inside one
    column is how a function silently stops measuring what it claims to."""
    from core import storage
    from pipelines.derived.curve import contract_panel_for

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)
    for series_id, value, source in (
        ("fut.cl.z2026.settle", 90.80, "manual"),
        ("fut.cl.z2026.close", 90.75, "ibkr"),
    ):
        storage.write_ts_long(
            pd.DataFrame(
                {
                    "series_id": [series_id], "source": [source],
                    "ts": [pd.Timestamp("2026-10-09")], "value": [value],
                    "unit": "USD/1000 bbl", "geo": "CL", "freq": "D",
                    "revision_date": [pd.Timestamp("2026-10-10")],
                }
            ),
            source=source,
        )
    meta = pd.DataFrame(
        {"root": ["cl"], "contract": ["z2026"], "expiry": [pd.Timestamp("2026-11-20")]}
    )
    panel, _, provenance = contract_panel_for("cl", meta, return_provenance=True)
    assert panel.loc[pd.Timestamp("2026-10-09"), "z2026"] == 90.80
    assert provenance["z2026"] == "settle"
