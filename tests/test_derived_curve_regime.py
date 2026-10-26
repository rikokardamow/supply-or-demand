"""`derived.curve.<root>.regime` must not publish a definite state where the inputs that
decide the state are absent.

`core.curve.curve_regime` classifies with `np.select(..., default="flat")`, so a row whose
`s12` or `cv` is NaN matches no condition and falls through to `"flat"` -- which
`REGIME_CODES` maps to a perfectly ordinary `6.0`, a real number that
`_write_derived`'s own `dropna()` cannot see. The real lake carries 8 such rows for `lco`
on dates where `derived.spread.lco.s12` and `derived.curve.lco.cv123` have no rows at all.

The fix lives in `pipelines/derived/curve.py`, not in `core/curve.py`: the pipeline decides
what is fit to write, and `"flat"` is only a genuine, determined state on the `s12 == 0`
knife edge it was added for.
"""

from __future__ import annotations

import pandas as pd
from tests.test_derived_curve_window import _write_contract


def _meta(expiries: dict[str, pd.Timestamp]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "root": ["xx"] * len(expiries),
            "contract": list(expiries),
            "expiry": list(expiries.values()),
        }
    )


def test_regime_is_not_written_when_convexity_cannot_be_computed(
    tmp_path, monkeypatch
) -> None:
    """Two contracts means no f03, so `convexity` is NaN on every date and no cv-dependent
    state can ever fire. `s12` is real and is written; the curve's shape is unknown, so
    the regime must be absent rather than reported as flat."""
    from core import storage
    from pipelines.derived.curve import pull_root

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)

    dates = pd.bdate_range("2025-12-22", "2026-01-09")
    expiries = {"a1": pd.Timestamp("2026-01-20"), "a2": pd.Timestamp("2026-02-19")}
    for i, contract in enumerate(expiries):
        _write_contract(storage, "xx", contract, 70.0 + i, dates)

    pull_root("xx", _meta(expiries), pd.Timestamp("2026-10-10"))

    assert not storage.read_ts_long(series_ids=["derived.spread.xx.s12"]).empty
    assert storage.read_ts_long(series_ids=["derived.curve.xx.cv123"]).empty
    assert storage.read_ts_long(series_ids=["derived.curve.xx.regime"]).empty


def test_regime_is_not_written_on_dates_where_the_second_rank_has_no_price(
    tmp_path, monkeypatch
) -> None:
    """The real lake's own shape: a ragged panel where the second-nearest contract has no
    rows for part of the history, so `s12` and `cv` are both NaN there. Those dates must
    carry no regime row, while the dates with a full panel still do."""
    from core import storage
    from pipelines.derived.curve import pull_root

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)

    all_dates = pd.bdate_range("2025-12-22", "2026-01-16")
    late_dates = pd.bdate_range("2026-01-05", "2026-01-16")
    expiries = {
        "a1": pd.Timestamp("2026-01-20"),
        "a2": pd.Timestamp("2026-02-19"),
        "a3": pd.Timestamp("2026-03-21"),
    }
    _write_contract(storage, "xx", "a1", 70.0, all_dates)
    _write_contract(storage, "xx", "a2", 71.0, late_dates)  # ragged: no early rows
    _write_contract(storage, "xx", "a3", 73.0, all_dates)

    pull_root("xx", _meta(expiries), pd.Timestamp("2026-10-10"))

    regime = storage.read_ts_long(series_ids=["derived.curve.xx.regime"])
    assert not regime.empty
    # a1 retires from every rank on its own roll date (5 business days before its
    # 2026-01-20 expiry, i.e. 2026-01-13), leaving two ranks and therefore no convexity
    # again -- so the determined window is the ragged gap's end up to that roll.
    assert set(regime["ts"]) == set(pd.bdate_range("2026-01-05", "2026-01-12"))
    assert set(regime["ts"]) <= set(late_dates)
    assert 6.0 not in set(regime["value"])  # no "flat" fallthrough survived


def test_a_genuine_flat_knife_edge_is_still_written(tmp_path, monkeypatch) -> None:
    """`"flat"` exists for the `s12 == 0` knife edge, and that case is determined, not
    absent -- masking must not throw it away with the fallthrough rows."""
    from core import storage
    from core.curve import REGIME_CODES
    from pipelines.derived.curve import pull_root

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)

    dates = pd.bdate_range("2025-12-22", "2026-01-09")
    expiries = {
        "a1": pd.Timestamp("2026-01-20"),
        "a2": pd.Timestamp("2026-02-19"),
        "a3": pd.Timestamp("2026-03-21"),
    }
    _write_contract(storage, "xx", "a1", 70.0, dates)
    _write_contract(storage, "xx", "a2", 70.0, dates)  # f01 - f02 == 0 exactly
    _write_contract(storage, "xx", "a3", 73.0, dates)

    pull_root("xx", _meta(expiries), pd.Timestamp("2026-10-10"))

    regime = storage.read_ts_long(series_ids=["derived.curve.xx.regime"])
    assert not regime.empty
    assert set(regime["value"]) == {float(REGIME_CODES["flat"])}
