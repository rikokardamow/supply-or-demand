from __future__ import annotations

import pandas as pd
import pytest
from core.sentiment import agreement_rate, overlap, rolling_correlation


def _lake_rows() -> pd.DataFrame:
    # Adanos has 01-03; social has 02-04. Only 02 and 03 overlap.
    return pd.DataFrame(
        {
            "series_id": (
                ["adanos.reddit.xom.sentiment_score"] * 3
                + ["social.reddit.xom.sentiment_score"] * 3
            ),
            "ts": pd.to_datetime(
                ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-02", "2026-09-03", "2026-09-04"]
            ),
            "value": [0.5, 0.4, -0.2, 0.1, 0.3, 0.9],
        }
    )


def test_overlap_is_an_inner_join_that_counts_what_it_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A deviation computed over 3 overlapping days is not a finding, so the count
    # must travel with the frame rather than being silently discarded.
    monkeypatch.setattr("core.sentiment.read_ts_long", lambda series_ids: _lake_rows())

    result = overlap("XOM", platform="reddit")

    assert result.overlap_days == 2
    assert result.dropped_days == 2
    assert list(result.frame["ts"].dt.strftime("%Y-%m-%d")) == ["2026-09-02", "2026-09-03"]


def test_dropped_days_tracks_the_actual_asymmetry_not_a_fixed_guess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A different overlap shape (4 adanos days, 2 social days, 1 shared day) must
    # produce a dropped_days count that reflects THIS shape, not a hard-coded 2.
    # 4 total distinct days (01,02,03,04), 1 kept -> 3 dropped.
    rows = pd.DataFrame(
        {
            "series_id": (
                ["adanos.reddit.xom.sentiment_score"] * 4
                + ["social.reddit.xom.sentiment_score"] * 2
            ),
            "ts": pd.to_datetime(
                ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-04", "2026-09-05"]
            ),
            "value": [0.5, 0.4, -0.2, 0.1, 0.9, 0.2],
        }
    )
    monkeypatch.setattr("core.sentiment.read_ts_long", lambda series_ids: rows)

    result = overlap("XOM", platform="reddit")

    assert result.overlap_days == 1
    assert result.dropped_days == 4
    assert list(result.frame["ts"].dt.strftime("%Y-%m-%d")) == ["2026-09-04"]


def test_gap_is_signed_social_minus_adanos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("core.sentiment.read_ts_long", lambda series_ids: _lake_rows())

    frame = overlap("XOM", platform="reddit").frame

    assert frame.iloc[0]["gap"] == pytest.approx(0.1 - 0.4)
    assert frame.iloc[1]["gap"] == pytest.approx(0.3 - (-0.2))
    # If the sign were flipped (adanos - social) these would be the negation of the
    # asserted values, so a sign regression fails both lines above.
    assert frame.iloc[0]["gap"] != pytest.approx(0.4 - 0.1)


def test_agreement_rate_is_the_share_of_days_the_two_agree_on_sign() -> None:
    frame = pd.DataFrame({"adanos": [0.4, -0.2, 0.5], "social": [0.1, 0.3, 0.2]})
    # Day 1 both positive (agree), day 2 signs differ, day 3 both positive (agree).
    assert agreement_rate(frame) == pytest.approx(2 / 3)


def test_agreement_rate_of_all_disagreeing_days_is_zero() -> None:
    # Guards against an implementation that always returns a high/constant rate
    # (e.g. comparing magnitudes instead of signs, or a bug that inverts the mask).
    frame = pd.DataFrame({"adanos": [0.4, -0.2, 0.5], "social": [-0.1, 0.3, -0.2]})
    assert agreement_rate(frame) == pytest.approx(0.0)


def test_no_overlap_returns_an_empty_frame_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("core.sentiment.read_ts_long", lambda series_ids: pd.DataFrame())

    result = overlap("XOM", platform="reddit")

    assert result.frame.empty
    assert result.overlap_days == 0
    assert agreement_rate(result.frame) == 0.0


def test_rolling_correlation_returns_a_series_of_the_right_length() -> None:
    frame = pd.DataFrame({"adanos": [0.1, 0.2, 0.3, 0.4], "social": [0.2, 0.1, 0.5, 0.3]})
    assert len(rolling_correlation(frame, window=2)) == 4


def test_rolling_correlation_values_move_with_the_underlying_relationship() -> None:
    # A perfectly matched pair should correlate to 1.0 within any full window, so an
    # implementation that returns a constant (e.g. always NaN, or zeros) fails this.
    frame = pd.DataFrame({"adanos": [0.1, 0.2, 0.3, 0.4], "social": [0.1, 0.2, 0.3, 0.4]})
    corr = rolling_correlation(frame, window=2)
    assert corr.iloc[-1] == pytest.approx(1.0)
