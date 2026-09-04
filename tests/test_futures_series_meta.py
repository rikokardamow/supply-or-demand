from __future__ import annotations

import pandas as pd
import pytest
from pipelines.futures.series_meta import ROLL_RULE, read_series_meta, write_series_meta


@pytest.fixture(autouse=True)
def _isolated_lake(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)


def _rows(contract: str, expiry: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "root": "cl",
                "contract": contract,
                "expiry": pd.Timestamp(expiry),
                "tick_size": 0.01,
                "contract_unit": "1000 bbl",
                "currency": "USD",
                "roll_rule": ROLL_RULE,
                "source": "manual",
            }
        ]
    )


def test_read_series_meta_empty_when_no_file_yet() -> None:
    result = read_series_meta()
    assert result.empty


def test_write_series_meta_has_expiry_for_every_contract() -> None:
    write_series_meta(_rows("z26", "2026-11-20"))
    write_series_meta(_rows("f27", "2026-12-19"))

    result = read_series_meta()

    assert len(result) == 2
    assert result["expiry"].notna().all()


def test_write_series_meta_overwrites_a_corrected_contract_spec() -> None:
    write_series_meta(_rows("z26", "2026-11-20"))
    corrected = _rows("z26", "2026-11-20")
    corrected["tick_size"] = 0.02  # a real correction, not a new contract
    write_series_meta(corrected)

    result = read_series_meta()

    assert len(result) == 1  # de-duped on (root, contract), keep last
    assert result.iloc[0]["tick_size"] == pytest.approx(0.02)
