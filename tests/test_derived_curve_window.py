"""Tests for the IBKR-capture rank-window defect fix in pipelines/derived/curve.py.

The IBKR connector's `search_futures` (without `include_expired=true`) only returns
contracts still live at capture time, so `core.curve.nearby_panel`'s f01..fn ranks are
only trustworthy from the date the panel's own earliest-expiry contract could first
have been genuinely front-month -- before that, a contract that has since expired
would have been nearer than anything the panel holds. See `valid_rank_window`'s own
docstring for the exact rule. `dec_dec` (contract-coded, not rank-coded) must stay
unaffected -- it never claims a rank, so the missing-expired-contract problem does not
apply to it at all."""

from __future__ import annotations

import pandas as pd


def _write_contract(storage, root: str, contract: str, price: float, dates) -> None:
    storage.write_ts_long(
        pd.DataFrame(
            {
                "series_id": f"fut.{root}.{contract}.close",
                "source": "ibkr",
                "ts": dates,
                "value": price,
                "unit": "USD/1000 bbl",
                "geo": root.upper(),
                "freq": "D",
                "revision_date": pd.Timestamp("2026-10-10"),
            }
        ),
        source="ibkr",
    )


def test_valid_rank_window_matches_the_suggested_criterion() -> None:
    from pipelines.derived.curve import valid_rank_window

    expiries = pd.Series(
        [
            pd.Timestamp("2026-01-20"),
            pd.Timestamp("2026-02-19"),
            pd.Timestamp("2026-03-21"),
            pd.Timestamp("2026-04-20"),
        ],
        index=["a1", "a2", "a3", "a4"],
    )
    # Gaps are 30, 30, 30 days -- median 30. min(expiries) - 30d = 2025-12-21.
    assert valid_rank_window(expiries) == pd.Timestamp("2025-12-21")


def test_valid_rank_window_against_the_real_cl_shape_from_the_task() -> None:
    """The task's own worked example: earliest expiry 2026-10-20, monthly contracts,
    yields roughly 2026-09-20."""
    from pipelines.derived.curve import valid_rank_window

    expiries = pd.Series(
        [
            pd.Timestamp("2026-10-20"),
            pd.Timestamp("2026-11-20"),
            pd.Timestamp("2026-12-21"),
            pd.Timestamp("2027-01-20"),
        ],
        index=["x2026", "z2026", "f2027", "g2027"],
    )
    window_start = valid_rank_window(expiries)
    assert window_start == pd.Timestamp("2026-09-19")


def test_pull_root_suppresses_rank_series_rows_before_the_valid_window(
    tmp_path, monkeypatch
) -> None:
    from core import storage
    from pipelines.derived.curve import pull_root

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)

    dates = pd.bdate_range("2025-11-03", "2025-12-31")
    contracts = {
        "a1": 70.0,
        "a2": 71.0,
        "a3": 72.0,
        "a4": 73.0,
    }
    expiries = {
        "a1": pd.Timestamp("2026-01-20"),
        "a2": pd.Timestamp("2026-02-19"),
        "a3": pd.Timestamp("2026-03-21"),
        "a4": pd.Timestamp("2026-04-20"),
    }
    for contract, price in contracts.items():
        _write_contract(storage, "xx", contract, price, dates)
    meta = pd.DataFrame(
        {
            "root": ["xx"] * 4,
            "contract": list(contracts),
            "expiry": [expiries[c] for c in contracts],
        }
    )

    pull_root("xx", meta, pd.Timestamp("2026-10-10"))

    window_start = pd.Timestamp("2025-12-21")
    s12 = storage.read_ts_long(series_ids=["derived.spread.xx.s12"])
    assert not s12.empty
    assert s12["ts"].min() >= window_start
    assert s12["ts"].max() == dates.max()
    # f01-f02 = 70-71 = -1.0 flat, by construction.
    assert s12.set_index("ts")["value"].round(6).eq(-1.0).all()

    regime = storage.read_ts_long(series_ids=["derived.curve.xx.regime"])
    assert regime["ts"].min() >= window_start


def test_pull_root_reports_the_window_and_the_suppressed_row_count(
    tmp_path, monkeypatch, capsys
) -> None:
    from core import storage
    from pipelines.derived.curve import pull_root

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)

    dates = pd.bdate_range("2025-11-03", "2025-12-31")
    contracts = {"a1": 70.0, "a2": 71.0, "a3": 72.0, "a4": 73.0}
    expiries = {
        "a1": pd.Timestamp("2026-01-20"),
        "a2": pd.Timestamp("2026-02-19"),
        "a3": pd.Timestamp("2026-03-21"),
        "a4": pd.Timestamp("2026-04-20"),
    }
    for contract, price in contracts.items():
        _write_contract(storage, "xx", contract, price, dates)
    meta = pd.DataFrame(
        {
            "root": ["xx"] * 4,
            "contract": list(contracts),
            "expiry": [expiries[c] for c in contracts],
        }
    )

    pull_root("xx", meta, pd.Timestamp("2026-10-10"))
    out = capsys.readouterr().out

    assert "2025-12-21" in out
    assert "suppressed" in out


def test_dec_dec_is_unaffected_even_when_the_entire_panel_is_outside_the_window(
    tmp_path, monkeypatch
) -> None:
    """The whole panel here sits before the rank window (2025-11-19), so every
    rank-based series is suppressed to nothing -- but dec_dec is contract-coded, not
    rank-coded, and must still be written over its full real history regardless."""
    from core import storage
    from pipelines.derived.curve import pull_root

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)

    dates = pd.bdate_range("2025-10-01", "2025-11-10")
    contracts = {"z2025": 70.0, "f2026": 71.0, "g2026": 72.0, "z2026": 73.0}
    expiries = {
        "z2025": pd.Timestamp("2025-12-20"),
        "f2026": pd.Timestamp("2026-01-20"),
        "g2026": pd.Timestamp("2026-02-19"),
        "z2026": pd.Timestamp("2026-12-21"),
    }
    for contract, price in contracts.items():
        _write_contract(storage, "xx", contract, price, dates)
    meta = pd.DataFrame(
        {
            "root": ["xx"] * 4,
            "contract": list(contracts),
            "expiry": [expiries[c] for c in contracts],
        }
    )

    pull_root("xx", meta, pd.Timestamp("2026-10-10"))

    s12 = storage.read_ts_long(series_ids=["derived.spread.xx.s12"])
    assert s12.empty  # every date in this panel is before the valid rank window

    # core.curve.dec_dec parses the delivery year from code[1:] -- against this
    # project's real 4-digit-year contract codes ("z2025"/"z2026") that reads as
    # 2000 + 2025 = 4025, giving "dec_dec_4025_4026". Pre-existing, out of this
    # task's scope (the task's own text names the real lake's analogous
    # "dec_dec_4026_4027" as correct, explicit contract naming) -- not something to
    # "fix" here; this test only needs the real series_id dec_dec actually writes.
    dec_dec = storage.read_ts_long(series_ids=["derived.spread.xx.dec_dec_4025_4026"])
    assert len(dec_dec) == len(dates)
    assert dec_dec.set_index("ts")["value"].round(6).eq(-3.0).all()  # 70 - 73
