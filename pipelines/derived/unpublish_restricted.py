"""Remove licence-restricted rows that are already on the serving layer (I-02).

`core.publish.publish()` now keeps class d data from reaching `serving.*`
(`core/rights.py`, `RIGHTS.md`), but upserts only add: rows published before the guard
existed stay readable by the anonymous role until something deletes them. This is that
something. It builds the list of what the register says must not be there, counts it, and,
only with `--apply`, deletes it.

    uv run python -m pipelines.derived.unpublish_restricted            # dry run
    uv run python -m pipelines.derived.unpublish_restricted --apply    # delete

**Dry run is the default and the only thing that ran during the build.** It reads the local
lake (to list the series of class d sources, including `derived` series that trace to one)
and the rights register, then counts matching rows with `select count(*)` on the connection
in `settings.supabase_db_url`. With no connection string it prints the plan and stops.

**Running it for real is the owner's call.** Nothing in the build session connected to a
database, ran a dry run against one, or applied it; the tests use a fake connection. Read
the dry-run counts first. The tables it can empty are `series_long`, `seasonal`, `flows`,
`events`, and whole `curve_settles`, `vessel_latest` and `sanctions` (each fed only by a
class d source: manual vendor data, aisstream, OFAC).

`--apply` runs in one transaction: for each target it counts again, deletes, and checks
that the delete removed exactly the rows it counted (a mismatch rolls everything back),
then appends one `publish_log` row per table with the table's own latest `as_of` so the
staleness badge does not move, and commits once. It never touches a table the register
does not list.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

import pandas as pd
import psycopg
from core.publish import _revalidate
from core.rights import (
    RESTRICTED_CLASSES,
    RESTRICTED_SERIES,
    SOURCE_CLASS,
    series_class,
)
from core.settings import settings
from core.storage import warehouse

PIPELINE: Final = "unpublish_restricted"

# Serving tables with a `source` column (supabase/migrations): rows are selected by it.
SOURCE_COLUMN_TABLES: Final = ("series_long", "flows", "events")

# Serving tables keyed by series id, which the series-level rules and lake lists reach.
SERIES_TABLES: Final = ("series_long", "seasonal")

# Tables fed by exactly one source: class d for that source empties the whole table.
ONE_SOURCE_TABLES: Final = {
    "curve_settles": "manual",
    "vessel_latest": "ais",
    "sanctions": "ofac",
}


class DeleteMismatchError(RuntimeError):
    """A DELETE removed a different number of rows than the count taken just before it."""


@dataclass(frozen=True)
class Target:
    """One set of rows to remove: a table, a SQL condition and its parameters."""

    table: str
    where: str
    params: tuple[Any, ...]
    label: str


@dataclass(frozen=True)
class Result:
    would_remove: int
    removed: int


def lake_series() -> pd.DataFrame:
    """Every `(source, series_id)` pair in the local lake's `ts_long`."""
    frame: pd.DataFrame = warehouse().execute(
        "select distinct source, series_id from ts_long"
    ).df()
    return frame


def build_targets(lake: pd.DataFrame) -> list[Target]:
    """What the rights register says must not be on the serving layer.

    An unregistered source in the lake raises `UnregisteredSourceError`: the register has
    to know every source before anything is deleted on its say-so.
    """
    class_d_sources = sorted(s for s, c in SOURCE_CLASS.items() if c in RESTRICTED_CLASSES)
    class_d_ids = sorted(
        {
            str(series_id)
            for source, series_id in zip(lake["source"], lake["series_id"], strict=True)
            if series_class(str(source), str(series_id)) in RESTRICTED_CLASSES
        }
    )

    targets: list[Target] = []
    for table in SERIES_TABLES:
        for pattern in RESTRICTED_SERIES:
            targets.append(Target(table, "series_id ~ %s", (pattern.pattern,), pattern.pattern))
    for table in SOURCE_COLUMN_TABLES:
        targets.append(
            Target(
                table,
                "source = any(%s)",
                (class_d_sources,),
                f"source of class d ({len(class_d_sources)} sources)",
            )
        )
    if class_d_ids:
        for table in SERIES_TABLES:
            targets.append(
                Target(
                    table,
                    "series_id = any(%s)",
                    (class_d_ids,),
                    f"lake series of class d ({len(class_d_ids)} series)",
                )
            )
    for table, source in ONE_SOURCE_TABLES.items():
        if SOURCE_CLASS[source] in RESTRICTED_CLASSES:
            targets.append(Target(table, "true", (), f"whole table, fed only by {source}"))
    return targets


def _count(cur: Any, target: Target) -> int:
    cur.execute(
        f"select count(*) from serving.{target.table} where {target.where}", target.params
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def run(*, apply: bool) -> Result:
    targets = build_targets(lake_series())
    db_url = settings.supabase_db_url

    if not db_url:
        if apply:
            raise SystemExit("--apply needs SUPABASE_DB_URL; nothing was changed")
        print("SUPABASE_DB_URL not configured: printing the plan without counts.")
        for t in targets:
            print(f"  {t.label} -> serving.{t.table} where {t.where}")
        return Result(would_remove=0, removed=0)

    with psycopg.connect(db_url, prepare_threshold=None) as conn, conn.cursor() as cur:
        counts = [(t, _count(cur, t)) for t in targets]
        for t, n in counts:
            print(f"{t.label}: {n} rows in {t.table}")
        would_remove = sum(n for _, n in counts)

        if not apply:
            print(
                f"dry run: {would_remove} row-matches would be removed (a row matched by two"
                " targets counts twice here). Nothing changed; add --apply to delete."
            )
            return Result(would_remove=would_remove, removed=0)
        if would_remove == 0:
            print("nothing to remove")
            return Result(would_remove=0, removed=0)

        removed_by_table: dict[str, int] = defaultdict(int)
        for t, n in counts:
            if n == 0:
                continue
            # Count again just before the delete: an earlier target may already have
            # removed some of these rows, and the check is against this delete's own count.
            expected = _count(cur, t)
            if expected == 0:
                continue
            cur.execute(f"delete from serving.{t.table} where {t.where}", t.params)
            if cur.rowcount != expected:
                raise DeleteMismatchError(
                    f"serving.{t.table} ({t.label}): counted {expected}, deleted"
                    f" {cur.rowcount}; rolled back, nothing was removed"
                )
            removed_by_table[t.table] += expected

        for table, n in removed_by_table.items():
            cur.execute(
                "select max(as_of) from serving.publish_log where table_name = %s", (table,)
            )
            row = cur.fetchone()
            last_as_of = row[0] if row else None
            if last_as_of is None:
                continue  # a table that was never logged has no staleness clock to keep
            cur.execute(
                "insert into serving.publish_log"
                " (table_name, as_of, source_note, row_count, pipeline)"
                " values (%s, %s, %s, %s, %s)",
                (table, last_as_of, f"unpublished {n} licence-restricted rows", 0, PIPELINE),
            )
        conn.commit()

    removed = sum(removed_by_table.values())
    for table, n in removed_by_table.items():
        print(f"deleted {n} rows from serving.{table}")
        _revalidate(table)
    return Result(would_remove=would_remove, removed=removed)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="delete the rows (default is a dry run that only counts and prints)",
    )
    args = parser.parse_args(argv)
    run(apply=args.apply)


if __name__ == "__main__":
    main()
