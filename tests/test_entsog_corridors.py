from __future__ import annotations

import pandas as pd
import pytest
from pipelines.entsog.corridors import CORRIDORS, validate_corridors


def _directory_covering_all_real_corridors() -> pd.DataFrame:
    rows = [
        {"pointKey": point.point_key, "directionKey": point.direction_key}
        for points in CORRIDORS.values()
        for point in points
    ]
    return pd.DataFrame(rows)


def test_validate_corridors_passes_when_every_point_is_present() -> None:
    directory = _directory_covering_all_real_corridors()

    validate_corridors(directory)  # must not raise


def test_validate_corridors_fails_loudly_on_a_missing_point() -> None:
    directory = _directory_covering_all_real_corridors()
    directory = directory[directory["pointKey"] != "ITP-00008"]  # drop TAP's point

    with pytest.raises(ValueError, match="ITP-00008"):
        validate_corridors(directory)


def test_validate_corridors_fails_loudly_on_a_wrong_direction() -> None:
    directory = _directory_covering_all_real_corridors()
    directory.loc[directory["pointKey"] == "ITP-00105", "directionKey"] = "exit"

    with pytest.raises(ValueError, match="ITP-00105"):
        validate_corridors(directory)
