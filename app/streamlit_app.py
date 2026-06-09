"""Streamlit entry point for the equity levels app."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from app.models import (
    DEFAULT_METRICS,
    EquityMetrics,
    GenerateRequest,
    GenerateResponse,
    MetricName,
    NewsArticle,
    NewsRequest,
    NewsResponse,
)
from app.services.market_data import MarketDataService
from app.services.news import NewsService
from app.services.pdf_report import PdfReportService


METRIC_OPTIONS: dict[MetricName, str] = {
    "previous_day": "Previous day OHLC",
    "premarket": "Premarket range",
    "first_five_minutes": "Opening range",
    "previous_session_vwap_5m": "Previous session VWAP",
    "fifty_two_week": "52-week range",
    "swing_levels": "Swing highs/lows",
    "bollinger_bands": "Bollinger Bands",
    "earnings_gap": "Earnings gap",
}


LEVELS_VIEW = "Investment Trading Levels"
NEWS_VIEW = "Stock News"


st.set_page_config(
    page_title="Investment Trading",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def market_data_service() -> MarketDataService:
    """Return one service instance per Streamlit worker process."""
    return MarketDataService()


@st.cache_resource
def pdf_report_service() -> PdfReportService:
    """Return one PDF renderer per Streamlit worker process."""
    return PdfReportService()


@st.cache_resource
def news_service() -> NewsService:
    """Return one news service instance per Streamlit worker process."""
    return NewsService()


@st.cache_data(ttl=300, show_spinner=False)
def build_report(tickers: tuple[str, ...], metrics: tuple[MetricName, ...]) -> GenerateResponse:
    """Fetch and calculate metrics, cached briefly to avoid repeated provider calls."""
    return GenerateResponse(
        generated_at=datetime.now(timezone.utc),
        metrics=market_data_service().build_metrics(list(tickers), list(metrics)),
    )


@st.cache_data(ttl=300, show_spinner=False)
def build_news(tickers: tuple[str, ...], per_ticker: int = 5, general_count: int = 8) -> NewsResponse:
    """Fetch and normalize watchlist plus broad market news."""
    return news_service().build_news(list(tickers), per_ticker=per_ticker, general_count=general_count)


def fmt(value: Any) -> str:
    """Format display values for Streamlit tables."""
    if value is None or value == "":
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def render_app_chrome() -> str:
    """Render app-level brand/navigation and return the active view."""
    if "active_view" not in st.session_state:
        st.session_state.active_view = LEVELS_VIEW

    st.markdown(
        """
        <style>
          :root {
            color-scheme: light;
          }
          .stApp {
            background: #eef2f1;
            color: #111827;
          }
          header[data-testid="stHeader"] {
            background: rgba(255, 255, 255, 0.96);
            border-bottom: 1px solid #d5ddd9;
          }
          .block-container {
            max-width: 1220px;
            padding-top: 2.75rem;
          }
          [data-testid="stSidebar"] {
            background: #ffffff;
            border-right: 1px solid #d5ddd9;
            box-shadow: 10px 0 28px rgba(17, 24, 39, 0.08);
          }
          [data-testid="stSidebar"] * {
            color: #111827;
          }
          [data-testid="stSidebar"] textarea {
            background: #ffffff;
            border: 1px solid #cbd5e1;
            border-radius: 0.5rem;
            color: #111827;
          }
          [data-testid="stSidebar"] [data-baseweb="select"] > div {
            background: #ffffff;
            border-color: #cbd5e1;
            border-radius: 0.5rem;
          }
          .streamlit-ribbon {
            align-items: center;
            background: rgba(255, 255, 255, 0.96);
            border-bottom: 1px solid #d5ddd9;
            display: grid;
            gap: 1rem;
            grid-template-columns: 1fr 1.4fr;
            margin: -1rem 0 1rem;
            padding: 0 0 1rem;
          }
          .streamlit-brand {
            align-items: center;
            display: inline-flex;
            gap: 0.75rem;
            min-height: 2.8rem;
          }
          .brand-mark {
            align-items: center;
            background: #ccfbf1;
            border: 1px solid #99f6e4;
            border-radius: 0.5rem;
            color: #0f766e;
            display: inline-flex;
            font-size: 0.78rem;
            font-weight: 900;
            height: 2.25rem;
            justify-content: center;
            letter-spacing: 0.05em;
            width: 2.25rem;
          }
          .brand-name {
            color: inherit;
            font-size: 1.25rem;
            font-weight: 900;
          }
          .subapp-eyebrow {
            color: #0f766e;
            font-size: 0.78rem;
            font-weight: 800;
            margin: 0 0 0.2rem;
            text-transform: uppercase;
          }
          .streamlit-ribbon div[data-testid="stHorizontalBlock"] {
            align-items: center;
          }
          div[data-testid="stHorizontalBlock"] button {
            border-radius: 0.5rem;
            font-weight: 800;
          }
          div[data-testid="stButton"] button[kind="primary"],
          div[data-testid="stDownloadButton"] button[kind="primary"] {
            background: #0f766e;
            border: 1px solid #0f766e;
            box-shadow: 0 10px 20px rgba(15, 118, 110, 0.18);
            color: #ffffff;
          }
          div[data-testid="stButton"] button[kind="secondary"],
          div[data-testid="stDownloadButton"] button[kind="secondary"] {
            background: #ffffff;
            border: 1px solid #d5ddd9;
            color: #334155;
          }
          div[data-testid="stButton"] button:hover,
          div[data-testid="stDownloadButton"] button:hover {
            border-color: #0f766e;
            transform: translateY(-1px);
          }
          .subapp-panel {
            align-items: center;
            background: #ffffff;
            border: 1px solid #d5ddd9;
            border-radius: 0.5rem;
            box-shadow: 0 8px 28px rgba(17, 24, 39, 0.08);
            display: grid;
            gap: 1rem;
            grid-template-columns: 1.8fr 1fr;
            margin: 1rem 0;
            padding: 1.5rem;
          }
          .subapp-panel h1 {
            color: #111827;
            font-size: clamp(2rem, 5vw, 3.8rem);
            line-height: 1.05;
            margin: 0;
          }
          .subapp-panel p {
            color: #334155;
            font-size: 1rem;
            margin: 0.8rem 0 0;
          }
          .streamlit-status {
            color: #047857;
            font-size: 1.1rem;
            font-weight: 900;
            line-height: 1.45;
          }
          .report-panel {
            background: #ffffff;
            border: 1px solid #d5ddd9;
            border-radius: 0.5rem;
            box-shadow: 0 8px 28px rgba(17, 24, 39, 0.08);
            margin: 1rem 0;
            padding: 1.5rem;
          }
          .report-header {
            align-items: center;
            display: flex;
            gap: 1rem;
            justify-content: space-between;
            margin-bottom: 1.5rem;
          }
          .report-header h2 {
            color: #111827;
            margin: 0 0 0.35rem;
          }
          .report-header p {
            color: #334155;
            margin: 0;
          }
          .metric-card {
            background: #ffffff;
            border: 1px solid #dbe3ef;
            border-radius: 0.5rem;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.07);
            margin-bottom: 1rem;
            overflow: hidden;
          }
          .metric-card-header {
            align-items: center;
            background: #12312f;
            color: #ffffff;
            display: flex;
            gap: 0.6rem;
            justify-content: space-between;
            padding: 0.95rem 1.1rem;
          }
          .metric-card-header h3 {
            color: #ffffff;
            letter-spacing: 0.06em;
            margin: 0;
          }
          .drag-glyph {
            color: #bfdbfe;
            font-weight: 900;
          }
          .metric-card-body {
            padding: 1rem;
          }
          .metric-section {
            border: 1px solid #e2e8f0;
            border-radius: 0.5rem;
            margin-bottom: 0.85rem;
            overflow: hidden;
          }
          .metric-section-title {
            background: #f1f5f9;
            color: #334155;
            font-size: 0.78rem;
            font-weight: 900;
            letter-spacing: 0.08em;
            padding: 0.7rem 0.85rem;
            text-transform: uppercase;
          }
          .metric-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
          .metric-cell {
            border-top: 1px solid #e2e8f0;
            padding: 0.8rem 0.95rem;
          }
          .metric-cell:nth-child(odd) {
            border-right: 1px solid #e2e8f0;
          }
          .metric-label {
            color: #64748b;
            display: block;
            font-size: 0.76rem;
            font-weight: 800;
            text-transform: uppercase;
          }
          .metric-value {
            color: #020617;
            display: block;
            font-size: 1.12rem;
            font-weight: 900;
            margin-top: 0.2rem;
          }
          .news-shell {
            background: #ffffff;
            border: 1px solid #d5ddd9;
            border-radius: 0.5rem;
            box-shadow: 0 8px 28px rgba(17, 24, 39, 0.08);
            margin: 1rem 0;
            padding: 1.25rem;
          }
          .news-shell h2,
          .news-shell h3,
          .news-shell h4 {
            color: #111827;
          }
          [data-testid="stVerticalBlockBorderWrapper"] {
            background: #ffffff;
            border: 1px solid #d5ddd9;
            border-radius: 0.5rem;
            box-shadow: 0 8px 28px rgba(17, 24, 39, 0.08);
          }
          div[data-testid="stVerticalBlock"]:has(.subapp-eyebrow):has(button):not(:has(.streamlit-brand)) {
            background: #ffffff;
            border: 1px solid #d5ddd9;
            border-radius: 0.5rem;
            box-shadow: 0 8px 28px rgba(17, 24, 39, 0.08);
            margin: 1rem 0;
            padding: 1.5rem;
          }
          @media (max-width: 760px) {
            .subapp-panel {
              grid-template-columns: 1fr;
            }
            .report-header {
              align-items: stretch;
              display: grid;
            }
            .metric-grid {
              grid-template-columns: 1fr;
            }
            .metric-cell:nth-child(odd) {
              border-right: 0;
            }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    brand_col, levels_col, news_col = st.columns([2.2, 1, 1], vertical_alignment="center")
    with brand_col:
        st.markdown(
            """
            <div class="streamlit-brand">
          <span class="brand-mark">IT</span>
          <span class="brand-name">Investment Trading</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with levels_col:
        st.button(
            "Trading Levels",
            type="primary" if st.session_state.active_view == LEVELS_VIEW else "secondary",
            use_container_width=True,
            on_click=set_active_view,
            args=(LEVELS_VIEW,),
        )
    with news_col:
        st.button(
            "Stock News",
            type="primary" if st.session_state.active_view == NEWS_VIEW else "secondary",
            use_container_width=True,
            on_click=set_active_view,
            args=(NEWS_VIEW,),
        )

    return str(st.session_state.active_view)


def set_active_view(view: str) -> None:
    """Persist the active Streamlit subapp."""
    st.session_state.active_view = view


def metric_rows(metric: EquityMetrics) -> list[dict[str, str]]:
    """Flatten selected metrics into table rows."""
    selected = set(metric.selected_metrics)
    rows: list[tuple[str, Any]] = []

    if "previous_day" in selected:
        rows.extend(
            [
                ("Previous Open", metric.previous_day.open),
                ("Previous High", metric.previous_day.high),
                ("Previous Low", metric.previous_day.low),
                ("Previous Close", metric.previous_day.close),
            ]
        )
    if "premarket" in selected:
        rows.extend(
            [
                ("Premarket High", metric.premarket.high),
                ("Premarket Low", metric.premarket.low),
                ("Premarket Bars", metric.premarket.bars),
            ]
        )
    if "first_five_minutes" in selected:
        rows.extend(
            [
                ("First 5m High", metric.first_five_minutes.high),
                ("First 5m Low", metric.first_five_minutes.low),
                ("First 5m Bars", metric.first_five_minutes.bars),
            ]
        )
    if "previous_session_vwap_5m" in selected:
        rows.append(("Previous Session VWAP (5m)", metric.previous_session_vwap_5m))
    if "fifty_two_week" in selected:
        rows.extend(
            [
                ("52-Week High", metric.fifty_two_week.high),
                ("52-Week Low", metric.fifty_two_week.low),
            ]
        )
    if "swing_levels" in selected:
        rows.extend(
            [
                ("Swing Highs", ", ".join(fmt(level) for level in sorted(metric.swing_levels.highs))),
                ("Swing Lows", ", ".join(fmt(level) for level in sorted(metric.swing_levels.lows, reverse=True))),
            ]
        )
    if "bollinger_bands" in selected:
        rows.extend(
            [
                ("Bollinger Upper", metric.bollinger_bands.upper),
                ("Bollinger Middle", metric.bollinger_bands.middle),
                ("Bollinger Lower", metric.bollinger_bands.lower),
            ]
        )
    if "earnings_gap" in selected:
        rows.extend(
            [
                ("Earnings Date", metric.earnings_gap.date.isoformat() if metric.earnings_gap.date else None),
                ("Earnings Gap", metric.earnings_gap.gap),
                ("Earnings Gap %", metric.earnings_gap.gap_percent),
            ]
        )

    return [{"Metric": label, "Value": fmt(value)} for label, value in rows]


def metric_sections(metric: EquityMetrics) -> list[dict[str, list[tuple[str, Any]]]]:
    """Group selected metrics into card sections that mirror the static app."""
    selected = set(metric.selected_metrics)
    sections: list[dict[str, list[tuple[str, Any]]]] = []

    session_rows: list[tuple[str, Any]] = []
    if "previous_day" in selected:
        session_rows.extend(
            [
                ("Prev Open", metric.previous_day.open),
                ("Prev High", metric.previous_day.high),
                ("Prev Low", metric.previous_day.low),
                ("Prev Close", metric.previous_day.close),
            ]
        )
    if "premarket" in selected:
        session_rows.extend(
            [
                ("Premarket High", metric.premarket.high),
                ("Premarket Low", metric.premarket.low),
            ]
        )
    if "first_five_minutes" in selected:
        session_rows.extend(
            [
                ("First 5m High", metric.first_five_minutes.high),
                ("First 5m Low", metric.first_five_minutes.low),
            ]
        )
    if session_rows:
        sections.append({"Session Levels": session_rows})

    level_rows: list[tuple[str, Any]] = []
    if "previous_session_vwap_5m" in selected:
        level_rows.append(("VWAP 5m", metric.previous_session_vwap_5m))
    if "fifty_two_week" in selected:
        level_rows.extend(
            [
                ("52W High", metric.fifty_two_week.high),
                ("52W Low", metric.fifty_two_week.low),
            ]
        )
    if "swing_levels" in selected:
        level_rows.extend(
            [
                ("Swing Highs", ", ".join(fmt(level) for level in sorted(metric.swing_levels.highs))),
                ("Swing Lows", ", ".join(fmt(level) for level in sorted(metric.swing_levels.lows, reverse=True))),
            ]
        )
    if level_rows:
        sections.append({"Range & Levels": level_rows})

    indicator_rows: list[tuple[str, Any]] = []
    if "bollinger_bands" in selected:
        indicator_rows.extend(
            [
                ("BB Upper", metric.bollinger_bands.upper),
                ("BB Middle", metric.bollinger_bands.middle),
                ("BB Lower", metric.bollinger_bands.lower),
            ]
        )
    if "earnings_gap" in selected:
        indicator_rows.extend(
            [
                ("Earnings Date", metric.earnings_gap.date.isoformat() if metric.earnings_gap.date else None),
                ("Earnings Gap", metric.earnings_gap.gap),
                ("Earnings Gap %", metric.earnings_gap.gap_percent),
            ]
        )
    if indicator_rows:
        sections.append({"Indicators & Events": indicator_rows})

    return sections


def render_metric_card(metric: EquityMetrics) -> None:
    """Render one ticker card styled like the static app."""
    section_html = []
    for section in metric_sections(metric):
        [(title, rows)] = section.items()
        cells = "".join(
            (
                '<div class="metric-cell">'
                f'<span class="metric-label">{escape(label)}</span>'
                f'<span class="metric-value">{escape(fmt(value))}</span>'
                "</div>"
            )
            for label, value in rows
        )
        section_html.append(
            '<section class="metric-section">'
            f'<div class="metric-section-title">{escape(title)}</div>'
            f'<div class="metric-grid">{cells}</div>'
            "</section>"
        )

    st.markdown(
        (
            '<article class="metric-card">'
            '<div class="metric-card-header">'
            f'<div><span class="drag-glyph">&vellip;</span> <h3 style="display:inline">{escape(metric.ticker)}</h3></div>'
            "</div>"
            f'<div class="metric-card-body">{"".join(section_html)}</div>'
            "</article>"
        ),
        unsafe_allow_html=True,
    )


def chart_frame(metric: EquityMetrics) -> pd.DataFrame:
    """Build a daily close chart frame for Streamlit."""
    return pd.DataFrame(
        [{"date": point.date, "close": point.close} for point in metric.price_history]
    )


def render_metric(metric: EquityMetrics) -> None:
    """Render one ticker report section."""
    render_metric_card(metric)
    history = chart_frame(metric)
    if history.empty:
        st.info(f"No daily close history was returned for {metric.ticker}.")
    else:
        with st.expander(f"{metric.ticker} chart", expanded=False):
            st.line_chart(history, x="date", y="close", use_container_width=True)
    if metric.warnings:
        with st.expander(f"{len(metric.warnings)} data warning(s)"):
            for warning in metric.warnings:
                st.warning(warning)


def render_article(article: NewsArticle) -> None:
    """Render one normalized news article."""
    published = article.published_at.astimezone().strftime("%Y-%m-%d %H:%M") if article.published_at else None
    meta = " - ".join(item for item in [article.publisher, published] if item)
    if article.url:
        st.markdown(f"**[{article.title}]({article.url})**")
    else:
        st.markdown(f"**{article.title}**")
    if meta:
        st.caption(meta)
    if article.summary:
        st.write(article.summary)
    if article.related_tickers:
        st.caption("Related: " + ", ".join(article.related_tickers[:8]))


def render_news(report: NewsResponse) -> None:
    """Render watchlist and general market news."""
    st.caption(f"Refreshed at {report.generated_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    for warning in report.warnings:
        st.warning(warning)

    st.subheader("General Market News")
    if report.general_market:
        for article in report.general_market:
            with st.container(border=True):
                render_article(article)
    else:
        st.info("No general market headlines were returned.")

    st.subheader("Watchlist News")
    for ticker_group in report.ticker_news:
        with st.expander(f"{ticker_group.ticker} - {len(ticker_group.articles)} headline(s)", expanded=True):
            for warning in ticker_group.warnings:
                st.warning(warning)
            if ticker_group.articles:
                for article in ticker_group.articles:
                    render_article(article)
                    st.divider()
            else:
                st.info("No recent headlines returned.")


def selected_metric_ids(labels: list[str]) -> list[MetricName]:
    """Translate selected labels back to metric ids."""
    label_to_id = {label: metric_id for metric_id, label in METRIC_OPTIONS.items()}
    return [label_to_id[label] for label in labels]


def main() -> None:
    """Run the Streamlit application."""
    view = render_app_chrome()

    with st.sidebar:
        st.header("Controls")
        ticker_text = st.text_area("Tickers", value="AAPL, MSFT, NVDA", height=110)
        selected_labels: list[str] = []
        if view == LEVELS_VIEW:
            selected_labels = st.multiselect(
                "Metrics",
                options=list(METRIC_OPTIONS.values()),
                default=[METRIC_OPTIONS[metric_id] for metric_id in DEFAULT_METRICS],
            )

    if "report" not in st.session_state:
        st.session_state.report = None
    if "news" not in st.session_state:
        st.session_state.news = None
    if "levels_status" not in st.session_state:
        st.session_state.levels_status = ""

    if view == LEVELS_VIEW:
        with st.container():
            heading_col, action_col = st.columns([2.2, 1], vertical_alignment="center")
            with heading_col:
                st.markdown('<p class="subapp-eyebrow">Subapp</p>', unsafe_allow_html=True)
                st.title("Investment Trading Levels")
                st.caption("Generate price-level reports from the shared watchlist.")
            with action_col:
                generate = st.button("Generate Levels", type="primary", use_container_width=True)
            levels_status_slot = st.empty()
            if st.session_state.levels_status:
                levels_status_slot.success(st.session_state.levels_status)
        refresh_news = False
    else:
        with st.container():
            heading_col, action_col = st.columns([2.2, 1], vertical_alignment="center")
            with heading_col:
                st.markdown('<p class="subapp-eyebrow">Subapp</p>', unsafe_allow_html=True)
                st.title("Stock News")
                st.caption("Use the shared watchlist to pull ticker-specific headlines plus broad US market news.")
            with action_col:
                refresh_news = st.button("Refresh News", type="primary", use_container_width=True)
        generate = False

    if generate:
        try:
            request = GenerateRequest(tickers=ticker_text, metrics=selected_metric_ids(selected_labels))
        except ValidationError as exc:
            st.error(exc.errors()[0]["msg"])
            return

        with st.spinner("Generating levels..."):
            st.session_state.report = build_report(tuple(request.tickers), tuple(request.metrics))
        st.session_state.levels_status = "Report generated successfully."
        levels_status_slot.success(st.session_state.levels_status)

    if refresh_news:
        try:
            request = NewsRequest(tickers=ticker_text)
        except ValidationError as exc:
            st.error(exc.errors()[0]["msg"])
            return

        with st.spinner("Loading news..."):
            st.session_state.news = build_news(tuple(request.tickers))

    if view == NEWS_VIEW:
        news: NewsResponse | None = st.session_state.news
        if news is None:
            st.info("Enter tickers and refresh news.")
            return
        render_news(news)
        return

    report: GenerateResponse | None = st.session_state.report
    if report is None:
        st.info("Enter tickers and generate levels to view a report.")
        return

    with st.container(border=True):
        header_col, download_col = st.columns([2.2, 1], vertical_alignment="center")
        with header_col:
            st.header("Report")
            st.caption(f"Generated at {report.generated_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")
        with download_col:
            pdf = pdf_report_service().build_pdf(report)
            st.download_button(
                "Download PDF Report",
                data=pdf,
                file_name=f"equity-levels-{report.generated_at.strftime('%Y%m%d-%H%M%S')}.pdf",
                mime="application/pdf",
                type="secondary",
                use_container_width=True,
            )

    for metric in report.metrics:
        render_metric(metric)


if __name__ == "__main__":
    main()
