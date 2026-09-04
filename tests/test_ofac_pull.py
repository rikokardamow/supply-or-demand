from __future__ import annotations

import pandas as pd
from pipelines.ofac.pull_ofac import compute_diff


def _make_tagged(sanction_ids: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sanction_id": sanction_ids,
            "name": [f"Entity {sid}" for sid in sanction_ids],
            "entity_type": ["entity"] * len(sanction_ids),
            "programs": [["CUBA"]] * len(sanction_ids),
            "call_sign": [None] * len(sanction_ids),
            "vess_type": [None] * len(sanction_ids),
            "vess_flag": [None] * len(sanction_ids),
            "vess_owner": [None] * len(sanction_ids),
            "remarks": [None] * len(sanction_ids),
            "imo": [None] * len(sanction_ids),
            "energy_related": [False] * len(sanction_ids),
        }
    )


def test_compute_diff_first_pull_marks_everything_active_and_new() -> None:
    pull_date_1 = pd.Timestamp("2026-09-01")
    current = compute_diff(pd.DataFrame(), _make_tagged(["1", "2", "3"]), pull_date_1)

    assert len(current) == 3
    assert (current["status"] == "active").all()
    assert (current["first_seen"] == pull_date_1).all()
    assert (current["last_seen"] == pull_date_1).all()


def test_compute_diff_second_pull_flips_a_missing_row_to_delisted() -> None:
    pull_date_1 = pd.Timestamp("2026-09-01")
    pull_date_2 = pd.Timestamp("2026-09-08")

    first = compute_diff(pd.DataFrame(), _make_tagged(["1", "2", "3"]), pull_date_1)
    second = compute_diff(first, _make_tagged(["1", "2"]), pull_date_2)  # "3" dropped

    assert len(second) == 3  # no duplicates -- 2 active + 1 delisted
    assert second["sanction_id"].nunique() == 3

    delisted = second[second["sanction_id"] == "3"].iloc[0]
    assert delisted["status"] == "delisted"
    assert delisted["first_seen"] == pull_date_1
    assert delisted["last_seen"] == pull_date_1  # unchanged -- last real appearance

    still_active = second[second["sanction_id"] == "1"].iloc[0]
    assert still_active["status"] == "active"
    assert still_active["first_seen"] == pull_date_1  # preserved
    assert still_active["last_seen"] == pull_date_2  # advanced


def test_compute_diff_a_relisted_sanction_gets_a_fresh_first_seen() -> None:
    # If a sanction_id reappears after having been dropped from a prior pull (not
    # carried in `previous` because a much earlier pull already dropped it), it's
    # treated as genuinely new -- first_seen resets. This models the case where
    # `previous` simply doesn't contain that id at all (already pruned/never passed
    # forward), matching compute_diff's own "else pull_date" fallback.
    pull_date = pd.Timestamp("2026-09-01")
    current = compute_diff(pd.DataFrame(), _make_tagged(["99"]), pull_date)

    assert current.iloc[0]["first_seen"] == pull_date
