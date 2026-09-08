"""Kardamow Energy Dashboard entrypoint: masthead, then the selected page.

Page content lives in pages/ -- this file owns only the chrome. The masthead mirrors
kardamow.substack.com: a centred wordmark over a hairline, with grouped navigation
beneath it (st.navigation, position="top") in place of the filename-derived sidebar.
The wordmark is the document's only <h1> -- page_header() paints each page's own title as
<h2> and section() paints <h3>, giving every page one valid descending outline with
"Kardamow" at its top.

Two ordering constraints: st.set_page_config must be the first Streamlit call, and
nav.build().run() must be the last -- it is what executes the selected page.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Kardamow Energy Dashboard", layout="wide")

import nav  # noqa: E402  -- must follow set_page_config
from core.design import HEADING_STACK, RULE, TEXT  # noqa: E402

st.markdown(
    f'<h1 style="text-align:center;font-family:{HEADING_STACK};font-size:3.25rem;'
    f'font-weight:600;color:{TEXT};margin:0;padding:0.4rem 0 0.7rem">Kardamow</h1>'
    f'<hr style="border:0;border-top:1px solid {RULE};margin:0 0 0.4rem">',
    unsafe_allow_html=True,
)

nav.build().run()
