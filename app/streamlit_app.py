"""Streamlit entry point for the equity levels app."""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from pydantic import ValidationError

from app.models import (
    CHART_DEFAULT_INTERVAL_BY_RANGE,
    CHART_INTERVALS_BY_RANGE,
    ChartHistoryResponse,
    ChartInterval,
    ChartRange,
    DEFAULT_METRICS,
    EquityMetrics,
    GenerateRequest,
    GenerateResponse,
    MarketSnapshotRequest,
    MarketSnapshotResponse,
    MetricName,
    NewsArticle,
    NewsRequest,
    NewsResponse,
    ScannerRequest,
    ScannerResponse,
    TickerChartHistory,
)
from app.services.market_data import MarketDataService
from app.services.news import NewsService
from app.services.pdf_report import PdfReportService
from app.services.scanner import ScannerService


NEWS_COLLAPSED_HEADLINE_COUNT = 5
NEWS_EXPANDED_HEADLINE_COUNT = 10
NEWS_CATEGORY_LABELS = {
    "rating_changes": "Price Rating Changes",
    "contracts": "Company Contract Announcements",
    "earnings": "Earnings Reports",
    "general": "General News",
}
CHART_TYPE_OPTIONS = ("Line", "Candles")
CHART_RANGE_OPTIONS: tuple[ChartRange, ...] = tuple(CHART_INTERVALS_BY_RANGE.keys())
CHART_RANGE_LABELS = {"1Y": "1YR"}
AUTO_REFRESH_SECONDS = 300
STREAMLIT_STATE_ENV = "INVESTMENT_TRADING_STREAMLIT_STATE"
LIGHTWEIGHT_CHARTS_BUNDLE_PATH = (
    Path(__file__).parent / "static" / "vendor" / "lightweight-charts" / "lightweight-charts.standalone.production.js"
)


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


@st.cache_resource
def scanner_service() -> ScannerService:
    """Return one scanner service instance per Streamlit worker process."""
    return ScannerService(market_data_service())


@st.cache_data(ttl=300, show_spinner=False)
def build_report(tickers: tuple[str, ...], metrics: tuple[MetricName, ...], refresh_token: int = 0) -> GenerateResponse:
    """Fetch and calculate metrics, cached briefly to avoid repeated provider calls."""
    return GenerateResponse(
        generated_at=datetime.now(timezone.utc),
        metrics=market_data_service().build_metrics(list(tickers), list(metrics)),
    )


@st.cache_data(ttl=300, show_spinner=False)
def build_news(
    tickers: tuple[str, ...],
    per_ticker: int = NEWS_EXPANDED_HEADLINE_COUNT,
    general_count: int = 8,
    refresh_token: int = 0,
) -> NewsResponse:
    """Fetch and normalize watchlist plus broad market news."""
    return news_service().build_news(list(tickers), per_ticker=per_ticker, general_count=general_count)


@st.cache_data(ttl=120, show_spinner=False)
def build_market_snapshot(tickers: tuple[str, ...], refresh_token: int = 0) -> MarketSnapshotResponse:
    """Fetch major market plus watchlist day-to-date performance."""
    return market_data_service().build_market_snapshot(list(tickers))


@st.cache_data(ttl=120, show_spinner=False)
def build_scanner(tickers: tuple[str, ...], refresh_token: int = 0) -> ScannerResponse:
    """Run setup scanner and intraday pattern analysis."""
    return scanner_service().build_scanner(list(tickers), include_setup=True, include_patterns=True)


@st.cache_data(ttl=120, show_spinner=False)
def build_chart_history(
    tickers: tuple[str, ...],
    chart_range: ChartRange,
    interval: ChartInterval,
    refresh_token: int = 0,
) -> ChartHistoryResponse:
    """Fetch OHLC chart history for line and candlestick charts."""
    return market_data_service().build_chart_history(list(tickers), chart_range, interval)


@st.cache_data(show_spinner=False)
def lightweight_charts_bundle_b64() -> str:
    """Return the vendored TradingView Lightweight Charts bundle for Streamlit iframes."""
    return base64.b64encode(LIGHTWEIGHT_CHARTS_BUNDLE_PATH.read_bytes()).decode("ascii")


def fmt(value: Any) -> str:
    """Format display values for Streamlit tables."""
    if value is None or value == "":
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def normalize_ticker_list(value: str | list[str]) -> list[str]:
    """Normalize delimited ticker text or a ticker list while preserving order."""
    candidates = value if isinstance(value, list) else value.replace(",", " ").split()
    cleaned: list[str] = []
    for candidate in candidates:
        ticker = str(candidate).strip().upper()
        if ticker and ticker not in cleaned:
            cleaned.append(ticker)
    return cleaned


def streamlit_state_path() -> Path:
    """Return the server-side Streamlit state file path."""
    configured = os.getenv(STREAMLIT_STATE_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".investment_trading" / "streamlit_state.json"


def load_streamlit_watchlist(path: Path | None = None) -> list[str]:
    """Load a persisted Streamlit watchlist, falling back quietly to empty."""
    state_path = path or streamlit_state_path()
    try:
        data = json.loads(state_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    return normalize_ticker_list(data.get("watchlist", []))


def save_streamlit_watchlist(tickers: list[str], path: Path | None = None) -> None:
    """Persist the Streamlit watchlist to a small server-side JSON file."""
    state_path = path or streamlit_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "watchlist": normalize_ticker_list(tickers),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def refresh_bucket(now: datetime | None = None, interval_seconds: int = AUTO_REFRESH_SECONDS) -> int:
    """Return the current auto-refresh bucket for cache invalidation."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return int(current.timestamp() // interval_seconds)


def bump_streamlit_refresh_token() -> int:
    """Advance the Streamlit data refresh token and return it."""
    st.session_state.streamlit_refresh_token = int(st.session_state.get("streamlit_refresh_token", 0)) + 1
    st.session_state.autoload_key = None
    return int(st.session_state.streamlit_refresh_token)


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
            --page-gutter: clamp(0.75rem, 2vw, 2.75rem);
            --content-max: 2600px;
            --content-width: min(var(--content-max), calc(100vw - (var(--page-gutter) * 2)));
            background: #eef2f1;
            color: #111827;
          }
          .stApp,
          .stApp p,
          .stApp label,
          .stApp li,
          .stApp div[data-testid="stMarkdownContainer"] {
            color: #111827;
          }
          .stApp a {
            color: #0284c7;
            font-weight: 800;
          }
          .stApp a:hover {
            color: #0f766e;
          }
          div[data-testid="stCaptionContainer"],
          div[data-testid="stCaptionContainer"] * {
            color: #64748b !important;
          }
          header[data-testid="stHeader"] {
            background: rgba(255, 255, 255, 0.96);
            border-bottom: 1px solid #d5ddd9;
          }
          .block-container {
            max-width: var(--content-max);
            padding-left: var(--page-gutter);
            padding-right: var(--page-gutter);
            padding-top: 2rem;
            width: 100%;
          }
          .stApp [data-testid="stDataFrame"],
          .stApp [data-testid="stDataFrame"] > div,
          .stApp [data-testid="stTable"],
          .stApp [data-testid="stTable"] > div {
            max-width: 100%;
            min-width: 0;
            overflow-x: auto !important;
          }
          .stApp [data-testid="stHorizontalBlock"],
          .stApp [data-testid="stVerticalBlock"],
          .stApp [data-testid="stVerticalBlockBorderWrapper"] {
            min-width: 0;
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
          .streamlit-brand-ribbon {
            align-items: center;
            background: rgba(255, 255, 255, 0.96);
            border-bottom: 1px solid #d5ddd9;
            display: flex;
            margin: -1rem 0 1rem;
            min-height: 4.25rem;
            padding: 0;
          }
          div[data-testid="stHorizontalBlock"]:has(.streamlit-nav-marker) {
            align-items: center;
            background: rgba(255, 255, 255, 0.94);
            border-bottom: 1px solid #d5ddd9;
            margin: -1rem 0 1rem;
            min-height: 3.25rem;
            padding: 0;
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
            color: #0f766e !important;
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
          div[data-testid="stButton"] button[kind="primary"] *,
          div[data-testid="stDownloadButton"] button[kind="primary"] * {
            color: #ffffff !important;
          }
          div[data-testid="stButton"] button[kind="secondary"],
          div[data-testid="stDownloadButton"] button[kind="secondary"] {
            background: #ffffff;
            border: 1px solid #d5ddd9;
            color: #334155;
          }
          div[data-testid="stButton"] button[kind="secondary"] *,
          div[data-testid="stDownloadButton"] button[kind="secondary"] * {
            color: #334155 !important;
          }
          div[data-testid="stButton"] button:hover,
          div[data-testid="stDownloadButton"] button:hover {
            border-color: #0f766e;
            transform: translateY(-1px);
          }
          div[data-testid="stVerticalBlock"]:has(.view-hero-marker):has(button):not(:has(.streamlit-brand)) {
            background: #ffffff;
            border: 1px solid #d5ddd9;
            border-radius: 0.5rem;
            box-shadow: 0 8px 28px rgba(17, 24, 39, 0.08);
            margin: 1rem 0;
            padding: 1.5rem;
          }
          div[data-testid="stVerticalBlock"]:has(.view-hero-marker) h1 {
            color: #111827;
            font-size: clamp(1.9rem, 4vw, 3.25rem);
            line-height: 1.05;
            margin: 0;
          }
          div[data-testid="stVerticalBlock"]:has(.view-hero-marker) p {
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
          .streamlit-news-card {
            background: #ffffff;
            border: 1px solid #dbe3ef;
            border-radius: 0.5rem;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
            display: grid;
            gap: 0.65rem;
            margin: 0 0 0.75rem;
            overflow: hidden;
            padding: 1rem;
          }
          .streamlit-market-grid {
            display: grid;
            gap: 0.75rem;
            grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
            margin: 0.5rem 0 1rem;
          }
          .streamlit-market-grid.major {
            background: #111827;
            border-radius: 0.5rem;
            padding: 0.8rem;
          }
          .streamlit-market-tile {
            background: #ffffff;
            border: 1px solid #dbe3ef;
            border-radius: 0.5rem;
            display: grid;
            gap: 0.35rem;
            padding: 0.8rem;
          }
          .streamlit-market-grid.major .streamlit-market-tile {
            background: transparent;
            border-color: rgba(148, 163, 184, 0.24);
            color: #ffffff !important;
          }
          .streamlit-market-tile h4 {
            color: inherit !important;
            font-size: 0.9rem;
            margin: 0;
          }
          .streamlit-market-price {
            color: inherit !important;
            font-size: 1.15rem;
            font-weight: 900;
          }
          .streamlit-market-change {
            color: #64748b !important;
            font-size: 0.86rem;
            font-weight: 900;
          }
          .streamlit-market-change.positive { color: #059669 !important; }
          .streamlit-market-change.negative { color: #dc2626 !important; }
          .streamlit-market-grid.major .streamlit-market-change.positive { color: #10b981 !important; }
          .streamlit-market-grid.major .streamlit-market-change.negative { color: #f43f5e !important; }
          .streamlit-news-card.with-image {
            grid-template-columns: 9rem 1fr;
          }
          .streamlit-news-card img {
            border-radius: 0.45rem;
            height: 100%;
            min-height: 7rem;
            object-fit: cover;
            width: 100%;
          }
          .streamlit-news-body {
            display: grid;
            gap: 0.45rem;
          }
          .streamlit-news-title {
            color: #111827 !important;
            font-size: 1rem;
            font-weight: 900;
            line-height: 1.35;
            text-decoration: none;
          }
          .streamlit-news-title:hover {
            color: #0f766e;
            text-decoration: underline;
          }
          .streamlit-news-meta,
          .streamlit-news-related {
            color: #64748b !important;
            font-size: 0.78rem;
            font-weight: 800;
          }
          .streamlit-news-summary {
            color: #334155 !important;
            line-height: 1.55;
            margin: 0;
          }
          .streamlit-related-tickers {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
          }
          .streamlit-related-tickers span {
            background: #fef3c7;
            border: 1px solid #fde68a;
            border-radius: 999px;
            color: #92400e !important;
            font-size: 0.72rem;
            font-weight: 900;
            padding: 0.25rem 0.45rem;
          }
          .streamlit-news-category {
            background: #12312f;
            border-left: 4px solid #0f766e;
            border-radius: 0.45rem;
            color: #ffffff !important;
            font-size: 0.82rem;
            font-weight: 900;
            letter-spacing: 0.02em;
            margin: 0.75rem 0 0.4rem;
            padding: 0.55rem 0.7rem;
            text-transform: uppercase;
          }
          .streamlit-scanner-card {
            background: #ffffff;
            border: 1px solid #d5ddd9;
            border-radius: 0.5rem;
            box-shadow: 0 8px 28px rgba(17, 24, 39, 0.08);
            margin: 1rem 0;
            min-width: 0;
            overflow: hidden;
            padding: 1.25rem;
          }
          .streamlit-scanner-card h2,
          .streamlit-scanner-card h3,
          .streamlit-scanner-card p {
            color: #111827;
          }
          .streamlit-heatmap {
            border: 1px solid #dbe3ef;
            border-radius: 0.5rem;
            display: grid;
            gap: 0.25rem;
            margin-top: 0.75rem;
            overflow-x: auto;
            padding: 0.75rem;
          }
          .streamlit-takeaway {
            background: #f8fafc;
            border: 1px solid #dbe3ef;
            border-radius: 0.5rem;
            color: #334155 !important;
            margin: 0.4rem 0;
            padding: 0.75rem;
          }
          div[data-testid="stExpander"] details {
            background: #ffffff !important;
            border: 1px solid #dbe3ef !important;
            border-radius: 0.5rem !important;
            overflow: hidden;
          }
          div[data-testid="stExpander"] summary {
            background: #f8fafc !important;
            border-bottom: 1px solid #e2e8f0 !important;
            color: #111827 !important;
            font-weight: 900 !important;
          }
          div[data-testid="stExpander"] summary * {
            color: #111827 !important;
          }
          div[data-testid="stAlert"] *,
          div[data-testid="stAlert"] p {
            color: inherit !important;
          }
          [data-testid="stVerticalBlockBorderWrapper"] {
            background: #ffffff;
            border: 1px solid #d5ddd9;
            border-radius: 0.5rem;
            box-shadow: 0 8px 28px rgba(17, 24, 39, 0.08);
          }
          .stApp .block-container {
            padding-top: 0.75rem;
          }
          [data-testid="stSidebarCollapsedControl"],
          [data-testid="stSidebarCollapseButton"],
          [data-testid="stExpandSidebarButton"] {
            height: 3rem !important;
            left: 0.75rem !important;
            opacity: 1 !important;
            position: fixed !important;
            top: 0.75rem !important;
            visibility: visible !important;
            width: 3rem !important;
            z-index: 100000 !important;
          }
          [data-testid="stSidebarCollapsedControl"] button,
          [data-testid="stSidebarCollapseButton"] button,
          [data-testid="stExpandSidebarButton"] button,
          [data-testid="stExpandSidebarButton"],
          button[aria-label="Open sidebar"],
          button[aria-label="Close sidebar"],
          button[title="Open sidebar"],
          button[title="Close sidebar"] {
            align-items: center !important;
            background: #0b2f2d !important;
            border: 2px solid #2dd4bf !important;
            border-radius: 0.7rem !important;
            box-shadow: 0 12px 28px rgba(17, 49, 47, 0.34) !important;
            color: #ccfbf1 !important;
            display: inline-flex !important;
            height: 3rem !important;
            justify-content: center !important;
            left: 0.75rem !important;
            min-height: 3rem !important;
            min-width: 3rem !important;
            opacity: 1 !important;
            overflow: hidden !important;
            padding: 0 !important;
            position: fixed !important;
            top: 0.75rem !important;
            width: 3rem !important;
            z-index: 100001 !important;
          }
          [data-testid="stSidebarCollapsedControl"] button:hover,
          [data-testid="stSidebarCollapseButton"] button:hover,
          [data-testid="stExpandSidebarButton"] button:hover,
          [data-testid="stExpandSidebarButton"]:hover,
          button[aria-label="Open sidebar"]:hover,
          button[aria-label="Close sidebar"]:hover,
          button[title="Open sidebar"]:hover,
          button[title="Close sidebar"]:hover {
            background: #0f766e !important;
            border-color: #5eead4 !important;
          }
          [data-testid="stSidebarCollapsedControl"] button:focus-visible,
          [data-testid="stSidebarCollapseButton"] button:focus-visible,
          [data-testid="stExpandSidebarButton"] button:focus-visible,
          [data-testid="stExpandSidebarButton"]:focus-visible,
          button[aria-label="Open sidebar"]:focus-visible,
          button[aria-label="Close sidebar"]:focus-visible,
          button[title="Open sidebar"]:focus-visible,
          button[title="Close sidebar"]:focus-visible {
            outline: 3px solid rgba(45, 212, 191, 0.45) !important;
            outline-offset: 2px !important;
          }
          [data-testid="stSidebarCollapsedControl"] button::before,
          [data-testid="stSidebarCollapseButton"] button::before,
          [data-testid="stExpandSidebarButton"] button::before,
          [data-testid="stExpandSidebarButton"]::before,
          button[aria-label="Open sidebar"]::before,
          button[aria-label="Close sidebar"]::before,
          button[title="Open sidebar"]::before,
          button[title="Close sidebar"]::before {
            align-items: center;
            color: #ccfbf1 !important;
            content: "\\00AB";
            display: flex;
            font-family: Arial, Helvetica, sans-serif;
            font-size: 1.75rem;
            font-weight: 900;
            inset: 0;
            justify-content: center;
            line-height: 1;
            pointer-events: none;
            position: absolute;
            z-index: 2;
          }
          [data-testid="stSidebarCollapsedControl"] button::before,
          [data-testid="stExpandSidebarButton"] button::before,
          [data-testid="stExpandSidebarButton"]::before,
          button[aria-label="Open sidebar"]::before,
          button[title="Open sidebar"]::before {
            content: "\\00BB";
          }
          [data-testid="stSidebarCollapsedControl"] button > *,
          [data-testid="stSidebarCollapseButton"] button > *,
          [data-testid="stExpandSidebarButton"] button > *,
          [data-testid="stExpandSidebarButton"] > *,
          button[aria-label="Open sidebar"] > *,
          button[aria-label="Close sidebar"] > *,
          button[title="Open sidebar"] > *,
          button[title="Close sidebar"] > * {
            opacity: 0 !important;
          }
          [data-testid="stSidebarCollapsedControl"] svg,
          [data-testid="stSidebarCollapseButton"] svg,
          [data-testid="stExpandSidebarButton"] svg,
          button[aria-label="Open sidebar"] svg,
          button[aria-label="Close sidebar"] svg,
          button[title="Open sidebar"] svg,
          button[title="Close sidebar"] svg,
          [data-testid="stSidebarCollapsedControl"] svg *,
          [data-testid="stSidebarCollapseButton"] svg *,
          [data-testid="stExpandSidebarButton"] svg *,
          button[aria-label="Open sidebar"] svg *,
          button[aria-label="Close sidebar"] svg *,
          button[title="Open sidebar"] svg *,
          button[title="Close sidebar"] svg * {
            color: #ccfbf1 !important;
            fill: #ccfbf1 !important;
            stroke: #ccfbf1 !important;
            -webkit-text-fill-color: #ccfbf1 !important;
          }
          [data-testid="stSidebar"] input,
          [data-testid="stSidebar"] textarea,
          [data-testid="stSidebar"] [data-baseweb="input"] input {
            background: #ffffff !important;
            border: 1px solid #cbd5e1 !important;
            color: #111827 !important;
            font-weight: 800 !important;
            min-height: 2.65rem;
          }
          [data-testid="stSidebar"] input::placeholder {
            color: #94a3b8 !important;
            font-weight: 700 !important;
            opacity: 1 !important;
          }
          [data-testid="stSidebar"] [data-testid="stButton"] button {
            align-items: center;
            border-radius: 0.55rem;
            font-weight: 900;
            justify-content: center;
            line-height: 1;
            min-height: 2.45rem;
            min-width: 2.35rem;
            padding: 0.45rem 0.65rem;
            white-space: nowrap;
          }
          [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] {
            background: #0f766e !important;
            border-color: #0f766e !important;
            color: #ffffff !important;
            box-shadow: 0 10px 20px rgba(15, 118, 110, 0.22) !important;
          }
          [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"]:hover {
            background: #115e59 !important;
            border-color: #115e59 !important;
          }
          [data-testid="stSidebar"] [data-testid="stButton"] button:disabled {
            opacity: 0.45 !important;
          }
          .streamlit-brand-ribbon {
            margin: -0.75rem 0 0;
            min-height: 4.25rem;
            position: sticky;
            top: 0;
            z-index: 30;
          }
          div[data-testid="stHorizontalBlock"]:has(.streamlit-nav-marker) {
            margin: 0 0 1rem;
            min-height: 3.25rem;
            position: sticky;
            top: 4.25rem;
            z-index: 29;
          }
          .streamlit-page-hero,
          .streamlit-section-panel,
          .streamlit-report-panel,
          .streamlit-scanner-panel {
            background: #ffffff;
            border: 1px solid #d5ddd9;
            border-radius: 0.5rem;
            box-shadow: 0 8px 28px rgba(17, 24, 39, 0.08);
            margin: 0 0 1rem;
            padding: 1.25rem;
          }
          .streamlit-page-hero {
            align-items: center;
            display: flex;
            gap: 1rem;
            justify-content: space-between;
          }
          .streamlit-page-hero h1 {
            color: #111827 !important;
            font-size: clamp(2rem, 4vw, 3.25rem);
            line-height: 1.05;
            margin: 0;
          }
          .streamlit-section-header,
          .streamlit-chart-header {
            align-items: center;
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            justify-content: space-between;
            margin-bottom: 0.85rem;
          }
          .streamlit-section-header h2,
          .streamlit-chart-header h2 {
            color: #111827;
            margin: 0;
          }
          .streamlit-status-chip {
            background: #ccfbf1;
            border: 1px solid #99f6e4;
            border-radius: 999px;
            color: #0f766e !important;
            font-size: 0.78rem;
            font-weight: 900;
            padding: 0.35rem 0.6rem;
          }
          .streamlit-watchlist-row {
            align-items: center;
            background: #f8fafc;
            border: 1px solid #dbe3ef;
            border-radius: 0.5rem;
            display: flex;
            gap: 0.55rem;
            justify-content: space-between;
            margin: 0.4rem 0;
            padding: 0.45rem 0.55rem 0.45rem 0.75rem;
          }
          .streamlit-watchlist-row strong {
            color: #111827;
            letter-spacing: 0.04em;
          }
          .streamlit-report-grid,
          .streamlit-chart-grid,
          .streamlit-ticker-news-grid {
            align-items: start;
            display: grid;
            gap: 0.9rem;
            grid-template-columns: repeat(auto-fit, minmax(min(340px, 100%), 1fr));
          }
          .streamlit-chart-grid {
            grid-template-columns: repeat(auto-fit, minmax(min(320px, 100%), 1fr));
          }
          .streamlit-news-grid {
            display: grid;
            gap: 0.75rem;
            grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr));
            margin-bottom: 1rem;
          }
          .streamlit-chart-card {
            background: #ffffff;
            border: 1px solid #dbe3ef;
            border-radius: 0.5rem;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.07);
            margin-bottom: 0.9rem;
            min-width: 0;
            padding: 0.75rem;
          }
          .streamlit-chart-card h4 {
            color: #0f172a;
            letter-spacing: 0.06em;
            margin: 0 0 0.65rem;
          }
          .streamlit-chart-controls {
            align-items: center;
            display: grid;
            gap: 0.55rem;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            margin-bottom: 0.75rem;
          }
          .streamlit-chart-controls [data-testid="stSelectbox"],
          .streamlit-chart-controls [data-testid="stRadio"] {
            min-width: 0;
          }
          .streamlit-chart-frame {
            border: 1px solid #eef2f7;
            border-radius: 0.5rem;
            min-height: 232px;
            overflow: hidden;
          }
          .streamlit-ticker-news-card {
            align-content: start;
            background: #f8fafc;
            border: 1px solid #dbe3ef;
            border-radius: 0.5rem;
            display: grid;
            gap: 0.65rem;
            padding: 0.85rem;
          }
          .streamlit-ticker-news-card h4 {
            color: #12312f;
            letter-spacing: 0.06em;
            margin: 0;
          }
          .streamlit-news-category-details {
            background: #ffffff;
            border: 1px solid #dbe3ef;
            border-left: 4px solid #0f766e;
            border-radius: 0.5rem;
            margin-top: 0.5rem;
            overflow: hidden;
          }
          .streamlit-news-category-details summary {
            background: #12312f;
            color: #ffffff;
            cursor: pointer;
            font-size: 0.78rem;
            font-weight: 900;
            letter-spacing: 0.05em;
            padding: 0.55rem 0.7rem;
            text-transform: uppercase;
          }
          .streamlit-news-category-details > div {
            display: grid;
            gap: 0.5rem;
            padding: 0.55rem;
          }
          @media (max-width: 760px) {
            .stApp {
              --page-gutter: 0.5rem;
            }
            .block-container {
              padding-left: 0.5rem;
              padding-right: 0.5rem;
            }
            .streamlit-news-card.with-image {
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
            .streamlit-page-hero,
            .streamlit-section-header,
            .streamlit-chart-header {
              align-items: stretch;
              display: grid;
            }
            .streamlit-chart-controls {
              grid-template-columns: 1fr;
            }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="streamlit-brand-ribbon">
          <div class="streamlit-brand">
            <span class="brand-mark">IT</span>
            <span class="brand-name">Investment Trading</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    nav_spacer, levels_col, news_col = st.columns([2.2, 1, 1], vertical_alignment="center")
    with nav_spacer:
        st.markdown('<span class="streamlit-nav-marker"></span>', unsafe_allow_html=True)
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
    """Persist the active Streamlit view."""
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


def metric_card_html(metric: EquityMetrics) -> str:
    """Return one ticker card styled like the static app."""
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

    warning_html = ""
    if metric.warnings:
        items = "".join(f"<li>{escape(warning)}</li>" for warning in metric.warnings)
        warning_html = (
            f'<details class="warning"><summary>{len(metric.warnings)} data warning(s)</summary>'
            f"<ul>{items}</ul></details>"
        )

    return (
        '<article class="metric-card">'
        '<div class="metric-card-header">'
        f'<div><span class="drag-glyph">&vellip;</span> <h3 style="display:inline">{escape(metric.ticker)}</h3></div>'
        "</div>"
        f'<div class="metric-card-body">{"".join(section_html)}{warning_html}</div>'
        "</article>"
    )


def render_metric_card(metric: EquityMetrics) -> None:
    """Render one ticker report card."""
    st.markdown(metric_card_html(metric), unsafe_allow_html=True)


def render_metric_grid(metrics: list[EquityMetrics]) -> None:
    """Render ticker report cards in a responsive grid."""
    cards = "".join(metric_card_html(metric) for metric in metrics)
    st.markdown(f'<div class="streamlit-report-grid">{cards}</div>', unsafe_allow_html=True)


def render_metric(metric: EquityMetrics) -> None:
    """Render one ticker report section."""
    render_metric_card(metric)
    if metric.warnings:
        with st.expander(f"{len(metric.warnings)} data warning(s)"):
            for warning in metric.warnings:
                st.warning(warning)


def chart_history_frame(chart: TickerChartHistory) -> pd.DataFrame:
    """Build a DataFrame from backend OHLC chart points."""
    return pd.DataFrame(
        [
            {
                "timestamp": point.timestamp,
                "open": point.open,
                "high": point.high,
                "low": point.low,
                "close": point.close,
            }
            for point in chart.points
        ]
    )


def render_chart_history(
    report: GenerateResponse,
    chart_range: ChartRange,
    interval: ChartInterval,
    chart_type: str,
    refresh_token: int = 0,
) -> None:
    """Render compact line/candlestick charts in report order."""
    tickers = tuple(metric.ticker for metric in report.metrics)
    if not tickers:
        return
    response = build_chart_history(tickers, chart_range, interval, refresh_token=refresh_token)
    charts_by_ticker = {chart.ticker: chart for chart in response.charts}
    st.markdown(
        (
            '<div class="streamlit-chart-header">'
            "<h2>Charts</h2>"
            '<span class="streamlit-status-chip">Auto-refreshes every 5 min</span>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    columns = st.columns(3)
    for index, ticker in enumerate(tickers):
        chart = charts_by_ticker.get(ticker)
        with columns[index % len(columns)]:
            with st.container(border=True):
                st.markdown(f'<span class="streamlit-chart-card-marker"></span><h4>{escape(ticker)}</h4>', unsafe_allow_html=True)
                override_range, override_interval, override_type = chart_range, interval, chart_type
                with st.expander("Chart settings", expanded=False):
                    override_type = st.radio(
                        "Type",
                        CHART_TYPE_OPTIONS,
                        horizontal=True,
                        key=f"chart-type-{ticker}",
                        index=CHART_TYPE_OPTIONS.index(chart_type),
                    )
                    override_range = st.selectbox(
                        "Range",
                        CHART_RANGE_OPTIONS,
                        key=f"chart-range-{ticker}",
                        index=CHART_RANGE_OPTIONS.index(chart_range),
                        format_func=format_chart_option,
                    )
                    interval_options = CHART_INTERVALS_BY_RANGE[override_range]
                    default_interval = interval if interval in interval_options else CHART_DEFAULT_INTERVAL_BY_RANGE[override_range]
                    override_interval = st.selectbox(
                        "Interval",
                        interval_options,
                        key=f"chart-interval-{ticker}",
                        index=interval_options.index(default_interval),
                    )
                if (override_range, override_interval) != (chart_range, interval):
                    chart = build_chart_history(
                        (ticker,),
                        override_range,
                        override_interval,
                        refresh_token=refresh_token,
                    ).charts[0]
                if chart is None or not chart.points:
                    st.caption("No chart data returned.")
                    continue
                render_single_chart(chart, override_type, override_range, override_interval)
                for warning in chart.warnings:
                    st.caption(warning)


def render_single_chart(
    chart: TickerChartHistory,
    chart_type: str,
    chart_range: ChartRange,
    interval: ChartInterval,
) -> None:
    """Render one Streamlit chart using TradingView Lightweight Charts."""
    if not chart.points:
        st.caption("No chart data returned.")
        return
    components.html(
        lightweight_chart_html(chart, chart_type, chart_range, interval),
        height=332,
        scrolling=False,
    )


def lightweight_chart_html(
    chart: TickerChartHistory,
    chart_type: str,
    chart_range: ChartRange,
    interval: ChartInterval,
) -> str:
    """Return an embeddable Lightweight Charts document for one ticker."""
    payload = {
        "ticker": chart.ticker,
        "chartType": "candles" if chart_type == "Candles" else "line",
        "range": format_chart_option(chart_range),
        "interval": interval,
        "points": [
            {
                "timestamp": point.timestamp.isoformat(),
                "open": point.open,
                "high": point.high,
                "low": point.low,
                "close": point.close,
            }
            for point in chart.points
        ],
    }
    payload_json = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    bundle_b64 = lightweight_charts_bundle_b64()
    return (
        """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <script src="data:text/javascript;base64,__LIGHTWEIGHT_CHARTS_BUNDLE__"></script>
  <style>
    :root {
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      background: transparent;
      margin: 0;
      overflow: hidden;
    }
    .chart-shell {
      background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
      border: 1px solid #dbe3ef;
      border-radius: 10px;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
      min-width: 0;
      overflow: hidden;
      padding: 12px 12px 8px;
      position: relative;
      width: 100%;
    }
    .chart-top {
      align-items: start;
      display: flex;
      gap: 10px;
      justify-content: space-between;
      min-height: 42px;
      padding: 0 2px 6px;
    }
    .ticker {
      color: #0f172a;
      font-size: 14px;
      font-weight: 900;
      letter-spacing: 0.06em;
      line-height: 1.2;
    }
    .meta {
      color: #64748b;
      font-size: 10px;
      font-weight: 800;
      letter-spacing: 0.08em;
      margin-top: 3px;
      text-transform: uppercase;
    }
    .last-price {
      color: #0f172a;
      font-size: 13px;
      font-weight: 900;
      line-height: 1.2;
      text-align: right;
      white-space: nowrap;
    }
    .change {
      color: #64748b;
      display: block;
      font-size: 11px;
      font-weight: 900;
      margin-top: 3px;
    }
    .change.up { color: #059669; }
    .change.down { color: #dc2626; }
    #chart-canvas {
      height: 238px;
      min-width: 0;
      position: relative;
      width: 100%;
    }
    .empty {
      align-items: center;
      background: #f8fafc;
      border: 1px dashed #cbd5e1;
      border-radius: 8px;
      color: #64748b;
      display: none;
      font-size: 13px;
      font-weight: 800;
      height: 238px;
      justify-content: center;
      text-align: center;
    }
    .tooltip {
      background: rgba(15, 23, 42, 0.92);
      border: 1px solid rgba(148, 163, 184, 0.35);
      border-radius: 8px;
      box-shadow: 0 14px 30px rgba(15, 23, 42, 0.18);
      color: #e2e8f0;
      display: none;
      font-size: 11px;
      font-weight: 800;
      left: 0;
      line-height: 1.45;
      min-width: 126px;
      padding: 8px 9px;
      pointer-events: none;
      position: absolute;
      top: 0;
      z-index: 10;
    }
    .tooltip strong {
      color: #ffffff;
      display: block;
      font-size: 11px;
      margin-bottom: 3px;
    }
    .attribution {
      color: #94a3b8;
      font-size: 10px;
      font-weight: 700;
      padding: 3px 2px 0;
    }
    .attribution a {
      color: #0f766e;
      font-weight: 900;
      text-decoration: none;
    }
  </style>
</head>
<body>
  <script type="application/json" id="chart-payload">__CHART_PAYLOAD__</script>
  <div class="chart-shell">
    <div class="chart-top">
      <div>
        <div class="ticker" id="ticker-label"></div>
        <div class="meta" id="chart-meta"></div>
      </div>
      <div class="last-price" id="last-price"></div>
    </div>
    <div id="chart-canvas"></div>
    <div class="empty" id="empty-state">No chart data returned.</div>
    <div class="tooltip" id="tooltip"></div>
    <div class="attribution">Lightweight Charts by <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView</a></div>
  </div>
  <script>
    (function () {
      const payload = JSON.parse(document.getElementById("chart-payload").textContent);
      const container = document.getElementById("chart-canvas");
      const empty = document.getElementById("empty-state");
      const tooltip = document.getElementById("tooltip");
      const tickerLabel = document.getElementById("ticker-label");
      const metaLabel = document.getElementById("chart-meta");
      const lastPrice = document.getElementById("last-price");
      const intradayIntervals = new Set(["5m", "15m", "1h"]);
      const isIntraday = intradayIntervals.has(payload.interval);
      const easternFormatter = new Intl.DateTimeFormat("en-US", {
        timeZone: "America/New_York",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
      const displayTimeFormatter = new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
        hour: isIntraday ? "numeric" : undefined,
        minute: isIntraday ? "2-digit" : undefined,
      });

      function price(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) return "-";
        return number.toLocaleString(undefined, {
          minimumFractionDigits: number >= 100 ? 2 : 2,
          maximumFractionDigits: number >= 100 ? 2 : 4,
        });
      }

      function numberOrNull(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number : null;
      }

      function easternTimestampSeconds(timestamp) {
        const date = new Date(timestamp);
        if (Number.isNaN(date.getTime())) return null;
        if (!isIntraday) return String(timestamp || "").slice(0, 10);
        const parts = Object.fromEntries(
          easternFormatter
            .formatToParts(date)
            .filter((part) => part.type !== "literal")
            .map((part) => [part.type, part.value])
        );
        const hour = Number(parts.hour) === 24 ? 0 : Number(parts.hour);
        return Math.floor(Date.UTC(
          Number(parts.year),
          Number(parts.month) - 1,
          Number(parts.day),
          hour,
          Number(parts.minute)
        ) / 1000);
      }

      function compareTimes(left, right) {
        if (typeof left.time === "number" && typeof right.time === "number") return left.time - right.time;
        return String(left.time).localeCompare(String(right.time));
      }

      const points = (payload.points || [])
        .map((point) => ({
          time: easternTimestampSeconds(point.timestamp),
          timestamp: point.timestamp,
          open: numberOrNull(point.open),
          high: numberOrNull(point.high),
          low: numberOrNull(point.low),
          close: numberOrNull(point.close),
        }))
        .filter((point) => point.time && Number.isFinite(point.close))
        .sort(compareTimes);

      tickerLabel.textContent = payload.ticker;
      metaLabel.textContent = `${payload.chartType === "candles" ? "Candles" : "Line"} · ${payload.range} · ${payload.interval}`;

      if (!window.LightweightCharts || points.length === 0) {
        container.style.display = "none";
        empty.style.display = "flex";
        return;
      }

      const first = points[0];
      const last = points[points.length - 1];
      const change = last.close - first.close;
      const changePercent = first.close ? (change / first.close) * 100 : 0;
      const changeClass = change > 0 ? "up" : change < 0 ? "down" : "";
      lastPrice.innerHTML = `${price(last.close)}<span class="change ${changeClass}">${change >= 0 ? "+" : ""}${price(change)} ${changePercent >= 0 ? "+" : ""}${changePercent.toFixed(2)}%</span>`;

      const chartApi = LightweightCharts.createChart(container, {
        width: container.clientWidth || 360,
        height: 238,
        layout: {
          background: { type: "solid", color: "#ffffff" },
          textColor: "#64748b",
          fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
          fontSize: 11,
        },
        grid: {
          vertLines: { color: "#f1f5f9" },
          horzLines: { color: "#edf2f7" },
        },
        rightPriceScale: {
          borderVisible: false,
          scaleMargins: { top: 0.14, bottom: 0.14 },
        },
        timeScale: {
          borderVisible: false,
          fixLeftEdge: true,
          fixRightEdge: true,
          minBarSpacing: 0.5,
          rightOffset: 2,
          timeVisible: isIntraday,
          secondsVisible: false,
        },
        crosshair: {
          mode: LightweightCharts.CrosshairMode.Normal,
          vertLine: { color: "#94a3b8", labelBackgroundColor: "#0f172a" },
          horzLine: { color: "#94a3b8", labelBackgroundColor: "#0f172a" },
        },
        localization: {
          priceFormatter: price,
        },
        handleScale: {
          axisPressedMouseMove: false,
          mouseWheel: false,
          pinch: false,
        },
        handleScroll: {
          horzTouchDrag: true,
          mouseWheel: false,
          pressedMouseMove: true,
          vertTouchDrag: false,
        },
      });

      const series = payload.chartType === "candles"
        ? chartApi.addSeries(LightweightCharts.CandlestickSeries, {
            upColor: "#059669",
            downColor: "#dc2626",
            borderVisible: false,
            wickUpColor: "#059669",
            wickDownColor: "#dc2626",
            priceLineVisible: false,
            lastValueVisible: true,
          })
        : chartApi.addSeries(LightweightCharts.AreaSeries, {
            lineColor: "#0f766e",
            topColor: "rgba(15, 118, 110, 0.22)",
            bottomColor: "rgba(15, 118, 110, 0.03)",
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: true,
            crosshairMarkerVisible: true,
            crosshairMarkerRadius: 4,
          });

      const seriesData = payload.chartType === "candles"
        ? points
            .filter((point) => [point.open, point.high, point.low, point.close].every(Number.isFinite))
            .map((point) => ({ time: point.time, open: point.open, high: point.high, low: point.low, close: point.close }))
        : points.map((point) => ({ time: point.time, value: point.close }));

      series.setData(seriesData);
      chartApi.timeScale().fitContent();

      function resizeChart() {
        chartApi.applyOptions({ width: container.clientWidth || 360, height: 238 });
        chartApi.timeScale().fitContent();
      }

      if (window.ResizeObserver) {
        new ResizeObserver(resizeChart).observe(container);
      } else {
        window.addEventListener("resize", resizeChart);
      }
      window.requestAnimationFrame(resizeChart);

      chartApi.subscribeCrosshairMove((param) => {
        const item = param.seriesData.get(series);
        if (!item || !param.point || param.point.x < 0 || param.point.y < 0) {
          tooltip.style.display = "none";
          return;
        }
        const index = Math.max(0, Math.min(points.length - 1, points.findIndex((point) => point.time === param.time)));
        const sourcePoint = points[index] || last;
        const close = item.value ?? item.close;
        const body = payload.chartType === "candles"
          ? `O ${price(item.open)} · H ${price(item.high)}<br>L ${price(item.low)} · C ${price(item.close)}`
          : `Close ${price(close)}`;
        tooltip.innerHTML = `<strong>${displayTimeFormatter.format(new Date(sourcePoint.timestamp))}</strong>${body}`;
        const box = tooltip.getBoundingClientRect();
        const shell = document.querySelector(".chart-shell").getBoundingClientRect();
        const left = Math.min(param.point.x + 16, shell.width - box.width - 12);
        const top = Math.max(54, Math.min(param.point.y + 56, shell.height - box.height - 18));
        tooltip.style.left = `${Math.max(8, left)}px`;
        tooltip.style.top = `${top}px`;
        tooltip.style.display = "block";
      });
    })();
  </script>
</body>
</html>
        """
        .replace("__LIGHTWEIGHT_CHARTS_BUNDLE__", bundle_b64)
        .replace("__CHART_PAYLOAD__", payload_json)
    )


def format_chart_option(option: str) -> str:
    """Return user-facing chart control labels without changing API values."""
    return CHART_RANGE_LABELS.get(option, option)


def render_article(article: NewsArticle) -> None:
    """Render one normalized news article as a readable light-theme card."""
    st.markdown(article_card_html(article), unsafe_allow_html=True)


def article_card_html(article: NewsArticle, compact: bool = False) -> str:
    """Return one normalized news article card."""
    published = article.published_at.astimezone().strftime("%Y-%m-%d %H:%M") if article.published_at else None
    meta = " | ".join(item for item in [article.publisher, published] if item)
    classes = "streamlit-news-card"
    if article.thumbnail_url and not compact:
        classes += " with-image"
    image_html = (
        f'<img src="{escape(article.thumbnail_url)}" alt="" loading="lazy" />'
        if article.thumbnail_url and not compact
        else ""
    )
    if article.url:
        title_html = (
            f'<a class="streamlit-news-title" href="{escape(article.url)}" '
            f'target="_blank" rel="noopener noreferrer">{escape(article.title)}</a>'
        )
    else:
        title_html = f'<span class="streamlit-news-title">{escape(article.title)}</span>'
    meta_html = f'<div class="streamlit-news-meta">{escape(meta)}</div>' if meta else ""
    summary_html = f'<p class="streamlit-news-summary">{escape(article.summary)}</p>' if article.summary else ""
    related_html = ""
    if article.related_tickers:
        ticker_spans = "".join(
            f"<span>{escape(ticker)}</span>" for ticker in article.related_tickers[:8]
        )
        related_html = (
            '<div class="streamlit-news-related">Related</div>'
            f'<div class="streamlit-related-tickers">{ticker_spans}</div>'
        )

    return (
        f'<article class="{classes}">'
        f"{image_html}"
        '<div class="streamlit-news-body">'
        f"{title_html}{meta_html}{summary_html}{related_html}"
        "</div>"
        "</article>"
    )


def render_article_grid(articles: list[NewsArticle], compact: bool = False) -> None:
    """Render articles in a responsive static-style grid."""
    cards = "".join(article_card_html(article, compact=compact) for article in articles)
    st.markdown(f'<div class="streamlit-news-grid">{cards}</div>', unsafe_allow_html=True)


def group_articles_by_category(articles: list[NewsArticle]) -> dict[str, list[NewsArticle]]:
    """Return news articles keyed by the shared news category labels."""
    grouped: dict[str, list[NewsArticle]] = {}
    for article in articles:
        category = article.category if article.category in NEWS_CATEGORY_LABELS else "general"
        grouped.setdefault(category, []).append(article)
    return grouped


def render_categorized_articles(articles: list[NewsArticle]) -> None:
    """Render the full article list in stable category sections."""
    grouped = group_articles_by_category(articles)
    for category, label in NEWS_CATEGORY_LABELS.items():
        category_articles = grouped.get(category, [])
        if not category_articles:
            continue
        st.markdown(f'<div class="streamlit-news-category">{escape(label)} ({len(category_articles)})</div>', unsafe_allow_html=True)
        for article in category_articles:
            render_article(article)


def ticker_news_card_html(ticker_group: Any) -> str:
    """Return one watchlist news card with collapsed top headlines and categorized details."""
    articles = list(ticker_group.articles or [])
    visible_articles = articles[:NEWS_COLLAPSED_HEADLINE_COUNT]
    warnings = "".join(f'<div class="inline-warning">{escape(warning)}</div>' for warning in ticker_group.warnings)
    top_html = "".join(article_card_html(article, compact=True) for article in visible_articles)
    if not top_html:
        top_html = '<p class="news-empty">No recent headlines returned.</p>'

    grouped = group_articles_by_category(articles[:NEWS_EXPANDED_HEADLINE_COUNT])
    category_html = []
    if len(articles) > NEWS_COLLAPSED_HEADLINE_COUNT:
        for category, label in NEWS_CATEGORY_LABELS.items():
            category_articles = grouped.get(category, [])
            if not category_articles:
                continue
            category_cards = "".join(article_card_html(article, compact=True) for article in category_articles)
            category_html.append(
                '<details class="streamlit-news-category-details">'
                f'<summary>{escape(label)} ({len(category_articles)})</summary>'
                f"<div>{category_cards}</div>"
                "</details>"
            )

    return (
        '<article class="streamlit-ticker-news-card">'
        f'<h4>{escape(ticker_group.ticker)} <span>{len(articles)} headline(s)</span></h4>'
        f"{warnings}{top_html}{''.join(category_html)}"
        "</article>"
    )


def render_ticker_news_grid(ticker_news: list[Any]) -> None:
    """Render watchlist news groups in a compact responsive grid."""
    if not ticker_news:
        st.info("No watchlist news was returned.")
        return
    cards = "".join(ticker_news_card_html(group) for group in ticker_news)
    st.markdown(f'<div class="streamlit-ticker-news-grid">{cards}</div>', unsafe_allow_html=True)


def render_x_timeline() -> None:
    """Embed the public @unusual_whales X.com timeline with a fallback link."""
    components.html(
        """
        <a
          class="twitter-timeline"
          data-height="560"
          data-theme="light"
          data-dnt="true"
          href="https://twitter.com/unusual_whales?ref_src=twsrc%5Etfw"
        >
          Posts by @unusual_whales
        </a>
        <p id="x-fallback" style="display:none; font: 13px sans-serif; color: #64748b;">
          If the timeline does not load, open
          <a href="https://x.com/unusual_whales" target="_blank" rel="noopener noreferrer">@unusual_whales on X.com</a>.
        </p>
        <script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>
        <script>
          window.setTimeout(function () {
            if (!document.querySelector("iframe")) {
              document.getElementById("x-fallback").style.display = "block";
            }
          }, 6500);
        </script>
        """,
        height=640,
    )


def signed_fmt(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:+,.2f}"


def signed_pct_fmt(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:+.2f}%"


def render_snapshot_grid(snapshot: MarketSnapshotResponse | None) -> None:
    """Render major market and watchlist day-to-date cards."""
    if snapshot is None:
        st.info("Market performance has not loaded yet.")
        return
    st.subheader("US Markets")
    render_performance_rows(snapshot.market, major=True)
    st.subheader("Watchlist Performance")
    render_performance_rows(snapshot.watchlist, major=False)
    if snapshot.warnings:
        with st.expander(f"{len(snapshot.warnings)} market data note(s)", expanded=False):
            for warning in snapshot.warnings:
                st.caption(warning)


def render_performance_rows(rows: list[Any], major: bool) -> None:
    if not rows:
        st.info("No performance data was returned.")
        return
    cards = []
    for row in rows:
        change_class = "negative" if (row.change or 0) < 0 or (row.change_percent or 0) < 0 else "positive"
        cards.append(
            (
                '<article class="streamlit-market-tile">'
                f"<h4>{escape(row.label or row.symbol)}</h4>"
                f'<div class="streamlit-market-price">{escape(fmt(row.price))}</div>'
                f'<div class="streamlit-market-change {change_class}">'
                f"{escape(signed_fmt(row.change))} {escape(signed_pct_fmt(row.change_percent))}"
                "</div>"
                "</article>"
            )
        )
    classes = "streamlit-market-grid major" if major else "streamlit-market-grid"
    st.markdown(f'<div class="{classes}">{"".join(cards)}</div>', unsafe_allow_html=True)


def render_news(report: NewsResponse, snapshot: MarketSnapshotResponse | None = None) -> None:
    """Render watchlist and general market news."""
    for warning in report.warnings:
        st.warning(warning)

    render_snapshot_grid(snapshot)

    st.markdown('<div class="streamlit-section-header"><h2>General Market News</h2></div>', unsafe_allow_html=True)
    if report.general_market:
        render_article_grid(report.general_market)
    else:
        st.info("No general market headlines were returned.")

    st.markdown('<div class="streamlit-section-header"><h2>Watchlist News</h2></div>', unsafe_allow_html=True)
    render_ticker_news_grid(report.ticker_news)

    st.markdown('<div class="streamlit-section-header"><h2>X.com</h2></div>', unsafe_allow_html=True)
    render_x_timeline()


def render_scanner(report: ScannerResponse) -> None:
    """Render setup scanner and intraday pattern analysis."""
    for warning in report.warnings:
        st.warning(warning)

    setup_tab, pattern_tab = st.tabs(["Setup Scanner", "Intraday Pattern Analysis"])
    with setup_tab:
        if not report.setup_rows:
            st.info("No setup scanner rows were returned.")
        else:
            st.dataframe(
                styled_scanner_setup_frame(report),
                use_container_width=True,
                hide_index=True,
                row_height=42,
                height=dataframe_height(len(report.setup_rows), row_height=42),
            )
            warned = [row for row in report.setup_rows if row.warnings]
            for row in warned:
                st.warning(f"{row.ticker}: {' '.join(row.warnings)}")
            data_notes = [(row.ticker, note) for row in report.setup_rows for note in row.data_notes]
            if data_notes:
                with st.expander(f"{len(data_notes)} scanner data note(s)", expanded=False):
                    for ticker, note in data_notes:
                        st.caption(f"{ticker}: {note}")

    with pattern_tab:
        if not report.pattern_summary:
            st.info("No intraday pattern analysis was returned.")
            return
        st.subheader("Pattern Summary")
        st.dataframe(
            pattern_summary_frame(report),
            use_container_width=True,
            hide_index=True,
            row_height=40,
            height=dataframe_height(len(report.pattern_summary), row_height=40),
        )
        st.subheader("5-Min Heatmap")
        st.caption("Average percent from open by 5-minute ET bucket. Negative values mark below-open periods.")
        heatmap_frame = pattern_heatmap_frame(report)
        st.dataframe(
            heatmap_frame,
            use_container_width=True,
            hide_index=True,
            row_height=40,
            height=dataframe_height(len(heatmap_frame), row_height=40),
        )
        st.subheader("Per-Ticker Detail")
        for ticker in sorted({detail.ticker for detail in report.pattern_details}):
            rows = [detail for detail in report.pattern_details if detail.ticker == ticker]
            with st.expander(f"{ticker} - {len(rows)} days", expanded=False):
                st.dataframe(
                    pattern_detail_frame(rows),
                    use_container_width=True,
                    hide_index=True,
                    row_height=40,
                    height=dataframe_height(len(rows), row_height=40),
                )
        st.subheader("Key Takeaways")
        if report.takeaways:
            for takeaway in report.takeaways:
                st.markdown(f'<div class="streamlit-takeaway">{escape(takeaway)}</div>', unsafe_allow_html=True)
        else:
            st.info("No strong recurring pattern takeaways were found.")


def dataframe_height(row_count: int, row_height: int = 40, min_height: int = 160, max_height: int = 520) -> int:
    """Return a readable dataframe height with breathing room for header and rows."""
    return min(max_height, max(min_height, row_count * row_height + 46))


def scanner_setup_frame(report: ScannerResponse) -> pd.DataFrame:
    """Build a display frame for setup scanner rows."""
    rows = []
    for row in report.setup_rows:
        rows.append(
            {
                "Score": f"{row.score}/8" if row.score is not None else "-",
                "Ticker": row.ticker,
                "Price": fmt(row.price),
                "Signal": row.signal or "-",
                "VWAP Ext": row.vwap_extension_label or "-",
                "RS vs SPY": row.rs_vs_spy_label or "-",
                "RS vs Sec": row.rs_vs_sector_label or "-",
                "Best Support": row.best_support or "-",
                "Sup Conf": row.support_confidence or "-",
                "Best Resistance": row.best_resistance or "-",
                "Res Conf": row.resistance_confidence or "-",
                "R/R": f"{row.risk_reward:.1f}R" if row.risk_reward else "-",
                "Setup At": row.setup_level or "-",
                "% Away": f"{row.setup_distance_percent:.2f}%" if row.setup_distance_percent is not None else "-",
                "Lows Held": f"{row.lows_held}x" if row.lows_held else "-",
                "Range": row.range_compression or "-",
                "Off High": f"{row.off_high_percent:.2f}%" if row.off_high_percent is not None else "-",
                "Momentum": row.momentum or "-",
            }
        )
    return pd.DataFrame(rows)


def scanner_cell_style(value: str) -> str:
    """Return Streamlit dataframe CSS for scanner signal cells."""
    text = str(value)
    if text.endswith("/8"):
        try:
            score = int(text.split("/", 1)[0])
        except ValueError:
            score = -1
        if score >= 7:
            return "background-color:#dcfce7;color:#166534;font-weight:800"
        if score >= 5:
            return "background-color:#ccfbf1;color:#0f766e;font-weight:800"
        if score >= 3:
            return "background-color:#fef3c7;color:#92400e;font-weight:800"
        if score >= 0:
            return "background-color:#fee2e2;color:#991b1b;font-weight:800"
    if text.endswith("x"):
        try:
            lows = int(text[:-1])
        except ValueError:
            lows = 0
        if lows >= 3:
            return "background-color:#dcfce7;color:#166534;font-weight:800"
        if lows == 2:
            return "background-color:#ccfbf1;color:#0f766e;font-weight:800"
        if lows == 1:
            return "background-color:#fef3c7;color:#92400e;font-weight:800"
    if text == "Turning Up":
        return "background-color:#dcfce7;color:#166534;font-weight:800"
    if text == "Ticking Up":
        return "background-color:#ccfbf1;color:#0f766e;font-weight:800"
    if text == "Still Falling":
        return "background-color:#fee2e2;color:#991b1b;font-weight:800"
    return "background-color:#f1f5f9;color:#64748b;font-weight:700" if text == "-" or text == "Flat" else ""


def styled_scanner_setup_frame(report: ScannerResponse):
    """Build a styled setup scanner frame with color-coded signal columns."""
    frame = scanner_setup_frame(report)
    if frame.empty:
        return frame
    return frame.style.map(scanner_cell_style, subset=["Score", "Lows Held", "Momentum"])


def pattern_summary_frame(report: ScannerResponse) -> pd.DataFrame:
    """Build a display frame for pattern summary rows."""
    return pd.DataFrame(
        [
            {
                "Sector": row.sector,
                "Ticker": row.ticker,
                "Days": row.total_days,
                "Dip Days": row.dip_days,
                "Consistency": f"{row.consistency_percent}%",
                "Avg Dip": f"{row.average_dip_percent:.2f}%",
                "Avg Recovery": f"{row.average_recovery_percent:+.2f}%",
                "Common Low Times": ", ".join(row.top_low_times) or "-",
            }
            for row in report.pattern_summary
        ]
    )


def pattern_heatmap_frame(report: ScannerResponse) -> pd.DataFrame:
    """Build a wide heatmap frame using existing table rendering."""
    labels = report.pattern_bucket_labels or report.pattern_buckets
    rows = []
    for row in report.pattern_heatmap:
        display = {"Ticker": row.ticker}
        for label, value in zip(labels, row.values, strict=False):
            display[label.replace(" ET", "")] = "" if value is None else f"{value:.2f}%"
        rows.append(display)
    return pd.DataFrame(rows)


def pattern_detail_frame(details: list[Any]) -> pd.DataFrame:
    """Build a display frame for per-day pattern details."""
    return pd.DataFrame(
        [
            {
                "Date": detail.date.isoformat(),
                "Morning Low": f"{detail.morning_low_percent:.2f}%",
                "Low Time": detail.morning_low_time,
                "Recovery": f"{detail.recovery_to_close_percent:+.2f}%",
                "Dip?": "Yes" if detail.dip_in_window else "No",
                "Day Low": f"{detail.day_low_percent:.2f}%",
                "Day Low Time": detail.day_low_time,
                "Close From Open": f"{detail.close_from_open_percent:+.2f}%",
            }
            for detail in details
        ]
    )


def ensure_streamlit_watchlist() -> None:
    """Initialize Streamlit session watchlist state."""
    if "watchlist_tickers" not in st.session_state:
        st.session_state.watchlist_tickers = load_streamlit_watchlist()


def persist_session_watchlist() -> None:
    """Persist the current Streamlit session watchlist."""
    st.session_state.watchlist_tickers = normalize_ticker_list(list(st.session_state.watchlist_tickers))
    save_streamlit_watchlist(list(st.session_state.watchlist_tickers))


def render_streamlit_watchlist_controls() -> tuple[str, ...]:
    """Render add/remove/reorder controls and return the current watchlist."""
    ensure_streamlit_watchlist()

    def add_pending_tickers() -> None:
        add_text = str(st.session_state.get("streamlit_ticker_add_text", ""))
        added = False
        for ticker in normalize_ticker_list(add_text):
            if ticker not in st.session_state.watchlist_tickers:
                st.session_state.watchlist_tickers.append(ticker)
                added = True
        if added:
            persist_session_watchlist()
            bump_streamlit_refresh_token()
        st.session_state.streamlit_ticker_add_text = ""

    st.text_input(
        "Ticker symbol",
        key="streamlit_ticker_add_text",
        placeholder="Add ticker symbols",
    )
    st.button("Add", type="primary", use_container_width=True, on_click=add_pending_tickers)
    if st.button(
        "▶ Run levels + news",
        key="streamlit-sidebar-run",
        type="primary",
        use_container_width=True,
        disabled=not bool(st.session_state.watchlist_tickers),
        help="Refresh levels, news, scanner, market snapshot, and charts for the saved watchlist.",
    ):
        st.session_state.sidebar_run_requested = True
        st.rerun()

    for index, ticker in enumerate(list(st.session_state.watchlist_tickers)):
        cols = st.columns([2.6, 1, 1, 1], vertical_alignment="center")
        cols[0].markdown(
            f'<div class="streamlit-watchlist-row"><strong>{escape(ticker)}</strong></div>',
            unsafe_allow_html=True,
        )
        if cols[1].button("↑", key=f"watch-up-{ticker}", disabled=index == 0, help=f"Move {ticker} up"):
            st.session_state.watchlist_tickers[index - 1], st.session_state.watchlist_tickers[index] = (
                st.session_state.watchlist_tickers[index],
                st.session_state.watchlist_tickers[index - 1],
            )
            persist_session_watchlist()
            bump_streamlit_refresh_token()
            st.rerun()
        if cols[2].button(
            "↓",
            key=f"watch-down-{ticker}",
            disabled=index == len(st.session_state.watchlist_tickers) - 1,
            help=f"Move {ticker} down",
        ):
            st.session_state.watchlist_tickers[index + 1], st.session_state.watchlist_tickers[index] = (
                st.session_state.watchlist_tickers[index],
                st.session_state.watchlist_tickers[index + 1],
            )
            persist_session_watchlist()
            bump_streamlit_refresh_token()
            st.rerun()
        if cols[3].button("×", key=f"watch-remove-{ticker}", help=f"Remove {ticker}"):
            st.session_state.watchlist_tickers.remove(ticker)
            persist_session_watchlist()
            bump_streamlit_refresh_token()
            st.rerun()
    if not st.session_state.watchlist_tickers:
        st.caption("No tickers saved.")
    return tuple(st.session_state.watchlist_tickers)


def load_streamlit_data(tickers: tuple[str, ...], metrics: tuple[MetricName, ...], refresh_token: int) -> None:
    """Load all Streamlit datasets for the current watchlist."""
    st.session_state.report = build_report(tickers, metrics, refresh_token=refresh_token)
    st.session_state.scanner = build_scanner(tickers, refresh_token=refresh_token)
    st.session_state.news = build_news(
        tickers,
        per_ticker=NEWS_EXPANDED_HEADLINE_COUNT,
        refresh_token=refresh_token,
    )
    st.session_state.market_snapshot = build_market_snapshot(tickers, refresh_token=refresh_token)


@st.fragment(run_every=AUTO_REFRESH_SECONDS)
def render_auto_refresh_fragment(enabled: bool) -> None:
    """Trigger full-app data refreshes on a native Streamlit timer."""
    if not enabled:
        return
    current_bucket = refresh_bucket()
    previous_bucket = st.session_state.get("auto_refresh_bucket")
    if previous_bucket is None:
        st.session_state.auto_refresh_bucket = current_bucket
        return
    if current_bucket != previous_bucket:
        st.session_state.auto_refresh_bucket = current_bucket
        bump_streamlit_refresh_token()
        st.rerun()


def render_streamlit_chart_controls() -> tuple[str, ChartRange, ChartInterval]:
    """Render global Streamlit chart controls."""
    if "chart_range" not in st.session_state:
        st.session_state.chart_range = "1D"
    if "chart_interval" not in st.session_state:
        st.session_state.chart_interval = "5m"
    if st.session_state.chart_interval not in CHART_INTERVALS_BY_RANGE[st.session_state.chart_range]:
        st.session_state.chart_interval = CHART_DEFAULT_INTERVAL_BY_RANGE[st.session_state.chart_range]

    type_col, range_col, interval_col = st.columns(3)
    with type_col:
        chart_type = st.radio("Chart type", CHART_TYPE_OPTIONS, horizontal=True, key="global-chart-type")
    with range_col:
        chart_range = st.selectbox("Range", CHART_RANGE_OPTIONS, key="chart_range", format_func=format_chart_option)
    if st.session_state.chart_interval not in CHART_INTERVALS_BY_RANGE[chart_range]:
        st.session_state.chart_interval = CHART_DEFAULT_INTERVAL_BY_RANGE[chart_range]
    with interval_col:
        chart_interval = st.selectbox("Interval", CHART_INTERVALS_BY_RANGE[chart_range], key="chart_interval")
    return chart_type, chart_range, chart_interval


def main() -> None:
    """Run the Streamlit application."""
    view = render_app_chrome()

    with st.sidebar:
        st.header("Controls")
        tickers = render_streamlit_watchlist_controls()

    if "report" not in st.session_state:
        st.session_state.report = None
    if "news" not in st.session_state:
        st.session_state.news = None
    if "scanner" not in st.session_state:
        st.session_state.scanner = None
    if "market_snapshot" not in st.session_state:
        st.session_state.market_snapshot = None
    if "levels_status" not in st.session_state:
        st.session_state.levels_status = ""
    if "autoload_key" not in st.session_state:
        st.session_state.autoload_key = None
    if "streamlit_refresh_token" not in st.session_state:
        st.session_state.streamlit_refresh_token = 0
    if "auto_refresh_bucket" not in st.session_state:
        st.session_state.auto_refresh_bucket = refresh_bucket()

    sidebar_run_requested = bool(st.session_state.pop("sidebar_run_requested", False))
    render_auto_refresh_fragment(bool(tickers))
    refresh_token = int(st.session_state.streamlit_refresh_token)
    if sidebar_run_requested and tickers:
        refresh_token = bump_streamlit_refresh_token()

    autoload_metrics = tuple(DEFAULT_METRICS)
    try:
        autoload_request = GenerateRequest(tickers=list(tickers), metrics=list(autoload_metrics))
    except ValidationError:
        autoload_request = None
    if autoload_request is not None:
        autoload_key = (tuple(autoload_request.tickers), tuple(autoload_request.metrics), refresh_token)
        if st.session_state.autoload_key != autoload_key:
            with st.spinner("Loading saved watchlist..."):
                load_streamlit_data(tuple(autoload_request.tickers), tuple(autoload_request.metrics), refresh_token)
            st.session_state.levels_status = ""
            st.session_state.autoload_key = autoload_key
    else:
        st.session_state.report = None
        st.session_state.scanner = None
        st.session_state.news = None
        st.session_state.market_snapshot = None
        st.session_state.autoload_key = None

    if view == LEVELS_VIEW:
        with st.container():
            heading_col, action_col = st.columns([2.2, 1], vertical_alignment="center")
            with heading_col:
                st.markdown('<span class="view-hero-marker"></span>', unsafe_allow_html=True)
                st.title("Investment Trading Levels")
            with action_col:
                generate = st.button("Generate Levels", type="primary", use_container_width=True)
            levels_status_slot = st.empty()
            if st.session_state.levels_status:
                levels_status_slot.success(st.session_state.levels_status)
        with st.container(border=True):
            scanner_text_col, scanner_action_col = st.columns([2.2, 1], vertical_alignment="center")
            with scanner_text_col:
                st.subheader("Scanner")
            with scanner_action_col:
                run_scanner = st.button("Run Scanner", type="primary", use_container_width=True)
        refresh_news = False
    else:
        with st.container():
            heading_col, action_col = st.columns([2.2, 1], vertical_alignment="center")
            with heading_col:
                st.markdown('<span class="view-hero-marker"></span>', unsafe_allow_html=True)
                st.title("Stock News")
            with action_col:
                refresh_news = st.button("Refresh News", type="primary", use_container_width=True)
        generate = False
        run_scanner = False

    if generate:
        try:
            request = GenerateRequest(tickers=list(tickers), metrics=list(DEFAULT_METRICS))
        except ValidationError as exc:
            st.error(exc.errors()[0]["msg"])
            return

        with st.spinner("Generating levels..."):
            refresh_token = bump_streamlit_refresh_token()
            load_streamlit_data(tuple(request.tickers), tuple(request.metrics), refresh_token)
        st.session_state.levels_status = ""

    if run_scanner:
        try:
            request = ScannerRequest(tickers=list(tickers))
        except ValidationError as exc:
            st.error(exc.errors()[0]["msg"])
            return

        with st.spinner("Running scanner..."):
            refresh_token = bump_streamlit_refresh_token()
            st.session_state.scanner = build_scanner(tuple(request.tickers), refresh_token=refresh_token)

    if refresh_news:
        try:
            request = NewsRequest(tickers=list(tickers), per_ticker=NEWS_EXPANDED_HEADLINE_COUNT)
            snapshot_request = MarketSnapshotRequest(tickers=list(tickers))
        except ValidationError as exc:
            st.error(exc.errors()[0]["msg"])
            return

        with st.spinner("Loading news..."):
            refresh_token = bump_streamlit_refresh_token()
            st.session_state.news = build_news(
                tuple(request.tickers),
                per_ticker=request.per_ticker,
                refresh_token=refresh_token,
            )
            st.session_state.market_snapshot = build_market_snapshot(
                tuple(snapshot_request.tickers),
                refresh_token=refresh_token,
            )

    if view == NEWS_VIEW:
        news: NewsResponse | None = st.session_state.news
        if news is None:
            return
        render_news(news, st.session_state.market_snapshot)
        return

    scanner: ScannerResponse | None = st.session_state.scanner
    if scanner is not None:
        with st.container(border=True):
            render_scanner(scanner)

    report: GenerateResponse | None = st.session_state.report
    if report is None:
        return

    with st.container(border=True):
        header_col, download_col = st.columns([2.2, 1], vertical_alignment="center")
        with header_col:
            st.header("Report")
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

    render_metric_grid(report.metrics)

    chart_type, chart_range, chart_interval = render_streamlit_chart_controls()
    render_chart_history(report, chart_range, chart_interval, chart_type, refresh_token=refresh_token)


if __name__ == "__main__":
    main()
