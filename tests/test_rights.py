"""The rights register and the publish guard's classification rules (I-01).

PROJECT-STARTER section 6: classes a to d, class d is private only, and a source whose
terms have not been read at source is class d.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pandas as pd
import pytest
from core import rights
from core.rights import (
    DISPUTED_SOURCES,
    RIGHTS,
    SOURCE_CLASS,
    UnregisteredSourceError,
    drop_restricted,
    series_class,
)

ROOT = Path(__file__).resolve().parent.parent

# Sources that cannot be found by reading the pipelines' keyword arguments: `ais` is a
# publish label for the AIS compactor, `ibkr` is a value of `settings.futures_source`.
EXTRA_SOURCES = {"ais", "ibkr"}


def _sources_written_by_pipelines() -> set[str]:
    """Every source id the pipelines name: `source=` and `platform=` keyword arguments,
    `"source": "x"` dict entries, and `*SOURCE = "x"` constants, read from the syntax
    tree so a comment or a docstring can never count."""
    found: set[str] = set()
    for path in (ROOT / "pipelines").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.keyword)
                and node.arg in {"source", "platform"}
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                found.add(node.value.value)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "source"
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                    ):
                        found.add(value.value)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id.endswith("SOURCE")
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, str)
                    ):
                        found.add(node.value.value)
    return found


def test_every_source_the_pipelines_write_has_a_class() -> None:
    written = _sources_written_by_pipelines() | EXTRA_SOURCES
    assert written, "the scan found nothing, so it is broken"
    assert written - set(SOURCE_CLASS) == set()


def test_classes_are_a_b_c_d_or_inherit() -> None:
    assert set(SOURCE_CLASS.values()) <= {"a", "b", "c", "d", "inherit"}
    assert [s for s, c in SOURCE_CLASS.items() if c == "inherit"] == ["derived"]


def test_yahoo_closes_and_manual_vendor_drops_are_class_d() -> None:
    # pipelines/futures/NOTES.md:330 and pipelines/manual_physical/NOTES.md:32.
    assert SOURCE_CLASS["yfinance"] == "d"
    assert SOURCE_CLASS["manual"] == "d"


def test_a_class_above_d_has_its_terms_read_at_source_unless_disputed() -> None:
    """Rule: a source's class above d needs its terms read at source, dated and signed.
    The six sources in dispute (I-06) are the one named exception, held at the reading the
    README gave them until the owner decides."""
    for source, row in RIGHTS.items():
        if row.cls in {"a", "b", "c"} and source not in DISPUTED_SOURCES:
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", row.read_on), source
            assert row.read_by.startswith("improve run-01"), source
            assert row.terms_url.startswith("https://"), source
    assert set(DISPUTED_SOURCES) == {"gie", "entsoe", "entsog", "fred", "opec_momr", "baker_hughes"}
    for source in DISPUTED_SOURCES:
        assert RIGHTS[source].owner_class == "d"
        assert RIGHTS[source].read_on == ""


def test_rights_md_is_the_rendering_of_the_register() -> None:
    assert (ROOT / "RIGHTS.md").read_text() == rights.render_markdown()


# --- series_class: how `derived` inherits ------------------------------------------


@pytest.mark.parametrize(
    ("series_id", "expected"),
    [
        ("derived.ma.cl.50", "d"),  # a moving average of the Yahoo closes
        ("derived.cushing.util_decile", "b"),  # EIA stocks and capacity
        ("derived.inv.dev_z.uscrude", "b"),
        ("derived.cot.cl.mm_pct_3y", "b"),  # CFTC
        ("derived.crack.us321.m1", "b"),  # EIA futures ranks
        ("derived.spread.cl.s12", "b"),
        ("derived.pos.carry.cl", "b"),
        ("derived.unmapped.thing", "d"),  # no input mapping: unknown means unread
    ],
)
def test_derived_series_inherit_the_class_of_their_inputs(series_id: str, expected: str) -> None:
    assert series_class("derived", series_id) == expected


def test_derived_spot_cracks_follow_fred_which_is_held_at_the_readme_reading() -> None:
    assert series_class("derived", "derived.crack.us321.spot") == SOURCE_CLASS["fred"]


def test_a_non_derived_source_ignores_the_series_id() -> None:
    assert series_class("eia", "anything") == "b"


def test_series_class_of_an_unknown_source_raises() -> None:
    with pytest.raises(UnregisteredSourceError):
        series_class("mystery", "x")


# --- drop_restricted -----------------------------------------------------------------


def _frame(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": [r[0] for r in rows],
            "source": [r[1] for r in rows],
            "ts": pd.to_datetime(["2026-10-01"] * len(rows)),
            "value": [1.0] * len(rows),
        }
    )


def test_drop_restricted_removes_class_d_rows_and_names_them() -> None:
    kept, dropped = drop_restricted(
        _frame([("WCESTUS1", "eia"), ("fut.cl.f01.close", "yfinance"), ("x", "manual")]),
        "series_long",
        pipeline=None,
    )
    assert list(kept["series_id"]) == ["WCESTUS1"]
    assert dropped == {"fut.cl.f01.close": 1, "x": 1}


def test_a_restricted_series_id_is_dropped_whatever_its_source_says() -> None:
    kept, dropped = drop_restricted(
        _frame([("fut.ng.f01.close", "eia"), ("fut.ng.f01.settle", "eia")]),
        "series_long",
        pipeline=None,
    )
    assert list(kept["series_id"]) == ["fut.ng.f01.settle"]
    assert dropped == {"fut.ng.f01.close": 1}


@pytest.mark.parametrize(
    "series_id",
    [
        "fut.cl.f01.close",
        "fut.lco.f01.close",
        "fut.ng.f01.close",
        "derived.ma.cl.200",
        "eex.eua.auction",
        "derived.eu_carbon.price.eua",
        "derived.eu_carbon.balance.net",
    ],
)
def test_restricted_series_patterns(series_id: str) -> None:
    assert any(p.search(series_id) for p in rights.RESTRICTED_SERIES)


@pytest.mark.parametrize(
    "series_id", ["fut.cl.f01.settle", "fut.cl.f02.close_adj", "WCESTUS1", "derived.cushing.util"]
)
def test_restricted_series_patterns_do_not_catch_clean_series(series_id: str) -> None:
    assert not any(p.search(series_id) for p in rights.RESTRICTED_SERIES)


def test_an_unregistered_source_raises() -> None:
    with pytest.raises(UnregisteredSourceError, match="mystery"):
        drop_restricted(_frame([("x", "mystery")]), "series_long", pipeline=None)


def test_a_missing_source_value_raises() -> None:
    frame = _frame([("x", "eia")])
    frame.loc[0, "source"] = None
    with pytest.raises(UnregisteredSourceError):
        drop_restricted(frame, "series_long", pipeline=None)


def test_a_frame_with_no_source_and_no_pipeline_cannot_be_classified() -> None:
    frame = _frame([("x", "eia")]).drop(columns="source")
    with pytest.raises(UnregisteredSourceError, match="cannot tell"):
        drop_restricted(frame, "seasonal", pipeline=None)


@pytest.mark.parametrize(
    ("pipeline", "table", "expected_kept"),
    [
        ("wpsr", "seasonal", 1),  # the WPSR pipeline is EIA
        ("gie", "seasonal", 1),
        ("cftc", "series_long", 1),
        ("yfinance", "seasonal", 0),  # Yahoo
        ("ais", "vessel_latest", 0),  # aisstream: terms not read
        ("curve", "spreads", 1),  # rank-based EIA settles
        ("curve", "curve_settles", 0),  # contract-coded vendor reconstruction
        ("manual", "series_long", 0),
        ("eia", "series_long", 1),  # the sweep passes the source id as the label
    ],
)
def test_a_pipeline_label_names_its_source_when_the_frame_has_no_source_column(
    pipeline: str, table: str, expected_kept: int
) -> None:
    frame = pd.DataFrame({"series_id": ["agsi.EU.full_pct"], "value": [1.0]})
    kept, _ = drop_restricted(frame, table, pipeline=pipeline)
    assert len(kept) == expected_kept


def test_a_neutral_label_needs_a_source_column() -> None:
    frame = pd.DataFrame({"mode": ["pipeline"], "value": [1.0]})
    with pytest.raises(UnregisteredSourceError):
        drop_restricted(frame, "flows", pipeline="flows")


def test_an_unknown_pipeline_label_raises() -> None:
    frame = pd.DataFrame({"series_id": ["x"], "value": [1.0]})
    with pytest.raises(UnregisteredSourceError, match="nonsense"):
        drop_restricted(frame, "series_long", pipeline="nonsense")


def test_events_rows_are_judged_by_their_own_source_column() -> None:
    events = pd.DataFrame(
        {
            "event_id": ["1", "2", "3"],
            "source": ["gdelt", "newsapi", "reddit"],
            "headline": ["a", "b", "c"],
        }
    )
    kept, dropped = drop_restricted(events, "events", pipeline="events")
    assert list(kept["source"]) == ["gdelt"]
    assert dropped == {"source=newsapi": 1, "source=reddit": 1}


def test_an_empty_frame_passes_through() -> None:
    kept, dropped = drop_restricted(_frame([]), "series_long", pipeline=None)
    assert kept.empty and dropped == {}
