"""IBKR MCP curve parsing. No cassettes exist for this source and none can: vcrpy records
HTTP made from Python, and this data arrives through an MCP tool, never through Python's
HTTP stack. The fixture under tests/fixtures/futures/ is a trimmed real response instead."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from pipelines.futures.client import ContractMeta, load_contract_specs, looks_like_rank_code
from pipelines.futures.ibkr_curve import (
    REJECTION_REASONS,
    bars_from_history,
    closes_to_ts_long,
    contract_code_from_month,
    contracts_from_ladder,
    liquid_bars,
    parse_envelope,
    series_meta_rows,
)
from pipelines.futures.pull_ibkr_curve import load_envelope

_FIXTURE = Path("tests/fixtures/futures/ibkr_curve_cl_20261010.json")
_RAGGED_FIXTURE = Path("tests/fixtures/futures/ibkr_curve_ragged.json")


def _ragged_fixture() -> dict:
    """Real ragged OHLCV arrays extracted verbatim from data/raw/ibkr/{cl,lco}-20261010.json
    -- 3 of the 72 real contracts captured 2026-10-10, confirmed by inspection. Not invented
    shapes: the lengths here are exactly the ones found live (see pipelines/futures/
    ibkr_curve.py's own docstring reference and the task table: cl 202901 open/time=180 but
    high/low/close=249 and volume=231; lco 202701 time=249 but everything else=250; lco
    202703 time/open/high/low/close=249 but volume=243)."""
    with _RAGGED_FIXTURE.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_contract_code_from_month_covers_every_month_letter() -> None:
    codes = [contract_code_from_month(f"2026{month:02d}") for month in range(1, 13)]
    assert codes == [
        "f2026", "g2026", "h2026", "j2026", "k2026", "m2026",
        "n2026", "q2026", "u2026", "v2026", "x2026", "z2026",
    ]


def test_every_derived_code_clears_the_rank_namespace_guard() -> None:
    """A two-digit year would collide: January is "f", so f27 reads as rank 27. Eight such
    series were live in the lake before that was caught."""
    for year in (2026, 2027, 2030, 2036):
        for month in range(1, 13):
            code = contract_code_from_month(f"{year}{month:02d}")
            assert not looks_like_rank_code(code), code


def test_contract_code_rejects_a_malformed_month() -> None:
    with pytest.raises(ValueError, match="contract_month"):
        contract_code_from_month("2026-12")


def test_contract_code_rejects_an_impossible_month() -> None:
    with pytest.raises(ValueError, match="contract_month"):
        contract_code_from_month("202613")


def test_bars_from_history_reads_the_parallel_arrays_and_normalises_to_dates() -> None:
    history = {
        "time": ["2026-09-10T13:30:00Z", "2026-09-11T13:30:00Z"],
        "open": [92.39, 90.76],
        "high": [94.87, 91.81],
        "low": [91.04, 90.66],
        "close": [93.93, 91.43],
        "volume": [34571, 21699],
    }
    bars = bars_from_history(history)
    assert list(bars.columns) == ["ts", "open", "high", "low", "close", "volume"]
    # A daily bar is stamped 13:30Z by the API; the lake's daily convention is the date.
    assert list(bars["ts"]) == [pd.Timestamp("2026-09-10"), pd.Timestamp("2026-09-11")]
    assert bars["close"].dtype == "float64"


def test_bars_from_history_tolerates_an_empty_response() -> None:
    bars = bars_from_history({})
    assert bars.empty
    assert list(bars.columns) == ["ts", "open", "high", "low", "close", "volume"]


def test_bars_from_history_raises_on_a_history_missing_an_ohlcv_key() -> None:
    """`time` present but `volume` entirely absent is a malformed capture, not an absent
    reading: it must fail loudly and name the gap, not silently become a NaN-filled
    column or surface as an opaque pandas length-mismatch error."""
    history = {
        "time": ["2026-09-10T13:30:00Z"],
        "open": [92.39],
        "high": [94.87],
        "low": [91.04],
        "close": [93.93],
    }
    with pytest.raises(ValueError, match="volume"):
        bars_from_history(history)


def test_bars_from_history_raises_naming_the_ragged_keys_and_lengths_against_real_captures() -> (
    None
):
    """Real connector output, not an invented shape: confirmed live 2026-10-10 against
    data/raw/ibkr/{cl,lco}-20261010.json, 3 of 72 contracts came back with present-but-
    ragged OHLCV arrays. `_required_array` already named an *absent* key; a *ragged* one
    must be named the same way, with its length against `time`'s -- not pandas' own
    "All arrays must be of the same length", which tells a future reader nothing about
    which key, or by how much."""
    extract = _ragged_fixture()
    cases = [
        (extract["cl_ragged_history"], 180, {"high": 249, "low": 249, "close": 249, "volume": 231}),
        (extract["lco_701_ragged_history"], 249,
         {"open": 250, "high": 250, "low": 250, "close": 250, "volume": 250}),
        (extract["lco_703_ragged_history"], 249, {"volume": 243}),
    ]
    for history, time_length, offending in cases:
        with pytest.raises(ValueError) as excinfo:
            bars_from_history(history)
        message = str(excinfo.value)
        assert str(time_length) in message, message
        for key, length in offending.items():
            assert key in message, (key, message)
            assert str(length) in message, (key, length, message)


def test_liquid_bars_rejects_the_real_zero_volume_stale_print() -> None:
    """CLZ7's 2021-12 bar is 57.31 four times on volume 0 -- a carried reference price,
    not a market. Confirmed live 2026-10-10."""
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2021-12-01", "2026-10-01"]),
            "open": [57.31, 75.17],
            "high": [57.31, 77.89],
            "low": [57.31, 74.45],
            "close": [57.31, 77.39],
            "volume": [0.0, 98071.0],
        }
    )
    kept, rejected = liquid_bars(bars)
    assert list(kept["ts"]) == [pd.Timestamp("2026-10-01")]
    assert rejected["stale_print"] == 1
    assert rejected["zero_volume"] == 0  # counted once, under the more specific reason


def test_liquid_bars_counts_a_plain_zero_volume_bar_separately() -> None:
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2022-01-03"]),
            "open": [59.12], "high": [62.25], "low": [59.07], "close": [61.95],
            "volume": [0.0],
        }
    )
    kept, rejected = liquid_bars(bars)
    assert kept.empty
    assert rejected["zero_volume"] == 1
    assert rejected["stale_print"] == 0


def test_liquid_bars_left_trims_rather_than_dropping_the_contract() -> None:
    """A far-dated contract runs illiquid then liquid as it approaches the front. Keep the
    liquid tail; drop the dead beginning."""
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2021-11-01", "2021-12-01", "2026-09-01", "2026-10-01"]),
            "open": [56.5, 57.31, 71.16, 75.17],
            "high": [59.95, 57.31, 75.80, 77.89],
            "low": [56.5, 57.31, 70.10, 74.45],
            "close": [60.13, 57.31, 75.44, 77.39],
            "volume": [2.0, 0.0, 223836.0, 98071.0],
        }
    )
    kept, _ = liquid_bars(bars)
    assert len(kept) == 3
    assert kept["ts"].min() == pd.Timestamp("2021-11-01")


def test_liquid_bars_rejects_a_missing_or_non_positive_close() -> None:
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-05"]),
            "open": [75.17, 75.00, 0.0],
            "high": [77.89, 76.00, 76.00],
            "low": [74.45, 74.00, 74.00],
            "close": [None, -1.0, 75.50],
            "volume": [98071.0, 98071.0, 98071.0],
        }
    )
    kept, rejected = liquid_bars(bars)
    assert list(kept["ts"]) == [pd.Timestamp("2026-10-05")]
    assert rejected["no_close"] == 1
    assert rejected["non_positive_close"] == 1


def test_every_rejection_reason_is_reported_even_when_zero() -> None:
    bars = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2026-10-01"]),
            "open": [75.17], "high": [77.89], "low": [74.45], "close": [77.39],
            "volume": [98071.0],
        }
    )
    _, rejected = liquid_bars(bars)
    assert set(rejected) == set(REJECTION_REASONS)
    assert sum(rejected.values()) == 0


_CL_Z2026 = ContractMeta(
    root="cl", contract="z2026", expiry=date(2026, 11, 20),
    tick_size=0.01, contract_unit="1000 bbl", currency="USD",
)


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": pd.to_datetime(["2026-10-08", "2026-10-09"]),
            "open": [90.78, 89.87], "high": [92.14, 91.22],
            "low": [89.50, 89.79], "close": [90.75, 91.01],
            "volume": [54091.0, 36647.0],
        }
    )


def test_closes_to_ts_long_writes_close_and_volume_but_never_oi() -> None:
    rows = closes_to_ts_long(
        {"z2026": _bars()}, root="cl",
        revision_date=pd.Timestamp("2026-10-10"), contracts=[_CL_Z2026], source="ibkr",
    )
    suffixes = {series_id.rsplit(".", 1)[1] for series_id in rows["series_id"]}
    assert suffixes == {"close", "volume"}
    assert not any(series_id.endswith(".oi") for series_id in rows["series_id"])
    assert not any(series_id.endswith(".settle") for series_id in rows["series_id"])


def test_closes_to_ts_long_uses_the_projects_unit_convention() -> None:
    rows = closes_to_ts_long(
        {"z2026": _bars()}, root="cl",
        revision_date=pd.Timestamp("2026-10-10"), contracts=[_CL_Z2026], source="ibkr",
    )
    close_rows = rows[rows["series_id"] == "fut.cl.z2026.close"]
    assert set(close_rows["unit"]) == {"USD/1000 bbl"}
    volume_rows = rows[rows["series_id"] == "fut.cl.z2026.volume"]
    assert set(volume_rows["unit"]) == {"contracts"}


def test_closes_to_ts_long_carries_the_source_through_the_frame() -> None:
    """A reused transform that hardcodes its source column silently misclassifies rows on
    read-back -- the gotcha pipelines/weather/degree_days.py hit for real. Exercised with
    two different `source` values: a test that only ever passes "ibkr" would still pass
    if the column were hardcoded to that same literal, so a second, different value is
    required to catch that regression."""
    rows = closes_to_ts_long(
        {"z2026": _bars()}, root="cl",
        revision_date=pd.Timestamp("2026-10-10"), contracts=[_CL_Z2026], source="ibkr",
    )
    assert set(rows["source"]) == {"ibkr"}
    assert set(rows["geo"]) == {"CL"}
    assert set(rows["freq"]) == {"D"}
    assert rows["value"].dtype == "float64"

    manual_rows = closes_to_ts_long(
        {"z2026": _bars()}, root="cl",
        revision_date=pd.Timestamp("2026-10-10"), contracts=[_CL_Z2026], source="manual",
    )
    assert set(manual_rows["source"]) == {"manual"}


def test_closes_to_ts_long_rejects_a_contract_code_that_looks_like_a_rank() -> None:
    bad = ContractMeta(
        root="cl", contract="f27", expiry=date(2027, 1, 20),
        tick_size=0.01, contract_unit="1000 bbl", currency="USD",
    )
    with pytest.raises(ValueError, match=r"f01\.\.f36"):
        closes_to_ts_long(
            {"f27": _bars()}, root="cl",
            revision_date=pd.Timestamp("2026-10-10"), contracts=[bad], source="ibkr",
        )


def test_a_sub_dollar_value_survives_the_round_trip(tmp_path, monkeypatch) -> None:
    """The v0.11 lesson: a 0.35 spread must not read back as 0. Written alongside a
    deliberately int64-typed sibling source, reproducing the original bug's conditions."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)

    sibling = tmp_path / "ts_long" / "source=rigs" / "year=2026"
    sibling.mkdir(parents=True)
    pq.write_table(
        pa.table(
            {
                "series_id": ["rigs.us.total"], "source": ["rigs"],
                "ts": [pd.Timestamp("2026-10-09")], "value": pa.array([588], type=pa.int64()),
                "unit": ["rigs"], "geo": ["US"], "freq": ["W"],
                "revision_date": [pd.Timestamp("2026-10-10")],
            }
        ),
        sibling / "part-0.parquet",
    )

    bars = _bars()
    bars.loc[:, "close"] = [0.35, 0.35]
    rows = closes_to_ts_long(
        {"z2026": bars}, root="cl",
        revision_date=pd.Timestamp("2026-10-10"), contracts=[_CL_Z2026], source="ibkr",
    )
    storage.write_ts_long(rows, source="ibkr")

    back = storage.read_ts_long(series_ids=["fut.cl.z2026.close"])
    assert set(back["value"]) == {0.35}


_LADDER = [
    {"contract_id": 296574787, "contract_month": "202612", "last_trading_date": "20261120"},
    {"contract_id": 304037396, "contract_month": "202701", "last_trading_date": "20261221"},
]


def test_contracts_from_ladder_derives_codes_and_real_expiries() -> None:
    contracts = contracts_from_ladder(_LADDER, root="cl", specs=load_contract_specs())
    assert [meta.contract for meta in contracts] == ["z2026", "f2027"]
    assert [meta.expiry for meta in contracts] == [date(2026, 11, 20), date(2026, 12, 21)]
    assert all(meta.root == "cl" for meta in contracts)
    assert all(meta.currency for meta in contracts)


def test_series_meta_rows_carry_every_column_the_manifest_requires() -> None:
    from pipelines.futures.series_meta import ROLL_RULE

    contracts = contracts_from_ladder(_LADDER, root="cl", specs=load_contract_specs())
    rows = series_meta_rows(contracts, source="ibkr")
    required = {
        "root", "contract", "expiry", "tick_size",
        "contract_unit", "currency", "roll_rule", "source",
    }
    assert required <= set(rows.columns)
    assert set(rows["source"]) == {"ibkr"}
    assert set(rows["roll_rule"]) == {ROLL_RULE}


def test_parse_envelope_maps_contract_ids_to_codes_and_reports_rejections() -> None:
    envelope = {
        "captured_at": "2026-10-10T10:39:00Z",
        "root": "cl",
        "exchange": "NYMEX",
        "ladder": _LADDER,
        "history": {
            "296574787": {
                "time": ["2026-10-08T13:30:00Z", "2026-10-09T13:30:00Z"],
                "open": [90.78, 89.87], "high": [92.14, 91.22],
                "low": [89.50, 89.79], "close": [90.75, 91.01],
                "volume": [54091, 36647],
            },
            "304037396": {
                "time": ["2026-10-09T13:30:00Z"],
                "open": [57.31], "high": [57.31], "low": [57.31], "close": [57.31],
                "volume": [0],
            },
        },
    }
    rows, meta, rejections, skipped = parse_envelope(envelope, specs=load_contract_specs())

    assert set(rows["series_id"]) == {"fut.cl.z2026.close", "fut.cl.z2026.volume"}
    assert set(rows["revision_date"]) == {pd.Timestamp("2026-10-10 10:39:00")}
    assert rejections["f2027"]["stale_print"] == 1
    assert rejections["z2026"]["stale_print"] == 0
    assert skipped == {}
    # series_meta lists every laddered contract, even one with no liquid bars.
    assert set(meta["contract"]) == {"z2026", "f2027"}


def test_parse_envelope_records_a_contract_with_no_history_as_a_skip() -> None:
    envelope = {
        "captured_at": "2026-10-10T10:39:00Z",
        "root": "cl",
        "exchange": "NYMEX",
        "ladder": _LADDER[:1],
        "history": {"296574787": {}},
    }
    rows, meta, rejections, skipped = parse_envelope(envelope, specs=load_contract_specs())
    assert rows.empty
    assert set(meta["contract"]) == {"z2026"}
    assert rejections["z2026"] == dict.fromkeys(REJECTION_REASONS, 0)
    assert skipped == {}


def test_parse_envelope_skips_a_ragged_contract_but_keeps_the_others() -> None:
    """The real bug: both real captures failed entirely because one ragged contract (3 of
    72) aborted the whole envelope via pandas' opaque error. A contract that cannot be
    parsed must be a recorded skip -- like an empty `history` entry already is -- not a
    reason to lose every other contract's rows.

    Design decision: the skip is NOT folded into `rejections`. `rejections[code]` is
    always exactly the 4 bar-level REJECTION_REASONS counts, so a reader can trust its
    shape; a contract that never reached `liquid_bars` has no entry there at all. The skip
    lives in a sibling `skipped` dict instead, so "ragged, could not parse" (a dict key
    that exists in `skipped`, absent from `rejections`) is never confused with "parsed
    fine, every bar rejected as stale" (a dict key in `rejections` whose counts happen to
    sum to the contract's whole bar count)."""
    extract = _ragged_fixture()
    ragged_id = str(extract["cl_ladder_ragged"]["contract_id"])
    healthy_id = str(extract["cl_ladder_healthy"]["contract_id"])
    envelope = {
        "captured_at": extract["cl_captured_at"],
        "root": "cl",
        "exchange": extract["cl_exchange"],
        "ladder": [extract["cl_ladder_healthy"], extract["cl_ladder_ragged"]],
        "history": {
            healthy_id: extract["cl_healthy_history_trimmed"],
            ragged_id: extract["cl_ragged_history"],
        },
    }
    rows, meta, rejections, skipped = parse_envelope(envelope, specs=load_contract_specs())

    assert set(skipped) == {"f2029"}
    assert isinstance(skipped["f2029"], Exception)
    assert "f2029" not in rejections

    assert not rows.empty
    assert set(rows["series_id"]) == {"fut.cl.x2026.close", "fut.cl.x2026.volume"}
    assert set(meta["contract"]) == {"x2026", "f2029"}  # meta is the ladder, skip or not


def test_the_real_fixture_parses_and_its_stale_print_is_refused() -> None:
    envelope = load_envelope(_FIXTURE)
    rows, meta, rejections, skipped = parse_envelope(envelope, specs=load_contract_specs())

    assert not rows.empty
    assert set(rows["source"]) == {"ibkr"}
    assert all(sid.endswith((".close", ".volume")) for sid in rows["series_id"])
    assert not meta.empty
    assert skipped == {}  # the committed fixture has no ragged contract
    # The fixture deliberately retains a real zero-volume bar.
    assert sum(counts["stale_print"] + counts["zero_volume"] for counts in rejections.values()) >= 1


def test_the_real_fixtures_mid_dated_contract_demonstrates_left_trim() -> None:
    """CLZ7 (z2027) carries two real stale prints (2024-07-17/18, volume 0, flat OHLC)
    immediately followed by six real liquid bars (2024-07-19 onward, real volume). This
    is the fixture's partial-rejection case -- the design spec requires the gate to be
    exercised "rejecting the stale print while keeping the liquid tail" against real
    bars, not only against the synthetic shape in test_liquid_bars_left_trims_rather_
    than_dropping_the_contract. z2030 (CLZ30) is the fixture's other case: a contract
    whose whole captured window is stale, rejected in full."""
    envelope = load_envelope(_FIXTURE)
    rows, _, rejections, _ = parse_envelope(envelope, specs=load_contract_specs())

    assert rejections["z2027"]["stale_print"] == 2
    assert rejections["z2030"]["stale_print"] == 8  # the whole window, rejected in full

    z2027_closes = rows[rows["series_id"] == "fut.cl.z2027.close"]
    assert len(z2027_closes) == 6  # fewer rows kept than the contract's 8 captured bars
    assert z2027_closes["ts"].min() == pd.Timestamp("2024-07-19")  # the later bars only


def test_parsing_the_fixture_twice_is_idempotent(tmp_path, monkeypatch) -> None:
    """Row count alone cannot see this. `core.storage` de-dups on `["series_id", "ts"]`
    only and keeps the LAST row, so a `revision_date` of `pd.Timestamp.now()` on each
    pass would leave the count identical while quietly restamping every row -- the exact
    mutation this test used to pass under. Idempotent means the lake's *content* is
    unchanged by a re-ingest, `revision_date` included, which is only true because
    `parse_envelope` takes it from the capture's own `captured_at`."""
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)
    envelope = load_envelope(_FIXTURE)
    captured_at = pd.Timestamp(str(envelope["captured_at"])).tz_localize(None)

    passes = []
    for _ in range(2):
        rows, _, _, _ = parse_envelope(envelope, specs=load_contract_specs())
        storage.write_ts_long(rows, source="ibkr")
        passes.append(
            storage.read_ts_long().sort_values(["series_id", "ts"]).reset_index(drop=True)
        )

    first_pass = len(parse_envelope(envelope, specs=load_contract_specs())[0])
    assert len(passes[0]) == first_pass
    assert len(passes[1]) == first_pass
    assert set(passes[1]["revision_date"]) == {captured_at}
    pd.testing.assert_frame_equal(passes[0], passes[1])


def test_revision_date_is_the_captures_own_captured_at(tmp_path, monkeypatch) -> None:
    """The property the idempotence test above rests on, pinned on its own against the
    real fixture: nothing in the write path may stamp the ingest's wall clock."""
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)
    envelope = load_envelope(_FIXTURE)
    rows, _, _, _ = parse_envelope(envelope, specs=load_contract_specs())

    expected = pd.Timestamp(str(envelope["captured_at"])).tz_localize(None)
    assert expected == pd.Timestamp("2026-10-10 12:22:00")  # the fixture's own capture
    assert set(rows["revision_date"]) == {expected}

    storage.write_ts_long(rows, source="ibkr")
    assert set(storage.read_ts_long()["revision_date"]) == {expected}


def test_main_writes_rows_and_reports_rejections_per_contract(
    tmp_path, monkeypatch, capsys
) -> None:
    """main()'s own wiring -- failure_scope, write_ts_long, write_series_meta and the
    per-contract refusal print -- was previously verified only by inspection. The explicit
    LAKE_ROOT and ARCHIVE_DIR monkeypatches are what isolate this: series_meta derives its
    own directory from core.storage.LAKE_ROOT at call time, so patching that moves the
    manifest too. The chdir is belt-and-braces against a relative path anywhere else in the
    entrypoint -- it is no longer load-bearing for the manifest itself."""
    from core import storage
    from pipelines.futures import pull_ibkr_curve

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    monkeypatch.setattr(pull_ibkr_curve, "ARCHIVE_DIR", archive_dir)

    envelope = {
        "captured_at": "2026-10-10T10:39:00Z",
        "root": "cl",
        "exchange": "NYMEX",
        "ladder": _LADDER,
        "history": {
            "296574787": {
                "time": ["2026-10-08T13:30:00Z", "2026-10-09T13:30:00Z"],
                "open": [90.78, 89.87], "high": [92.14, 91.22],
                "low": [89.50, 89.79], "close": [90.75, 91.01],
                "volume": [54091, 36647],
            },
            "304037396": {
                "time": ["2026-10-09T13:30:00Z"],
                "open": [57.31], "high": [57.31], "low": [57.31], "close": [57.31],
                "volume": [0],
            },
        },
    }
    (archive_dir / "cl-20261010.json").write_text(json.dumps(envelope), encoding="utf-8")

    pull_ibkr_curve.main()

    out = capsys.readouterr().out
    assert "cl-20261010.json: wrote" in out
    assert "f2027: refused {'stale_print': 1}" in out
    assert not storage.read_ts_long().empty
    # The count must be the contracts actually WRITTEN, not the ladder: this capture
    # ladders two contracts and writes one, f2027's only bar being a stale print. The
    # real run printed "across 36 contracts" for captures that wrote 35 and 34.
    assert "across 1 contract" in out
    assert "2 in the ladder" in out
    assert "0 skipped" in out
    assert "1 with no bars kept" in out


def test_main_continues_past_a_malformed_capture_but_still_exits_non_zero(
    tmp_path, monkeypatch, capsys
) -> None:
    """A bad capture must not cost a good one (core.failures' whole point), but the run
    must still fail loudly overall -- raising PartialFailureError, exactly like any other
    pipeline wrapped in failure_scope, is what makes Task Scheduler's exit code honest."""
    from core import storage
    from core.failures import PartialFailureError
    from pipelines.futures import pull_ibkr_curve

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    monkeypatch.setattr(pull_ibkr_curve, "ARCHIVE_DIR", archive_dir)

    good_envelope = {
        "captured_at": "2026-10-10T10:39:00Z",
        "root": "cl",
        "exchange": "NYMEX",
        "ladder": _LADDER,
        "history": {
            "296574787": {
                "time": ["2026-10-08T13:30:00Z", "2026-10-09T13:30:00Z"],
                "open": [90.78, 89.87], "high": [92.14, 91.22],
                "low": [89.50, 89.79], "close": [90.75, 91.01],
                "volume": [54091, 36647],
            },
            "304037396": {
                "time": [], "open": [], "high": [], "low": [], "close": [], "volume": [],
            },
        },
    }
    (archive_dir / "cl-20261010.json").write_text(json.dumps(good_envelope), encoding="utf-8")
    # Not a capture envelope at all -- load_envelope rejects a bare JSON list.
    (archive_dir / "ng-20261010.json").write_text(json.dumps(["not", "an", "envelope"]))

    with pytest.raises(PartialFailureError):
        pull_ibkr_curve.main()

    out = capsys.readouterr().out
    assert "ng-20261010.json: FAILED" in out
    assert "cl-20261010.json: wrote" in out
    assert not storage.read_ts_long().empty


def test_main_skips_a_ragged_contract_but_still_writes_the_others_and_exits_non_zero(
    tmp_path, monkeypatch, capsys
) -> None:
    """The real regression, end to end: a capture with one ragged contract among several
    good ones must write the good ones' rows, print the ragged contract's skip
    distinguishably from a bar-level "refused {...}" line, and still exit non-zero --
    `main()` must not report success for a run that silently dropped a contract."""
    from core import storage
    from core.failures import PartialFailureError
    from pipelines.futures import pull_ibkr_curve

    extract = _ragged_fixture()  # loaded before chdir -- it uses a cwd-relative path
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    monkeypatch.setattr(pull_ibkr_curve, "ARCHIVE_DIR", archive_dir)

    ragged_id = str(extract["cl_ladder_ragged"]["contract_id"])
    healthy_id = str(extract["cl_ladder_healthy"]["contract_id"])
    envelope = {
        "captured_at": extract["cl_captured_at"],
        "root": "cl",
        "exchange": extract["cl_exchange"],
        "ladder": [extract["cl_ladder_healthy"], extract["cl_ladder_ragged"]],
        "history": {
            healthy_id: extract["cl_healthy_history_trimmed"],
            ragged_id: extract["cl_ragged_history"],
        },
    }
    (archive_dir / "cl-20261010.json").write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(PartialFailureError):
        pull_ibkr_curve.main()

    out = capsys.readouterr().out
    assert "cl-20261010.json: wrote" in out  # the file itself did not fail outright
    assert "f2029" in out
    assert "FAILED" in out  # the skip reads distinguishably from a "refused {...}" line
    assert not storage.read_ts_long().empty  # the healthy contract's rows still landed
