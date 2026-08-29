"""Kardamow one-liner captions — a short in-voice read placed under each chart.

These are static text, written by hand (via the one-liner-kardamow skill) from a
snapshot of the lake's current values. They go stale as new data lands — re-generate
and re-paste the affected lines after a pull moves the numbers enough to matter,
rather than treating them as live commentary."""

from __future__ import annotations

import streamlit as st


def kardamow_take(text: str) -> None:
    st.caption(f"🖋️ **Kardamow take:** {text}")
