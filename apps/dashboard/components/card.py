"""Bordered "card" section wrapper -- the institutional look documented in root
CLAUDE.md's chart house style. Every chart section uses this instead of a bare
st.subheader, going forward."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st


@contextmanager
def card(title: str) -> Iterator[None]:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        yield
