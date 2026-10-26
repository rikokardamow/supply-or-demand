"""`apps/dash_app`: every page renders from the shared views, empty lake and seeded lake.
All figures synthetic; seeding reuses the Streamlit page tests' helpers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import plotly
import pytest

REPO_ROOT = Path(__file__).parent.parent
for path in (REPO_ROOT / "apps" / "dashboard", REPO_ROOT / "apps", Path(__file__).parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture
def isolated_lake(tmp_path, monkeypatch):
    from core import storage

    monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path / "lake")
    return storage


@pytest.fixture
def dash_app() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "dash_app_main", REPO_ROOT / "apps/dash_app/app.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _text(component: object) -> str:
    return json.dumps(component, cls=plotly.utils.PlotlyJSONEncoder)


def test_the_real_dash_library_is_not_shadowed(dash_app) -> None:
    import dash

    assert "site-packages" in (dash.__file__ or "")
    assert dash_app.create_app().title == "Kardamow Energy Dashboard"


@pytest.mark.parametrize(
    ("slug", "command"),
    [
        ("eu_gas_balance", "pipelines.eurostat_gas.pull"),
        ("uk_gas_balance", "pipelines.desnz_gas.pull"),
        ("eu_carbon", "pipelines.carbon.pull"),
        ("lng", "pipelines.eia.pull_lng_exports"),
    ],
)
def test_an_empty_lake_names_the_command_on_every_page(isolated_lake, dash_app, slug, command):
    text = _text(dash_app.page_layout(f"/{slug}"))

    assert command in text
    assert "No data" in text


def test_an_unknown_path_falls_back_to_the_first_page(isolated_lake, dash_app) -> None:
    assert "EU Gas Balance" in _text(dash_app.page_layout("/nowhere"))
    assert "EU Gas Balance" in _text(dash_app.page_layout("/"))


def test_seeded_pages_carry_the_same_words_as_streamlit(isolated_lake, dash_app) -> None:
    import test_pages_eu_carbon as carbon
    import test_pages_eu_gas_balance as eu_gas
    import test_pages_uk_gas_balance as uk_gas

    eu_gas._seed(isolated_lake)
    uk_gas._seed(isolated_lake)
    carbon._seed(isolated_lake)

    eu = _text(dash_app.page_layout("/eu_gas_balance"))
    uk = _text(dash_app.page_layout("/uk_gas_balance"))
    co2 = _text(dash_app.page_layout("/eu_carbon"))

    assert "An assumption, not a forecast" in eu and "DataTable" in eu and '"Graph"' in eu
    assert "2026 9.0 bcm" in uk  # the same projected total the Streamlit test pins
    assert "auction clearing price, not" in co2 and "2025 is still being reported" in co2
