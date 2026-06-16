"""Streamlit entry point for the equity levels app."""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
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
    normalize_ticker_symbol,
    split_ticker_candidates,
)
from app.services.market_data import MarketDataService
from app.services.news import NewsService
from app.services.pdf_report import PdfReportService
from app.services.scanner import ScannerService
from app.services.display import (
    DEFAULT_LEVEL_FILTER,
    DEFAULT_REPORT_LAYOUT,
    LEVEL_FILTER_OPTIONS,
    level_filter_label,
    normalize_level_filter,
    report_layout_catalog,
)
from app.streamlit_ui.metrics import metric_card_html, metric_rows, render_metric, render_metric_grid


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
AUTO_REFRESH_SECONDS = 60
STREAMLIT_REPORT_BATCH_SIZE = 3
REFRESH_BANNER_DEFAULT_TITLE = "Refreshing data"
STREAMLIT_STATE_ENV = "INVESTMENT_TRADING_STREAMLIT_STATE"
STREAMLIT_DATASETS = ("report", "scanner", "news", "market_snapshot", "chart")
LIGHTWEIGHT_CHARTS_BUNDLE_PATH = (
    Path(__file__).parent / "static" / "vendor" / "lightweight-charts" / "lightweight-charts.standalone.production.js"
)
RefreshStep = tuple[str, Callable[[], None]]
ReportBatchLoader = Callable[[tuple[str, ...], tuple[MetricName, ...], int], GenerateResponse]
ScannerBatchLoader = Callable[[tuple[str, ...], int], ScannerResponse]


LEVELS_VIEW = "Investment Trading Levels"
NEWS_VIEW = "Stock News"


@dataclass(frozen=True)
class PipelinedLoadEvent:
    """One data event emitted by the Streamlit levels/scanner producer."""

    kind: str
    batch_index: int = 0
    total_batches: int = 0
    batch: tuple[str, ...] = ()
    report: GenerateResponse | None = None
    scanner: ScannerResponse | None = None
    error: BaseException | None = None


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


def ticker_batches(tickers: tuple[str, ...], batch_size: int = STREAMLIT_REPORT_BATCH_SIZE) -> list[tuple[str, ...]]:
    """Split tickers into stable batches for progressive Streamlit loading."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    return [tickers[index : index + batch_size] for index in range(0, len(tickers), batch_size)]


def progressive_report_responses(
    tickers: tuple[str, ...],
    metrics: tuple[MetricName, ...],
    refresh_token: int,
    *,
    batch_size: int = STREAMLIT_REPORT_BATCH_SIZE,
    loader: Callable[[tuple[str, ...], tuple[MetricName, ...], int], GenerateResponse] | None = None,
) -> list[GenerateResponse]:
    """Return partial report responses as each ticker batch is loaded."""
    report_loader = loader or (lambda batch, selected, token: build_report(batch, selected, refresh_token=token))
    responses: list[GenerateResponse] = []
    accumulated: list[EquityMetrics] = []
    generated_at = datetime.now(timezone.utc)
    for batch in ticker_batches(tickers, batch_size=batch_size):
        batch_response = report_loader(batch, metrics, refresh_token)
        generated_at = batch_response.generated_at
        accumulated.extend(batch_response.metrics)
        responses.append(GenerateResponse(generated_at=generated_at, metrics=list(accumulated)))
    if not responses:
        responses.append(GenerateResponse(generated_at=generated_at, metrics=[]))
    return responses


def start_pipelined_levels_scanner_loader(
    tickers: tuple[str, ...],
    metrics: tuple[MetricName, ...],
    report_refresh_token: int,
    scanner_refresh_token: int,
    report_loader: ReportBatchLoader,
    scanner_loader: ScannerBatchLoader,
    *,
    batch_size: int = STREAMLIT_REPORT_BATCH_SIZE,
) -> tuple[Queue[PipelinedLoadEvent], Thread]:
    """Start a one-worker producer for progressive levels and scanner batches."""
    events: Queue[PipelinedLoadEvent] = Queue()
    batches = ticker_batches(tickers, batch_size=batch_size)

    def produce() -> None:
        try:
            for index, batch in enumerate(batches, start=1):
                report = report_loader(batch, metrics, report_refresh_token)
                events.put(
                    PipelinedLoadEvent(
                        kind="levels",
                        batch_index=index,
                        total_batches=len(batches),
                        batch=batch,
                        report=report,
                    )
                )
                scanner = scanner_loader(batch, scanner_refresh_token)
                events.put(
                    PipelinedLoadEvent(
                        kind="scanner",
                        batch_index=index,
                        total_batches=len(batches),
                        batch=batch,
                        scanner=scanner,
                    )
                )
        except BaseException as exc:
            events.put(PipelinedLoadEvent(kind="error", error=exc))
        finally:
            events.put(PipelinedLoadEvent(kind="done", total_batches=len(batches)))

    worker = Thread(target=produce, name="streamlit-levels-scanner-loader", daemon=True)
    worker.start()
    return events, worker


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
    try:
        candidates = split_ticker_candidates(value)
    except ValueError:
        return []
    cleaned: list[str] = []
    for candidate in candidates:
        try:
            ticker = normalize_ticker_symbol(candidate)
        except ValueError:
            continue
        if ticker not in cleaned:
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


def ensure_streamlit_data_state() -> None:
    """Initialize per-dataset Streamlit freshness state."""
    if "streamlit_refresh_token" not in st.session_state:
        st.session_state.streamlit_refresh_token = 0
    tokens = st.session_state.get("streamlit_refresh_tokens")
    if not isinstance(tokens, dict):
        tokens = {dataset: int(st.session_state.streamlit_refresh_token) for dataset in STREAMLIT_DATASETS}
    for dataset in STREAMLIT_DATASETS:
        tokens.setdefault(dataset, int(st.session_state.streamlit_refresh_token))
    st.session_state.streamlit_refresh_tokens = tokens
    if "loaded_data_keys" not in st.session_state or not isinstance(st.session_state.loaded_data_keys, dict):
        st.session_state.loaded_data_keys = {}


def dataset_refresh_token(dataset: str) -> int:
    """Return the cache-busting token for one Streamlit dataset."""
    ensure_streamlit_data_state()
    return int(st.session_state.streamlit_refresh_tokens.get(dataset, 0))


def streamlit_theme_type() -> str:
    """Return Streamlit's resolved light/dark theme for this browser session."""
    theme_type = getattr(st.context.theme, "type", None)
    return "dark" if theme_type == "dark" else "light"


def render_streamlit_theme_bridge() -> None:
    """Mirror Streamlit's actual rendered theme onto a page marker for CSS."""
    st.iframe(
        """
        <script>
          (function () {
            function detectTheme(parentDocument) {
              const selectors = [
                "[data-testid='stSidebar']",
                "[data-testid='stAppViewContainer']",
                ".stApp"
              ];
              for (const selector of selectors) {
                const element = parentDocument.querySelector(selector);
                if (!element) continue;
                const scheme = parentDocument.defaultView.getComputedStyle(element).colorScheme || "";
                if (scheme.includes("dark")) return "dark";
                if (scheme.includes("light")) return "light";
              }
              return parentDocument.defaultView.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
            }

            function syncTheme() {
              try {
                const parentDocument = window.parent.document;
                const theme = detectTheme(parentDocument);
                if (parentDocument.documentElement.dataset.streamlitTheme !== theme) {
                  parentDocument.documentElement.dataset.streamlitTheme = theme;
                }
                if (parentDocument.body.dataset.streamlitTheme !== theme) {
                  parentDocument.body.dataset.streamlitTheme = theme;
                }
                parentDocument.querySelectorAll(".streamlit-theme-marker").forEach(function (marker) {
                  if (marker.getAttribute("data-app-theme") !== theme) {
                    marker.setAttribute("data-app-theme", theme);
                  }
                });
              } catch (error) {
                // The component iframe is best-effort; CSS falls back to Streamlit's initial context value.
              }
            }

            syncTheme();
            try {
              const parentDocument = window.parent.document;
              parentDocument.defaultView.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", syncTheme);
              window.setInterval(syncTheme, 800);
            } catch (error) {}
          })();
        </script>
        """,
        height=1,
    )


def bump_streamlit_refresh_token(
    reason: str | None = None,
    datasets: tuple[str, ...] = STREAMLIT_DATASETS,
) -> int:
    """Advance the Streamlit data refresh token and return it."""
    ensure_streamlit_data_state()
    st.session_state.streamlit_refresh_token = int(st.session_state.get("streamlit_refresh_token", 0)) + 1
    for dataset in datasets:
        if dataset in STREAMLIT_DATASETS:
            st.session_state.streamlit_refresh_tokens[dataset] = int(st.session_state.streamlit_refresh_token)
    if reason:
        st.session_state.refresh_banner_title = reason
    return int(st.session_state.streamlit_refresh_token)


def render_app_chrome() -> str:
    """Render app-level brand/navigation and return the active view."""
    if "active_view" not in st.session_state:
        st.session_state.active_view = LEVELS_VIEW

    st.markdown(
        f'<span class="streamlit-theme-marker" data-app-theme="{streamlit_theme_type()}"></span>',
        unsafe_allow_html=True,
    )
    render_streamlit_theme_bridge()

    st.markdown(
        """
        <style>
	          :root {
	            color-scheme: light dark;
	          }
	          .stApp {
	            --page-gutter: clamp(0.75rem, 2vw, 2.75rem);
	            --content-max: 2600px;
	            --content-width: min(var(--content-max), calc(100vw - (var(--page-gutter) * 2)));
	            --app-bg: #eef2f1;
	            --surface-bg: #ffffff;
	            --surface-soft: #f8fafc;
	            --surface-muted: #f1f5f9;
	            --border: #d5ddd9;
	            --border-soft: #dbe3ef;
	            --text: #111827;
	            --text-strong: #020617;
	            --text-muted: #64748b;
	            --text-subtle: #334155;
	            --brand-deep: #12312f;
	            --brand: #0f766e;
	            --brand-soft: #ccfbf1;
	            --brand-border: #99f6e4;
	            --warning-bg: #fef3c7;
	            --warning-border: #fde68a;
	            --warning-text: #92400e;
	            --shadow: 0 8px 28px rgba(17, 24, 39, 0.08);
	            --signal-strong-bg: #dcfce7;
	            --signal-strong-fg: #166534;
	            --signal-good-bg: #ccfbf1;
	            --signal-good-fg: #0f766e;
	            --signal-watch-bg: #fef3c7;
	            --signal-watch-fg: #92400e;
	            --signal-danger-bg: #fee2e2;
	            --signal-danger-fg: #991b1b;
	            --signal-neutral-bg: #f1f5f9;
	            --signal-neutral-fg: #64748b;
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
          .streamlit-refresh-banner {
            align-items: center;
            background: #f0fdfa;
            border: 1px solid #99f6e4;
            border-radius: 0.5rem;
            box-shadow: 0 10px 24px rgba(15, 118, 110, 0.12);
            display: flex;
            gap: 0.75rem;
            justify-content: space-between;
            margin: 0 0 1rem;
            padding: 0.75rem 0.9rem;
          }
          .streamlit-refresh-banner strong {
            color: #0f172a;
            font-size: 0.92rem;
          }
          .streamlit-refresh-banner span {
            color: #0f766e !important;
            font-size: 0.78rem;
            font-weight: 900;
            letter-spacing: 0.05em;
            text-transform: uppercase;
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
          .streamlit-report-layout-price-ladder,
          .streamlit-report-layout-compact {
            grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr));
          }
          .streamlit-report-layout-compare {
            margin-bottom: 1rem;
            overflow-x: auto;
          }
          .ladder-body {
            padding: 0.85rem;
          }
          .levels-table,
          .compare-table {
            border-collapse: collapse;
            width: 100%;
          }
          .levels-table th,
          .compare-table th {
            color: #475569;
            font-size: 0.68rem;
            font-weight: 900;
            letter-spacing: 0.06em;
            padding: 0.5rem 0.65rem;
            text-align: left;
            text-transform: uppercase;
          }
          .levels-table th:nth-child(n + 2),
          .levels-table td:nth-child(n + 2),
          .compare-table td {
            text-align: right;
          }
          .levels-table td,
          .compare-table td,
          .compare-table th {
            border-bottom: 1px solid #e2e8f0;
            padding: 0.5rem 0.65rem;
          }
          .levels-table .current td {
            background: #12312f;
            color: #ffffff;
            font-weight: 900;
          }
          .levels-table .above td {
            color: #b91c1c;
          }
          .levels-table .below td {
            color: #047857;
          }
          .levels-table .neutral td {
            color: #0f172a;
          }
          .levels-table .priority td {
            font-weight: 900;
          }
          .ladder-notes {
            display: grid;
            gap: 0.5rem;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            margin-top: 0.75rem;
          }
          .ladder-notes div,
          .compact-metric {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 0.5rem;
            padding: 0.5rem 0.65rem;
          }
          .ladder-notes span,
          .compact-metric span {
            color: #64748b;
            display: block;
            font-size: 0.68rem;
            font-weight: 900;
            letter-spacing: 0.04em;
            text-transform: uppercase;
          }
          .ladder-notes strong,
          .compact-metric strong {
            color: #0f172a;
            display: block;
            font-size: 0.95rem;
            margin-top: 0.15rem;
          }
          .compact-body {
            display: grid;
            gap: 0.5rem;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            padding: 0.85rem;
          }
          .compact-body .warning {
            grid-column: 1 / -1;
          }
          .compact-metric.priority {
            background: #fefce8;
            border-color: #facc15;
          }
          .compact-metric.current {
            background: #ccfbf1;
            border-color: #99f6e4;
          }
          .compare-wrap {
            background: #ffffff;
            border: 1px solid #dbe3ef;
            border-radius: 0.5rem;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.07);
            overflow-x: auto;
          }
          .compare-table {
            min-width: 980px;
          }
          .compare-table th:first-child {
            background: #12312f;
            color: #ffffff;
            left: 0;
            position: sticky;
            z-index: 1;
          }
          .metric-empty {
            border: 1px dashed #cbd5e1;
            border-radius: 0.5rem;
            color: #64748b;
            padding: 0.85rem;
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
          .streamlit-ticker-news-header {
            align-items: center;
            display: flex;
            gap: 0.5rem;
            justify-content: space-between;
            margin-bottom: 0.65rem;
          }
          .streamlit-news-toggle-details {
            display: grid;
            gap: 0.65rem;
          }
          .streamlit-news-toggle-details summary {
            cursor: pointer;
            list-style: none;
            margin-bottom: 0;
          }
          .streamlit-news-toggle-details summary::-webkit-details-marker {
            display: none;
          }
          .streamlit-news-toggle-arrow {
            align-items: center;
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            border-radius: 999px;
            color: #1d4ed8;
            display: inline-flex;
            flex: 0 0 auto;
            font-size: 0.72rem;
            font-weight: 900;
            height: 1.85rem;
            justify-content: center;
            line-height: 1;
            width: 1.85rem;
          }
          .streamlit-news-toggle-arrow::before {
            content: "▾";
          }
          .streamlit-news-toggle-details[open] .streamlit-news-toggle-arrow::before {
            content: "▴";
          }
          .streamlit-news-toggle-details[open] + .streamlit-news-collapsed-body {
            display: none;
          }
          .streamlit-news-expanded-body,
          .streamlit-news-collapsed-body {
            display: grid;
            gap: 0.5rem;
          }
          .streamlit-ticker-news-title h4 {
            color: #12312f;
            letter-spacing: 0.06em;
            margin: 0;
          }
          .streamlit-ticker-news-title span {
            color: #64748b !important;
            display: block;
            font-size: 0.76rem;
            font-weight: 800;
            margin-top: 0.15rem;
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
	          @media (prefers-color-scheme: dark) {
	            .stApp {
	              --app-bg: #0b1115;
	              --surface-bg: #111827;
	              --surface-soft: #17202c;
	              --surface-muted: #1f2937;
	              --border: #263241;
	              --border-soft: #334155;
	              --text: #e5edf4;
	              --text-strong: #f8fafc;
	              --text-muted: #94a3b8;
	              --text-subtle: #cbd5e1;
	              --brand-deep: #0b2f2d;
	              --brand: #2dd4bf;
	              --brand-soft: #0b3b37;
	              --brand-border: #0f766e;
	              --warning-bg: #3f2e12;
	              --warning-border: #92400e;
	              --warning-text: #fde68a;
	              --shadow: 0 12px 28px rgba(0, 0, 0, 0.28);
	              --signal-strong-bg: #064e3b;
	              --signal-strong-fg: #d1fae5;
	              --signal-good-bg: #0b3b37;
	              --signal-good-fg: #99f6e4;
	              --signal-watch-bg: #3f2e12;
	              --signal-watch-fg: #fde68a;
	              --signal-danger-bg: #4c1d1d;
	              --signal-danger-fg: #fecaca;
	              --signal-neutral-bg: #1f2937;
	              --signal-neutral-fg: #cbd5e1;
	              background: var(--app-bg) !important;
	              color: var(--text) !important;
	            }
	            .stApp,
	            .stApp p,
	            .stApp label,
	            .stApp li,
	            .stApp div[data-testid="stMarkdownContainer"],
	            .stApp h1,
	            .stApp h2,
	            .stApp h3,
	            .stApp h4,
	            .stApp h5 {
	              color: var(--text) !important;
	            }
	            .stApp a {
	              color: #67e8f9 !important;
	            }
	            div[data-testid="stCaptionContainer"],
	            div[data-testid="stCaptionContainer"] * {
	              color: var(--text-muted) !important;
	            }
	            header[data-testid="stHeader"],
	            .streamlit-brand-ribbon,
	            div[data-testid="stHorizontalBlock"]:has(.streamlit-nav-marker) {
	              background: rgba(12, 18, 24, 0.96) !important;
	              border-color: var(--border) !important;
	            }
	            [data-testid="stSidebar"],
	            [data-testid="stVerticalBlockBorderWrapper"],
	            div[data-testid="stVerticalBlock"]:has(.view-hero-marker):has(button):not(:has(.streamlit-brand)),
	            .report-panel,
	            .metric-card,
	            .streamlit-news-card,
	            .streamlit-market-tile,
	            .streamlit-scanner-card,
	            .streamlit-page-hero,
	            .streamlit-section-panel,
	            .streamlit-report-panel,
	            .streamlit-scanner-panel,
	            .compare-wrap,
	            .streamlit-chart-card,
	            .streamlit-ticker-news-card,
	            .streamlit-news-category-details,
	            div[data-testid="stExpander"] details {
	              background: var(--surface-bg) !important;
	              border-color: var(--border) !important;
	              box-shadow: var(--shadow) !important;
	              color: var(--text) !important;
	            }
	            [data-testid="stSidebar"] *,
	            .report-header h2,
	            .streamlit-page-hero h1,
	            .streamlit-section-header h2,
	            .streamlit-chart-header h2,
	            .metric-value,
	            .streamlit-news-title,
	            .streamlit-scanner-card h2,
	            .streamlit-scanner-card h3,
	            .streamlit-scanner-card p,
	            .levels-table .neutral td,
	            .ladder-notes strong,
	            .compact-metric strong,
	            .streamlit-chart-card h4,
	            .streamlit-ticker-news-title h4,
	            div[data-testid="stExpander"] summary,
	            div[data-testid="stExpander"] summary * {
	              color: var(--text) !important;
	            }
	            .report-header p,
	            .metric-label,
	            .streamlit-news-meta,
	            .streamlit-news-related,
	            .streamlit-news-summary,
	            .streamlit-ticker-news-title span,
	            .levels-table th,
	            .compare-table th,
	            .ladder-notes span,
	            .compact-metric span,
	            .metric-empty,
	            .streamlit-market-change,
	            .streamlit-watchlist-row strong {
	              color: var(--text-muted) !important;
	            }
	            [data-testid="stSidebar"] input,
	            [data-testid="stSidebar"] textarea,
	            [data-testid="stSidebar"] [data-baseweb="input"] input,
	            [data-testid="stSidebar"] [data-baseweb="select"] > div,
	            .stApp input,
	            .stApp textarea,
	            .stApp [data-baseweb="input"] input,
	            .stApp [data-baseweb="select"] > div {
	              background: #1a2230 !important;
	              border-color: var(--border-soft) !important;
	              color: var(--text) !important;
	            }
	            .stApp input::placeholder,
	            [data-testid="stSidebar"] input::placeholder {
	              color: var(--text-muted) !important;
	            }
	            div[data-testid="stButton"] button[kind="secondary"],
	            div[data-testid="stDownloadButton"] button[kind="secondary"],
	            [data-testid="stSidebar"] [data-testid="stButton"] button:not([kind="primary"]),
	            .streamlit-watchlist-row,
	            .metric-section-title,
	            .streamlit-takeaway,
	            div[data-testid="stExpander"] summary,
	            .ladder-notes div,
	            .compact-metric,
	            .metric-empty,
	            .streamlit-chart-frame {
	              background: var(--surface-soft) !important;
	              border-color: var(--border-soft) !important;
	              color: var(--text) !important;
	            }
	            .metric-section,
	            .metric-cell,
	            .levels-table td,
	            .compare-table td,
	            .compare-table th,
	            .streamlit-heatmap {
	              border-color: var(--border) !important;
	            }
	            .streamlit-status-chip,
	            .streamlit-refresh-banner,
	            .brand-mark,
	            .compact-metric.current {
	              background: var(--brand-soft) !important;
	              border-color: var(--brand-border) !important;
	              color: #99f6e4 !important;
	            }
	            .streamlit-refresh-banner strong,
	            .streamlit-refresh-banner span {
	              color: #99f6e4 !important;
	            }
	            .compact-metric.priority,
	            .streamlit-related-tickers span,
	            div[data-testid="stAlert"],
	            .inline-warning {
	              background: var(--warning-bg) !important;
	              border-color: var(--warning-border) !important;
	              color: var(--warning-text) !important;
	            }
	            div[data-testid="stAlert"] *,
	            div[data-testid="stAlert"] p,
	            .inline-warning * {
	              color: var(--warning-text) !important;
	            }
	            .streamlit-market-grid.major {
	              background: #080d12 !important;
	              border: 1px solid var(--border) !important;
	            }
	            .streamlit-market-grid.major .streamlit-market-tile {
	              background: transparent !important;
	              border-color: rgba(148, 163, 184, 0.26) !important;
	              color: #ffffff !important;
	              box-shadow: none !important;
	            }
	            .streamlit-news-toggle-arrow {
	              background: #172554 !important;
	              border-color: #1d4ed8 !important;
	              color: #bfdbfe !important;
	            }
	            .streamlit-news-category-details summary,
	            .metric-card-header,
	            .compare-table th:first-child,
	            .levels-table .current td {
	              background: var(--brand-deep) !important;
	              color: #ffffff !important;
	            }
	            .streamlit-news-category-details > div {
	              background: var(--surface-bg) !important;
	            }
	            .streamlit-chart-card iframe,
	            .stApp iframe {
	              color-scheme: dark;
	            }
	            .stApp [data-testid="stDataFrame"],
	            .stApp [data-testid="stDataFrame"] > div,
	            .stApp [data-testid="stTable"],
	            .stApp [data-testid="stTable"] > div {
	              background: var(--surface-bg) !important;
	              color: var(--text) !important;
	            }
	          }
            .streamlit-theme-marker {
              display: none !important;
            }
            body:has(.streamlit-theme-marker[data-app-theme="light"]) .stApp {
              --app-color-scheme: light;
              --app-bg: #eef2f1;
              --surface-bg: #ffffff;
              --surface-soft: #f8fafc;
              --surface-muted: #f1f5f9;
              --border: #d5ddd9;
              --border-soft: #dbe3ef;
              --text: #111827;
              --text-strong: #020617;
              --text-muted: #64748b;
              --text-subtle: #334155;
              --brand-deep: #12312f;
              --brand: #0f766e;
              --brand-soft: #ccfbf1;
              --brand-border: #99f6e4;
              --warning-bg: #fef3c7;
              --warning-border: #fde68a;
              --warning-text: #92400e;
              --shadow: 0 8px 28px rgba(17, 24, 39, 0.08);
              --signal-strong-bg: #dcfce7;
              --signal-strong-fg: #166534;
              --signal-good-bg: #ccfbf1;
              --signal-good-fg: #0f766e;
              --signal-watch-bg: #fef3c7;
              --signal-watch-fg: #92400e;
              --signal-danger-bg: #fee2e2;
              --signal-danger-fg: #991b1b;
              --signal-neutral-bg: #f1f5f9;
              --signal-neutral-fg: #64748b;
              --major-market-bg: #111827;
              --major-market-border: #1f2937;
              --button-secondary-text: #334155;
              --link: #0284c7;
              --link-hover: #0f766e;
              --input-bg: #ffffff;
            }
            body:has(.streamlit-theme-marker[data-app-theme="dark"]) .stApp {
              --app-color-scheme: dark;
              --app-bg: #0b1115;
              --surface-bg: #111827;
              --surface-soft: #17202c;
              --surface-muted: #1f2937;
              --border: #263241;
              --border-soft: #334155;
              --text: #e5edf4;
              --text-strong: #f8fafc;
              --text-muted: #94a3b8;
              --text-subtle: #cbd5e1;
              --brand-deep: #0b2f2d;
              --brand: #2dd4bf;
              --brand-soft: #0b3b37;
              --brand-border: #0f766e;
              --warning-bg: #3f2e12;
              --warning-border: #92400e;
              --warning-text: #fde68a;
              --shadow: 0 12px 28px rgba(0, 0, 0, 0.28);
              --signal-strong-bg: #064e3b;
              --signal-strong-fg: #d1fae5;
              --signal-good-bg: #0b3b37;
              --signal-good-fg: #99f6e4;
              --signal-watch-bg: #3f2e12;
              --signal-watch-fg: #fde68a;
              --signal-danger-bg: #4c1d1d;
              --signal-danger-fg: #fecaca;
              --signal-neutral-bg: #1f2937;
              --signal-neutral-fg: #cbd5e1;
              --major-market-bg: #080d12;
              --major-market-border: #263241;
              --button-secondary-text: #e5edf4;
              --link: #67e8f9;
              --link-hover: #5eead4;
              --input-bg: #1a2230;
            }
            body:has(.streamlit-theme-marker) .stApp {
              background: var(--app-bg) !important;
              color: var(--text) !important;
              color-scheme: var(--app-color-scheme, light);
            }
            body:has(.streamlit-theme-marker) .stApp,
            body:has(.streamlit-theme-marker) .stApp p,
            body:has(.streamlit-theme-marker) .stApp label,
            body:has(.streamlit-theme-marker) .stApp li,
            body:has(.streamlit-theme-marker) .stApp h1,
            body:has(.streamlit-theme-marker) .stApp h2,
            body:has(.streamlit-theme-marker) .stApp h3,
            body:has(.streamlit-theme-marker) .stApp h4,
            body:has(.streamlit-theme-marker) .stApp h5,
            body:has(.streamlit-theme-marker) .stApp div[data-testid="stMarkdownContainer"] {
              color: var(--text) !important;
            }
            body:has(.streamlit-theme-marker) .stApp a {
              color: var(--link) !important;
            }
            body:has(.streamlit-theme-marker) .stApp a:hover {
              color: var(--link-hover) !important;
            }
            body:has(.streamlit-theme-marker) header[data-testid="stHeader"],
            body:has(.streamlit-theme-marker) .streamlit-brand-ribbon,
            body:has(.streamlit-theme-marker) div[data-testid="stHorizontalBlock"]:has(.streamlit-nav-marker) {
              background: color-mix(in srgb, var(--surface-bg) 96%, transparent) !important;
              border-color: var(--border) !important;
            }
            body:has(.streamlit-theme-marker) [data-testid="stSidebar"],
            body:has(.streamlit-theme-marker) [data-testid="stVerticalBlockBorderWrapper"],
            body:has(.streamlit-theme-marker) div[data-testid="stVerticalBlock"]:has(.view-hero-marker):has(button):not(:has(.streamlit-brand)),
            body:has(.streamlit-theme-marker) .report-panel,
            body:has(.streamlit-theme-marker) .metric-card,
            body:has(.streamlit-theme-marker) .streamlit-news-card,
            body:has(.streamlit-theme-marker) .streamlit-market-tile,
            body:has(.streamlit-theme-marker) .streamlit-scanner-card,
            body:has(.streamlit-theme-marker) .streamlit-page-hero,
            body:has(.streamlit-theme-marker) .streamlit-section-panel,
            body:has(.streamlit-theme-marker) .streamlit-report-panel,
            body:has(.streamlit-theme-marker) .streamlit-scanner-panel,
            body:has(.streamlit-theme-marker) .compare-wrap,
            body:has(.streamlit-theme-marker) .streamlit-chart-card,
            body:has(.streamlit-theme-marker) .streamlit-ticker-news-card,
            body:has(.streamlit-theme-marker) .streamlit-news-category-details,
            body:has(.streamlit-theme-marker) div[data-testid="stExpander"] details,
            body:has(.streamlit-theme-marker) .stApp [data-testid="stDataFrame"],
            body:has(.streamlit-theme-marker) .stApp [data-testid="stDataFrame"] > div,
            body:has(.streamlit-theme-marker) .stApp [data-testid="stTable"],
            body:has(.streamlit-theme-marker) .stApp [data-testid="stTable"] > div {
              background: var(--surface-bg) !important;
              border-color: var(--border) !important;
              box-shadow: var(--shadow) !important;
              color: var(--text) !important;
            }
            body:has(.streamlit-theme-marker) [data-testid="stSidebar"] *,
            body:has(.streamlit-theme-marker) .report-header h2,
            body:has(.streamlit-theme-marker) .streamlit-page-hero h1,
            body:has(.streamlit-theme-marker) .streamlit-section-header h2,
            body:has(.streamlit-theme-marker) .streamlit-chart-header h2,
            body:has(.streamlit-theme-marker) .metric-value,
            body:has(.streamlit-theme-marker) .streamlit-news-title,
            body:has(.streamlit-theme-marker) .streamlit-scanner-card h2,
            body:has(.streamlit-theme-marker) .streamlit-scanner-card h3,
            body:has(.streamlit-theme-marker) .streamlit-scanner-card p,
            body:has(.streamlit-theme-marker) .levels-table .neutral td,
            body:has(.streamlit-theme-marker) .ladder-notes strong,
            body:has(.streamlit-theme-marker) .compact-metric strong,
            body:has(.streamlit-theme-marker) .streamlit-chart-card h4,
            body:has(.streamlit-theme-marker) .streamlit-ticker-news-title h4,
            body:has(.streamlit-theme-marker) div[data-testid="stExpander"] summary,
            body:has(.streamlit-theme-marker) div[data-testid="stExpander"] summary * {
              color: var(--text) !important;
            }
            body:has(.streamlit-theme-marker) .report-header p,
            body:has(.streamlit-theme-marker) .metric-label,
            body:has(.streamlit-theme-marker) .streamlit-news-meta,
            body:has(.streamlit-theme-marker) .streamlit-news-related,
            body:has(.streamlit-theme-marker) .streamlit-news-summary,
            body:has(.streamlit-theme-marker) .streamlit-ticker-news-title span,
            body:has(.streamlit-theme-marker) .levels-table th,
            body:has(.streamlit-theme-marker) .compare-table th,
            body:has(.streamlit-theme-marker) .ladder-notes span,
            body:has(.streamlit-theme-marker) .compact-metric span,
            body:has(.streamlit-theme-marker) .metric-empty,
            body:has(.streamlit-theme-marker) .streamlit-market-change,
            body:has(.streamlit-theme-marker) .streamlit-watchlist-row strong,
            body:has(.streamlit-theme-marker) div[data-testid="stCaptionContainer"],
            body:has(.streamlit-theme-marker) div[data-testid="stCaptionContainer"] * {
              color: var(--text-muted) !important;
            }
            body:has(.streamlit-theme-marker) [data-testid="stSidebar"] input,
            body:has(.streamlit-theme-marker) [data-testid="stSidebar"] textarea,
            body:has(.streamlit-theme-marker) [data-testid="stSidebar"] [data-baseweb="input"] input,
            body:has(.streamlit-theme-marker) [data-testid="stSidebar"] [data-baseweb="select"] > div,
            body:has(.streamlit-theme-marker) .stApp input,
            body:has(.streamlit-theme-marker) .stApp textarea,
            body:has(.streamlit-theme-marker) .stApp [data-baseweb="input"] input,
            body:has(.streamlit-theme-marker) .stApp [data-baseweb="select"] > div {
              background: var(--input-bg) !important;
              border-color: var(--border-soft) !important;
              color: var(--text) !important;
            }
            body:has(.streamlit-theme-marker) .stApp input::placeholder,
            body:has(.streamlit-theme-marker) [data-testid="stSidebar"] input::placeholder {
              color: var(--text-muted) !important;
            }
            body:has(.streamlit-theme-marker) div[data-testid="stButton"] button[kind="secondary"],
            body:has(.streamlit-theme-marker) div[data-testid="stDownloadButton"] button[kind="secondary"],
            body:has(.streamlit-theme-marker) [data-testid="stSidebar"] [data-testid="stButton"] button:not([kind="primary"]),
            body:has(.streamlit-theme-marker) .streamlit-watchlist-row,
            body:has(.streamlit-theme-marker) .metric-section-title,
            body:has(.streamlit-theme-marker) .streamlit-takeaway,
            body:has(.streamlit-theme-marker) div[data-testid="stExpander"] summary,
            body:has(.streamlit-theme-marker) .ladder-notes div,
            body:has(.streamlit-theme-marker) .compact-metric,
            body:has(.streamlit-theme-marker) .metric-empty,
            body:has(.streamlit-theme-marker) .streamlit-chart-frame {
              background: var(--surface-soft) !important;
              border-color: var(--border-soft) !important;
              color: var(--button-secondary-text) !important;
            }
            body:has(.streamlit-theme-marker) div[data-testid="stButton"] button[kind="secondary"] *,
            body:has(.streamlit-theme-marker) div[data-testid="stDownloadButton"] button[kind="secondary"] * {
              color: var(--button-secondary-text) !important;
            }
            body:has(.streamlit-theme-marker) .metric-section,
            body:has(.streamlit-theme-marker) .metric-cell,
            body:has(.streamlit-theme-marker) .levels-table td,
            body:has(.streamlit-theme-marker) .compare-table td,
            body:has(.streamlit-theme-marker) .compare-table th,
            body:has(.streamlit-theme-marker) .streamlit-heatmap {
              border-color: var(--border) !important;
            }
            body:has(.streamlit-theme-marker) .streamlit-status-chip,
            body:has(.streamlit-theme-marker) .streamlit-refresh-banner,
            body:has(.streamlit-theme-marker) .brand-mark,
            body:has(.streamlit-theme-marker) .compact-metric.current {
              background: var(--brand-soft) !important;
              border-color: var(--brand-border) !important;
              color: var(--brand) !important;
            }
            body:has(.streamlit-theme-marker) .streamlit-refresh-banner strong,
            body:has(.streamlit-theme-marker) .streamlit-refresh-banner span {
              color: var(--brand) !important;
            }
            body:has(.streamlit-theme-marker) .compact-metric.priority,
            body:has(.streamlit-theme-marker) .streamlit-related-tickers span,
            body:has(.streamlit-theme-marker) div[data-testid="stAlert"],
            body:has(.streamlit-theme-marker) .inline-warning {
              background: var(--warning-bg) !important;
              border-color: var(--warning-border) !important;
              color: var(--warning-text) !important;
            }
            body:has(.streamlit-theme-marker) div[data-testid="stAlert"] *,
            body:has(.streamlit-theme-marker) div[data-testid="stAlert"] p,
            body:has(.streamlit-theme-marker) .inline-warning * {
              color: var(--warning-text) !important;
            }
            body:has(.streamlit-theme-marker) .streamlit-market-grid.major {
              background: var(--major-market-bg) !important;
              border: 1px solid var(--major-market-border) !important;
            }
            body:has(.streamlit-theme-marker) .streamlit-market-grid.major .streamlit-market-tile {
              background: transparent !important;
              border-color: rgba(148, 163, 184, 0.26) !important;
              color: #ffffff !important;
              box-shadow: none !important;
            }
            body:has(.streamlit-theme-marker) .streamlit-news-category-details summary,
            body:has(.streamlit-theme-marker) .metric-card-header,
            body:has(.streamlit-theme-marker) .compare-table th:first-child,
            body:has(.streamlit-theme-marker) .levels-table .current td {
              background: var(--brand-deep) !important;
              color: #ffffff !important;
            }
            body:has(.streamlit-theme-marker) .streamlit-news-category-details > div {
              background: var(--surface-bg) !important;
            }
            body:has(.streamlit-theme-marker) .streamlit-chart-card iframe,
            body:has(.streamlit-theme-marker) .stApp iframe {
              color-scheme: var(--app-color-scheme, light);
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
            width="stretch",
            on_click=set_active_view,
            args=(LEVELS_VIEW,),
        )
    with news_col:
        st.button(
            "Stock News",
            type="primary" if st.session_state.active_view == NEWS_VIEW else "secondary",
            width="stretch",
            on_click=set_active_view,
            args=(NEWS_VIEW,),
        )

    return str(st.session_state.active_view)


def set_active_view(view: str) -> None:
    """Persist the active Streamlit view."""
    st.session_state.active_view = view


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
    visible_tickers: tuple[str, ...] | None = None,
) -> None:
    """Render compact line/candlestick charts in report order."""
    tickers = tuple(metric.ticker for metric in report.metrics)
    if not tickers:
        return
    response = build_chart_history(tickers, chart_range, interval, refresh_token=refresh_token)
    charts_by_ticker = {chart.ticker: chart for chart in response.charts}
    display_tickers = visible_tickers or tickers
    st.markdown(
        (
            '<div class="streamlit-chart-header">'
            "<h2>Charts</h2>"
            '<span class="streamlit-status-chip">Auto-refreshes every 1 min</span>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    st.session_state.chart_loaded = True
    columns = st.columns(3)
    for index, ticker in enumerate(display_tickers):
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
    st.iframe(
        lightweight_chart_html(chart, chart_type, chart_range, interval, streamlit_theme_type()),
        height=332,
    )


def lightweight_chart_html(
    chart: TickerChartHistory,
    chart_type: str,
    chart_range: ChartRange,
    interval: ChartInterval,
    theme_type: str | None = None,
) -> str:
    """Return an embeddable Lightweight Charts document for one ticker."""
    chart_theme = "dark" if theme_type == "dark" else "light"
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
<html data-app-theme="__APP_THEME__">
<head>
  <meta charset="utf-8" />
  <script src="data:text/javascript;base64,__LIGHTWEIGHT_CHARTS_BUNDLE__"></script>
  <script>
    (function () {
      function parentTheme() {
        try {
          return window.parent.document.querySelector(".streamlit-theme-marker")?.getAttribute("data-app-theme");
        } catch (error) {
          return null;
        }
      }
      function syncTheme() {
        document.documentElement.dataset.appTheme = parentTheme() || document.documentElement.dataset.appTheme || "light";
      }
      syncTheme();
      window.setInterval(syncTheme, 800);
    })();
  </script>
  <style>
	    :root {
	      color-scheme: light dark;
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
	    html[data-app-theme="dark"] .chart-shell {
	      background: linear-gradient(180deg, #111827 0%, #0b1115 100%);
	      border-color: #263241;
	      box-shadow: 0 12px 28px rgba(0, 0, 0, 0.28);
	    }
	    html[data-app-theme="dark"] .ticker,
	    html[data-app-theme="dark"] .last-price {
	      color: #e5edf4;
	    }
	    html[data-app-theme="dark"] .meta,
	    html[data-app-theme="dark"] .change,
	    html[data-app-theme="dark"] .attribution {
	      color: #94a3b8;
	    }
	    html[data-app-theme="dark"] .empty {
	      background: #17202c;
	      border-color: #334155;
	      color: #94a3b8;
	    }
	    html[data-app-theme="dark"] .attribution a {
	      color: #5eead4;
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

	      const darkMode = document.documentElement.dataset.appTheme === "dark";
	      const theme = darkMode
	        ? {
	          background: "#111827",
	          text: "#94a3b8",
	          gridVert: "#1f2937",
	          gridHorz: "#1f2937",
	          crosshair: "#64748b",
	          crosshairLabel: "#0b1115",
	        }
	        : {
	          background: "#ffffff",
	          text: "#64748b",
	          gridVert: "#f1f5f9",
	          gridHorz: "#edf2f7",
	          crosshair: "#94a3b8",
	          crosshairLabel: "#0f172a",
	        };
	      const chartApi = LightweightCharts.createChart(container, {
	        width: container.clientWidth || 360,
	        height: 238,
	        layout: {
	          background: { type: "solid", color: theme.background },
	          textColor: theme.text,
	          fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
	          fontSize: 11,
	        },
	        grid: {
	          vertLines: { color: theme.gridVert },
	          horzLines: { color: theme.gridHorz },
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
	          vertLine: { color: theme.crosshair, labelBackgroundColor: theme.crosshairLabel },
	          horzLine: { color: theme.crosshair, labelBackgroundColor: theme.crosshairLabel },
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
        .replace("__APP_THEME__", chart_theme)
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
    thumbnail_url = safe_url(article.thumbnail_url)
    article_url = safe_url(article.url)
    if thumbnail_url and not compact:
        classes += " with-image"
    image_html = (
        f'<img src="{escape(thumbnail_url)}" alt="" loading="lazy" />'
        if thumbnail_url and not compact
        else ""
    )
    if article_url:
        title_html = (
            f'<a class="streamlit-news-title" href="{escape(article_url)}" '
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


def safe_url(value: object) -> str | None:
    """Return http(s) URLs only for Streamlit unsafe HTML rendering."""
    if not value:
        return None
    parsed = urlparse(str(value).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return str(value).strip()


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


def ticker_news_body_html(ticker_group: Any, expanded: bool = False) -> str:
    """Return one watchlist news card body for collapsed or expanded state."""
    articles = list(ticker_group.articles or [])
    visible_count = NEWS_EXPANDED_HEADLINE_COUNT if expanded else NEWS_COLLAPSED_HEADLINE_COUNT
    visible_articles = articles[:visible_count]
    warnings = "".join(f'<div class="inline-warning">{escape(warning)}</div>' for warning in ticker_group.warnings)

    if expanded:
        grouped = group_articles_by_category(visible_articles)
        category_html = []
        for category, label in NEWS_CATEGORY_LABELS.items():
            category_articles = grouped.get(category, [])
            if not category_articles:
                continue
            category_cards = "".join(article_card_html(article, compact=True) for article in category_articles)
            category_html.append(
                '<details class="streamlit-news-category-details" open>'
                f'<summary>{escape(label)} ({len(category_articles)})</summary>'
                f"<div>{category_cards}</div>"
                "</details>"
            )
        body_html = "".join(category_html) or '<p class="news-empty">No categorized headlines returned.</p>'
    else:
        body_html = "".join(article_card_html(article, compact=True) for article in visible_articles)
        if not body_html:
            body_html = '<p class="news-empty">No recent headlines returned.</p>'

    return f"{warnings}{body_html}"


def ticker_news_card_html(ticker_group: Any, expanded: bool = False) -> str:
    """Return one static HTML watchlist news card for tests and non-interactive contexts."""
    articles = list(ticker_group.articles or [])
    expanded_attr = " open" if expanded else ""
    expanded_class = " expanded" if expanded else ""
    collapsed_body = ticker_news_body_html(ticker_group, expanded=False)
    expanded_body = ticker_news_body_html(ticker_group, expanded=True)
    can_expand = len(articles) > NEWS_COLLAPSED_HEADLINE_COUNT
    if not can_expand:
        return (
            '<article class="streamlit-ticker-news-card">'
            '<div class="streamlit-ticker-news-header">'
            f'<div class="streamlit-ticker-news-title"><h4>{escape(ticker_group.ticker)}</h4>'
            f"<span>{len(articles)} headline(s)</span></div>"
            "</div>"
            f"{collapsed_body}"
            "</article>"
        )
    return (
        f'<article class="streamlit-ticker-news-card{expanded_class}">'
        f'<details class="streamlit-news-toggle-details"{expanded_attr}>'
        '<summary class="streamlit-ticker-news-header">'
        f'<div class="streamlit-ticker-news-title"><h4>{escape(ticker_group.ticker)}</h4>'
        f'<span>{len(articles)} headline(s)</span></div><span class="streamlit-news-toggle-arrow" aria-hidden="true"></span>'
        "</summary>"
        f'<div class="streamlit-news-expanded-body">{expanded_body}</div>'
        "</details>"
        f'<div class="streamlit-news-collapsed-body">{collapsed_body}</div>'
        "</article>"
    )


def render_ticker_news_card(ticker_group: Any) -> None:
    """Render one watchlist news card with local HTML expansion."""
    st.markdown(ticker_news_card_html(ticker_group), unsafe_allow_html=True)


def filter_ticker_news_groups(ticker_news: list[Any], query: object) -> list[Any]:
    """Return ticker news groups whose ticker matches any search term."""
    terms = level_search_terms(query)
    if not terms:
        return list(ticker_news)
    return [group for group in ticker_news if any(term in str(group.ticker).upper() for term in terms)]


def render_ticker_news_grid(ticker_news: list[Any], empty_message: str = "No watchlist news was returned.") -> None:
    """Render watchlist news groups in a compact responsive grid."""
    if not ticker_news:
        st.info(empty_message)
        return
    columns = st.columns(min(3, len(ticker_news)))
    for index, group in enumerate(ticker_news):
        with columns[index % len(columns)]:
            render_ticker_news_card(group)


def render_x_timeline() -> None:
    """Embed the public @unusual_whales X.com timeline with a fallback link."""
    theme = streamlit_theme_type()
    st.iframe(
        """
        <a
          class="twitter-timeline"
          data-height="560"
          data-theme="__X_THEME__"
          data-dnt="true"
          href="https://twitter.com/unusual_whales?ref_src=twsrc%5Etfw"
        >
          Posts by @unusual_whales
        </a>
        <p id="x-fallback" style="display:none; font: 13px sans-serif; color: #64748b;">
          If the timeline does not load, open
          <a href="https://x.com/unusual_whales" target="_blank" rel="noopener noreferrer">@unusual_whales on X.com</a>.
        </p>
        <script>
          (function () {
            try {
              var theme = window.parent.document.querySelector(".streamlit-theme-marker")?.getAttribute("data-app-theme");
              if (theme) {
                document.querySelector(".twitter-timeline")?.setAttribute("data-theme", theme);
              }
            } catch (error) {}
          })();
        </script>
        <script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>
        <script>
          window.setTimeout(function () {
            if (!document.querySelector("iframe")) {
              document.getElementById("x-fallback").style.display = "block";
            }
          }, 6500);
        </script>
        """.replace("__X_THEME__", theme),
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

    watchlist_heading_col, watchlist_search_col = st.columns([1.6, 1], vertical_alignment="center")
    with watchlist_heading_col:
        st.markdown('<div class="streamlit-section-header"><h2>Watchlist News</h2></div>', unsafe_allow_html=True)
    with watchlist_search_col:
        news_search = st.text_input(
            "Search watchlist news",
            placeholder="AAPL, MSFT",
            key="watchlist_news_search",
        )
    visible_ticker_news = filter_ticker_news_groups(report.ticker_news, news_search)
    if news_search and not visible_ticker_news:
        render_ticker_news_grid([], f"No ticker matching '{normalize_level_search(news_search)}'.")
    else:
        if news_search:
            st.caption(f"Showing {len(visible_ticker_news)} of {len(report.ticker_news)} ticker(s).")
        render_ticker_news_grid(visible_ticker_news)

    st.markdown('<div class="streamlit-section-header"><h2>X.com</h2></div>', unsafe_allow_html=True)
    render_x_timeline()


def split_scanner_global_messages(warnings: list[str]) -> tuple[list[str], list[str]]:
    """Split scanner-wide warnings into visible failures and lower-priority notes."""
    visible: list[str] = []
    notes: list[str] = []
    for warning in warnings:
        if warning.startswith("No pattern data was returned for "):
            notes.append(warning)
        else:
            visible.append(warning)
    return visible, notes


def render_scanner_message_notes(
    label: str,
    messages: list[tuple[str, str]],
    *,
    expanded: bool = False,
) -> None:
    """Render ticker-scoped scanner messages in a compact expander."""
    if not messages:
        return
    grouped: dict[str, list[str]] = {}
    for ticker, message in messages:
        grouped.setdefault(ticker, []).append(message)
    with st.expander(f"{len(grouped)} ticker(s) with {label}", expanded=expanded):
        for ticker, ticker_messages in grouped.items():
            st.caption(f"{ticker}: {' '.join(ticker_messages)}")


def render_scanner_global_notes(label: str, messages: list[str], *, expanded: bool = False) -> None:
    """Render scanner-wide informational notes without warning-block noise."""
    if not messages:
        return
    with st.expander(f"{len(messages)} {label}", expanded=expanded):
        for message in messages:
            st.caption(message)


def render_scanner(report: ScannerResponse) -> None:
    """Render setup scanner and intraday pattern analysis."""
    visible_warnings, pattern_notes = split_scanner_global_messages(report.warnings)
    for warning in visible_warnings:
        st.warning(warning)
    render_scanner_global_notes("scanner pattern note(s)", pattern_notes)

    setup_tab, pattern_tab = st.tabs(["Setup Scanner", "Intraday Pattern Analysis"])
    with setup_tab:
        if not report.setup_rows:
            st.info("No setup scanner rows were returned.")
        else:
            st.dataframe(
                styled_scanner_setup_frame(report),
                width="stretch",
                hide_index=True,
                row_height=42,
                height=dataframe_height(len(report.setup_rows), row_height=42),
            )
            row_warnings = [(row.ticker, warning) for row in report.setup_rows for warning in row.warnings]
            render_scanner_message_notes("scanner warning(s)", row_warnings)
            data_notes = [(row.ticker, note) for row in report.setup_rows for note in row.data_notes]
            render_scanner_message_notes("scanner data note(s)", data_notes)

    with pattern_tab:
        if not report.pattern_summary:
            st.info("No intraday pattern analysis was returned.")
            return
        st.subheader("Pattern Summary")
        st.dataframe(
            pattern_summary_frame(report),
            width="stretch",
            hide_index=True,
            row_height=40,
            height=dataframe_height(len(report.pattern_summary), row_height=40),
        )
        st.subheader("5-Min Heatmap")
        st.caption("Average percent from open by 5-minute ET bucket. Negative values mark below-open periods.")
        heatmap_frame = pattern_heatmap_frame(report)
        st.dataframe(
            heatmap_frame,
            width="stretch",
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
                    width="stretch",
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
                "Sup Conf": str(row.support_confidence) if row.support_confidence is not None else "-",
                "Best Resistance": row.best_resistance or "-",
                "Res Conf": str(row.resistance_confidence) if row.resistance_confidence is not None else "-",
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
            return "background-color:var(--signal-strong-bg,#dcfce7);color:var(--signal-strong-fg,#166534);font-weight:800"
        if score >= 5:
            return "background-color:var(--signal-good-bg,#ccfbf1);color:var(--signal-good-fg,#0f766e);font-weight:800"
        if score >= 3:
            return "background-color:var(--signal-watch-bg,#fef3c7);color:var(--signal-watch-fg,#92400e);font-weight:800"
        if score >= 0:
            return "background-color:var(--signal-danger-bg,#fee2e2);color:var(--signal-danger-fg,#991b1b);font-weight:800"
    if text.endswith("x"):
        try:
            lows = int(text[:-1])
        except ValueError:
            lows = 0
        if lows >= 3:
            return "background-color:var(--signal-strong-bg,#dcfce7);color:var(--signal-strong-fg,#166534);font-weight:800"
        if lows == 2:
            return "background-color:var(--signal-good-bg,#ccfbf1);color:var(--signal-good-fg,#0f766e);font-weight:800"
        if lows == 1:
            return "background-color:var(--signal-watch-bg,#fef3c7);color:var(--signal-watch-fg,#92400e);font-weight:800"
    if text == "Turning Up":
        return "background-color:var(--signal-strong-bg,#dcfce7);color:var(--signal-strong-fg,#166534);font-weight:800"
    if text == "Ticking Up":
        return "background-color:var(--signal-good-bg,#ccfbf1);color:var(--signal-good-fg,#0f766e);font-weight:800"
    if text == "Still Falling":
        return "background-color:var(--signal-danger-bg,#fee2e2);color:var(--signal-danger-fg,#991b1b);font-weight:800"
    return "background-color:var(--signal-neutral-bg,#f1f5f9);color:var(--signal-neutral-fg,#64748b);font-weight:700" if text == "-" or text == "Flat" else ""


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
        invalid: list[str] = []
        try:
            candidates = split_ticker_candidates(add_text)
        except ValueError:
            candidates = []
        for candidate in candidates:
            try:
                ticker = normalize_ticker_symbol(candidate)
            except ValueError:
                if str(candidate).strip():
                    invalid.append(str(candidate).strip())
                continue
            if ticker not in st.session_state.watchlist_tickers:
                st.session_state.watchlist_tickers.append(ticker)
                added = True
        if invalid:
            st.session_state.watchlist_validation_message = (
                f"Skipped invalid ticker{'s' if len(invalid) != 1 else ''}: {', '.join(invalid[:4])}."
            )
        else:
            st.session_state.pop("watchlist_validation_message", None)
        if added:
            persist_session_watchlist()
            bump_streamlit_refresh_token("Refreshing watchlist")
        st.session_state.streamlit_ticker_add_text = ""

    st.text_input(
        "Ticker symbol",
        key="streamlit_ticker_add_text",
        placeholder="Add ticker symbols",
    )
    st.button("Add", type="primary", width="stretch", on_click=add_pending_tickers)
    if st.session_state.get("watchlist_validation_message"):
        st.warning(str(st.session_state.watchlist_validation_message))
    if st.button(
        "▶ Run levels + news",
        key="streamlit-sidebar-run",
        type="primary",
        width="stretch",
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
            bump_streamlit_refresh_token("Refreshing watchlist")
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
            bump_streamlit_refresh_token("Refreshing watchlist")
            st.rerun()
        if cols[3].button("×", key=f"watch-remove-{ticker}", help=f"Remove {ticker}"):
            st.session_state.watchlist_tickers.remove(ticker)
            persist_session_watchlist()
            bump_streamlit_refresh_token("Refreshing watchlist")
            st.rerun()
    if not st.session_state.watchlist_tickers:
        st.caption("No tickers saved.")
    return tuple(st.session_state.watchlist_tickers)


def load_streamlit_data(tickers: tuple[str, ...], metrics: tuple[MetricName, ...], refresh_token: int) -> None:
    """Load all Streamlit datasets for the current watchlist."""
    st.session_state.report = build_report(tickers, metrics, refresh_token=refresh_token)
    st.session_state.scanner = build_scanner(tickers, refresh_token=refresh_token)
    st.session_state.market_snapshot = build_market_snapshot(tickers, refresh_token=refresh_token)
    st.session_state.news = build_news(
        tickers,
        per_ticker=NEWS_EXPANDED_HEADLINE_COUNT,
        refresh_token=refresh_token,
    )


def run_refresh_steps(refresh_slot: Any, title: str, steps: list[RefreshStep]) -> None:
    """Show a temporary top-of-page refresh banner while running refresh steps."""
    if not steps:
        return
    safe_title = title or REFRESH_BANNER_DEFAULT_TITLE
    with refresh_slot.container():
        st.markdown(
            (
                '<div class="streamlit-refresh-banner">'
                f"<strong>{escape(safe_title)}</strong>"
                f"<span>{escape(steps[0][0])}</span>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        progress = st.progress(0, text=steps[0][0])

    total_steps = len(steps)
    try:
        for index, (label, action) in enumerate(steps, start=1):
            progress.progress((index - 1) / total_steps, text=label)
            action()
            progress.progress(index / total_steps, text=label)
    finally:
        refresh_slot.empty()
        st.session_state.pop("refresh_banner_title", None)


def streamlit_data_key(dataset: str, tickers: tuple[str, ...], metrics: tuple[MetricName, ...]) -> tuple[tuple[str, ...], tuple[MetricName, ...], int]:
    """Return the loaded-state key for one Streamlit dataset."""
    return (tuple(tickers), tuple(metrics), dataset_refresh_token(dataset))


def streamlit_dataset_current(dataset: str, tickers: tuple[str, ...], metrics: tuple[MetricName, ...]) -> bool:
    """Return whether one Streamlit dataset is current for the watchlist and token."""
    ensure_streamlit_data_state()
    return st.session_state.loaded_data_keys.get(dataset) == streamlit_data_key(dataset, tickers, metrics)


def mark_streamlit_data_current(
    tickers: tuple[str, ...],
    metrics: tuple[MetricName, ...],
    refresh_token: int | None = None,
    datasets: tuple[str, ...] = STREAMLIT_DATASETS,
) -> None:
    """Mark selected Streamlit datasets as loaded for their active refresh tokens."""
    del refresh_token
    ensure_streamlit_data_state()
    for dataset in datasets:
        if dataset in STREAMLIT_DATASETS:
            st.session_state.loaded_data_keys[dataset] = streamlit_data_key(dataset, tickers, metrics)


def loaded_streamlit_datasets() -> tuple[str, ...]:
    """Return datasets that have already been loaded in this Streamlit session."""
    loaded: list[str] = []
    if st.session_state.get("report") is not None:
        loaded.append("report")
    if st.session_state.get("scanner") is not None:
        loaded.append("scanner")
    if st.session_state.get("news") is not None:
        loaded.append("news")
    if st.session_state.get("market_snapshot") is not None:
        loaded.append("market_snapshot")
    if st.session_state.get("chart_loaded"):
        loaded.append("chart")
    return tuple(loaded)


def merge_streamlit_datasets(*dataset_groups: tuple[str, ...]) -> tuple[str, ...]:
    """Merge dataset names in Streamlit load order without duplicates."""
    merged: list[str] = []
    for group in dataset_groups:
        for dataset in group:
            if dataset in STREAMLIT_DATASETS and dataset not in merged:
                merged.append(dataset)
    return tuple(merged)


def load_streamlit_data_with_banner(
    tickers: tuple[str, ...],
    metrics: tuple[MetricName, ...],
    refresh_slot: Any,
    title: str,
    datasets: tuple[str, ...] = ("report", "scanner", "news", "market_snapshot"),
) -> None:
    """Load all Streamlit datasets with a temporary top banner."""

    def load_levels() -> None:
        st.session_state.report = build_report(tickers, metrics, refresh_token=dataset_refresh_token("report"))

    def load_scanner() -> None:
        st.session_state.scanner = build_scanner(tickers, refresh_token=dataset_refresh_token("scanner"))

    def load_headlines() -> None:
        st.session_state.news = build_news(
            tickers,
            per_ticker=NEWS_EXPANDED_HEADLINE_COUNT,
            refresh_token=dataset_refresh_token("news"),
        )

    def load_snapshot() -> None:
        st.session_state.market_snapshot = build_market_snapshot(tickers, refresh_token=dataset_refresh_token("market_snapshot"))

    all_steps: dict[str, RefreshStep] = {
        "report": ("Calculating levels...", load_levels),
        "scanner": ("Running scanner...", load_scanner),
        "market_snapshot": ("Refreshing market snapshot...", load_snapshot),
        "news": ("Loading headlines...", load_headlines),
    }
    steps = [all_steps[dataset] for dataset in datasets if dataset in all_steps]

    run_refresh_steps(
        refresh_slot,
        title,
        steps,
    )


@st.fragment(run_every=AUTO_REFRESH_SECONDS)
def render_auto_refresh_fragment(enabled: bool, view: str) -> None:
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
        datasets = loaded_streamlit_datasets() or streamlit_autoload_datasets(view)
        st.session_state.auto_refresh_pending_datasets = datasets
        bump_streamlit_refresh_token("Auto-refreshing watchlist", datasets=datasets)
        st.rerun()


def streamlit_autoload_datasets(view: str, *, include_news: bool = False) -> tuple[str, ...]:
    """Return Streamlit datasets to load for the current view in priority order."""
    if include_news or view == NEWS_VIEW:
        return ("report", "scanner", "market_snapshot", "news")
    return ("report", "scanner")


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


def report_layout_options() -> tuple[str, ...]:
    """Return configured report layout IDs in display order."""
    return tuple(layout.id for layout in report_layout_catalog())


def report_layout_label(layout_id: str) -> str:
    """Return the display label for a report layout ID."""
    return next((layout.label for layout in report_layout_catalog() if layout.id == layout_id), layout_id)


def normalize_report_layout(layout_id: object) -> str:
    """Return a supported report layout ID."""
    candidate = str(layout_id or "")
    options = report_layout_options()
    return candidate if candidate in options else DEFAULT_REPORT_LAYOUT


def render_report_layout_selector() -> str:
    """Render and persist the Streamlit report layout selector."""
    st.session_state.report_layout = normalize_report_layout(st.session_state.get("report_layout", DEFAULT_REPORT_LAYOUT))
    return str(
        st.selectbox(
            "View",
            report_layout_options(),
            format_func=report_layout_label,
            key="report_layout",
        )
    )


def render_level_filter_selector() -> str:
    """Render and persist the Streamlit Levels card filter selector."""
    st.session_state.level_filter = normalize_level_filter(st.session_state.get("level_filter", DEFAULT_LEVEL_FILTER))
    return str(
        st.selectbox(
            "Level filter",
            LEVEL_FILTER_OPTIONS,
            format_func=level_filter_label,
            key="level_filter",
            help=(
                "All Levels shows every price level. Scanner Levels Only matches scanner support/resistance inputs. "
                "Weight 20+ Only shows the highest-trust levels."
            ),
        )
    )


def normalize_level_search(query: object) -> str:
    """Normalize a report ticker search query."""
    return str(query or "").strip().upper()


def level_search_terms(query: object) -> list[str]:
    """Return comma/space separated report search terms."""
    normalized = normalize_level_search(query)
    if not normalized:
        return []
    try:
        candidates = split_ticker_candidates(normalized)
    except ValueError:
        candidates = [normalized]
    terms: list[str] = []
    for candidate in candidates:
        raw = str(candidate).strip().upper()
        if not raw:
            continue
        try:
            term = normalize_ticker_symbol(raw)
        except ValueError:
            term = raw
        if term not in terms:
            terms.append(term)
    return terms


def filter_report_metrics(metrics: list[EquityMetrics], query: object) -> list[EquityMetrics]:
    """Return report metrics whose ticker contains the search query."""
    terms = level_search_terms(query)
    if not terms:
        return list(metrics)
    return [metric for metric in metrics if any(term in metric.ticker.upper() for term in terms)]


def replace_report_metrics(
    tickers: tuple[str, ...],
    report: GenerateResponse,
    updates: list[EquityMetrics],
) -> GenerateResponse:
    """Return report with updated metrics in original watchlist order."""
    ticker_order = [ticker.upper().strip() for ticker in tickers if ticker.strip()]
    metrics_by_ticker = {metric.ticker: metric for metric in report.metrics}
    metrics_by_ticker.update({metric.ticker: metric for metric in updates})
    ordered_metrics = [
        metrics_by_ticker[ticker]
        for ticker in ticker_order
        if ticker in metrics_by_ticker
    ]
    return GenerateResponse(generated_at=datetime.now(timezone.utc), metrics=ordered_metrics)


def render_report_panel(
    report: GenerateResponse,
    *,
    complete: bool,
    total_tickers: int | None = None,
    chart_slot: Any | None = None,
) -> None:
    """Render report cards, with optional final-only controls and charts."""
    with st.container(border=True):
        if complete:
            header_col, search_col, layout_col, filter_col = st.columns(
                [1.25, 1.1, 0.85, 1.05],
                vertical_alignment="center",
            )
            with header_col:
                st.header("Levels")
            with search_col:
                report_search = st.text_input(
                    "Search ticker",
                    placeholder="Type ticker...",
                    key="levels_report_search",
                )
            with layout_col:
                report_layout = render_report_layout_selector()
            with filter_col:
                level_filter = render_level_filter_selector()
        else:
            st.header("Levels")
            loaded_count = len(report.metrics)
            target_count = total_tickers or loaded_count
            st.caption(f"Loaded {loaded_count} of {target_count} ticker(s). Charts and PDF will appear when loading completes.")
            report_search = ""
            report_layout = normalize_report_layout(st.session_state.get("report_layout", DEFAULT_REPORT_LAYOUT))
            level_filter = normalize_level_filter(st.session_state.get("level_filter", DEFAULT_LEVEL_FILTER))

        visible_metrics = filter_report_metrics(report.metrics, report_search)
        if report_search and not visible_metrics:
            st.caption(f"No ticker matching '{normalize_level_search(report_search)}'")
        elif report_search:
            st.caption(f"Showing {len(visible_metrics)} of {len(report.metrics)} ticker(s).")

        render_metric_grid(visible_metrics, report_layout, level_filter=level_filter)

        if complete:
            st.divider()
            export_text_col, export_button_col = st.columns([2.1, 1], vertical_alignment="center")
            with export_text_col:
                st.caption("Export the completed Levels report after the on-screen cards are loaded.")
            with export_button_col:
                pdf = pdf_report_service().build_pdf(report)
                st.download_button(
                    "Download PDF Levels",
                    data=pdf,
                    file_name=f"equity-levels-{report.generated_at.strftime('%Y%m%d-%H%M%S')}.pdf",
                    mime="application/pdf",
                    type="secondary",
                    width="stretch",
                )

    if complete and visible_metrics and chart_slot is not None:
        chart_slot.empty()
        with chart_slot.container():
            chart_type, chart_range, chart_interval = render_streamlit_chart_controls()
            render_chart_history(
                report,
                chart_range,
                chart_interval,
                chart_type,
                refresh_token=dataset_refresh_token("chart"),
                visible_tickers=tuple(metric.ticker for metric in visible_metrics),
            )


def render_report_panel_in_slot(
    slot: Any,
    report: GenerateResponse,
    *,
    complete: bool,
    total_tickers: int | None = None,
    chart_slot: Any | None = None,
) -> None:
    """Replace the report placeholder with the latest report render."""
    slot.empty()
    with slot.container():
        render_report_panel(report, complete=complete, total_tickers=total_tickers, chart_slot=chart_slot)


def render_scanner_panel_in_slot(slot: Any, scanner: ScannerResponse) -> None:
    """Replace the scanner placeholder with the rendered scanner table."""
    slot.empty()
    with slot.container():
        with st.container(border=True):
            render_scanner(scanner)


def load_levels_and_scanner_progressively(
    tickers: tuple[str, ...],
    metrics: tuple[MetricName, ...],
    report_slot: Any,
    scanner_slot: Any,
    refresh_slot: Any,
    chart_slot: Any | None = None,
) -> tuple[GenerateResponse, ScannerResponse]:
    """Load levels/scanner batches and render each partial result as it arrives."""
    batches = ticker_batches(tickers)
    report_responses: list[GenerateResponse] = []
    scanner_responses: list[ScannerResponse] = []
    partial_metrics: list[EquityMetrics] = []
    final_report = GenerateResponse(generated_at=datetime.now(timezone.utc), metrics=[])
    final_scanner = ScannerService.merge_responses(tickers, [])
    st.session_state.chart_loaded = False
    if chart_slot is not None:
        chart_slot.empty()

    market_data = market_data_service()
    scanner = scanner_service()

    def load_levels_batch(
        batch: tuple[str, ...],
        selected_metrics: tuple[MetricName, ...],
        refresh_token: int,
    ) -> GenerateResponse:
        del refresh_token
        return GenerateResponse(
            generated_at=datetime.now(timezone.utc),
            metrics=market_data.build_metrics(list(batch), list(selected_metrics), include_earnings=False),
        )

    def load_scanner_batch(batch: tuple[str, ...], refresh_token: int) -> ScannerResponse:
        del refresh_token
        return scanner.build_scanner(list(batch), include_setup=True, include_patterns=True, include_earnings=False)

    with refresh_slot.container():
        st.markdown(
            (
                '<div class="streamlit-refresh-banner">'
                "<strong>Loading levels and scanner</strong>"
                "<span>Loading first ticker batch...</span>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        progress = st.progress(0, text="Loading first ticker batch...")

    events, worker = start_pipelined_levels_scanner_loader(
        tickers,
        metrics,
        dataset_refresh_token("report"),
        dataset_refresh_token("scanner"),
        load_levels_batch,
        load_scanner_batch,
    )
    total_events = max(1, len(batches) * 3)
    rendered_events = 0
    try:
        while True:
            event = events.get()
            if event.kind == "done":
                break
            if event.kind == "error":
                raise event.error or RuntimeError("Levels/scanner loading failed.")

            rendered_events += 1
            if event.kind == "levels" and event.report is not None:
                report_responses.append(event.report)
                partial_metrics.extend(event.report.metrics)
                final_report = GenerateResponse(
                    generated_at=event.report.generated_at,
                    metrics=list(partial_metrics),
                )
                st.session_state.report = final_report
                render_report_panel_in_slot(report_slot, final_report, complete=False, total_tickers=len(tickers))
                progress.progress(
                    min(rendered_events / total_events, 1.0),
                    text=f"Loaded levels for {len(partial_metrics)} of {len(tickers)} ticker(s).",
                )
            elif event.kind == "scanner" and event.scanner is not None:
                scanner_responses.append(event.scanner)
                final_scanner = ScannerService.merge_responses(tickers, scanner_responses)
                st.session_state.scanner = final_scanner
                render_scanner_panel_in_slot(scanner_slot, final_scanner)
                progress.progress(
                    min(rendered_events / total_events, 1.0),
                    text=f"Loaded scanner batch {event.batch_index} of {event.total_batches}.",
                )

        metrics_by_ticker = {metric.ticker: metric for metric in final_report.metrics}
        for index, batch in enumerate(batches, start=1):
            batch_metrics = [
                metrics_by_ticker[ticker.upper().strip()]
                for ticker in batch
                if ticker.upper().strip() in metrics_by_ticker
            ]
            if not batch_metrics:
                continue
            completed_metrics = market_data.complete_metrics_earnings(batch_metrics)
            final_report = replace_report_metrics(tickers, final_report, completed_metrics)
            metrics_by_ticker = {metric.ticker: metric for metric in final_report.metrics}
            st.session_state.report = final_report
            render_report_panel_in_slot(report_slot, final_report, complete=False, total_tickers=len(tickers))

            scanner_update = scanner.build_scanner(
                list(batch),
                include_setup=True,
                include_patterns=False,
                include_earnings=True,
            )
            final_scanner = ScannerService.replace_setup_rows(tickers, final_scanner, [scanner_update])
            st.session_state.scanner = final_scanner
            render_scanner_panel_in_slot(scanner_slot, final_scanner)

            rendered_events += 1
            progress.progress(
                min(rendered_events / total_events, 1.0),
                text=f"Loaded earnings metadata for batch {index} of {len(batches)}.",
            )
    finally:
        worker.join()
        refresh_slot.empty()
        st.session_state.pop("refresh_banner_title", None)

    st.session_state.report = final_report
    st.session_state.scanner = final_scanner
    return final_report, final_scanner


def main() -> None:
    """Run the Streamlit application."""
    view = render_app_chrome()
    refresh_banner_slot = st.empty()

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
    ensure_streamlit_data_state()
    if "auto_refresh_bucket" not in st.session_state:
        st.session_state.auto_refresh_bucket = refresh_bucket()
    if "report_layout" not in st.session_state:
        st.session_state.report_layout = DEFAULT_REPORT_LAYOUT

    sidebar_run_requested = bool(st.session_state.pop("sidebar_run_requested", False))
    render_auto_refresh_fragment(bool(tickers), view)
    refresh_token = int(st.session_state.streamlit_refresh_token)
    if sidebar_run_requested and tickers:
        refresh_token = bump_streamlit_refresh_token("Refreshing levels and news")

    autoload_metrics = tuple(DEFAULT_METRICS)
    try:
        autoload_request = GenerateRequest(tickers=list(tickers), metrics=list(autoload_metrics))
    except ValidationError:
        autoload_request = None

    if view == LEVELS_VIEW:
        with st.container():
            heading_col, action_col = st.columns([2.2, 1], vertical_alignment="center")
            with heading_col:
                st.markdown('<span class="view-hero-marker"></span>', unsafe_allow_html=True)
                st.title("Investment Trading Levels")
            with action_col:
                generate = st.button("Generate Levels", type="primary", width="stretch")
            levels_status_slot = st.empty()
            if st.session_state.levels_status:
                levels_status_slot.success(st.session_state.levels_status)
        with st.container(border=True):
            scanner_text_col, scanner_action_col = st.columns([2.2, 1], vertical_alignment="center")
            with scanner_text_col:
                st.subheader("Scanner")
            with scanner_action_col:
                run_scanner = st.button("Run Scanner", type="primary", width="stretch")
        refresh_news = False
        scanner_slot = st.empty()
        report_slot = st.empty()
        chart_slot = st.empty()
    else:
        with st.container():
            heading_col, action_col = st.columns([2.2, 1], vertical_alignment="center")
            with heading_col:
                st.markdown('<span class="view-hero-marker"></span>', unsafe_allow_html=True)
                st.title("Stock News")
            with action_col:
                refresh_news = st.button("Refresh News", type="primary", width="stretch")
        generate = False
        run_scanner = False
        report_slot = None
        chart_slot = None
        scanner_slot = None

    if generate:
        try:
            request = GenerateRequest(tickers=list(tickers), metrics=list(DEFAULT_METRICS))
        except ValidationError as exc:
            st.error(exc.errors()[0]["msg"])
            return

        refresh_token = bump_streamlit_refresh_token("Generating levels", datasets=("report", "scanner"))
        load_levels_and_scanner_progressively(
            tuple(request.tickers),
            tuple(request.metrics),
            report_slot,
            scanner_slot,
            refresh_banner_slot,
            chart_slot,
        )
        mark_streamlit_data_current(tuple(request.tickers), tuple(request.metrics), datasets=("report", "scanner"))
        st.session_state.levels_status = ""

    if run_scanner:
        try:
            request = ScannerRequest(tickers=list(tickers))
        except ValidationError as exc:
            st.error(exc.errors()[0]["msg"])
            return

        refresh_token = bump_streamlit_refresh_token("Refreshing scanner", datasets=("scanner",))

        def refresh_scanner() -> None:
            st.session_state.scanner = build_scanner(tuple(request.tickers), refresh_token=dataset_refresh_token("scanner"))

        run_refresh_steps(refresh_banner_slot, "Refreshing scanner", [("Running scanner...", refresh_scanner)])
        mark_streamlit_data_current(tuple(request.tickers), autoload_metrics, refresh_token, datasets=("scanner",))

    if refresh_news:
        try:
            request = NewsRequest(tickers=list(tickers), per_ticker=NEWS_EXPANDED_HEADLINE_COUNT)
            snapshot_request = MarketSnapshotRequest(tickers=list(tickers))
        except ValidationError as exc:
            st.error(exc.errors()[0]["msg"])
            return

        refresh_token = bump_streamlit_refresh_token("Refreshing news", datasets=("news", "market_snapshot"))

        def refresh_headlines() -> None:
            st.session_state.news = build_news(
                tuple(request.tickers),
                per_ticker=request.per_ticker,
                refresh_token=dataset_refresh_token("news"),
            )

        def refresh_snapshot() -> None:
            st.session_state.market_snapshot = build_market_snapshot(
                tuple(snapshot_request.tickers),
                refresh_token=dataset_refresh_token("market_snapshot"),
            )

        run_refresh_steps(
            refresh_banner_slot,
            "Refreshing news",
            [("Loading headlines...", refresh_headlines), ("Refreshing market snapshot...", refresh_snapshot)],
        )
        mark_streamlit_data_current(
            tuple(request.tickers),
            autoload_metrics,
            refresh_token,
            datasets=("news", "market_snapshot"),
        )

    if autoload_request is not None:
        autoload_tickers = tuple(autoload_request.tickers)
        autoload_metrics_tuple = tuple(autoload_request.metrics)
        pending_auto_refresh_datasets = tuple(st.session_state.pop("auto_refresh_pending_datasets", ()))
        autoload_datasets = merge_streamlit_datasets(
            streamlit_autoload_datasets(view, include_news=sidebar_run_requested),
            pending_auto_refresh_datasets,
        )
        stale_datasets = tuple(
            dataset
            for dataset in autoload_datasets
            if not streamlit_dataset_current(dataset, autoload_tickers, autoload_metrics_tuple)
        )
        if stale_datasets:
            refresh_title = str(st.session_state.pop("refresh_banner_title", "Loading saved watchlist"))
            if (
                view == LEVELS_VIEW
                and ("report" in stale_datasets or "scanner" in stale_datasets)
                and report_slot is not None
                and scanner_slot is not None
            ):
                load_levels_and_scanner_progressively(
                    autoload_tickers,
                    autoload_metrics_tuple,
                    report_slot,
                    scanner_slot,
                    refresh_banner_slot,
                    chart_slot,
                )
                mark_streamlit_data_current(autoload_tickers, autoload_metrics_tuple, datasets=("report", "scanner"))
                stale_datasets = tuple(dataset for dataset in stale_datasets if dataset not in {"report", "scanner"})
            if stale_datasets:
                load_streamlit_data_with_banner(
                    autoload_tickers,
                    autoload_metrics_tuple,
                    refresh_banner_slot,
                    refresh_title,
                    datasets=stale_datasets,
                )
                mark_streamlit_data_current(autoload_tickers, autoload_metrics_tuple, datasets=stale_datasets)
            st.session_state.levels_status = ""
    else:
        st.session_state.report = None
        st.session_state.scanner = None
        st.session_state.news = None
        st.session_state.market_snapshot = None
        st.session_state.autoload_key = None
        st.session_state.loaded_data_keys = {}
        st.session_state.chart_loaded = False

    if view == NEWS_VIEW:
        news: NewsResponse | None = st.session_state.news
        if news is None:
            return
        render_news(news, st.session_state.market_snapshot)
        return

    report: GenerateResponse | None = st.session_state.report
    if report is not None and report_slot is not None:
        render_report_panel_in_slot(report_slot, report, complete=True, chart_slot=chart_slot)

    scanner: ScannerResponse | None = st.session_state.scanner
    if scanner is not None and scanner_slot is not None:
        render_scanner_panel_in_slot(scanner_slot, scanner)


if __name__ == "__main__":
    main()
