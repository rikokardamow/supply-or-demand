"""Macro/FX Overlay (Spec 10, Session C): the four visuals from the spec's own
visualisation spec -- broad dollar vs. WTI, real-vs-nominal crude (indexed 2018=100),
energy-in-EUR-vs-USD small multiples, and an ESI heat-strip by country.

Visual 1 uses WTI directly from pipelines/macro (FRED) rather than a Spec-07-sourced
crude price -- Spec 07 (refinery cracks, needs a local IB Gateway) is still deferred,
and FRED's own WTI series (pulled since Session A) makes the spec's own "placeholder
until then" note moot: this is real data, not a placeholder.

Also carries Spec 17's Adanos sentiment overlay (see `_adanos_sentiment_section`) --
a separate, independent data source sharing this page rather than getting its own,
per that spec's own visualisation-spec text."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.card import card
from components.kardamow_take import kardamow_take
from core.macro import deflate, index_to, to_currency
from core.sentiment import (
    DEFAULT_CORRELATION_WINDOW,
    Overlap,
    agreement_rate,
    disagrees_on_sign,
    overlap,
    rolling_correlation,
)
from core.storage import read_ts_long
from core.theme import (
    GREY,
    LIGHT_BLUE,
    NAVY,
    RED,
    category_time_heatmap,
    dual_axis_chart,
    simple_time_series_chart,
)
from pipelines.adanos.tickers import PLATFORMS, TICKERS
from pipelines.social.queries import TICKER_QUERIES, TOPIC_QUERIES

INDEX_BASE_PERIOD = "2018-01-01"
RANGE_DAYS = {"1Y": 365, "3Y": 1095, "5Y": 1825, "10Y": 3650, "All": None}

ENERGY_SMALL_MULTIPLES = [
    ("fred.dcoilwtico", "WTI Crude", "$/bbl"),
    ("fred.dcoilbrenteu", "Brent Crude", "$/bbl"),
    ("fred.dhhngsp", "Henry Hub Gas", "$/MMBtu"),
]
ESI_GEOS = ["EU", "DE", "FR", "IT", "ES", "IE"]


def _series_by_ts(series_id: str) -> pd.Series:
    df = read_ts_long(series_ids=[series_id]).sort_values("ts")
    return df.set_index("ts")["value"]


def _trim_recent(series: pd.Series, days: int | None) -> pd.Series:
    if days is None or series.empty:
        return series
    cutoff = series.index.max() - pd.Timedelta(days=days)
    result: pd.Series = series[series.index >= cutoff]
    return result


def _dollar_vs_wti_section(days: int | None) -> None:
    dollar = _trim_recent(_series_by_ts("fred.dtwexbgs"), days)
    wti = _trim_recent(_series_by_ts("fred.dcoilwtico"), days)
    if dollar.empty or wti.empty:
        st.info("No data yet — run `pipelines/macro/pull_macro.py`.")
        return

    title = "Broad USD Index vs. WTI Crude"
    fig = dual_axis_chart(
        dollar,
        wti,
        title=title,
        left_label="Broad USD Index (Jan 2006=100)",
        right_label="WTI ($/bbl)",
    )
    with card(title):
        st.plotly_chart(fig)
        kardamow_take(
            "A stronger dollar is a headwind for dollar-priced crude almost "
            "mechanically — this is the chart that separates a real demand story "
            "from a currency one before either gets treated as the explanation."
        )


def _real_vs_nominal_section(days: int | None) -> None:
    wti = _series_by_ts("fred.dcoilwtico")
    cpi = _series_by_ts("fred.cpiaucsl")
    if wti.empty or cpi.empty:
        st.info("No data yet — run `pipelines/macro/pull_macro.py`.")
        return

    real_wti = deflate(wti, cpi, base_period=INDEX_BASE_PERIOD)
    nominal_indexed = _trim_recent(index_to(wti, base_period=INDEX_BASE_PERIOD), days)
    real_indexed = _trim_recent(index_to(real_wti, base_period=INDEX_BASE_PERIOD), days)

    title = "WTI Crude — Real vs. Nominal (2018=100)"
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=nominal_indexed.index,
            y=nominal_indexed.values,
            name="Nominal",
            line={"color": NAVY, "width": 2},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=real_indexed.index,
            y=real_indexed.values,
            name="Real (CPI-adjusted)",
            line={"color": LIGHT_BLUE, "width": 2},
        )
    )
    fig.update_layout(title=title, yaxis_title="Index (2018=100)")
    with card(title):
        st.plotly_chart(fig)
        kardamow_take(
            "The gap between these two lines is pure inflation — whatever's left "
            "once it's closed is the actual real-terms move oil has made since 2018."
        )


def _energy_small_multiples_section(days: int | None) -> None:
    fx_eur = _series_by_ts("fx.usd_eur")
    if fx_eur.empty:
        st.info("No FX data yet — run `pipelines/macro/pull_macro.py`.")
        return

    cols = st.columns(len(ENERGY_SMALL_MULTIPLES))
    for i, (series_id, label, unit) in enumerate(ENERGY_SMALL_MULTIPLES):
        usd = _series_by_ts(series_id)
        if usd.empty:
            with cols[i]:
                st.info(f"No data yet for {label}.")
            continue

        eur = to_currency(usd, fx_eur, target="EUR")
        usd_trimmed = _trim_recent(usd, days)
        eur_trimmed = _trim_recent(eur, days)

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=usd_trimmed.index,
                y=usd_trimmed.values,
                name="USD",
                line={"color": NAVY, "width": 1.5},
            )
        )
        fig.add_trace(
            go.Scatter(
                x=eur_trimmed.index,
                y=eur_trimmed.values,
                name="EUR",
                line={"color": LIGHT_BLUE, "width": 1.5},
            )
        )
        fig.update_layout(title=f"{label} ({unit})", showlegend=True)
        with cols[i], card(label):
            st.plotly_chart(fig)


def _esi_heat_strip_section() -> None:
    frames = []
    for geo in ESI_GEOS:
        series = _series_by_ts(f"estat.esi.{geo}").tail(36)  # last 3 years, monthly
        if series.empty:
            continue
        frames.append(series.rename(geo))

    if not frames:
        st.info("No ESI data yet — run `pipelines/macro/pull_macro.py`.")
        return

    wide = pd.concat(frames, axis=1).T
    wide.columns = [pd.Timestamp(c).strftime("%Y-%m") for c in wide.columns]

    title = "Economic Sentiment Indicator — Heat-Strip"
    fig = category_time_heatmap(wide, title=title, unit="ESI (100=long-run avg)")
    with card(title):
        st.plotly_chart(fig)
        kardamow_take(
            "Sentiment leads hard data by a quarter or two more often than not — a "
            "country cooling off here is worth watching before it shows up in "
            "industrial production or demand numbers."
        )


_PLATFORM_COLOURS = {"reddit": NAVY, "x": LIGHT_BLUE, "news": RED, "polymarket": GREY}
_TOP_N_TICKERS_FOR_SENTIMENT_BAR = 12


def _adanos_long_frame(metric: str) -> pd.DataFrame:
    """`metric` is "buzz_score" or "sentiment_score". Returns long-form (ts,
    platform, ticker, value) across every curated ticker/platform combination --
    series_ids are built deterministically from tickers.py rather than discovered,
    since read_ts_long has no wildcard/prefix filter."""
    ids = [f"adanos.{p}.{t.lower()}.{metric}" for p in PLATFORMS for t in TICKERS]
    df = read_ts_long(series_ids=ids)
    if df.empty:
        return df
    df = df.copy()
    parts = df["series_id"].str.split(".")
    df["platform"] = parts.str[1]
    df["ticker"] = parts.str[2].str.upper()
    return df


def _adanos_buzz_by_platform_section() -> None:
    df = _adanos_long_frame("buzz_score")
    if df.empty:
        st.info("No Adanos data yet — run `pipelines/adanos/pull_adanos.py`.")
        return

    fig = go.Figure()
    for platform in PLATFORMS:
        platform_df = df[df["platform"] == platform]
        if platform_df.empty:
            continue
        daily_mean = platform_df.groupby("ts")["value"].mean()
        fig.add_trace(
            go.Scatter(
                x=daily_mean.index,
                y=daily_mean.values,
                name=platform.capitalize(),
                mode="lines",
                line={"color": _PLATFORM_COLOURS.get(platform, GREY), "width": 2},
            )
        )
    fig.update_layout(title="Ticker-basket mean buzz score by platform", yaxis_title="Buzz (0-100)")
    with card("Buzz by platform"):
        st.plotly_chart(fig)


def _adanos_sentiment_by_ticker_section() -> None:
    df = _adanos_long_frame("sentiment_score")
    if df.empty:
        st.info("No Adanos sentiment data yet.")
        return

    latest = df.sort_values("ts").groupby(["ticker", "platform"], as_index=False).last()
    top_tickers = (
        latest.groupby("ticker")["value"].apply(lambda v: v.abs().sum())
        .sort_values(ascending=False)
        .head(_TOP_N_TICKERS_FOR_SENTIMENT_BAR)
        .index
    )
    latest = latest[latest["ticker"].isin(top_tickers)]

    fig = go.Figure()
    for platform in PLATFORMS:
        platform_df = latest[latest["platform"] == platform].set_index("ticker")
        if platform_df.empty:
            continue
        fig.add_trace(
            go.Bar(
                x=platform_df.index,
                y=platform_df["value"],
                name=platform.capitalize(),
                marker={"color": _PLATFORM_COLOURS.get(platform, GREY)},
            )
        )
    fig.update_layout(
        title=f"Latest sentiment, top {_TOP_N_TICKERS_FOR_SENTIMENT_BAR} tickers by attention",
        yaxis_title="Sentiment (-1 to +1)",
        barmode="group",
    )
    with card("Latest sentiment by ticker"):
        st.plotly_chart(fig)


def _adanos_sector_trend_section() -> None:
    series = _series_by_ts("adanos.reddit.sector_energy.buzz_score")
    if series.empty:
        st.info("No Adanos sector-trend data yet.")
        return

    fig = simple_time_series_chart(
        series, title="Reddit Energy-sector buzz trend", unit="Buzz (0-100)"
    )
    with card("Sector buzz trend"):
        st.plotly_chart(fig)


def _adanos_sentiment_section() -> None:
    _adanos_buzz_by_platform_section()
    _adanos_sentiment_by_ticker_section()
    _adanos_sector_trend_section()
    kardamow_take(
        "This measures how much people are talking and how they feel, not whether "
        "they're right — attention and flow data for a curated energy-complex "
        "ticker basket, never a trading signal."
    )


def _social_comparison_section(ticker: str, result: Overlap) -> None:
    """Reddit only -- Set A (TICKER_QUERIES) exists solely to give an
    apples-to-apples overlap against Adanos for the same ticker/platform/day
    (see pipelines/social/queries.py). `ticker`/`result` come from
    `_social_sentiment_section`, which reads the selectbox and calls `overlap()`
    once so this and `_social_deviation_section` below don't each run their own
    identical, uncached DuckDB scan for the same ticker."""
    if result.frame.empty:
        st.info(
            "No overlapping Adanos/self-hosted days yet — run "
            "`pipelines/social/pull_social.py`."
        )
        return

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=result.frame["ts"],
            y=result.frame["adanos"],
            name="Adanos (vendor)",
            mode="lines",
            line={"color": NAVY, "width": 2},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=result.frame["ts"],
            y=result.frame["social"],
            name="Self-hosted",
            mode="lines",
            line={"color": LIGHT_BLUE, "width": 2},
        )
    )
    rate = agreement_rate(result.frame)
    # result.frame is non-empty here (checked above), so overlap_days > 0 and rate is
    # never actually None -- the "—" fallback exists so this reads correctly even if
    # that invariant is ever loosened, rather than crashing on a None format spec.
    rate_text = f"{rate:.0%} sign agreement" if rate is not None else "— sign agreement"
    fig.add_annotation(
        x=result.frame["ts"].iloc[-1],
        y=result.frame["social"].iloc[-1],
        text=(
            f"{result.overlap_days} overlapping days · "
            f"{result.dropped_days} dropped · "
            f"{rate_text}"
        ),
        showarrow=True,
        xanchor="right",
    )
    fig.update_layout(
        title=f"{ticker} sentiment — vendor vs self-hosted",
        yaxis_title="Sentiment (-1 to +1)",
    )
    with card(f"{ticker}: Adanos vs self-hosted"):
        st.plotly_chart(fig)
        if result.overlap_days < 10:
            st.warning(
                f"Only {result.overlap_days} overlapping days — too few to read as "
                "a finding. Both series need more history before the gap between "
                "them means anything."
            )


def _social_deviation_section(ticker: str, result: Overlap) -> None:
    """`ticker`/`result` come from `_social_sentiment_section` -- see
    `_social_comparison_section`'s docstring for why this and that section share a
    single `overlap()` call rather than each computing their own."""
    if result.frame.empty:
        return

    disagree = disagrees_on_sign(result.frame["adanos"], result.frame["social"])
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=result.frame["ts"],
            y=result.frame["gap"],
            name="Self-hosted - Adanos",
            marker={"color": [RED if d else NAVY for d in disagree]},
        )
    )
    fig.update_layout(
        title=f"{ticker} deviation (self-hosted - Adanos)", yaxis_title="Difference"
    )

    window = DEFAULT_CORRELATION_WINDOW
    latest_corr = rolling_correlation(result.frame, window=window).dropna()
    if latest_corr.empty:
        corr_caption = (
            f"Rolling correlation ({window}-day window): not enough overlapping "
            "days yet for a reading."
        )
    else:
        corr_caption = (
            f"Rolling correlation ({window}-day window): latest = "
            f"{latest_corr.iloc[-1]:.2f}."
        )

    with card(f"{ticker} deviation"):
        st.plotly_chart(fig)
        st.caption(
            f"Computed over {result.overlap_days} overlapping days "
            f"({result.dropped_days} dropped, where only one source reported that "
            "day). Red bars mark days where the two sources land on strictly opposite "
            "sides of zero; an exact 0.0 on either side is never treated as "
            "disagreement."
        )
        st.caption(corr_caption)
        if result.overlap_days < 10:
            st.warning(
                f"Only {result.overlap_days} overlapping days — too thin to read "
                "this deviation as a finding rather than noise."
            )


def _social_topic_attention_section() -> None:
    """Set B -- commodity/geopolitical topics Adanos cannot express at all,
    since it is a ticker-basket product. Reddit only: `post_count` has no
    Adanos counterpart to compare against."""
    ids = [f"social.reddit.{q['slug']}.post_count" for q in TOPIC_QUERIES]
    df = read_ts_long(series_ids=ids)
    if df.empty:
        st.info("No social topic data yet — run `pipelines/social/pull_social.py`.")
        return

    df = df.copy()
    df["topic"] = df["series_id"].str.split(".").str[2]
    # aggregate_to_ts_long deliberately writes no row for a quiet topic (missing, not
    # a fabricated zero) -- so "each topic's most recent row" can land on genuinely
    # different dates across topics. Rather than call that "Latest" with no date shown
    # (which reads as one point in time), each bar is labelled with its own date and
    # the caption states the range spanned.
    latest = df.sort_values("ts").groupby("topic", as_index=False).last()
    latest = latest.sort_values("value", ascending=False)
    bar_dates = pd.to_datetime(latest["ts"]).dt.strftime("%Y-%m-%d")

    fig = go.Figure(
        go.Bar(
            x=latest["topic"],
            y=latest["value"],
            marker={"color": NAVY},
            text=bar_dates,
            textposition="outside",
        )
    )
    fig.update_layout(title="Post count by topic (most recent pull per topic)", yaxis_title="Posts")
    with card("Topic attention"):
        st.plotly_chart(fig)
        min_date, max_date = bar_dates.min(), bar_dates.max()
        if min_date == max_date:
            date_caption = f"All bars are from the {max_date} pull."
        else:
            date_caption = (
                f"Bars span {min_date} to {max_date}, labelled individually above — "
                "each shows that topic's own most recent pull, not necessarily the "
                "same run, since a quiet topic writes no row at all rather than a "
                "zero."
            )
        st.caption(date_caption)
        st.caption(
            "These topics have no Adanos counterpart — a ticker basket cannot "
            "express them. Attention only, not sentiment."
        )


def _social_polymarket_attention_section() -> None:
    """Polymarket has no keyword search -- `q`/`search` are silently ignored
    (confirmed live, see pipelines/social/CLAUDE.md) -- so it contributes one
    tag-level attention series (`social.polymarket.energy.*`), never a
    per-topic view the way Reddit does above."""
    series = _series_by_ts("social.polymarket.energy.post_count")
    if series.empty:
        st.info(
            "No Polymarket attention data yet — run `pipelines/social/pull_social.py`."
        )
        return

    fig = simple_time_series_chart(
        series, title="Polymarket 'energy' tag — post count", unit="Posts"
    )
    with card("Polymarket attention (tag-level)"):
        st.plotly_chart(fig)
        st.caption(
            "Polymarket has no keyword search, so this is attention on the whole "
            "'energy' tag, not any single ticker or topic."
        )


def _social_sentiment_section() -> None:
    # Selectbox and overlap() are read/called exactly once here and passed down to
    # both sections below, rather than each section reading session_state and
    # re-running the same uncached DuckDB scan for itself.
    ticker = st.selectbox("Ticker", options=TICKER_QUERIES, key="social_ticker")
    result = overlap(ticker, platform="reddit")
    _social_comparison_section(ticker, result)
    _social_deviation_section(ticker, result)
    _social_topic_attention_section()
    _social_polymarket_attention_section()
    kardamow_take(
        "Two independent readings of the same chatter, shown side by side rather "
        "than averaged into one. Where they disagree, neither is authoritative — "
        "the gap is the information. Attention and flow data, never a trading "
        "signal."
    )


st.title("Macro & FX")

range_label = st.segmented_control(
    "Time range", options=list(RANGE_DAYS), default="5Y", required=True, key="macro_range"
)
days = RANGE_DAYS[range_label]

st.subheader("Dollar vs. crude")
_dollar_vs_wti_section(days)

st.subheader("Real vs. nominal crude")
_real_vs_nominal_section(days)

st.subheader("Energy prices, USD vs. EUR")
_energy_small_multiples_section(days)

st.subheader("Economic sentiment by country")
_esi_heat_strip_section()

st.subheader("Energy-sector sentiment (Adanos)")
_adanos_sentiment_section()

st.subheader("Self-hosted social sentiment")
_social_sentiment_section()
