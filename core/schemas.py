"""Canonical schemas for the data lake: ts_long (scalar time series) and flows (directional)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pyarrow as pa
from pydantic import BaseModel


class TsLongRecord(BaseModel):
    series_id: str
    source: str
    ts: datetime
    value: float
    unit: str
    geo: str
    freq: str
    revision_date: datetime


class FlowsRecord(BaseModel):
    source: str
    from_node: str
    to_node: str
    value: float
    unit: str
    ts: datetime
    mode: str


class EventsRecord(BaseModel):
    event_id: str
    ts: datetime
    headline: str
    source: str
    url: str
    tags: list[str]
    geo: str
    commodity: str
    severity: int
    language: str


class SanctionsRecord(BaseModel):
    sanction_id: str
    name: str
    entity_type: str
    programs: list[str]
    vess_type: str | None
    vess_flag: str | None
    vess_owner: str | None
    call_sign: str | None
    remarks: str | None
    imo: str | None
    first_seen: datetime
    last_seen: datetime
    status: str
    energy_related: bool


TS_LONG_SCHEMA = pa.schema(
    [
        pa.field("series_id", pa.string()),
        pa.field("source", pa.string()),
        pa.field("ts", pa.timestamp("us")),
        pa.field("value", pa.float64()),
        pa.field("unit", pa.string()),
        pa.field("geo", pa.string()),
        pa.field("freq", pa.string()),
        pa.field("revision_date", pa.timestamp("us")),
    ]
)

FLOWS_SCHEMA = pa.schema(
    [
        pa.field("source", pa.string()),
        pa.field("from_node", pa.string()),
        pa.field("to_node", pa.string()),
        pa.field("value", pa.float64()),
        pa.field("unit", pa.string()),
        pa.field("ts", pa.timestamp("us")),
        pa.field("mode", pa.string()),
    ]
)

EVENTS_SCHEMA = pa.schema(
    [
        pa.field("event_id", pa.string()),
        pa.field("ts", pa.timestamp("us")),
        pa.field("headline", pa.string()),
        pa.field("source", pa.string()),
        pa.field("url", pa.string()),
        pa.field("tags", pa.list_(pa.string())),
        pa.field("geo", pa.string()),
        pa.field("commodity", pa.string()),
        pa.field("severity", pa.int64()),
        pa.field("language", pa.string()),
    ]
)

SANCTIONS_SCHEMA = pa.schema(
    [
        pa.field("sanction_id", pa.string()),
        pa.field("name", pa.string()),
        pa.field("entity_type", pa.string()),
        pa.field("programs", pa.list_(pa.string())),
        pa.field("vess_type", pa.string()),
        pa.field("vess_flag", pa.string()),
        pa.field("vess_owner", pa.string()),
        pa.field("call_sign", pa.string()),
        pa.field("remarks", pa.string()),
        pa.field("imo", pa.string()),
        pa.field("first_seen", pa.timestamp("us")),
        pa.field("last_seen", pa.timestamp("us")),
        pa.field("status", pa.string()),
        pa.field("energy_related", pa.bool_()),
    ]
)


def _validate_columns(df: pd.DataFrame, schema: pa.Schema) -> None:
    required = set(schema.names)
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")

    # An unknown column is not harmless. `_write_partitioned` writes whatever columns the
    # frame carries, so it lands in the parquet file -- and `core.storage._typed_select`
    # then selects only the schema's own columns, so every reader silently never sees it.
    # A pipeline that misnames a column (`geo_code` for `geo`, say) would satisfy the
    # missing-column check via its own real `geo`, quietly write a dead column forever,
    # and give no signal anywhere. Nothing in the lake violates this today; the check
    # keeps it that way.
    unexpected = set(df.columns) - required
    if unexpected:
        raise ValueError(f"unexpected columns: {sorted(unexpected)}")

    numeric_cols = {"value"}
    datetime_cols = {
        name for name in schema.names if pa.types.is_timestamp(schema.field(name).type)
    }

    for col in numeric_cols & required:
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise ValueError(f"column {col!r} must be numeric, got dtype {df[col].dtype}")

    for col in datetime_cols:
        if not pd.api.types.is_datetime64_any_dtype(df[col]):
            raise ValueError(f"column {col!r} must be datetime, got dtype {df[col].dtype}")


def validate_ts_long(df: pd.DataFrame) -> None:
    _validate_columns(df, TS_LONG_SCHEMA)


def validate_flows(df: pd.DataFrame) -> None:
    _validate_columns(df, FLOWS_SCHEMA)


def validate_events(df: pd.DataFrame) -> None:
    _validate_columns(df, EVENTS_SCHEMA)


def validate_sanctions(df: pd.DataFrame) -> None:
    _validate_columns(df, SANCTIONS_SCHEMA)
