"""Build step for the publishing layer.

    python -m apps.artifacts.build [--lake data/lake] [--pages dashboard ...] [--skip-office]

Reads the local lake, writes one compact JSON per page under `apps/artifacts/dist/`,
renders three self-contained HTML pages from `templates/` (data, styles and chart code
inlined; Plotly is the only external script), and writes the Excel and PowerPoint
exports. Fails rather than ships if a `.env` value appears in any output or a page
outgrows its size budget. Publishing the pages is a separate step -- see artifacts.md.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import io
import json
import os
import sys
import zipfile
from contextlib import suppress
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final
from urllib.parse import quote, unquote, urlsplit

import pandas as pd
from core.settings import Settings
from dotenv import dotenv_values

from . import exhibits, tables
from .exhibits import Book

HERE: Final = Path(__file__).parent
DIST: Final = HERE / "dist"
EXPORTS: Final = Path("exports")
PAGES: Final = ("dashboard", "briefing", "motion")
PAGE_BUDGET_BYTES: Final = 4 * 1024 * 1024
MIN_SECRET_LENGTH: Final = 8
SECRET_NAME_PARTS: Final = (
    "KEY",
    "TOKEN",
    "SECRET",
    "PASS",
    "PWD",
    "DSN",
    "CREDENTIAL",
    "AUTH",
    "DB_URL",
    "DATABASE_URL",
)
# The project's own credentials. The leak check only counts as armed when it holds at
# least one of these -- an unrelated token in the shell is not something to compare with.
PROJECT_CREDENTIALS: Final = frozenset(
    name.upper()
    for name in Settings.model_fields
    if any(part in name.upper() for part in SECRET_NAME_PARTS)
)
KPI_EXHIBITS: Final = [
    "crude_stocks",
    "cushing",
    "eu_storage",
    "us_gas_storage",
    "brent_wti",
    "cracks",
]


class SecretLeakError(RuntimeError):
    """An output file contains a value from `.env`."""


class NoSecretsToCheckError(RuntimeError):
    """No credential was found, so the leak check would have compared against nothing."""


class NothingToPublishError(RuntimeError):
    """The lake cannot support a page; publishing an empty one would hide that."""


class PageTooLargeError(RuntimeError):
    """A rendered page exceeds `PAGE_BUDGET_BYTES`."""


def meta(book: Book, built_at: datetime) -> dict[str, Any]:
    """Header facts: when this build ran and which pipeline runs its rows came from."""
    runs: list[pd.Timestamp] = []
    for frame in book.series_long:
        if frame.empty or frame["revision_date"].isna().all():
            continue
        runs.extend(pd.to_datetime(frame.groupby("series_id")["revision_date"].max()).tolist())
    return {
        "built_at": built_at.strftime("%Y-%m-%d %H:%M UTC"),
        "newest_run": exhibits.day(max(runs)) if runs else None,
        "oldest_run": exhibits.day(min(runs)) if runs else None,
        "stale": sum(1 for e in book.exhibits if e["gap"]),
        "exhibits": len(book.exhibits),
    }


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for row in frame.to_dict("records"):
        clean: dict[str, Any] = {}
        for key, value in row.items():
            if value is None or value is pd.NaT or (isinstance(value, float) and pd.isna(value)):
                clean[str(key)] = None
            elif isinstance(value, (pd.Timestamp, datetime, date)):
                clean[str(key)] = exhibits.day(value)
            elif isinstance(value, float):
                clean[str(key)] = round(value, 2)
            else:
                clean[str(key)] = value
        out.append(clean)
    return out


def motion_payload(head: dict[str, Any], today: date) -> dict[str, Any]:
    weekly = tables.storage_weekly()
    if weekly.empty or "EU" not in weekly:
        raise NothingToPublishError("motion page: no AGSI+ fullness rows for the EU in the lake")
    countries = [c for c in weekly.columns if c != "EU"]
    run = tables.pulled_at("ts_long", "gie")
    through = weekly.index.max()
    return {
        "meta": head,
        "dates": [d.strftime("%Y-%m-%d") for d in weekly.index],
        "countries": countries,
        "values": {
            c: [None if pd.isna(v) else round(float(v), 1) for v in weekly[c]] for c in countries
        },
        "eu": [None if pd.isna(v) else round(float(v), 1) for v in weekly["EU"]],
        "unit": "% full",
        "source": (
            "Source: GIE AGSI+ · lake table ts_long/gie (agsi.<country>.full_pct) · "
            f"data to {exhibits.day(through)} · pipeline run "
            f"{exhibits.day(run) if run else 'not recorded'}"
        ),
        "gap": exhibits.stale_flag(through, 2, today),
        "note": "Sampled each Monday, plus the latest day.",
    }


def payloads(book: Book, built_at: datetime) -> dict[str, dict[str, Any]]:
    head = meta(book, built_at)
    slides = [e for i in exhibits.BRIEFING_ORDER for e in book.exhibits if e["id"] == i]
    return {
        "dashboard": {
            "meta": head,
            "tabs": [{"id": i, "label": label} for i, label in exhibits.TABS],
            "kpis": [e["stat"] for i in KPI_EXHIBITS for e in book.exhibits if e["id"] == i],
            "exhibits": book.exhibits,
            "wpsr": _records(book.sheets["wpsr_lines"]),
            "status": _records(book.sheets["freshness"]),
            "gaps": [{"output": o, "state": s} for o, s in exhibits.KNOWN_GAPS],
            "issues": book.issues,
        },
        "briefing": {"meta": head, "slides": slides},
        "motion": motion_payload(head, built_at.date()),
    }


def render(page: str, payload: dict[str, Any]) -> str:
    """Inline the payload, the shared stylesheet and the shared chart code into a page."""
    # Escaped for the HTML the JSON sits in, not just for "</script>": "<!--<script>"
    # inside a script element makes the parser swallow the real closing tag.
    data = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    for char in ("<", ">", "&", "\u2028", "\u2029"):
        data = data.replace(char, f"\\u{ord(char):04x}")
    html = (HERE / "templates" / f"{page}.html").read_text(encoding="utf-8")
    return (
        html.replace("/*__BASE_CSS__*/", (HERE / "static" / "base.css").read_text(encoding="utf-8"))
        .replace("/*__CHARTS_JS__*/", (HERE / "static" / "charts.js").read_text(encoding="utf-8"))
        .replace("/*__DATA__*/", data)
    )


def env_secrets(paths: list[Path]) -> dict[str, set[bytes]]:
    """Every credential-length value a variable holds, across each `.env` and the shell.

    All of a name's values are kept, not one: the shell overrides `.env` for
    `core.settings`, so the live credential may be the exported one while `.env` still
    holds a rotated-out value, and two `.env` files may disagree. Values are only ever
    compared against output bytes -- never printed or logged.

    `.env` is read with python-dotenv, the parser `core.settings` itself uses, so quotes
    and trailing comments are stripped exactly as they are for the live value."""
    found: dict[str, set[bytes]] = {}
    for path in paths:
        if not path.is_file():
            continue
        for name, value in dotenv_values(path).items():
            if value and len(value) >= MIN_SECRET_LENGTH:
                found.setdefault(name, set()).update(needles(value))
    for name, value in os.environ.items():
        # Credentials exported into the shell rather than written to .env.
        if (
            any(part in name.upper() for part in SECRET_NAME_PARTS)
            and len(value) >= MIN_SECRET_LENGTH
        ):
            found.setdefault(name, set()).update(needles(value))
    return found


def needles(value: str) -> set[bytes]:
    """The byte forms one credential could take inside an output: as written, JSON-escaped
    (pages), XML/HTML-escaped (Office members), URL-encoded and base64. A connection
    string's password is searched for on its own as well."""
    forms = {value}
    if "://" in value:
        with suppress(ValueError):
            password = urlsplit(value).password
            if password and len(password) >= MIN_SECRET_LENGTH:
                forms |= {password, unquote(password)}
    out: set[bytes] = set()
    for form in forms:
        raw = form.encode("utf-8")
        out |= {
            raw,
            json.dumps(form)[1:-1].encode("utf-8"),
            json.dumps(form, ensure_ascii=False)[1:-1].encode("utf-8"),
            html.escape(form).encode("utf-8"),
            html.escape(form, quote=False).encode("utf-8"),
            quote(form, safe="").encode("utf-8"),
            base64.b64encode(raw),
        }
    return out


def _unzipped(blob: bytes) -> list[bytes]:
    """A blob and, when it is a zip (an Office file, or a workbook embedded in one), every
    member inside it."""
    if not zipfile.is_zipfile(io.BytesIO(blob)):
        return [blob]
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        return [inner for name in archive.namelist() for inner in _unzipped(archive.read(name))]


def discard(outputs: list[Path]) -> list[Path]:
    """Remove this build's outputs and return any that could not be removed (a file held
    open elsewhere, such as a workbook in Excel). A survivor has not passed the leak
    check, so callers must name it rather than let the failure pass quietly."""
    survivors = []
    for path in outputs:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            survivors.append(path)
    return survivors


def _left_behind(survivors: list[Path]) -> str:
    if not survivors:
        return "every output of this build was deleted"
    names = ", ".join(str(path) for path in survivors)
    return f"COULD NOT DELETE {names} -- close and delete by hand; do not publish or share"


def assert_no_secrets(outputs: list[Path], secrets: dict[str, set[bytes]]) -> None:
    """Scan every output before acting on any: a page and its JSON hold the same payload,
    so stopping at the first hit would leave the other on disk ready to publish."""
    hits: dict[str, list[str]] = {}
    for path in outputs:
        blobs = _unzipped(path.read_bytes())
        leaked = sorted(
            name
            for name, values in secrets.items()
            if any(value in blob for value in values for blob in blobs)
        )
        if leaked:
            hits[path.name] = leaked
    if hits:
        raise SecretLeakError(
            f"outputs contained credential values {hits}; {_left_behind(discard(outputs))}"
        )


def write_manifest(built: dict[str, dict[str, Any]], book: Book) -> list[str]:
    """Record what this build produced and return a plain-English diff against the last."""
    path = DIST / "manifest.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    current: dict[str, dict[str, Any]] = {
        "pages": {
            page: hashlib.sha256(
                # `meta` and `status` carry the build clock, so they change on every run.
                json.dumps(
                    {k: v for k, v in data.items() if k not in ("meta", "status")}, sort_keys=True
                ).encode()
            ).hexdigest()
            for page, data in built.items()
        },
        "exhibits": {e["id"]: {"source": e["source"], "gap": e["gap"]} for e in book.exhibits},
    }
    changes = [
        f"page {page}: data changed"
        for page, digest in current["pages"].items()
        if previous.get("pages", {}).get(page) != digest
    ]
    before = previous.get("exhibits", {})
    for exhibit_id, now in current["exhibits"].items():
        if exhibit_id not in before:
            changes.append(f"exhibit {exhibit_id}: new")
        elif before[exhibit_id] != now:
            changes.append(f"exhibit {exhibit_id}: {now['source'].split(' · ', 2)[-1]}")
    changes.extend(f"exhibit {gone}: removed" for gone in before if gone not in current["exhibits"])
    path.write_text(json.dumps(current, indent=1, sort_keys=True), encoding="utf-8")
    return changes


def write_outputs(
    args: argparse.Namespace, book: Book, built: dict[str, dict[str, Any]], outputs: list[Path]
) -> None:
    """Write every page and export, recording each path in `outputs` before it is written
    so a failure part-way still leaves the caller a complete list to discard."""
    DIST.mkdir(exist_ok=True)
    for page in args.pages:
        json_path, html_path = DIST / f"{page}.json", DIST / f"{page}.html"
        outputs += [json_path, html_path]
        json_path.write_text(
            json.dumps(built[page], separators=(",", ":"), allow_nan=False), encoding="utf-8"
        )
        html_path.write_text(render(page, built[page]), encoding="utf-8")
        size = html_path.stat().st_size
        if size > PAGE_BUDGET_BYTES:
            raise PageTooLargeError(f"{html_path.name} is {size:,} bytes")
        print(f"{html_path.name}: {size / 1024:,.0f} KiB", flush=True)

    if not args.skip_office:
        from . import office

        EXPORTS.mkdir(exist_ok=True)
        outputs += [EXPORTS / office.WORKBOOK_NAME, EXPORTS / office.DECK_NAME]
        office.write_workbook(book, built["dashboard"]["meta"], EXPORTS)
        office.write_deck(built["briefing"], EXPORTS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lake", type=Path, default=Path("data/lake"))
    parser.add_argument("--pages", nargs="+", choices=PAGES, default=list(PAGES))
    parser.add_argument("--skip-office", action="store_true")
    parser.add_argument(
        "--allow-missing-env",
        action="store_true",
        help="build even when no credential is found to check outputs against (CI)",
    )
    args = parser.parse_args(argv)

    lake = args.lake.resolve()
    if not (lake / "ts_long").is_dir():
        print(f"no lake at {lake}", flush=True)
        return 1
    tables.use_lake(lake)
    built_at = datetime.now(UTC)
    book = exhibits.build(built_at.date())
    if not book.exhibits:
        raise NothingToPublishError(f"no exhibit could be built from {lake}")
    built = payloads(book, built_at)

    outputs: list[Path] = []
    try:
        write_outputs(args, book, built, outputs)
        # Judged on what there is to compare against, not on a file merely existing: an
        # empty or all-placeholder .env, or an unrelated token in the shell, would
        # otherwise wave every output through.
        secrets = env_secrets([Path(".env"), lake.parent.parent / ".env"])
        if not (PROJECT_CREDENTIALS & secrets.keys()) and not args.allow_missing_env:
            raise NoSecretsToCheckError(
                "none of this project's credentials found in .env (working directory or "
                "beside the lake) or the shell, so the leak check had nothing to compare; "
                "outputs deleted. Pass --allow-missing-env if this checkout genuinely "
                "holds no credentials."
            )
        assert_no_secrets(outputs, secrets)
    except BaseException:
        # Whatever stopped the build, nothing it wrote has passed the leak check.
        print(f"build failed: {_left_behind(discard(outputs))}", file=sys.stderr, flush=True)
        raise

    changes = write_manifest(built, book)
    print(f"{len(book.exhibits)} exhibits, {built['dashboard']['meta']['stale']} stale", flush=True)
    for line in changes or ["no data changes since the last build"]:
        print(f"changed: {line}", flush=True)
    for issue in book.issues:
        print(f"issue: {issue}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
