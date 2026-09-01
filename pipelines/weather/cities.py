"""Loads the hand-maintained city list (pipelines/weather/cities.csv) -- same precedent as
pipelines/opec_momr/quotas.csv: a small reference table living in the pipeline's own
directory rather than fetched from anywhere. See CLAUDE.md for the population-weight
source/vintage."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

CITIES_CSV_PATH = Path(__file__).parent / "cities.csv"

EU_BASE = "c18"
US_BASE = "f65"


def load_cities(path: Path = CITIES_CSV_PATH) -> pd.DataFrame:
    return pd.read_csv(path)
