"""pipelines/derived/curve.py keeps class d settles out of the shared derived partition (I-18)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from core import rights
from core.storage import read_ts_long, write_ts_long
from pipelines.derived import curve
from pipelines.futures.series_meta import write_series_meta


@pytest.fixture(autouse=True)
def _isolated_lake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def _seed_brent_settles(source: str) -> pd.DataFrame:
    days = pd.bdate_range("2026-09-01", "2026-11-20")
    frames = []
    for i, contract in enumerate(("z2026", "f2027")):
        frames.append(
            pd.DataFrame(
                {
                    "series_id": f"fut.lco.{contract}.settle",
                    "source": source,
                    "ts": days,
                    "value": 80.0 + i + 0.05 * np.arange(len(days)),
                    "unit": "USD/bbl",
                    "geo": "LCO",
                    "freq": "D",
                    "revision_date": pd.Timestamp("2026-11-21"),
                }
            )
        )
    write_ts_long(pd.concat(frames, ignore_index=True), source=source)
    meta = pd.DataFrame(
        {
            "root": "lco",
            "contract": ["z2026", "f2027"],
            "expiry": pd.to_datetime(["2026-11-30", "2026-12-31"]),
            "tick_size": 0.01,
            "contract_unit": "bbl",
            "currency": "USD",
            "roll_rule": "5bd_before_expiry",
            "source": source,
        }
    )
    write_series_meta(meta)
    return meta


def test_settles_from_a_class_d_source_write_no_derived_rows(
    capsys: pytest.CaptureFixture[str],
) -> None:
    meta = _seed_brent_settles("manual")
    assert rights.SOURCE_CLASS["manual"] == "d"

    written = curve.pull_root("lco", meta, pd.Timestamp("2026-11-21"))

    assert written == 0
    assert read_ts_long(source="derived").empty
    assert "class d source" in capsys.readouterr().out


def test_the_same_settles_are_used_when_their_source_is_not_class_d(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meta = _seed_brent_settles("manual")
    monkeypatch.setattr(rights, "SOURCE_CLASS", {**rights.SOURCE_CLASS, "manual": "b"})

    assert curve.pull_root("lco", meta, pd.Timestamp("2026-11-21")) > 0
    assert not read_ts_long(source="derived").empty


def test_a_root_without_settles_still_says_there_is_no_curve_yet(
    capsys: pytest.CaptureFixture[str],
) -> None:
    meta = pd.DataFrame(columns=["root", "contract", "expiry"])
    assert curve.pull_root("lco", meta, pd.Timestamp("2026-11-21")) == 0
    assert "not enough contracts" in capsys.readouterr().out

