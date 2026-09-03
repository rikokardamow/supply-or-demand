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


def _validate_columns(df: pd.DataFrame, schema: pa.Schema) -> None:
    required = set(schema.names)
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")

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
