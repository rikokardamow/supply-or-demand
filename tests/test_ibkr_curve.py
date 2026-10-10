"""IBKR MCP curve parsing. No cassettes exist for this source and none can: vcrpy records
HTTP made from Python, and this data arrives through an MCP tool, never through Python's
HTTP stack. The fixture under tests/fixtures/futures/ is a trimmed real response instead."""

from __future__ import annotations

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
    rows, meta, rejections = parse_envelope(envelope, specs=load_contract_specs())

    assert set(rows["series_id"]) == {"fut.cl.z2026.close", "fut.cl.z2026.volume"}
    assert set(rows["revision_date"]) == {pd.Timestamp("2026-10-10 10:39:00")}
    assert rejections["f2027"]["stale_print"] == 1
    assert rejections["z2026"]["stale_print"] == 0
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
    rows, meta, rejections = parse_envelope(envelope, specs=load_contract_specs())
    assert rows.empty
    assert set(meta["contract"]) == {"z2026"}
    assert rejections["z2026"] == dict.fromkeys(REJECTION_REASONS, 0)


def test_the_real_fixture_parses_and_its_stale_print_is_refused() -> None:
    envelope = load_envelope(_FIXTURE)
    rows, meta, rejections = parse_envelope(envelope, specs=load_contract_specs())

    assert not rows.empty
    assert set(rows["source"]) == {"ibkr"}
    assert all(sid.endswith((".close", ".volume")) for sid in rows["series_id"])
    assert not meta.empty
    # The fixture deliberately retains a real zero-volume bar.
    assert sum(counts["stale_print"] + counts["zero_volume"] for counts in rejections.values()) >= 1


def test_parsing_the_fixture_twice_is_idempotent(tmp_path, monkeypatch) -> None:
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)
    envelope = load_envelope(_FIXTURE)

    for _ in range(2):
        rows, _, _ = parse_envelope(envelope, specs=load_contract_specs())
        storage.write_ts_long(rows, source="ibkr")

    first_pass = len(parse_envelope(envelope, specs=load_contract_specs())[0])
    assert len(storage.read_ts_long()) == first_pass
