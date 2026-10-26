"""Tests for pipelines/derived/curve.py::contract_panel_for -- the per-contract
settle-vs-close metric choice. See pipelines/futures/NOTES.md for the measured
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
    ts = pd.Timestamp("2026-10-09")
    assert panel.loc[ts, "z2026"] == 104.43
    assert panel.loc[ts, "f2027"] == 103.80


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


def test_contract_panel_for_chooses_metric_per_contract_not_per_root(tmp_path, monkeypatch) -> None:
    """Discriminates per-contract selection from a root-global variant ("if this root has
    any settle rows anywhere, keep only settle rows"). Contract a1 has settle rows (so a
    root-global rule would keep settle only, root-wide); contract b1 has close rows only.
    The correct per-contract rule keeps BOTH columns -- a1 from its settle rows, b1 from
    its close rows -- while the root-global mutant would drop b1 entirely, since b1 has no
    settle rows anywhere to survive a root-wide settle-only filter."""
    from core import storage
    from pipelines.derived.curve import contract_panel_for

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)
    rows = [
        # a1: 3 settle rows outnumber its 1 close row -- settle wins for a1.
        ("fut.ng.a1.settle", 3.10, "manual", "2026-10-05"),
        ("fut.ng.a1.settle", 3.20, "manual", "2026-10-06"),
        ("fut.ng.a1.settle", 3.30, "manual", "2026-10-07"),
        ("fut.ng.a1.close", 3.25, "ibkr", "2026-10-08"),
        # b1: close rows only, no settle rows at all anywhere for this contract.
        ("fut.ng.b1.close", 4.10, "ibkr", "2026-10-05"),
        ("fut.ng.b1.close", 4.20, "ibkr", "2026-10-06"),
    ]
    for series_id, value, source, ts in rows:
        storage.write_ts_long(
            pd.DataFrame(
                {
                    "series_id": [series_id], "source": [source],
                    "ts": [pd.Timestamp(ts)], "value": [value],
                    "unit": "USD/MMBtu", "geo": "NG", "freq": "D",
                    "revision_date": [pd.Timestamp("2026-10-10")],
                }
            ),
            source=source,
        )
    meta = pd.DataFrame(
        {
            "root": ["ng", "ng"],
            "contract": ["a1", "b1"],
            "expiry": [pd.Timestamp("2026-11-20"), pd.Timestamp("2026-12-20")],
        }
    )
    panel, _, provenance = contract_panel_for("ng", meta, return_provenance=True)
    assert sorted(panel.columns) == ["a1", "b1"]
    assert provenance["a1"] == "settle"
    assert provenance["b1"] == "close"


def test_contract_panel_for_prefers_close_when_settle_is_outnumbered(tmp_path, monkeypatch) -> None:
    """The real lco shape this change exists for: one stale settle row (the Barchart
    reconstruction, source="manual") against many real IBKR close rows must resolve to
    close, not settle -- presence alone is not enough to win, it must also have the rows.
    A rule that reverts to "settle if any settle rows exist" passes every other test in
    this file but fails this one, by both selection and value: the lone settle value must
    not merely lose the vote, it must not appear anywhere in the resulting column."""
    from core import storage
    from pipelines.derived.curve import contract_panel_for

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)
    stale_settle = 999.99
    rows = [
        ("fut.lco.z2027.settle", stale_settle, "manual", "2026-09-04"),
        ("fut.lco.z2027.close", 80.10, "ibkr", "2026-10-05"),
        ("fut.lco.z2027.close", 80.20, "ibkr", "2026-10-06"),
        ("fut.lco.z2027.close", 80.30, "ibkr", "2026-10-07"),
    ]
    for series_id, value, source, ts in rows:
        storage.write_ts_long(
            pd.DataFrame(
                {
                    "series_id": [series_id], "source": [source],
                    "ts": [pd.Timestamp(ts)], "value": [value],
                    "unit": "USD/1000 bbl", "geo": "LCO", "freq": "D",
                    "revision_date": [pd.Timestamp("2026-10-10")],
                }
            ),
            source=source,
        )
    meta = pd.DataFrame(
        {"root": ["lco"], "contract": ["z2027"], "expiry": [pd.Timestamp("2027-01-20")]}
    )
    panel, _, provenance = contract_panel_for("lco", meta, return_provenance=True)
    assert provenance["z2027"] == "close"
    assert stale_settle not in panel["z2027"].to_numpy()
