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


def test_series_meta_path_follows_lake_root_rather_than_the_cwd(tmp_path, monkeypatch) -> None:
    """The manifest holds the only real contract expiries this project has, and it used
    to live at a *relative* `Path("data/lake/futures_meta")` independent of
    `core.storage.LAKE_ROOT` -- so only `monkeypatch.chdir` isolated it, and one test
    missing that one line would overwrite the real file. Deriving the directory from
    `LAKE_ROOT` at call time makes the ordinary lake patch sufficient."""
    from core import storage
    from pipelines.futures import series_meta

    lake = tmp_path / "elsewhere"
    monkeypatch.setattr(storage, "LAKE_ROOT", lake)

    write_series_meta(_rows("z26", "2026-11-20"))

    assert (lake / "futures_meta" / "series_meta.parquet").exists()
    assert len(read_series_meta()) == 1
    assert series_meta.series_meta_path() == lake / "futures_meta" / "series_meta.parquet"
