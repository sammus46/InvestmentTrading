"""Streamlit entry point for the equity levels app."""

from __future__ import annotations

import base64
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Any, get_args
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
    LevelScoreBasisName,
    MarketSnapshotRequest,
    MarketSnapshotResponse,
    MetricName,
    NewsArticle,
    NewsRequest,
    NewsResponse,
    ScannerRequest,
    ScannerResponse,
    SectorAnalyticsResponse,
    ScoreHistoryAxis,
    ScoreHistoryRange,
    ScoreHistoryPoint,
    ScoreHistoryResponse,
    ScoreHistoryTicker,
    ScoreMetricName,
    TickerChartHistory,
    normalize_ticker_symbol,
    split_ticker_candidates,
)
from app.services.market_data import MarketDataService
from app.services.news import NewsService
from app.services.pdf_report import PdfReportService
from app.services.scanner import ScannerService
from app.services.score_history import ScoreHistoryService
from app.services.display import (
    DEFAULT_LEVEL_FILTER,
    DEFAULT_REPORT_LAYOUT,
    LEVEL_FILTER_OPTIONS,
    level_filter_label,
    level_type_weight_defaults,
    normalize_level_filter,
    report_layout_catalog,
)
from app.streamlit_ui.metrics import metric_card_html, metric_rows, render_metric, render_metric_grid


NEWS_COLLAPSED_HEADLINE_COUNT = 5
NEWS_EXPANDED_HEADLINE_COUNT = 10
NEWS_MAX_HEADLINE_COUNT = 20
LEVEL_WEIGHT_MIN = 0
LEVEL_WEIGHT_MAX = 50
NEWS_CATEGORY_LABELS = {
    "rating_changes": "Price Rating Changes",
    "contracts": "Company Contract Announcements",
    "earnings": "Earnings Reports",
    "general": "General News",
}
CHART_TYPE_OPTIONS = ("Line", "Candles")
CHART_RANGE_OPTIONS: tuple[ChartRange, ...] = tuple(CHART_INTERVALS_BY_RANGE.keys())
CHART_RANGE_LABELS = {"1Y": "1YR"}
SCORE_ANALYTICS_RANGE_CANDIDATES = ("1D", "7D", "30D", "90D", "1Y", "All")
SCORE_ANALYTICS_DAILY_RANGES = ("7D", "30D", "90D", "1Y", "All")


def supported_score_history_ranges(range_type: object = ScoreHistoryRange) -> tuple[str, ...]:
    """Return score ranges supported by the currently loaded model module."""
    model_ranges = set(get_args(range_type))
    ranges = tuple(option for option in SCORE_ANALYTICS_RANGE_CANDIDATES if option in model_ranges)
    return ranges or SCORE_ANALYTICS_DAILY_RANGES


def default_score_history_range(ranges: tuple[str, ...]) -> str:
    """Return the safest default range for the loaded ScoreHistoryRange model."""
    return "1D" if "1D" in ranges else "30D"


SCORE_ANALYTICS_RANGES: tuple[ScoreHistoryRange, ...] = supported_score_history_ranges()  # type: ignore[assignment]
SCORE_ANALYTICS_DEFAULT_RANGE: ScoreHistoryRange = default_score_history_range(SCORE_ANALYTICS_RANGES)  # type: ignore[assignment]
SCORE_ANALYTICS_METRICS: tuple[ScoreMetricName, ...] = ("setup", "level", "both")
SCORE_ANALYTICS_CHART_METRICS = ("heat", "setup", "level")
SCORE_ANALYTICS_MOVEMENTS = ("all", "improving", "declining", "flat")
SCORE_ANALYTICS_SORTS = ("watchlist", "setup", "level", "gain", "drop")
SCORE_RANGE_WIDGET_KEY = "_score_range_widget"
SCORE_METRIC_WIDGET_KEY = "_score_metric_widget"
SCORE_CHART_METRIC_WIDGET_KEY = "_score_chart_metric_widget"
SCORE_LEVEL_BASIS_WIDGET_KEY = "_score_level_basis_widget"
SCORE_MOVEMENT_WIDGET_KEY = "_score_movement_widget"
SCORE_SORT_WIDGET_KEY = "_score_sort_widget"
SCORE_OPTION_LABELS = {
    "1D": "1D",
    "7D": "7D",
    "30D": "30D",
    "90D": "90D",
    "1Y": "1Y",
    "All": "All",
    "setup": "Adam Setup",
    "level": "Derived Level",
    "both": "Both",
    "heat": "Derived Heat",
    "all": "All",
    "scanner": "Scanner",
    "weight_20": "Weight 20+",
    "improving": "Improving",
    "declining": "Declining",
    "flat": "Flat/New",
    "watchlist": "Watchlist",
    "gain": "Biggest Gain",
    "drop": "Biggest Drop",
}
AUTO_REFRESH_SECONDS = 60
STREAMLIT_REPORT_BATCH_SIZE = 3
REFRESH_BANNER_DEFAULT_TITLE = "Refreshing data"
STREAMLIT_STATE_ENV = "INVESTMENT_TRADING_STREAMLIT_STATE"
STREAMLIT_DATASETS = ("report", "scanner", "sector_analytics", "news", "market_snapshot", "chart")
LIGHTWEIGHT_CHARTS_BUNDLE_PATH = (
    Path(__file__).parent / "static" / "vendor" / "lightweight-charts" / "lightweight-charts.standalone.production.js"
)
RefreshStep = tuple[str, Callable[[], None]]
ReportBatchLoader = Callable[[tuple[str, ...], tuple[MetricName, ...], int], GenerateResponse]
ScannerBatchLoader = Callable[[tuple[str, ...], int], ScannerResponse]


LEVELS_VIEW = "Investment Trading Levels"
NEWS_VIEW = "Stock News"
ANALYTICS_VIEW = "Sector Analytics"
STREAMLIT_VIEWS = (LEVELS_VIEW, NEWS_VIEW, ANALYTICS_VIEW)
SCANNER_VIEW_OPTIONS = ("auto", "table", "cards")
SCANNER_VIEW_LABELS = {
    "auto": "Auto",
    "table": "Table",
    "cards": "Cards",
}
SCANNER_SORT_OPTIONS = {
    "score": "Setup score",
    "ticker": "Ticker",
    "price": "Price",
    "signal": "Signal",
    "vwap_extension_percent": "VWAP extension",
    "rs_vs_spy_percent": "RS vs SPY",
    "rs_vs_sector_percent": "RS vs sector",
    "support_confidence": "Support confidence",
    "resistance_confidence": "Resistance confidence",
    "risk_reward": "Risk/reward",
    "setup_distance_percent": "Distance from setup",
    "lows_held": "Lows held",
    "off_high_percent": "Distance from high",
    "momentum": "Momentum",
}
STREAMLIT_DEFAULT_SETTINGS = {
    "default_view": LEVELS_VIEW,
    "report_layout": DEFAULT_REPORT_LAYOUT,
    "level_filter": DEFAULT_LEVEL_FILTER,
    "level_weights": {},
    "scanner_view": "auto",
    "chart_type": "Line",
    "chart_range": "1D",
    "chart_interval": "5m",
    "auto_load": True,
    "auto_refresh": True,
    "news_per_ticker": NEWS_EXPANDED_HEADLINE_COUNT,
}


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


@st.cache_resource
def score_history_service() -> ScoreHistoryService:
    """Return one score-history store per Streamlit worker process."""
    return ScoreHistoryService()


@st.cache_data(ttl=300, show_spinner=False)
def build_report_payload(tickers: tuple[str, ...], metrics: tuple[MetricName, ...], refresh_token: int = 0) -> dict[str, Any]:
    """Fetch and calculate metrics as cache-safe JSON-compatible data."""
    return GenerateResponse(
        generated_at=datetime.now(timezone.utc),
        metrics=normalize_equity_metrics(market_data_service().build_metrics(list(tickers), list(metrics))),
    ).model_dump(mode="json")


def build_report(tickers: tuple[str, ...], metrics: tuple[MetricName, ...], refresh_token: int = 0) -> GenerateResponse:
    """Fetch and calculate metrics, cached briefly to avoid repeated provider calls."""
    return GenerateResponse.model_validate(build_report_payload(tickers, metrics, refresh_token=refresh_token))


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
        accumulated.extend(normalize_equity_metrics(batch_response.metrics))
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
def build_news_payload(
    tickers: tuple[str, ...],
    per_ticker: int = NEWS_EXPANDED_HEADLINE_COUNT,
    general_count: int = 8,
    refresh_token: int = 0,
) -> dict[str, Any]:
    """Fetch watchlist plus broad market news as cache-safe JSON-compatible data."""
    return news_service().build_news(
        list(tickers),
        per_ticker=per_ticker,
        general_count=general_count,
    ).model_dump(mode="json")


def build_news(
    tickers: tuple[str, ...],
    per_ticker: int = NEWS_EXPANDED_HEADLINE_COUNT,
    general_count: int = 8,
    refresh_token: int = 0,
) -> NewsResponse:
    """Fetch and normalize watchlist plus broad market news."""
    return NewsResponse.model_validate(
        build_news_payload(
            tickers,
            per_ticker=per_ticker,
            general_count=general_count,
            refresh_token=refresh_token,
        )
    )


@st.cache_data(ttl=120, show_spinner=False)
def build_market_snapshot_payload(tickers: tuple[str, ...], refresh_token: int = 0) -> dict[str, Any]:
    """Fetch major market plus watchlist performance as cache-safe JSON-compatible data."""
    return market_data_service().build_market_snapshot(list(tickers)).model_dump(mode="json")


def build_market_snapshot(tickers: tuple[str, ...], refresh_token: int = 0) -> MarketSnapshotResponse:
    """Fetch major market plus watchlist day-to-date performance."""
    return MarketSnapshotResponse.model_validate(build_market_snapshot_payload(tickers, refresh_token=refresh_token))


@st.cache_data(ttl=120, show_spinner=False)
def build_scanner_payload(tickers: tuple[str, ...], refresh_token: int = 0) -> dict[str, Any]:
    """Run setup scanner rows as cache-safe JSON-compatible data."""
    return normalize_scanner_response(
        scanner_service().build_scanner(list(tickers), include_setup=True, include_patterns=False)
    ).model_dump(mode="json")


def build_scanner(tickers: tuple[str, ...], refresh_token: int = 0) -> ScannerResponse:
    """Run setup scanner rows."""
    return ScannerResponse.model_validate(build_scanner_payload(tickers, refresh_token=refresh_token))


@st.cache_data(ttl=120, show_spinner=False)
def build_sector_analytics_payload(tickers: tuple[str, ...], refresh_token: int = 0) -> dict[str, Any]:
    """Run sector analytics as cache-safe JSON-compatible data."""
    del refresh_token
    return scanner_service().build_sector_analytics(list(tickers)).model_dump(mode="json")


def build_sector_analytics(tickers: tuple[str, ...], refresh_token: int = 0) -> SectorAnalyticsResponse:
    """Run sector trend and intraday pattern analytics."""
    return SectorAnalyticsResponse.model_validate(build_sector_analytics_payload(tickers, refresh_token=refresh_token))


@st.cache_data(ttl=120, show_spinner=False)
def build_chart_history_payload(
    tickers: tuple[str, ...],
    chart_range: ChartRange,
    interval: ChartInterval,
    refresh_token: int = 0,
) -> dict[str, Any]:
    """Fetch OHLC chart history as cache-safe JSON-compatible data."""
    return market_data_service().build_chart_history(list(tickers), chart_range, interval).model_dump(mode="json")


def build_chart_history(
    tickers: tuple[str, ...],
    chart_range: ChartRange,
    interval: ChartInterval,
    refresh_token: int = 0,
) -> ChartHistoryResponse:
    """Fetch OHLC chart history for line and candlestick charts."""
    return ChartHistoryResponse.model_validate(
        build_chart_history_payload(tickers, chart_range, interval, refresh_token=refresh_token)
    )


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


def normalize_equity_metrics(metrics: list[Any] | tuple[Any, ...]) -> list[EquityMetrics]:
    """Return current-module EquityMetrics instances from cached or freshly built metrics."""
    normalized: list[EquityMetrics] = []
    for metric in metrics:
        if isinstance(metric, EquityMetrics):
            normalized.append(metric)
        elif hasattr(metric, "model_dump"):
            normalized.append(EquityMetrics.model_validate(metric.model_dump()))
        else:
            normalized.append(EquityMetrics.model_validate(metric))
    return normalized


def normalize_scanner_response(response: Any) -> ScannerResponse:
    """Return a current-module ScannerResponse from cached or freshly built scanner data."""
    if isinstance(response, ScannerResponse):
        return response
    if hasattr(response, "model_dump"):
        return ScannerResponse.model_validate(response.model_dump())
    return ScannerResponse.model_validate(response)


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


def load_streamlit_state(path: Path | None = None) -> dict[str, Any]:
    """Load persisted Streamlit app state, falling back quietly to defaults."""
    state_path = path or streamlit_state_path()
    try:
        data = json.loads(state_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def normalize_news_count(value: object) -> int:
    """Return a supported per-ticker news headline count."""
    try:
        count = int(value)
    except (TypeError, ValueError):
        return NEWS_EXPANDED_HEADLINE_COUNT
    return max(1, min(NEWS_MAX_HEADLINE_COUNT, count))


def normalize_chart_type(value: object) -> str:
    """Return a supported Streamlit chart type label."""
    candidate = str(value or "")
    return candidate if candidate in CHART_TYPE_OPTIONS else str(STREAMLIT_DEFAULT_SETTINGS["chart_type"])


def normalize_scanner_view(value: object) -> str:
    """Return a supported scanner presentation mode."""
    candidate = str(value or "")
    return candidate if candidate in SCANNER_VIEW_OPTIONS else str(STREAMLIT_DEFAULT_SETTINGS["scanner_view"])


def normalize_chart_range(value: object) -> ChartRange:
    """Return a supported chart range."""
    candidate = str(value or "")
    return candidate if candidate in CHART_INTERVALS_BY_RANGE else STREAMLIT_DEFAULT_SETTINGS["chart_range"]  # type: ignore[return-value]


def normalize_chart_interval(chart_range: ChartRange, value: object) -> ChartInterval:
    """Return a supported interval for the selected chart range."""
    candidate = str(value or "")
    options = CHART_INTERVALS_BY_RANGE[chart_range]
    return candidate if candidate in options else CHART_DEFAULT_INTERVAL_BY_RANGE[chart_range]  # type: ignore[return-value]


def normalize_score_history_range(value: object) -> ScoreHistoryRange:
    """Return a supported score-history range."""
    candidate = str(value or "")
    return candidate if candidate in SCORE_ANALYTICS_RANGES else SCORE_ANALYTICS_DEFAULT_RANGE


def normalize_score_metric(value: object) -> ScoreMetricName:
    """Return a supported score analytics metric selector."""
    candidate = str(value or "")
    return candidate if candidate in SCORE_ANALYTICS_METRICS else "both"  # type: ignore[return-value]


def normalize_score_chart_metric(value: object) -> str:
    """Return a supported score chart metric selector."""
    candidate = str(value or "")
    return candidate if candidate in SCORE_ANALYTICS_CHART_METRICS else "heat"


def normalize_score_movement(value: object) -> str:
    """Return a supported score movement filter."""
    candidate = str(value or "")
    return candidate if candidate in SCORE_ANALYTICS_MOVEMENTS else "all"


def normalize_score_sort(value: object) -> str:
    """Return a supported score analytics sort option."""
    candidate = str(value or "")
    return candidate if candidate in SCORE_ANALYTICS_SORTS else "watchlist"


def score_option_label(value: object) -> str:
    """Return a human label for score analytics controls."""
    return SCORE_OPTION_LABELS.get(str(value), str(value))


def normalize_level_weight(value: object) -> int | None:
    """Return a supported custom level weight."""
    try:
        number = round(float(value))
    except (TypeError, ValueError):
        return None
    return max(LEVEL_WEIGHT_MIN, min(LEVEL_WEIGHT_MAX, number))


def normalize_level_weights(value: object) -> dict[str, int]:
    """Normalize custom level weight overrides and drop stale/default values."""
    if not isinstance(value, dict):
        return {}
    defaults = level_type_weight_defaults()
    normalized: dict[str, int] = {}
    for label, raw_weight in value.items():
        if label not in defaults:
            continue
        weight = normalize_level_weight(raw_weight)
        if weight is None or weight == defaults[label]:
            continue
        normalized[str(label)] = weight
    return normalized


def active_streamlit_level_weights() -> dict[str, int]:
    """Return default Streamlit level weights with session overrides applied."""
    return {
        **level_type_weight_defaults(),
        **normalize_level_weights(st.session_state.get("level_weights", {})),
    }


def normalize_streamlit_settings(value: object) -> dict[str, Any]:
    """Normalize persisted Streamlit settings and backfill missing keys."""
    source = value if isinstance(value, dict) else {}
    default_view = str(source.get("default_view") or STREAMLIT_DEFAULT_SETTINGS["default_view"])
    chart_range = normalize_chart_range(source.get("chart_range"))
    return {
        "default_view": default_view if default_view in STREAMLIT_VIEWS else STREAMLIT_DEFAULT_SETTINGS["default_view"],
        "report_layout": normalize_report_layout(source.get("report_layout")),
        "level_filter": normalize_level_filter(source.get("level_filter")),
        "level_weights": normalize_level_weights(source.get("level_weights")),
        "scanner_view": normalize_scanner_view(source.get("scanner_view")),
        "chart_type": normalize_chart_type(source.get("chart_type")),
        "chart_range": chart_range,
        "chart_interval": normalize_chart_interval(chart_range, source.get("chart_interval")),
        "auto_load": bool(source.get("auto_load", STREAMLIT_DEFAULT_SETTINGS["auto_load"])),
        "auto_refresh": bool(source.get("auto_refresh", STREAMLIT_DEFAULT_SETTINGS["auto_refresh"])),
        "news_per_ticker": normalize_news_count(source.get("news_per_ticker")),
    }


def load_streamlit_settings(path: Path | None = None) -> dict[str, Any]:
    """Load persisted Streamlit settings while supporting old watchlist-only files."""
    return normalize_streamlit_settings(load_streamlit_state(path).get("settings", {}))


def save_streamlit_state(
    tickers: list[str] | None = None,
    settings: dict[str, Any] | None = None,
    path: Path | None = None,
) -> None:
    """Persist Streamlit watchlist and settings to a small server-side JSON file."""
    state_path = path or streamlit_state_path()
    existing = load_streamlit_state(state_path)
    watchlist_source = tickers if tickers is not None else existing.get("watchlist", [])
    settings_source = settings if settings is not None else existing.get("settings", {})
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "watchlist": normalize_ticker_list(watchlist_source),
        "settings": normalize_streamlit_settings(settings_source),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_streamlit_watchlist(path: Path | None = None) -> list[str]:
    """Load a persisted Streamlit watchlist, falling back quietly to empty."""
    data = load_streamlit_state(path)
    if not data:
        return []
    return normalize_ticker_list(data.get("watchlist", []))


def save_streamlit_watchlist(tickers: list[str], path: Path | None = None) -> None:
    """Persist the Streamlit watchlist to a small server-side JSON file."""
    save_streamlit_state(tickers=tickers, path=path)


def save_streamlit_settings(settings: dict[str, Any], path: Path | None = None) -> None:
    """Persist Streamlit settings while preserving the saved watchlist."""
    save_streamlit_state(settings=settings, path=path)


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
    theme_type = getattr(getattr(st, "context", None), "theme", None)
    theme_type = getattr(theme_type, "type", None)
    return "dark" if theme_type == "dark" else "light"


def render_html_component(html: str, *, height: int, scrolling: bool = False) -> None:
    """Render iframe-backed HTML using Streamlit's stable components API."""
    components.html(html, height=height, scrolling=scrolling)


def render_streamlit_theme_bridge() -> None:
    """Mirror Streamlit's actual rendered theme onto a page marker for CSS."""
    render_html_component(
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


def remember_score_history_warnings(warnings: list[str]) -> None:
    """Store non-fatal score-history warnings for the analytics pane."""
    if not warnings:
        return
    existing = st.session_state.get("score_history_warnings", [])
    if not isinstance(existing, list):
        existing = []
    st.session_state.score_history_warnings = list(dict.fromkeys([*existing, *warnings]))


def record_streamlit_score_history(
    report: GenerateResponse | None = None,
    scanner: ScannerResponse | None = None,
) -> list[str]:
    """Persist score history from Streamlit refreshes without failing the UI."""
    warnings: list[str] = []
    if report is not None:
        try:
            warnings.extend(score_history_service().record_level_scores(report.metrics))
        except Exception as exc:
            warnings.append(f"Score history could not save level scores: {exc}")
    if scanner is not None:
        try:
            warnings.extend(score_history_service().record_setup_scores(scanner.setup_rows))
        except Exception as exc:
            warnings.append(f"Score history could not save setup scores: {exc}")
    remember_score_history_warnings(warnings)
    return warnings


def render_app_chrome() -> str:
    """Render app-level brand/navigation and return the active view."""
    ensure_streamlit_settings()

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
	            --signal-info-bg: #dbeafe;
	            --signal-info-fg: #1d4ed8;
	            --action-primary-bg: #ccfbf1;
	            --action-primary-border: #5eead4;
	            --action-primary-text: #12312f;
	            --action-primary-shadow: 0 10px 20px rgba(15, 118, 110, 0.14);
	            --emphasis-bg: #ccfbf1;
	            --emphasis-border: #99f6e4;
	            --emphasis-text: #12312f;
	            --emphasis-muted: #0f766e;
	            --sidebar-toggle-bg: #ccfbf1;
	            --sidebar-toggle-border: #5eead4;
	            --sidebar-toggle-text: #12312f;
	            --sidebar-toggle-shadow: 0 8px 18px rgba(15, 118, 110, 0.16);
	            --major-market-bg: #f0fdfa;
	            --major-market-border: #99f6e4;
	            --major-market-text: #12312f;
	            --major-market-tile-border: rgba(15, 118, 110, 0.18);
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
            background: var(--action-primary-bg);
            border: 1px solid var(--action-primary-border);
            box-shadow: var(--action-primary-shadow);
            color: var(--action-primary-text);
          }
          div[data-testid="stButton"] button[kind="primary"] *,
          div[data-testid="stDownloadButton"] button[kind="primary"] * {
            color: var(--action-primary-text) !important;
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
            background: var(--emphasis-bg);
            border-bottom: 1px solid var(--emphasis-border);
            color: var(--emphasis-text);
            display: flex;
            gap: 0.6rem;
            justify-content: space-between;
            padding: 0.95rem 1.1rem;
          }
          .metric-card-header h3 {
            color: var(--emphasis-text);
            letter-spacing: 0.06em;
            margin: 0;
          }
          .drag-glyph {
            color: var(--emphasis-muted);
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
            background: var(--major-market-bg);
            border: 1px solid var(--major-market-border);
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
            border-color: var(--major-market-tile-border);
            color: var(--major-market-text) !important;
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
            background: var(--emphasis-bg);
            border: 1px solid var(--emphasis-border);
            border-left: 4px solid #0f766e;
            border-radius: 0.45rem;
            color: var(--emphasis-text) !important;
            font-size: 0.82rem;
            font-weight: 900;
            letter-spacing: 0.02em;
            margin: 0.75rem 0 0.4rem;
            padding: 0.55rem 0.7rem;
            text-transform: uppercase;
          }
          .streamlit-scanner-render {
            display: grid;
            gap: 0.75rem;
            min-width: 0;
          }
          .streamlit-scanner-table-panel,
          .streamlit-scanner-card-panel {
            min-width: 0;
          }
          .streamlit-scanner-card-panel {
            display: none;
          }
          .streamlit-scanner-render.view-cards .streamlit-scanner-table-panel {
            display: none;
          }
          .streamlit-scanner-render.view-cards .streamlit-scanner-card-panel {
            display: block;
          }
          .streamlit-scanner-card {
            background: var(--surface-bg, #ffffff);
            border: 1px solid var(--border-soft, #dbe3ef);
            border-left: 4px solid var(--border-soft, #dbe3ef);
            border-radius: 0.5rem;
            display: grid;
            gap: 0.65rem;
            min-width: 0;
            padding: 0.75rem;
          }
          .streamlit-scanner-card.tone-strong { border-left-color: var(--signal-strong-fg, #166534); }
          .streamlit-scanner-card.tone-good { border-left-color: var(--signal-good-fg, #0f766e); }
          .streamlit-scanner-card.tone-watch { border-left-color: var(--signal-watch-fg, #92400e); }
          .streamlit-scanner-card.tone-danger { border-left-color: var(--signal-danger-fg, #991b1b); }
          .streamlit-scanner-card-list {
            display: grid;
            gap: 0.65rem;
          }
          .streamlit-scanner-card-header {
            align-items: center;
            display: flex;
            gap: 0.65rem;
            justify-content: space-between;
          }
          .streamlit-scanner-card-header h3 {
            color: var(--text, #111827);
            font-size: 1.1rem;
            letter-spacing: 0.04em;
            margin: 0;
          }
          .streamlit-scanner-card-header span {
            color: var(--text-muted, #64748b);
            font-size: 0.9rem;
            font-weight: 700;
          }
          .streamlit-scanner-card-primary,
          .streamlit-scanner-card-zones,
          .streamlit-scanner-card-secondary {
            display: grid;
            gap: 0.5rem;
            grid-template-columns: repeat(4, minmax(0, 1fr));
          }
          .streamlit-scanner-card-secondary {
            grid-template-columns: repeat(auto-fit, minmax(6rem, 1fr));
          }
          .streamlit-scanner-card-metric {
            background: var(--surface-soft, #f8fafc);
            border: 1px solid var(--border-soft, #dbe3ef);
            border-radius: 0.5rem;
            min-width: 0;
            padding: 0.45rem 0.5rem;
          }
          .streamlit-scanner-card-metric.wide {
            grid-column: span 2;
          }
          .streamlit-scanner-card-metric > span {
            color: var(--text-muted, #64748b);
            display: block;
            font-size: 0.72rem;
            font-weight: 850;
            letter-spacing: 0.04em;
            margin-bottom: 0.25rem;
            text-transform: uppercase;
          }
          .streamlit-scanner-card-metric > div {
            color: var(--text, #111827);
            font-size: 0.92rem;
            min-width: 0;
            overflow-wrap: anywhere;
          }
          .streamlit-scanner-card-warning {
            background: var(--warning-bg, #fef3c7);
            border-radius: 0.5rem;
            color: var(--warning-text, #92400e) !important;
            font-size: 0.86rem;
            margin: 0;
            padding: 0.5rem 0.6rem;
          }
          .streamlit-scanner-card .streamlit-scanner-card-warning {
            color: var(--warning-text, #92400e) !important;
          }
          .streamlit-scanner-table-wrap {
            border: 1px solid var(--border-soft, #dbe3ef);
            border-radius: 0.5rem;
            box-shadow: inset -18px 0 18px -24px rgba(15, 23, 42, 0.5);
            margin: 0.25rem 0 1rem;
            max-width: 100%;
            overflow-x: auto;
            overflow-y: hidden;
            overscroll-behavior-x: contain;
            scrollbar-color: var(--border-soft, #dbe3ef) transparent;
            scrollbar-width: thin;
            width: 100%;
            -webkit-overflow-scrolling: touch;
          }
          .streamlit-scanner-table {
            --streamlit-scanner-score-col: 6rem;
            --streamlit-scanner-ticker-col: 5.8rem;
            background: var(--surface-bg, #ffffff);
            border-collapse: separate;
            border-spacing: 0;
            min-width: 1280px;
            width: 100%;
          }
          .streamlit-scanner-table th {
            background: var(--surface-soft, #f8fafc);
            border-bottom: 1px solid var(--border-soft, #dbe3ef);
            color: var(--text-muted, #64748b) !important;
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.03em;
            padding: 0.5rem 0.56rem;
            position: sticky;
            text-align: left;
            text-transform: uppercase;
            top: 0;
            white-space: nowrap;
            z-index: 1;
          }
          .streamlit-scanner-table td {
            border-bottom: 1px solid var(--border-soft, #dbe3ef);
            color: var(--text, #111827) !important;
            font-size: 0.9rem;
            padding: 0.5rem 0.56rem;
            vertical-align: middle;
            white-space: nowrap;
          }
          .streamlit-scanner-table th.streamlit-scanner-cell-score,
          .streamlit-scanner-table td.streamlit-scanner-cell-score {
            left: 0;
            min-width: var(--streamlit-scanner-score-col);
            position: sticky;
            width: var(--streamlit-scanner-score-col);
            z-index: 3;
          }
          .streamlit-scanner-table th.streamlit-scanner-cell-ticker,
          .streamlit-scanner-table td.streamlit-scanner-cell-ticker {
            left: var(--streamlit-scanner-score-col);
            min-width: var(--streamlit-scanner-ticker-col);
            position: sticky;
            width: var(--streamlit-scanner-ticker-col);
            z-index: 3;
          }
          .streamlit-scanner-table th.streamlit-scanner-cell-score,
          .streamlit-scanner-table th.streamlit-scanner-cell-ticker {
            z-index: 4;
          }
          .streamlit-scanner-table td.streamlit-scanner-cell-score,
          .streamlit-scanner-table td.streamlit-scanner-cell-ticker {
            background: var(--surface-bg, #ffffff);
            box-shadow: 1px 0 0 var(--border-soft, #dbe3ef);
          }
          .streamlit-scanner-table th.align-center,
          .streamlit-scanner-table td.align-center {
            text-align: center;
          }
          .streamlit-scanner-table th.align-right,
          .streamlit-scanner-table td.align-right {
            text-align: right;
          }
          .streamlit-scanner-table td.wrap {
            line-height: 1.35;
            max-width: 13rem;
            min-width: 9rem;
            white-space: normal;
          }
          .streamlit-scanner-table tr:last-child td {
            border-bottom: 0;
          }
          .streamlit-scanner-table tbody tr {
            position: relative;
          }
          .streamlit-scanner-table tbody tr[class*="tone-"] td:first-child {
            border-left: 4px solid transparent;
            padding-left: 0.31rem;
          }
          .streamlit-scanner-table tbody tr.tone-strong td:first-child {
            border-left-color: var(--signal-strong-fg, #166534);
          }
          .streamlit-scanner-table tbody tr.tone-good td:first-child {
            border-left-color: var(--signal-good-fg, #0f766e);
          }
          .streamlit-scanner-table tbody tr.tone-watch td:first-child {
            border-left-color: var(--signal-watch-fg, #92400e);
          }
          .streamlit-scanner-table tbody tr.tone-danger td:first-child {
            border-left-color: var(--signal-danger-fg, #991b1b);
          }
          .streamlit-scanner-pill {
            align-items: center;
            border-radius: 999px;
            display: inline-flex;
            font-size: 0.86rem;
            font-weight: 800;
            gap: 0.35rem;
            justify-content: center;
            line-height: 1;
            min-height: 1.65rem;
            min-width: 2.8rem;
            padding: 0.3rem 0.55rem;
          }
          .streamlit-scanner-pill.tone-strong {
            background: var(--signal-strong-bg, #dcfce7);
            color: var(--signal-strong-fg, #166534) !important;
          }
          .streamlit-scanner-pill.tone-good {
            background: var(--signal-good-bg, #ccfbf1);
            color: var(--signal-good-fg, #0f766e) !important;
          }
          .streamlit-scanner-pill.tone-watch {
            background: var(--signal-watch-bg, #fef3c7);
            color: var(--signal-watch-fg, #92400e) !important;
          }
          .streamlit-scanner-pill.tone-danger {
            background: var(--signal-danger-bg, #fee2e2);
            color: var(--signal-danger-fg, #991b1b) !important;
          }
          .streamlit-scanner-pill.tone-neutral {
            background: var(--signal-neutral-bg, #f1f5f9);
            color: var(--signal-neutral-fg, #64748b) !important;
          }
          .streamlit-scanner-pill.tone-info {
            background: var(--signal-info-bg, #dbeafe);
            color: var(--signal-info-fg, #1d4ed8) !important;
          }
          .streamlit-scanner-symbol {
            min-width: 1.8rem;
            padding-left: 0.38rem;
            padding-right: 0.38rem;
          }
          .streamlit-scanner-score {
            --score-fill: #e2e8f0;
            align-items: center;
            background: var(--surface-soft, #f8fafc);
            border: 1px solid var(--border-soft, #dbe3ef);
            border-radius: 999px;
            color: var(--text-muted, #334155) !important;
            display: inline-flex;
            font-size: 0.9rem;
            font-weight: 850;
            justify-content: center;
            line-height: 1;
            min-height: 1.85rem;
            min-width: 4.8rem;
            overflow: hidden;
            padding: 0.3rem 0.65rem;
            position: relative;
          }
          .streamlit-scanner-score::before {
            background: var(--score-fill);
            content: "";
            inset: 0 auto 0 0;
            opacity: 0.78;
            position: absolute;
            width: var(--score-width, 0%);
          }
          .streamlit-scanner-score > span {
            position: relative;
            z-index: 1;
          }
          .streamlit-scanner-score.tone-strong { --score-fill: var(--signal-strong-bg, #dcfce7); border-color: var(--signal-strong-fg, #166534); color: var(--signal-strong-fg, #166534) !important; }
          .streamlit-scanner-score.tone-good { --score-fill: var(--signal-good-bg, #ccfbf1); border-color: var(--signal-good-fg, #0f766e); color: var(--signal-good-fg, #0f766e) !important; }
          .streamlit-scanner-score.tone-watch { --score-fill: var(--signal-watch-bg, #fef3c7); border-color: var(--signal-watch-fg, #92400e); color: var(--signal-watch-fg, #92400e) !important; }
          .streamlit-scanner-score.tone-danger { --score-fill: var(--signal-danger-bg, #fee2e2); border-color: var(--signal-danger-fg, #991b1b); color: var(--signal-danger-fg, #991b1b) !important; }
          .streamlit-scanner-score.tone-neutral { --score-fill: var(--signal-neutral-bg, #f1f5f9); border-color: var(--signal-neutral-fg, #64748b); color: var(--signal-neutral-fg, #64748b) !important; }
          .streamlit-scanner-text {
            font-weight: 700;
          }
          .streamlit-scanner-ticker {
            font-size: 0.95rem;
            font-weight: 800;
            letter-spacing: 0.03em;
          }
          .streamlit-scanner-metric-combo {
            align-items: center;
            display: inline-flex;
            gap: 0.3rem;
            justify-content: center;
          }
          .streamlit-scanner-metric-combo > span:first-child {
            font-variant-numeric: tabular-nums;
          }
          .streamlit-scanner-text.tone-strong,
          .streamlit-scanner-text.tone-good {
            color: var(--signal-good-fg, #0f766e) !important;
          }
          .streamlit-scanner-text.tone-watch {
            color: var(--signal-watch-fg, #92400e) !important;
          }
          .streamlit-scanner-text.tone-danger {
            color: var(--signal-danger-fg, #991b1b) !important;
          }
          .streamlit-scanner-text.tone-info {
            color: var(--signal-info-fg, #1d4ed8) !important;
          }
          .streamlit-scanner-muted,
          .streamlit-scanner-reason {
            color: var(--text-muted, #64748b) !important;
          }
          .streamlit-scanner-reason {
            display: block;
            font-size: 0.8rem;
            font-weight: 700;
            margin-top: 0.2rem;
            max-width: 22rem;
            white-space: normal;
          }
          .streamlit-scanner-zone {
            color: var(--text, #111827) !important;
            font-size: 0.92rem;
            font-weight: 750;
          }
          .streamlit-scanner-warning-row td {
            background: var(--warning-bg, #fef3c7);
            color: var(--warning-text, #92400e) !important;
            font-weight: 800;
            white-space: normal;
          }
          @media (max-width: 760px) {
            .streamlit-scanner-table {
              --streamlit-scanner-score-col: 5.4rem;
              --streamlit-scanner-ticker-col: 5.2rem;
              min-width: 1120px;
            }
            .streamlit-scanner-table th {
              font-size: 0.66rem;
              padding: 0.38rem 0.44rem;
            }
            .streamlit-scanner-table td {
              font-size: 0.82rem;
              padding: 0.38rem 0.44rem;
            }
            .streamlit-scanner-table tbody tr[class*="tone-"] td:first-child {
              padding-left: 0.19rem;
            }
            .streamlit-scanner-score {
              font-size: 0.8rem;
              min-height: 1.62rem;
              min-width: 4.25rem;
              padding: 0.25rem 0.5rem;
            }
            .streamlit-scanner-pill {
              font-size: 0.78rem;
              min-height: 1.45rem;
              min-width: 2.25rem;
              padding: 0.25rem 0.44rem;
            }
            .streamlit-scanner-zone,
            .streamlit-scanner-ticker {
              font-size: 0.84rem;
            }
            .streamlit-scanner-card-primary,
            .streamlit-scanner-card-zones {
              grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .streamlit-scanner-card-secondary {
              grid-template-columns: repeat(3, minmax(0, 1fr));
            }
          }
          @media (max-width: 460px) {
            .streamlit-scanner-card-primary,
            .streamlit-scanner-card-zones,
            .streamlit-scanner-card-secondary {
              grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .streamlit-scanner-card-metric.wide {
              grid-column: 1 / -1;
            }
          }
          .streamlit-scanner-data-notes {
            background: var(--surface-soft, #f8fafc);
            border: 1px solid var(--border-soft, #dbe3ef);
            border-radius: 0.5rem;
            color: var(--text-muted, #64748b) !important;
            margin-top: 0.75rem;
            padding: 0.65rem 0.8rem;
          }
          .streamlit-scanner-data-notes summary {
            cursor: pointer;
            font-size: 0.84rem;
            font-weight: 900;
          }
          .streamlit-scanner-data-notes ul {
            margin: 0.5rem 0 0;
            padding-left: 1.15rem;
          }
          .streamlit-scanner-data-notes li {
            margin-bottom: 0.25rem;
            white-space: normal;
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
            background: var(--sidebar-toggle-bg, #ccfbf1) !important;
            border: 2px solid var(--sidebar-toggle-border, #5eead4) !important;
            border-radius: 0.7rem !important;
            box-shadow: var(--sidebar-toggle-shadow, 0 8px 18px rgba(15, 118, 110, 0.16)) !important;
            color: var(--sidebar-toggle-text, #12312f) !important;
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
            background: var(--brand-soft, #99f6e4) !important;
            border-color: var(--sidebar-toggle-border, #5eead4) !important;
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
            color: var(--sidebar-toggle-text, #12312f) !important;
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
            color: var(--sidebar-toggle-text, #12312f) !important;
            fill: var(--sidebar-toggle-text, #12312f) !important;
            stroke: var(--sidebar-toggle-text, #12312f) !important;
            -webkit-text-fill-color: var(--sidebar-toggle-text, #12312f) !important;
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
            background: var(--action-primary-bg, #ccfbf1) !important;
            border-color: var(--action-primary-border, #5eead4) !important;
            color: var(--action-primary-text, #12312f) !important;
            box-shadow: var(--action-primary-shadow, 0 10px 20px rgba(15, 118, 110, 0.14)) !important;
          }
          [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"]:hover {
            background: var(--brand-soft, #99f6e4) !important;
            border-color: var(--action-primary-border, #5eead4) !important;
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
          div[data-testid="stHorizontalBlock"]:has(.streamlit-brand-ribbon-marker) {
            align-items: center;
            background: rgba(255, 255, 255, 0.96);
            border-bottom: 1px solid #d5ddd9;
            margin: -0.75rem 0 0;
            min-height: 4.25rem;
            padding: 0 0.75rem;
            position: sticky;
            top: 0;
            z-index: 30;
          }
          div[data-testid="stHorizontalBlock"]:has(.streamlit-brand-ribbon-marker) [data-testid="stButton"] button {
            align-items: center;
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            border-radius: 0.55rem;
            box-shadow: none;
            color: #12312f;
            display: inline-flex;
            font-size: 1rem;
            height: 2.65rem;
            justify-content: center;
            min-height: 2.65rem;
            padding: 0;
          }
          .streamlit-settings-panel-marker {
            display: none !important;
          }
          div[data-testid="stVerticalBlock"]:has(.streamlit-settings-panel-marker):not(:has(div[data-testid="stVerticalBlock"] .streamlit-settings-panel-marker)) {
            background: #ffffff;
            border-left: 1px solid #d5ddd9;
            box-shadow: -18px 0 48px rgba(17, 24, 39, 0.18);
            gap: 0.85rem;
            height: calc(100vh - 4.25rem);
            max-width: calc(100vw - 2rem);
            overflow-y: auto;
            padding: 1rem;
            position: fixed;
            right: 0;
            top: 4.25rem;
            width: 24rem;
            z-index: 100002;
          }
          div[data-testid="stVerticalBlock"]:has(.streamlit-settings-panel-marker):not(:has(div[data-testid="stVerticalBlock"] .streamlit-settings-panel-marker)) [data-testid="stButton"] button {
            min-height: 2.25rem;
            padding: 0.35rem 0.65rem;
          }
          .streamlit-settings-title {
            color: #111827;
            font-size: 1.35rem;
            font-weight: 900;
            margin: 0;
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
            background: var(--emphasis-bg);
            color: var(--emphasis-text);
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
            background: var(--emphasis-bg);
            color: var(--emphasis-text);
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
          .streamlit-score-analytics-header {
            align-items: center;
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            justify-content: space-between;
            margin-bottom: 0.85rem;
          }
          .streamlit-score-analytics-header h2 {
            color: #111827;
            margin: 0;
          }
          .streamlit-score-summary-strip {
            display: grid;
            gap: 0.7rem;
            grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
            margin: 0.7rem 0 0.9rem;
          }
          .streamlit-score-summary-tile,
          .streamlit-score-card,
          .streamlit-score-sparkline-card {
            background: #f8fafc;
            border: 1px solid #dbe3ef;
            border-radius: 0.5rem;
          }
          .streamlit-score-summary-tile {
            padding: 0.65rem 0.75rem;
          }
          .streamlit-score-line-panel {
            background: #f8fafc;
            border: 1px solid #dbe3ef;
            border-radius: 0.5rem;
            display: grid;
            gap: 0.55rem;
            margin: 0.7rem 0 0.9rem;
            min-width: 0;
            padding: 0.75rem;
          }
          .streamlit-score-line-header {
            align-items: center;
            display: flex;
            gap: 0.75rem;
            justify-content: space-between;
          }
          .streamlit-score-line-header h4 {
            color: #0f172a;
            letter-spacing: 0.04em;
            margin: 0;
          }
          .streamlit-score-line-header span {
            color: #64748b !important;
            font-size: 0.78rem;
            font-weight: 900;
            text-transform: uppercase;
          }
          .streamlit-score-line-chart {
            display: block;
            height: auto;
            max-height: 230px;
            width: 100%;
          }
          .streamlit-score-line-grid line {
            stroke: #e2e8f0;
            stroke-width: 1;
          }
          .streamlit-score-line-grid text {
            fill: #64748b;
            font-size: 11px;
            font-weight: 800;
          }
          .streamlit-score-line-x-axis line {
            stroke: #cbd5e1;
            stroke-width: 1;
          }
          .streamlit-score-line-x-axis text {
            fill: #64748b;
            font-size: 10px;
            font-weight: 800;
          }
          .streamlit-score-line-series polyline {
            fill: none;
            stroke: var(--score-series-color);
            stroke-linecap: round;
            stroke-linejoin: round;
            stroke-width: 3;
          }
          .streamlit-score-line-series circle {
            fill: var(--score-series-color);
            stroke: #ffffff;
            stroke-width: 2;
          }
          .streamlit-score-line-end-label {
            fill: var(--score-series-color);
            font-size: 10px;
            font-weight: 900;
          }
          .streamlit-score-line-legend {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem 0.65rem;
          }
          .streamlit-score-line-legend-item {
            align-items: center;
            color: #334155 !important;
            display: inline-flex;
            font-size: 0.76rem;
            font-weight: 900;
            gap: 0.3rem;
          }
          .streamlit-score-line-legend-item i {
            background: var(--score-series-color);
            border-radius: 999px;
            display: inline-block;
            height: 0.5rem;
            width: 0.5rem;
          }
          .streamlit-score-line-empty {
            background: repeating-linear-gradient(90deg, #e2e8f0 0 7px, transparent 7px 14px);
            border-radius: 0.4rem;
            height: 96px;
            opacity: 0.7;
          }
          .streamlit-score-summary-tile span,
          .streamlit-score-summary-tile small,
          .streamlit-score-card header span,
          .streamlit-score-latest span,
          .streamlit-score-latest small,
          .streamlit-score-sparkline-card span,
          .streamlit-score-heat-strip-card span,
          .streamlit-score-thermometer span {
            color: #64748b !important;
          }
          .streamlit-score-summary-tile span,
          .streamlit-score-latest span,
          .streamlit-score-sparkline-card span,
          .streamlit-score-heat-strip-card span,
          .streamlit-score-thermometer span {
            display: block;
            font-size: 0.68rem;
            font-weight: 900;
            letter-spacing: 0.05em;
            text-transform: uppercase;
          }
          .streamlit-score-summary-tile strong {
            color: #0f172a;
            display: block;
            font-size: 1.35rem;
            line-height: 1.15;
            margin: 0.12rem 0;
          }
          .streamlit-score-trend-grid {
            display: grid;
            gap: 0.75rem;
            grid-template-columns: repeat(auto-fit, minmax(min(360px, 100%), 1fr));
          }
          .streamlit-score-card {
            border-left: 4px solid #94a3b8;
            display: grid;
            gap: 0.7rem;
            min-width: 0;
            padding: 0.8rem;
          }
          .streamlit-score-card.movement-improving { border-left-color: #059669; }
          .streamlit-score-card.movement-declining { border-left-color: #dc2626; }
          .streamlit-score-card header {
            align-items: center;
            display: flex;
            gap: 0.6rem;
            justify-content: space-between;
          }
          .streamlit-score-card h4 {
            color: #0f172a;
            letter-spacing: 0.06em;
            margin: 0;
          }
          .streamlit-score-movement-row {
            align-items: center;
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
          }
          .streamlit-score-movement {
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 900;
            padding: 0.25rem 0.5rem;
            white-space: nowrap;
          }
          .streamlit-score-movement.improving {
            background: #dcfce7;
            color: #166534 !important;
          }
          .streamlit-score-movement.declining {
            background: #fee2e2;
            color: #991b1b !important;
          }
          .streamlit-score-movement.flat {
            background: #e2e8f0;
            color: #475569 !important;
          }
          .streamlit-score-latest-grid,
          .streamlit-score-sparkline-grid {
            display: grid;
            gap: 0.55rem;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
          }
          .streamlit-score-latest {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 0.5rem;
            padding: 0.55rem 0.65rem;
          }
          .streamlit-score-latest strong {
            color: #0f172a;
            display: block;
            font-size: 0.98rem;
            line-height: 1.3;
            margin: 0.12rem 0;
          }
          .streamlit-score-thermometer {
            align-items: center;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 0.5rem;
            display: grid;
            gap: 0.6rem;
            grid-template-columns: minmax(72px, auto) 1fr auto;
            padding: 0.55rem 0.65rem;
          }
          .streamlit-score-thermometer strong {
            color: #0f172a;
            display: block;
            font-size: 1rem;
            line-height: 1.1;
          }
          .streamlit-score-thermometer small {
            color: var(--heat-color, #64748b) !important;
            font-size: 0.78rem;
            font-weight: 900;
            text-transform: uppercase;
          }
          .streamlit-score-thermometer-track {
            background: #e2e8f0;
            border-radius: 999px;
            height: 0.75rem;
            overflow: hidden;
          }
          .streamlit-score-thermometer-track span {
            background: var(--heat-color, #94a3b8);
            border-radius: inherit;
            display: block;
            height: 100%;
            min-width: 4px;
          }
          .streamlit-score-heat-strip-card {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 0.5rem;
            display: grid;
            gap: 0.45rem;
            padding: 0.55rem 0.65rem;
          }
          .streamlit-score-heat-strip {
            display: grid;
            gap: 3px;
            grid-template-columns: repeat(auto-fit, minmax(8px, 1fr));
            min-height: 1.1rem;
          }
          .streamlit-score-heat-strip i {
            background: var(--heat-color, #cbd5e1);
            border-radius: 0.25rem;
            min-height: 1.1rem;
          }
          .streamlit-score-heat-strip i.empty {
            background: transparent;
            border: 1px dashed #cbd5e1;
          }
          .streamlit-score-heat-strip i.status-current {
            box-shadow: inset 0 0 0 2px rgba(15, 23, 42, 0.22);
          }
          .streamlit-score-heat-strip i.status-future {
            opacity: 0.5;
          }
          .streamlit-score-heat-strip-axis {
            color: #64748b !important;
            display: flex;
            font-size: 0.68rem;
            font-weight: 800;
            justify-content: space-between;
            line-height: 1.2;
          }
          .streamlit-score-heat-strip.empty {
            background: repeating-linear-gradient(90deg, #e2e8f0 0 4px, transparent 4px 9px);
            border-radius: 0.4rem;
            opacity: 0.7;
          }
          .streamlit-heat-cold { --heat-color: #2563eb; }
          .streamlit-heat-cool { --heat-color: #0f766e; }
          .streamlit-heat-warm { --heat-color: #ca8a04; }
          .streamlit-heat-hot { --heat-color: #dc2626; }
          .streamlit-heat-none { --heat-color: #94a3b8; }
          .streamlit-score-delta.positive { color: #059669 !important; }
          .streamlit-score-delta.negative { color: #dc2626 !important; }
          .streamlit-score-delta.neutral { color: #64748b !important; }
          .streamlit-score-sparkline-card {
            padding: 0.5rem 0.55rem;
          }
          .streamlit-score-sparkline-title {
            align-items: center;
            display: flex;
            gap: 0.5rem;
            justify-content: space-between;
          }
          .streamlit-score-sparkline-title small,
          .streamlit-score-sparkline-caption {
            color: #64748b !important;
            font-size: 0.68rem;
            font-weight: 900;
          }
          .streamlit-score-sparkline,
          .streamlit-score-sparkline-empty {
            display: block;
            height: 72px;
            margin-top: 0.35rem;
            width: 100%;
          }
          .streamlit-score-sparkline {
            overflow: visible;
          }
          .streamlit-score-sparkline polyline {
            fill: none;
            stroke: #0f766e;
            stroke-linecap: round;
            stroke-linejoin: round;
            stroke-width: 3;
          }
          .streamlit-score-sparkline circle {
            fill: #0f766e;
            stroke: #ffffff;
            stroke-width: 2;
          }
          .streamlit-score-sparkline-grid-line {
            stroke: #dbe3ef;
            stroke-width: 1;
          }
          .streamlit-score-sparkline-scale {
            fill: #64748b;
            font-size: 9px;
            font-weight: 900;
          }
          .streamlit-score-sparkline-empty {
            background: repeating-linear-gradient(90deg, #e2e8f0 0 7px, transparent 7px 14px);
            border-radius: 0.4rem;
            opacity: 0.7;
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
            background: var(--emphasis-bg);
            color: var(--emphasis-text);
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
	              --signal-info-bg: #172554;
	              --signal-info-fg: #bfdbfe;
	              --action-primary-bg: #0b3b37;
	              --action-primary-border: #0f766e;
	              --action-primary-text: #ccfbf1;
	              --action-primary-shadow: 0 10px 20px rgba(45, 212, 191, 0.12);
	              --emphasis-bg: #0b2f2d;
	              --emphasis-border: #0f766e;
	              --emphasis-text: #ccfbf1;
	              --emphasis-muted: #99f6e4;
	              --sidebar-toggle-bg: #0b3b37;
	              --sidebar-toggle-border: #0f766e;
	              --sidebar-toggle-text: #ccfbf1;
	              --sidebar-toggle-shadow: 0 8px 18px rgba(0, 0, 0, 0.26);
	              --major-market-bg: #080d12;
	              --major-market-border: #263241;
	              --major-market-text: #f8fafc;
	              --major-market-tile-border: rgba(148, 163, 184, 0.26);
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
	              background: var(--major-market-bg) !important;
	              border: 1px solid var(--major-market-border) !important;
	            }
	            .streamlit-market-grid.major .streamlit-market-tile {
	              background: transparent !important;
	              border-color: var(--major-market-tile-border) !important;
	              color: var(--major-market-text) !important;
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
	              background: var(--emphasis-bg) !important;
	              border-color: var(--emphasis-border) !important;
	              color: var(--emphasis-text) !important;
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
              --signal-info-bg: #dbeafe;
              --signal-info-fg: #1d4ed8;
              --action-primary-bg: #ccfbf1;
              --action-primary-border: #5eead4;
              --action-primary-text: #12312f;
              --action-primary-shadow: 0 10px 20px rgba(15, 118, 110, 0.14);
              --emphasis-bg: #ccfbf1;
              --emphasis-border: #99f6e4;
              --emphasis-text: #12312f;
              --emphasis-muted: #0f766e;
              --nav-active-bg: linear-gradient(135deg, #ccfbf1, #f0fdfa);
              --nav-active-border: #99f6e4;
              --nav-active-text: #12312f;
              --sidebar-toggle-bg: #ccfbf1;
              --sidebar-toggle-border: #5eead4;
              --sidebar-toggle-text: #12312f;
              --sidebar-toggle-shadow: 0 8px 18px rgba(15, 118, 110, 0.16);
              --major-market-bg: #f0fdfa;
              --major-market-border: #99f6e4;
              --major-market-text: #12312f;
              --major-market-tile-border: rgba(15, 118, 110, 0.18);
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
              --signal-info-bg: #172554;
              --signal-info-fg: #bfdbfe;
              --action-primary-bg: #0b3b37;
              --action-primary-border: #0f766e;
              --action-primary-text: #ccfbf1;
              --action-primary-shadow: 0 10px 20px rgba(45, 212, 191, 0.12);
              --emphasis-bg: #0b2f2d;
              --emphasis-border: #0f766e;
              --emphasis-text: #ccfbf1;
              --emphasis-muted: #99f6e4;
              --nav-active-bg: linear-gradient(135deg, #0b2f2d, #0f766e);
              --nav-active-border: rgba(45, 212, 191, 0.58);
              --nav-active-text: #ffffff;
              --sidebar-toggle-bg: #0b3b37;
              --sidebar-toggle-border: #0f766e;
              --sidebar-toggle-text: #ccfbf1;
              --sidebar-toggle-shadow: 0 8px 18px rgba(0, 0, 0, 0.26);
              --major-market-bg: #080d12;
              --major-market-border: #263241;
              --major-market-text: #f8fafc;
              --major-market-tile-border: rgba(148, 163, 184, 0.26);
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
            body:has(.streamlit-theme-marker) div[data-testid="stHorizontalBlock"]:has(.streamlit-brand-ribbon-marker),
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
            body:has(.streamlit-theme-marker) div[data-testid="stVerticalBlock"]:has(.streamlit-settings-panel-marker):not(:has(div[data-testid="stVerticalBlock"] .streamlit-settings-panel-marker)),
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
            body:has(.streamlit-theme-marker) .streamlit-settings-title,
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
            body:has(.streamlit-theme-marker) div[data-testid="stHorizontalBlock"]:has(.streamlit-brand-ribbon-marker) [data-testid="stButton"] button,
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
            body:has(.streamlit-theme-marker) div[data-testid="stButton"] button[kind="primary"],
            body:has(.streamlit-theme-marker) div[data-testid="stDownloadButton"] button[kind="primary"],
            body:has(.streamlit-theme-marker) [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] {
              background: var(--action-primary-bg) !important;
              border-color: var(--action-primary-border) !important;
              box-shadow: var(--action-primary-shadow) !important;
              color: var(--action-primary-text) !important;
              -webkit-text-fill-color: var(--action-primary-text) !important;
            }
            body:has(.streamlit-theme-marker) div[data-testid="stButton"] button[kind="primary"] *,
            body:has(.streamlit-theme-marker) div[data-testid="stDownloadButton"] button[kind="primary"] *,
            body:has(.streamlit-theme-marker) [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] * {
              color: var(--action-primary-text) !important;
              -webkit-text-fill-color: var(--action-primary-text) !important;
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
              border-color: var(--major-market-tile-border) !important;
              color: var(--major-market-text) !important;
              box-shadow: none !important;
            }
            body:has(.streamlit-theme-marker) .streamlit-news-category-details summary,
            body:has(.streamlit-theme-marker) .metric-card-header,
            body:has(.streamlit-theme-marker) .compare-table th:first-child,
            body:has(.streamlit-theme-marker) .levels-table .current td {
              background: var(--emphasis-bg) !important;
              border-color: var(--emphasis-border) !important;
              color: var(--emphasis-text) !important;
            }
            body:has(.streamlit-theme-marker) .metric-card-header *,
            body:has(.streamlit-theme-marker) .compare-table th:first-child *,
            body:has(.streamlit-theme-marker) .levels-table .current td * {
              color: var(--emphasis-text) !important;
              -webkit-text-fill-color: var(--emphasis-text) !important;
            }
            body:has(.streamlit-theme-marker) .streamlit-news-category-details > div {
              background: var(--surface-bg) !important;
            }
            body:has(.streamlit-theme-marker) .streamlit-chart-card iframe,
            body:has(.streamlit-theme-marker) .stApp iframe {
              color-scheme: var(--app-color-scheme, light);
            }
            .streamlit-top-nav {
              display: contents;
            }
            .streamlit-nav-marker {
              display: none !important;
            }
            body:has(.streamlit-theme-marker) div[role="radiogroup"] {
              align-items: center;
              background: color-mix(in srgb, var(--surface-bg) 90%, transparent);
              border: 1px solid var(--border);
              border-radius: 999px;
              box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05), 0 10px 28px rgba(15, 23, 42, 0.12);
              display: inline-flex;
              gap: 0.25rem;
              max-width: 100%;
              overflow-x: auto;
              padding: 0.2rem;
              width: fit-content;
            }
            body:has(.streamlit-theme-marker) div[role="radiogroup"] label {
              align-items: center;
              border: 1px solid transparent;
              border-radius: 999px;
              color: var(--text-muted);
              display: inline-flex;
              flex: 0 0 auto;
              font-size: 0.92rem;
              font-weight: 850;
              justify-content: center;
              line-height: 1.1;
              min-height: 1.95rem;
              min-width: 0;
              padding: 0.38rem 0.85rem !important;
              position: relative;
              transition: background 140ms ease, border-color 140ms ease, color 140ms ease, box-shadow 140ms ease;
              white-space: nowrap;
            }
            body:has(.streamlit-theme-marker) div[role="radiogroup"] label:hover {
              background: var(--surface-soft);
              border-color: var(--border-soft);
              color: var(--text);
            }
            body:has(.streamlit-theme-marker) div[role="radiogroup"] label > div:first-child,
            body:has(.streamlit-theme-marker) div[role="radiogroup"] input[type="radio"] {
              height: 1px !important;
              margin: 0 !important;
              opacity: 0 !important;
              overflow: hidden !important;
              pointer-events: none !important;
              position: absolute !important;
              width: 1px !important;
            }
            body:has(.streamlit-theme-marker) div[role="radiogroup"] label > div:last-child {
              align-items: center !important;
              display: inline-flex !important;
              height: auto !important;
              min-height: 0 !important;
              padding: 0 !important;
            }
            body:has(.streamlit-theme-marker) div[role="radiogroup"] label > div:last-child > div,
            body:has(.streamlit-theme-marker) div[role="radiogroup"] label p {
              font-size: 0.92rem !important;
              line-height: 1.1 !important;
              margin: 0 !important;
            }
            body:has(.streamlit-theme-marker) div[role="radiogroup"] label:has(input:checked) {
              background: var(--nav-active-bg);
              border-color: var(--nav-active-border);
              box-shadow: 0 8px 18px rgba(15, 118, 110, 0.24);
              color: var(--nav-active-text) !important;
              font-weight: 900;
            }
            body:has(.streamlit-theme-marker) div[role="radiogroup"] label:has(input:checked) *,
            body:has(.streamlit-theme-marker) div[role="radiogroup"] label:has(input:checked) p {
              color: var(--nav-active-text) !important;
            }
            @media (max-width: 760px) {
              body:has(.streamlit-theme-marker) .stApp .block-container {
                padding-left: 0.45rem;
                padding-right: 0.45rem;
                padding-top: 0.35rem;
              }
              body:has(.streamlit-theme-marker) [data-testid="stSidebarCollapsedControl"],
              body:has(.streamlit-theme-marker) [data-testid="stSidebarCollapseButton"],
              body:has(.streamlit-theme-marker) [data-testid="stExpandSidebarButton"] {
                height: 2.45rem !important;
                left: 0.5rem !important;
                top: 0.55rem !important;
                width: 2.45rem !important;
              }
              body:has(.streamlit-theme-marker) [data-testid="stSidebarCollapsedControl"] button,
              body:has(.streamlit-theme-marker) [data-testid="stSidebarCollapseButton"] button,
              body:has(.streamlit-theme-marker) [data-testid="stExpandSidebarButton"] button,
              body:has(.streamlit-theme-marker) [data-testid="stExpandSidebarButton"],
              body:has(.streamlit-theme-marker) button[aria-label="Open sidebar"],
              body:has(.streamlit-theme-marker) button[aria-label="Close sidebar"],
              body:has(.streamlit-theme-marker) button[title="Open sidebar"],
              body:has(.streamlit-theme-marker) button[title="Close sidebar"] {
                background: var(--sidebar-toggle-bg) !important;
                border-color: var(--sidebar-toggle-border) !important;
                border-radius: 0.55rem !important;
                box-shadow: var(--sidebar-toggle-shadow) !important;
                height: 2.45rem !important;
                left: 0.5rem !important;
                min-height: 2.45rem !important;
                min-width: 2.45rem !important;
                top: 0.55rem !important;
                width: 2.45rem !important;
              }
              body:has(.streamlit-theme-marker) [data-testid="stSidebarCollapsedControl"] button::before,
              body:has(.streamlit-theme-marker) [data-testid="stSidebarCollapseButton"] button::before,
              body:has(.streamlit-theme-marker) [data-testid="stExpandSidebarButton"] button::before,
              body:has(.streamlit-theme-marker) [data-testid="stExpandSidebarButton"]::before,
              body:has(.streamlit-theme-marker) button[aria-label="Open sidebar"]::before,
              body:has(.streamlit-theme-marker) button[aria-label="Close sidebar"]::before,
              body:has(.streamlit-theme-marker) button[title="Open sidebar"]::before,
              body:has(.streamlit-theme-marker) button[title="Close sidebar"]::before {
                color: var(--sidebar-toggle-text) !important;
                font-size: 1.35rem;
              }
              body:has(.streamlit-theme-marker) div[data-testid="stVerticalBlock"]:has(.view-hero-marker):has(button):not(:has(.streamlit-brand)) {
                margin: 0.5rem 0 0.75rem !important;
                padding: 0.85rem !important;
              }
              body:has(.streamlit-theme-marker) div[data-testid="stVerticalBlock"]:has(.view-hero-marker):has(button):not(:has(.streamlit-brand)) h1 {
                font-size: clamp(1.85rem, 9vw, 2.45rem) !important;
                line-height: 1.08 !important;
              }
              body:has(.streamlit-theme-marker) div[data-testid="stVerticalBlock"]:has(.view-hero-marker):has(button):not(:has(.streamlit-brand)) [data-testid="stButton"] button[kind="primary"] {
                font-size: 0.98rem !important;
                min-height: 2.85rem !important;
                padding: 0.55rem 0.8rem !important;
              }
              body:has(.streamlit-theme-marker) .metric-card-header {
                min-height: 0 !important;
                padding: 0.68rem 0.8rem !important;
              }
              body:has(.streamlit-theme-marker) .metric-card-header h3 {
                font-size: 1.15rem !important;
                line-height: 1.15 !important;
              }
              body:has(.streamlit-theme-marker) .metric-card-body,
              body:has(.streamlit-theme-marker) .ladder-body,
              body:has(.streamlit-theme-marker) .compact-body {
                padding: 0.65rem !important;
              }
              body:has(.streamlit-theme-marker) div[role="radiogroup"] label {
                font-size: 0.86rem !important;
                min-height: 1.8rem;
                padding: 0.32rem 0.62rem !important;
              }
              body:has(.streamlit-theme-marker) div[role="radiogroup"] label > div:last-child > div,
              body:has(.streamlit-theme-marker) div[role="radiogroup"] label p {
                font-size: 0.86rem !important;
              }
            }
	        </style>
        """,
        unsafe_allow_html=True,
    )

    brand_col, settings_col = st.columns([1, 0.08], vertical_alignment="center")
    with brand_col:
        st.markdown(
            """
            <span class="streamlit-brand-ribbon-marker"></span>
            <div class="streamlit-brand">
              <span class="brand-mark">IT</span>
              <span class="brand-name">Investment Trading</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with settings_col:
        st.button(
            ":material/settings:",
            key="streamlit-settings-toggle",
            help="Open settings",
            use_container_width=True,
            on_click=toggle_streamlit_settings_panel,
        )

    st.markdown('<div class="streamlit-top-nav"><span class="streamlit-nav-marker"></span>', unsafe_allow_html=True)
    active_view = st.radio(
        "Primary view",
        STREAMLIT_VIEWS,
        key="active_view",
        horizontal=True,
        label_visibility="collapsed",
        on_change=persist_session_settings,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    return str(active_view)


def set_active_view(view: str) -> None:
    """Persist the active Streamlit view."""
    st.session_state.active_view = view
    persist_session_settings()


def toggle_streamlit_settings_panel() -> None:
    """Toggle the right-side Streamlit settings panel."""
    st.session_state.settings_panel_open = not bool(st.session_state.get("settings_panel_open", False))


def close_streamlit_settings_panel() -> None:
    """Close the right-side Streamlit settings panel."""
    st.session_state.settings_panel_open = False


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


def sync_score_level_basis_to_level_filter() -> None:
    """Keep the score level-basis selector aligned with the report level filter."""
    st.session_state.score_level_basis = normalize_level_filter(
        st.session_state.get(SCORE_LEVEL_BASIS_WIDGET_KEY, DEFAULT_LEVEL_FILTER)
    )
    st.session_state.level_filter = st.session_state.score_level_basis
    persist_session_settings()


def render_score_analytics_controls() -> tuple[ScoreHistoryRange, ScoreMetricName, LevelScoreBasisName, str, str, str]:
    """Render Score Analytics controls and return normalized values."""
    level_filter = normalize_level_filter(st.session_state.get("level_filter", DEFAULT_LEVEL_FILTER))
    score_range_default = normalize_score_history_range(
        st.session_state.get("score_range", SCORE_ANALYTICS_DEFAULT_RANGE)
    )
    score_metric_default = normalize_score_metric(st.session_state.get("score_metric", "both"))
    chart_metric_default = normalize_score_chart_metric(st.session_state.get("score_chart_metric", "heat"))
    level_basis_default = normalize_level_filter(st.session_state.get("score_level_basis", level_filter))
    movement_default = normalize_score_movement(st.session_state.get("score_movement", "all"))
    sort_default = normalize_score_sort(st.session_state.get("score_sort", "watchlist"))
    if level_basis_default != level_filter:
        level_basis_default = level_filter

    st.session_state.score_range = score_range_default
    st.session_state.score_metric = score_metric_default
    st.session_state.score_chart_metric = chart_metric_default
    st.session_state.score_level_basis = level_basis_default
    st.session_state.score_movement = movement_default
    st.session_state.score_sort = sort_default
    st.session_state.setdefault(SCORE_RANGE_WIDGET_KEY, score_range_default)
    st.session_state.setdefault(SCORE_METRIC_WIDGET_KEY, score_metric_default)
    st.session_state.setdefault(SCORE_CHART_METRIC_WIDGET_KEY, chart_metric_default)
    st.session_state.setdefault(SCORE_LEVEL_BASIS_WIDGET_KEY, level_basis_default)
    st.session_state.setdefault(SCORE_MOVEMENT_WIDGET_KEY, movement_default)
    st.session_state.setdefault(SCORE_SORT_WIDGET_KEY, sort_default)

    range_col, metric_col, chart_col, basis_col, movement_col, sort_col = st.columns(
        [0.7, 0.78, 0.78, 0.88, 0.92, 1.08],
        vertical_alignment="center",
    )
    with range_col:
        score_range = st.selectbox(
            "Range",
            SCORE_ANALYTICS_RANGES,
            key=SCORE_RANGE_WIDGET_KEY,
            format_func=score_option_label,
        )
    with metric_col:
        score_metric = st.selectbox(
            "Metric",
            SCORE_ANALYTICS_METRICS,
            key=SCORE_METRIC_WIDGET_KEY,
            format_func=score_option_label,
        )
    with chart_col:
        chart_metric = st.selectbox(
            "Chart metric",
            SCORE_ANALYTICS_CHART_METRICS,
            key=SCORE_CHART_METRIC_WIDGET_KEY,
            format_func=score_option_label,
        )
    with basis_col:
        level_basis = st.selectbox(
            "Level basis",
            LEVEL_FILTER_OPTIONS,
            key=SCORE_LEVEL_BASIS_WIDGET_KEY,
            format_func=score_option_label,
            on_change=sync_score_level_basis_to_level_filter,
        )
    with movement_col:
        movement = st.selectbox(
            "Movement",
            SCORE_ANALYTICS_MOVEMENTS,
            key=SCORE_MOVEMENT_WIDGET_KEY,
            format_func=score_option_label,
        )
    with sort_col:
        sort = st.selectbox(
            "Sort",
            SCORE_ANALYTICS_SORTS,
            key=SCORE_SORT_WIDGET_KEY,
            format_func=score_option_label,
        )
    st.session_state.score_range = normalize_score_history_range(score_range)
    st.session_state.score_metric = normalize_score_metric(score_metric)
    st.session_state.score_chart_metric = normalize_score_chart_metric(chart_metric)
    st.session_state.score_level_basis = normalize_level_filter(level_basis)
    st.session_state.score_movement = normalize_score_movement(movement)
    st.session_state.score_sort = normalize_score_sort(sort)
    return (
        st.session_state.score_range,
        st.session_state.score_metric,
        st.session_state.score_level_basis,
        st.session_state.score_movement,
        st.session_state.score_sort,
        st.session_state.score_chart_metric,
    )


def render_score_analytics(
    report: GenerateResponse,
    *,
    visible_tickers: tuple[str, ...],
    search_query: str,
) -> None:
    """Render daily score history below Streamlit charts."""
    with st.container(border=True):
        st.markdown(
            (
                '<span class="streamlit-score-analytics-marker"></span>'
                '<div class="streamlit-score-analytics-header">'
                "<h2>Score Analytics</h2>"
                '<span class="streamlit-status-chip">Adam + derived trends</span>'
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        score_range, score_metric, level_basis, movement, sort, chart_metric = render_score_analytics_controls()
        watchlist_order = tuple(metric.ticker for metric in report.metrics)
        if not watchlist_order:
            st.info("Score history will appear after levels or scanner data refreshes.")
            return
        if not visible_tickers:
            label = normalize_level_search(search_query)
            st.info(f"No score analytics ticker matches '{label}'." if label else "No visible tickers for score analytics.")
            return

        try:
            response = score_history_service().build_response(
                list(visible_tickers),
                score_range=score_range,
                score_metric=score_metric,
                level_basis=level_basis,
            )
        except ValidationError as exc:
            if score_range != "1D":
                st.warning(f"Score history could not be loaded: {exc}")
                return
            fallback_range = normalize_score_history_range("30D")
            st.session_state.score_range = fallback_range
            st.warning(
                "1D score analytics is not available in this running app process yet, "
                "so the panel is showing 30D. Reboot the Streamlit app to enable 1D after deploy."
            )
            try:
                response = score_history_service().build_response(
                    list(visible_tickers),
                    score_range=fallback_range,
                    score_metric=score_metric,
                    level_basis=level_basis,
                )
            except Exception as fallback_exc:
                st.warning(f"Score history could not be loaded: {fallback_exc}")
                return
        except Exception as exc:
            st.warning(f"Score history could not be loaded: {exc}")
            return

        rows = sort_score_rows(
            filter_score_rows(response.tickers, movement, score_metric),
            sort,
            score_metric,
            watchlist_order,
        )
        warnings = score_history_warnings(response)
        if warnings:
            with st.expander(f"{len(warnings)} score history note(s)", expanded=False):
                for warning in warnings:
                    st.caption(warning)
        if not rows:
            st.info("No score history matches the current filters.")
            return

        axis = score_response_axis(response)
        st.markdown(score_summary_html(rows, score_metric, axis), unsafe_allow_html=True)
        st.markdown(score_line_chart_html(rows, chart_metric, axis), unsafe_allow_html=True)
        st.markdown(score_trend_cards_html(rows, score_metric, axis), unsafe_allow_html=True)


def score_history_warnings(response: ScoreHistoryResponse) -> list[str]:
    """Return unique score-history warnings for the Streamlit pane."""
    session_warnings = st.session_state.get("score_history_warnings", [])
    if not isinstance(session_warnings, list):
        session_warnings = []
    warnings = [
        *session_warnings,
        *(response.warnings or []),
        *[warning for row in response.tickers for warning in (row.warnings or [])],
    ]
    return list(dict.fromkeys(str(warning) for warning in warnings if warning))


def score_response_axis(response: object) -> ScoreHistoryAxis | None:
    """Return optional score-history axis metadata from current or legacy responses."""
    axis = getattr(response, "axis", None)
    if axis is None:
        return None
    if isinstance(axis, ScoreHistoryAxis):
        return axis
    try:
        return ScoreHistoryAxis.model_validate(axis)
    except Exception:
        return None


def filter_score_rows(
    rows: list[ScoreHistoryTicker],
    movement: str,
    score_metric: ScoreMetricName,
) -> list[ScoreHistoryTicker]:
    """Filter score rows by the selected movement category."""
    if movement == "all":
        return list(rows)
    return [row for row in rows if score_movement(row, score_metric) == movement]


def sort_score_rows(
    rows: list[ScoreHistoryTicker],
    sort: str,
    score_metric: ScoreMetricName,
    watchlist_order: tuple[str, ...],
) -> list[ScoreHistoryTicker]:
    """Sort score rows by watchlist order or latest/movement scores."""
    order = {ticker: index for index, ticker in enumerate(watchlist_order)}

    def watchlist_index(row: ScoreHistoryTicker) -> int:
        return order.get(row.ticker, len(order))

    def value_or_empty(value: int | float | None) -> float:
        return float(value) if value is not None else float("-inf")

    if sort == "setup":
        return sorted(rows, key=lambda row: (value_or_empty(row.latest_setup_score), -watchlist_index(row)), reverse=True)
    if sort == "level":
        return sorted(rows, key=lambda row: (value_or_empty(row.latest_level_score_normalized), -watchlist_index(row)), reverse=True)
    if sort == "gain":
        return sorted(rows, key=lambda row: (value_or_empty(score_movement_amount(row, score_metric)), -watchlist_index(row)), reverse=True)
    if sort == "drop":
        return sorted(rows, key=lambda row: score_movement_amount(row, score_metric) if score_movement_amount(row, score_metric) is not None else float("inf"))
    return sorted(rows, key=watchlist_index)


def score_summary_html(
    rows: list[ScoreHistoryTicker],
    score_metric: ScoreMetricName,
    axis: ScoreHistoryAxis | None = None,
) -> str:
    """Return summary tile markup for score analytics."""
    setup_values = [row.latest_setup_score for row in rows if row.latest_setup_score is not None]
    level_values = [row.latest_level_score_normalized for row in rows if row.latest_level_score_normalized is not None]
    heat_values = [latest_heat_score(row) for row in rows if latest_heat_score(row) is not None]
    improving = sum(1 for row in rows if score_movement(row, score_metric) == "improving")
    declining = sum(1 for row in rows if score_movement(row, score_metric) == "declining")
    flat = len(rows) - improving - declining
    movement_window = score_movement_window_label(axis)
    tiles = [
        score_summary_tile_html("Tracked", len([row for row in rows if row.points]), f"{len(rows)} visible"),
        score_summary_tile_html("Avg Derived Heat", score_average(heat_values), "hot/cold"),
        score_summary_tile_html("Avg Adam Setup", score_average(setup_values), "0-8"),
        score_summary_tile_html("Avg Derived Level", score_average(level_values), "normalized"),
        score_summary_tile_html("Improving", improving, movement_window),
        score_summary_tile_html("Declining", declining, movement_window),
        score_summary_tile_html("Flat/New", flat, movement_window),
    ]
    return f'<div class="streamlit-score-summary-strip">{"".join(tiles)}</div>'


def score_summary_tile_html(label: str, value: int | float | None, meta: str) -> str:
    """Return one score summary tile."""
    return (
        '<div class="streamlit-score-summary-tile">'
        f"<span>{escape(label)}</span>"
        f"<strong>{format_score_summary_value(value)}</strong>"
        f"<small>{escape(meta)}</small>"
        "</div>"
    )


def score_line_chart_html(
    rows: list[ScoreHistoryTicker],
    chart_metric: str,
    axis: ScoreHistoryAxis | None = None,
) -> str:
    """Return all-visible ticker line chart markup for the selected 0-100 score metric."""
    metric = normalize_score_chart_metric(chart_metric)
    metric_label = score_option_label(metric)
    colors = ("#0f766e", "#2563eb", "#dc2626", "#ca8a04", "#7c3aed", "#0891b2", "#be185d", "#4d7c0f")
    axis_items = score_axis_items(rows, metric, axis)
    series = []
    for index, row in enumerate(rows):
        point_by_axis_key = {point["axis_key"]: point for point in score_display_points(row, axis)}
        points = []
        for axis_index, item in enumerate(axis_items):
            display_point = point_by_axis_key.get(item["key"])
            source_point = display_point["point"] if display_point else None
            value = score_point_metric_value(source_point, metric) if source_point is not None else None
            points.append({"index": axis_index, "key": item["key"], "label": item["label"], "value": value})
        if any(point["value"] is not None for point in points):
            series.append({"ticker": row.ticker, "color": colors[index % len(colors)], "points": points})
    if not series or not axis_items:
        return (
            '<section class="streamlit-score-line-panel">'
            '<div class="streamlit-score-line-header">'
            f"<h4>{escape(metric_label)} Trend</h4>"
            f"<span>No {escape(metric_label.lower())} chart data</span>"
            "</div>"
            '<div class="streamlit-score-line-empty"></div>'
            "</section>"
        )

    width = 840
    height = 220
    left = 42
    right = 64
    top = 14
    bottom = 48
    plot_width = width - left - right
    plot_height = height - top - bottom

    def x_for_index(index: int) -> float:
        return left + plot_width / 2 if len(axis_items) == 1 else left + (index / (len(axis_items) - 1)) * plot_width

    def y_for_value(value: float) -> float:
        return top + ((100 - clamp_percent(value)) / 100) * plot_height

    grid = "".join(
        (
            '<g class="streamlit-score-line-grid">'
            f'<line x1="{left}" y1="{y_for_value(value):.2f}" x2="{width - right}" y2="{y_for_value(value):.2f}"></line>'
            f'<text x="8" y="{y_for_value(value) + 4:.2f}">{value}</text>'
            "</g>"
        )
        for value in (0, 25, 50, 75, 100)
    )
    x_axis_ticks = "".join(
        (
            "<g>"
            f'<line x1="{x_for_index(index):.2f}" y1="{height - bottom}" x2="{x_for_index(index):.2f}" y2="{height - bottom + 5}"></line>'
            f'<text x="{x_for_index(index):.2f}" y="{height - 16}" text-anchor="middle">{escape(str(axis_items[index]["label"]))}</text>'
            "</g>"
        )
        for index in score_axis_tick_indexes(axis_items, axis)
    )
    x_axis = (
        '<g class="streamlit-score-line-x-axis">'
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}"></line>'
        f"{x_axis_ticks}</g>"
    )
    series_markup = []
    legend = []
    for row in series:
        pieces = []
        segment = []
        finite_points = [point for point in row["points"] if point["value"] is not None]
        for point in row["points"]:
            if point["value"] is not None:
                segment.append(point)
                continue
            if segment:
                pieces.append(score_svg_segment_markup(segment, x_for_index, y_for_value))
                segment = []
        if segment:
            pieces.append(score_svg_segment_markup(segment, x_for_index, y_for_value))
        latest = finite_points[-1]
        end_label = ""
        if len(series) <= len(colors):
            end_label = (
                f'<text class="streamlit-score-line-end-label" x="{min(width - 38, x_for_index(int(latest["index"])) + 7):.2f}" '
                f'y="{y_for_value(float(latest["value"])) + 4:.2f}">{escape(str(row["ticker"]))}</text>'
            )
        series_markup.append(
            f'<g class="streamlit-score-line-series" style="--score-series-color:{escape(str(row["color"]))}">'
            f'{"".join(pieces)}{end_label}</g>'
        )
        legend.append(
            f'<span class="streamlit-score-line-legend-item" style="--score-series-color:{escape(str(row["color"]))}">'
            f'<i></i>{escape(str(row["ticker"]))} {format_score_summary_value(float(latest["value"]))}</span>'
        )
    axis_meta = score_chart_axis_meta(axis_items, axis)
    return (
        '<section class="streamlit-score-line-panel">'
        '<div class="streamlit-score-line-header">'
        f"<h4>{escape(metric_label)} Trend</h4>"
        f"<span>{escape(axis_meta)}</span>"
        "</div>"
        f'<svg class="streamlit-score-line-chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(metric_label)} trend for visible tickers">'
        f"<title>{escape(metric_label)} trend for visible tickers</title>"
        f"{grid}{x_axis}{''.join(series_markup)}</svg>"
        f'<div class="streamlit-score-line-legend">{"".join(legend)}</div>'
        "</section>"
    )


def score_is_intraday_axis(axis: ScoreHistoryAxis | None) -> bool:
    """Return whether score analytics should use the intraday bucket axis."""
    return bool(axis and axis.mode == "intraday" and axis.buckets)


def score_axis_items(
    rows: list[ScoreHistoryTicker],
    metric: str,
    axis: ScoreHistoryAxis | None = None,
) -> list[dict[str, str]]:
    """Return ordered axis keys/labels for score charts."""
    if score_is_intraday_axis(axis):
        return [
            {"key": bucket.key, "label": bucket.label, "status": bucket.status}
            for bucket in axis.buckets
        ]
    dates = sorted(
        {
            point.date.isoformat()
            for row in rows
            for point in row.points
            if score_point_metric_value(point, metric) is not None
        }
    )
    return [{"key": day, "label": day, "status": "past"} for day in dates]


def score_display_points(
    row: ScoreHistoryTicker,
    axis: ScoreHistoryAxis | None = None,
) -> list[dict[str, Any]]:
    """Expand row points across the active axis, preserving intraday gaps."""
    if not score_is_intraday_axis(axis):
        return [
            {"axis_key": point.date.isoformat(), "axis_label": point.date.isoformat(), "point": point}
            for point in row.points
        ]
    point_by_bucket = {point.bucket: point for point in row.points if point.bucket}
    return [
        {
            "axis_key": bucket.key,
            "axis_label": bucket.label,
            "bucket_status": bucket.status,
            "point": point_by_bucket.get(bucket.key),
        }
        for bucket in axis.buckets
    ]


def score_svg_segment_markup(segment: list[dict[str, Any]], x_for_index: Any, y_for_value: Any) -> str:
    """Return SVG line/circle markup for one contiguous score segment."""
    if len(segment) == 1:
        point = segment[0]
        return (
            f'<circle cx="{x_for_index(int(point["index"])):.2f}" '
            f'cy="{y_for_value(float(point["value"])):.2f}" r="4"></circle>'
        )
    coordinates = " ".join(
        f'{x_for_index(int(point["index"])):.2f},{y_for_value(float(point["value"])):.2f}'
        for point in segment
    )
    return f'<polyline points="{coordinates}"></polyline>'


def score_axis_tick_indexes(axis_items: list[dict[str, str]], axis: ScoreHistoryAxis | None = None) -> list[int]:
    """Return readable x-axis tick indexes for score charts."""
    count = len(axis_items)
    if count <= 1:
        return [0] if count else []
    if score_is_intraday_axis(axis):
        return [index for index in range(count) if index % 2 == 0 or index == count - 1]
    if count <= 6:
        return list(range(count))
    return sorted({0, (count - 1) // 2, count - 1})


def score_chart_axis_meta(axis_items: list[dict[str, str]], axis: ScoreHistoryAxis | None = None) -> str:
    """Return compact axis metadata text."""
    if score_is_intraday_axis(axis):
        start = format_score_session_time(axis.session_start or "09:30")
        end = format_score_session_time(axis.session_end or "16:00")
        bucket_minutes = axis.bucket_minutes or 30
        return f"{start} - {end} {score_timezone_label(axis.timezone)} · {bucket_minutes}m buckets"
    first = axis_items[0]["label"] if axis_items else ""
    last = axis_items[-1]["label"] if axis_items else ""
    return first if first == last else f"{first} - {last}"


def format_score_session_time(value: str) -> str:
    """Format HH:MM session times as readable market time."""
    try:
        hour_text, minute_text = value.split(":", maxsplit=1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError:
        return value
    suffix = "AM" if hour < 12 else "PM"
    return f"{hour % 12 or 12}:{minute:02d} {suffix}"


def score_timezone_label(value: str | None) -> str:
    """Return compact timezone text for score axes."""
    return "ET" if value == "America/New_York" else value or ""


def score_trend_cards_html(
    rows: list[ScoreHistoryTicker],
    score_metric: ScoreMetricName,
    axis: ScoreHistoryAxis | None = None,
) -> str:
    """Return per-ticker score trend card markup."""
    cards = "".join(score_trend_card_html(row, score_metric, axis) for row in rows)
    return f'<div class="streamlit-score-trend-grid">{cards}</div>'


def score_trend_card_html(
    row: ScoreHistoryTicker,
    score_metric: ScoreMetricName,
    axis: ScoreHistoryAxis | None = None,
) -> str:
    """Return one ticker score trend card."""
    show_setup = score_metric != "level"
    show_level = score_metric != "setup"
    movement = score_movement(row, score_metric)
    latest = []
    sparklines = []
    if show_setup:
        latest.append(
            score_latest_html("Adam Setup", format_setup_score(row.latest_setup_score), row.setup_delta_1d, row.setup_delta_5d, axis)
        )
        sparklines.append(score_sparkline_html(row, "setup_score", "Adam setup score", axis))
    if show_level:
        latest.append(
            score_latest_html(
                "Derived Level",
                format_level_score(row.latest_level_score, row.latest_level_score_normalized, row.latest_level_count),
                row.level_normalized_delta_1d,
                row.level_normalized_delta_5d,
                axis,
            )
        )
        sparklines.append(score_sparkline_html(row, "level_score_normalized", "Derived level score", axis))
    return (
        f'<article class="streamlit-score-card movement-{movement}">'
        "<header>"
        "<div>"
        f"<h4>{escape(row.ticker)}</h4>"
        f"<span>{escape(score_trend_point_label(row, axis))}</span>"
        "</div>"
        "</header>"
        f'<div class="streamlit-score-latest-grid">{"".join(latest)}</div>'
        f'<div class="streamlit-score-movement-row">{score_movement_badge_html(row, score_metric, axis)}</div>'
        f"{score_heat_thermometer_html(row)}"
        f"{score_heat_strip_html(row, axis)}"
        f'<div class="streamlit-score-sparkline-grid">{"".join(sparklines)}</div>'
        "</article>"
    )


def score_latest_html(
    label: str,
    value: str,
    delta_1d: int | float | None,
    delta_5d: int | float | None,
    axis: ScoreHistoryAxis | None = None,
) -> str:
    """Return latest score/delta markup."""
    return (
        '<div class="streamlit-score-latest">'
        f"<span>{escape(label)}</span>"
        f"<strong>{value}</strong>"
        f"<small>{score_delta_window_text(delta_1d, delta_5d, axis)}</small>"
        "</div>"
    )


def score_sparkline_html(
    row: ScoreHistoryTicker,
    field: str,
    label: str,
    axis: ScoreHistoryAxis | None = None,
) -> str:
    """Return a compact SVG sparkline for one score field."""
    is_setup = field == "setup_score"
    max_value = 8 if is_setup else 100
    scale_label = "0-8" if is_setup else "0-100%"
    display_points = score_display_points(row, axis)
    series = [
        {
            "index": index,
            "axis_label": str(display_point["axis_label"]),
            "value": value,
        }
        for index, display_point in enumerate(display_points)
        for point in [display_point["point"]]
        for value in [numeric_or_none(getattr(point, field, None)) if point is not None else None]
    ]
    finite_points = [point for point in series if point["value"] is not None]
    if not finite_points:
        return (
            '<div class="streamlit-score-sparkline-card">'
            '<div class="streamlit-score-sparkline-title">'
            f"<span>{escape(label)}</span><small>{escape(scale_label)}</small>"
            "</div>"
            '<div class="streamlit-score-sparkline-empty"></div>'
            "</div>"
        )
    width = 220
    height = 72
    left = 24
    right = 6
    top = 8
    bottom = 18
    plot_width = width - left - right
    plot_height = height - top - bottom

    def x_for_index(index: int) -> float:
        return left + plot_width / 2 if len(series) == 1 else left + (index / (len(series) - 1)) * plot_width

    def y_for_value(value: float) -> float:
        return top + ((max_value - clamp_between(value, 0, max_value)) / max_value) * plot_height

    pieces = []
    segment = []
    for point in series:
        if point["value"] is not None:
            segment.append(point)
            continue
        if segment:
            pieces.append(score_svg_segment_markup(segment, x_for_index, y_for_value))
            segment = []
    if segment:
        pieces.append(score_svg_segment_markup(segment, x_for_index, y_for_value))
    caption = score_sparkline_caption(finite_points)
    return (
        '<div class="streamlit-score-sparkline-card">'
        '<div class="streamlit-score-sparkline-title">'
        f"<span>{escape(label)}</span><small>{escape(scale_label)}</small>"
        "</div>"
        f'<svg class="streamlit-score-sparkline" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(label)} trend">'
        f'<title>{escape(label)} trend from {escape(str(finite_points[0]["axis_label"]))} to {escape(str(finite_points[-1]["axis_label"]))}</title>'
        f'<line class="streamlit-score-sparkline-grid-line" x1="{left}" y1="{top}" x2="{width - right}" y2="{top}"></line>'
        f'<line class="streamlit-score-sparkline-grid-line" x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}"></line>'
        f'<text class="streamlit-score-sparkline-scale" x="2" y="{top + 4}">{max_value}</text>'
        f'<text class="streamlit-score-sparkline-scale" x="2" y="{height - bottom + 4}">0</text>'
        f'{"".join(pieces)}'
        "</svg>"
        f'<small class="streamlit-score-sparkline-caption">{escape(caption)}</small>'
        "</div>"
    )


def score_heat_thermometer_html(row: ScoreHistoryTicker) -> str:
    """Return latest hot/cold score thermometer markup."""
    heat = latest_heat_score(row)
    band_id, band_label = heat_band(heat)
    width = clamp_percent(heat or 0)
    return (
        f'<div class="streamlit-score-thermometer streamlit-heat-{band_id}">'
        "<div>"
        "<span>Derived Heat</span>"
        f"<strong>{format_heat_score(heat)}</strong>"
        "</div>"
        f'<div class="streamlit-score-thermometer-track" aria-label="Derived heat score {escape(format_heat_score(heat))}">'
        f'<span style="width:{width:.1f}%"></span>'
        "</div>"
        f"<small>{escape(band_label)}</small>"
        "</div>"
    )


def score_heat_strip_html(row: ScoreHistoryTicker, axis: ScoreHistoryAxis | None = None) -> str:
    """Return daily hot/cold heat strip markup."""
    points = score_display_points(row, axis)
    label = "Trading Day Derived Heat" if score_is_intraday_axis(axis) else "Daily Derived Heat History"
    if not points:
        return (
            '<div class="streamlit-score-heat-strip-card">'
            f"<span>{escape(label)}</span>"
            '<div class="streamlit-score-heat-strip empty"></div>'
            "</div>"
        )
    first_label = str(points[0]["axis_label"]) if points else ""
    last_label = str(points[-1]["axis_label"]) if points else ""
    cells = []
    for display_point in points:
        point = display_point["point"]
        heat = score_point_heat(point) if point is not None else None
        band_id, band_label = heat_band(heat)
        status = str(display_point.get("bucket_status") or "past")
        axis_label = str(display_point["axis_label"])
        empty_reason = "Not happened yet" if status == "future" else "No score snapshot"
        title = f"{axis_label}: {format_heat_score(heat)} {band_label}" if heat is not None else f"{axis_label}: {empty_reason}"
        state = "filled" if heat is not None else "empty"
        cells.append(
            f'<i class="streamlit-heat-{band_id} status-{escape(status)} {state}" title="{escape(title)}" aria-label="{escape(title)}"></i>'
        )
    return (
        '<div class="streamlit-score-heat-strip-card">'
        f"<span>{escape(label)}</span>"
        f'<div class="streamlit-score-heat-strip">{"".join(cells)}</div>'
        f'<div class="streamlit-score-heat-strip-axis"><span>{escape(first_label)}</span><span>{escape(last_label)}</span></div>'
        "</div>"
    )


def score_trend_point_label(row: ScoreHistoryTicker, axis: ScoreHistoryAxis | None = None) -> str:
    """Return the score card point-count label."""
    count = len(row.points)
    if score_is_intraday_axis(axis):
        return f"{count} observed bucket{'' if count == 1 else 's'}"
    return f"{count} point{'' if count == 1 else 's'}"


def score_movement_badge_html(
    row: ScoreHistoryTicker,
    score_metric: ScoreMetricName,
    axis: ScoreHistoryAxis | None = None,
) -> str:
    """Return explicit movement badge markup."""
    movement = score_movement(row, score_metric)
    amount = score_movement_amount(row, score_metric)
    metric = score_movement_metric_label(score_metric)
    delta = f" {format_score_delta_text(amount)}" if amount is not None else ""
    text = f"{score_option_label(movement)}{delta} {metric}, compared with {score_movement_window_label(axis).lower()}"
    return f'<span class="streamlit-score-movement {movement}" title="{escape(text)}">{escape(text)}</span>'


def score_movement_metric_label(score_metric: ScoreMetricName) -> str:
    """Return the metric used by movement calculations."""
    if score_metric == "setup":
        return "setup"
    if score_metric == "level":
        return "level"
    return "heat"


def score_movement_window_label(axis: ScoreHistoryAxis | None = None) -> str:
    """Return movement comparison window text."""
    return "Prior bucket" if score_is_intraday_axis(axis) else "Prior day"


def score_delta_window_text(
    delta_1d: int | float | None,
    delta_5d: int | float | None,
    axis: ScoreHistoryAxis | None = None,
) -> str:
    """Return latest delta text for daily or intraday score cards."""
    if score_is_intraday_axis(axis):
        return f"Prev bucket {format_score_delta(delta_1d)} / 5 buckets {format_score_delta(delta_5d)}"
    return f"1D {format_score_delta(delta_1d)} / 5D {format_score_delta(delta_5d)}"


def format_score_delta_text(value: int | float | None) -> str:
    """Return plain signed score delta text."""
    if value is None:
        return ""
    number = float(value)
    formatted = f"{number:.1f}".removesuffix(".0")
    return f"+{formatted}" if number > 0 else formatted


def score_sparkline_caption(points: list[dict[str, Any]]) -> str:
    """Return first/latest label text for a score sparkline."""
    if not points:
        return ""
    first = str(points[0]["axis_label"])
    last = str(points[-1]["axis_label"])
    return first if first == last else f"{first} - {last}"


def score_point_metric_value(point: ScoreHistoryPoint, metric: str) -> float | None:
    """Return a point value for the selected 0-100 chart metric."""
    if metric == "setup":
        return setup_score_normalized(point.setup_score)
    if metric == "level":
        return numeric_or_none(point.level_score_normalized)
    return score_point_heat(point)


def score_point_heat(point: ScoreHistoryPoint) -> float | None:
    """Return stored or derived point heat score."""
    stored_heat = numeric_or_none(getattr(point, "heat_score", None))
    if stored_heat is not None:
        return stored_heat
    return heat_score(point.setup_score, point.level_score_normalized)


def latest_heat_score(row: ScoreHistoryTicker) -> float | None:
    """Return latest stored or derived ticker heat score."""
    stored_heat = numeric_or_none(getattr(row, "latest_heat_score", None))
    if stored_heat is not None:
        return stored_heat
    for point in reversed(row.points):
        heat = score_point_heat(point)
        if heat is not None:
            return heat
    return heat_score(row.latest_setup_score, row.latest_level_score_normalized)


def heat_score(setup_score: int | None, level_score_normalized: float | None) -> float | None:
    """Return a 0-100 hot/cold score with 60/40 setup/level weighting."""
    components: list[tuple[float, float]] = []
    setup = setup_score_normalized(setup_score)
    level = numeric_or_none(level_score_normalized)
    if setup is not None:
        components.append((setup, 0.6))
    if level is not None:
        components.append((clamp_percent(level), 0.4))
    if not components:
        return None
    total_weight = sum(weight for _, weight in components)
    return round(sum(value * weight for value, weight in components) / total_weight, 1)


def setup_score_normalized(value: int | None) -> float | None:
    """Normalize scanner setup score to 0-100."""
    number = numeric_or_none(value)
    return round((max(0.0, min(8.0, number)) / 8) * 100, 1) if number is not None else None


def numeric_or_none(value: object) -> float | None:
    """Return a finite float or None."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def clamp_percent(value: float | None) -> float:
    """Clamp a percent value to 0-100."""
    if value is None:
        return 0.0
    return max(0.0, min(100.0, float(value)))


def clamp_between(value: float, minimum: float, maximum: float) -> float:
    """Clamp a value to an inclusive numeric range."""
    return max(minimum, min(maximum, float(value)))


def heat_band(value: float | None) -> tuple[str, str]:
    """Return hot/cold band id and label."""
    number = numeric_or_none(value)
    if number is None:
        return ("none", "No heat")
    if number < 40:
        return ("cold", "Cold")
    if number < 60:
        return ("cool", "Cool")
    if number < 75:
        return ("warm", "Warm")
    return ("hot", "Hot")


def format_heat_score(value: float | None) -> str:
    """Format a heat score."""
    number = numeric_or_none(value)
    if number is None:
        return "-"
    return f"{number:.1f}".removesuffix(".0")


def score_movement(row: ScoreHistoryTicker, score_metric: ScoreMetricName) -> str:
    """Return movement category for a score row."""
    movement = score_movement_amount(row, score_metric)
    if movement is None or abs(float(movement)) < 0.01:
        return "flat"
    return "improving" if float(movement) > 0 else "declining"


def score_movement_amount(row: ScoreHistoryTicker, score_metric: ScoreMetricName) -> float | None:
    """Return the 1-day movement amount for sorting/filtering."""
    if score_metric == "setup":
        return float(row.setup_delta_1d) if row.setup_delta_1d is not None else None
    if score_metric == "level":
        return float(row.level_normalized_delta_1d) if row.level_normalized_delta_1d is not None else None
    heat_delta_1d = getattr(row, "heat_delta_1d", None)
    if heat_delta_1d is not None:
        return float(heat_delta_1d)
    heat_values = [value for value in [score_point_heat(point) for point in row.points] if value is not None]
    return heat_values[-1] - heat_values[-2] if len(heat_values) > 1 else None


def score_average(values: list[int | float]) -> float | None:
    """Return average score value."""
    return round(sum(float(value) for value in values) / len(values), 1) if values else None


def format_score_summary_value(value: int | float | None) -> str:
    """Format score summary values."""
    if value is None:
        return "-"
    return f"{float(value):.1f}".removesuffix(".0")


def format_setup_score(value: int | None) -> str:
    """Format latest scanner setup score."""
    return "-" if value is None else f"{int(value)}/8"


def format_level_score(score: int | None, normalized: float | None, count: int) -> str:
    """Format latest weighted level score."""
    if score is None:
        return "-"
    normalized_text = "" if normalized is None else f" ({float(normalized):.1f}%)"
    count_text = f" / {count} levels" if count > 0 else ""
    return f"{int(score):,}{normalized_text}{count_text}"


def format_score_delta(value: int | float | None) -> str:
    """Return score-delta markup."""
    if value is None:
        return '<span class="streamlit-score-delta neutral">-</span>'
    number = float(value)
    tone = "positive" if number > 0 else "negative" if number < 0 else "neutral"
    formatted = f"{number:+.1f}".removesuffix(".0")
    return f'<span class="streamlit-score-delta {tone}">{escape(formatted)}</span>'


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
    render_html_component(
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
      const intradayIntervals = new Set(["1m", "2m", "5m", "15m", "30m", "1h"]);
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
    configured_count = normalize_news_count(st.session_state.get("news_per_ticker", NEWS_EXPANDED_HEADLINE_COUNT))
    visible_count = configured_count if expanded else min(NEWS_COLLAPSED_HEADLINE_COUNT, configured_count)
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
    render_html_component(
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


def pct_fmt(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}%"


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


def render_streamlit_scanner_sort_controls(scanner_view: str) -> None:
    """Render compact scanner sort controls for card-capable layouts."""
    if scanner_view == "table":
        return
    if st.session_state.get("scanner_sort_key") not in SCANNER_SORT_OPTIONS:
        st.session_state.scanner_sort_key = "score"
    if st.session_state.get("scanner_sort_direction") not in {"desc", "asc"}:
        st.session_state.scanner_sort_direction = "desc"
    render_index = int(st.session_state.get("_scanner_sort_render_index", 0)) + 1
    st.session_state._scanner_sort_render_index = render_index
    sort_key = f"scanner_sort_key_control_{render_index}"
    direction_key = f"scanner_sort_direction_control_{render_index}"
    st.session_state[sort_key] = st.session_state.scanner_sort_key
    st.session_state[direction_key] = st.session_state.scanner_sort_direction
    sort_col, direction_col = st.columns([1, 0.42], vertical_alignment="center")
    with sort_col:
        st.selectbox(
            "Scanner sort",
            tuple(SCANNER_SORT_OPTIONS),
            format_func=lambda value: SCANNER_SORT_OPTIONS.get(value, value),
            key=sort_key,
            on_change=sync_streamlit_scanner_sort_control,
            args=(sort_key, "scanner_sort_key"),
        )
    with direction_col:
        st.radio(
            "Direction",
            ("desc", "asc"),
            format_func=lambda value: "Desc" if value == "desc" else "Asc",
            horizontal=True,
            key=direction_key,
            on_change=sync_streamlit_scanner_sort_control,
            args=(direction_key, "scanner_sort_direction"),
        )


def sync_streamlit_scanner_sort_control(widget_key: str, target_key: str) -> None:
    """Copy a unique scanner sort widget value into the canonical setting."""
    st.session_state[target_key] = st.session_state.get(widget_key, st.session_state.get(target_key))


def scanner_sort_value(row: ScannerSetupRow, key: str) -> object:
    """Return a stable display-sort value for one scanner row."""
    value = getattr(row, key, None)
    if isinstance(value, str):
        return value.casefold()
    return value


def sorted_scanner_response(report: ScannerResponse) -> ScannerResponse:
    """Return a copy of the scanner response sorted by Streamlit controls."""
    key = st.session_state.get("scanner_sort_key", "score")
    if key not in SCANNER_SORT_OPTIONS:
        key = "score"
    direction = st.session_state.get("scanner_sort_direction", "desc")
    filled: list[ScannerSetupRow] = []
    empty: list[ScannerSetupRow] = []
    for row in report.setup_rows:
        value = scanner_sort_value(row, key)
        if value is None or value == "":
            empty.append(row)
        else:
            filled.append(row)
    filled.sort(key=lambda row: scanner_sort_value(row, key), reverse=direction == "desc")
    return report.model_copy(update={"setup_rows": filled + empty})


def render_scanner(report: ScannerResponse) -> None:
    """Render setup scanner rows."""
    visible_warnings, pattern_notes = split_scanner_global_messages(report.warnings)
    for warning in visible_warnings:
        st.warning(warning)
    render_scanner_global_notes("scanner pattern note(s)", pattern_notes)

    if not report.setup_rows:
        st.info("No setup scanner rows were returned.")
        return

    scanner_view = normalize_scanner_view(st.session_state.get("scanner_view", STREAMLIT_DEFAULT_SETTINGS["scanner_view"]))
    render_streamlit_scanner_sort_controls(scanner_view)
    st.markdown(scanner_setup_html(sorted_scanner_response(report), scanner_view), unsafe_allow_html=True)


def render_pattern_analysis(report: Any) -> None:
    """Render intraday pattern sections shared by analytics surfaces."""
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


def render_sector_analytics(report: SectorAnalyticsResponse) -> None:
    """Render sector analytics and intraday pattern sections."""
    for warning in report.warnings:
        if not warning.startswith("No pattern data was returned for "):
            st.warning(warning)
    pattern_notes = [warning for warning in report.warnings if warning.startswith("No pattern data was returned for ")]
    render_scanner_global_notes("pattern data note(s)", pattern_notes)

    st.subheader("Sector Coverage")
    if report.sector_rows:
        coverage_cards = []
        for row in report.sector_rows:
            coverage_cards.append(
                (
                    '<article class="streamlit-market-tile">'
                    f"<h4>{escape(row.sector)}</h4>"
                    f'<div class="streamlit-market-price">{row.weight_percent:.1f}%</div>'
                    f'<div class="streamlit-market-change">{row.ticker_count} ticker{"s" if row.ticker_count != 1 else ""}: '
                    f"{escape(', '.join(row.tickers))}</div>"
                    "</article>"
                )
            )
        st.markdown(f'<div class="streamlit-market-grid">{"".join(coverage_cards)}</div>', unsafe_allow_html=True)
    else:
        st.info("No sector coverage was returned.")

    st.subheader("Recommendations")
    if report.recommendations:
        for item in report.recommendations:
            tickers = f" ({', '.join(item.tickers)})" if item.tickers else ""
            st.markdown(
                f'<div class="streamlit-takeaway"><strong>{escape(item.title)}</strong>{escape(tickers)}<br>{escape(item.message)}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("No sector recommendations were returned.")

    st.subheader("Sector Trends")
    if report.sector_rows:
        st.dataframe(
            sector_analytics_frame(report),
            use_container_width=True,
            hide_index=True,
            row_height=40,
            height=dataframe_height(len(report.sector_rows), row_height=40),
        )
    else:
        st.info("No sector trend rows were returned.")

    st.subheader("Intraday Pattern Analysis")
    render_pattern_analysis(report)


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


def scanner_tone_class(tone: str | None) -> str:
    """Return a supported scanner tone class suffix."""
    return tone if tone in {"strong", "good", "watch", "danger", "neutral", "info"} else "neutral"


def scanner_dash_html() -> str:
    """Return muted scanner empty-cell markup."""
    return '<span class="streamlit-scanner-muted">&mdash;</span>'


def scanner_pill_html(label: str, tone: str | None, *, extra_class: str = "", title: str | None = None) -> str:
    """Return a compact scanner pill."""
    classes = f"streamlit-scanner-pill tone-{scanner_tone_class(tone)}"
    if extra_class:
        classes = f"{classes} {extra_class}"
    title_attr = f' title="{escape(title)}" aria-label="{escape(title)}"' if title else ""
    return f'<span class="{classes}"{title_attr}>{escape(label)}</span>'


def scanner_empty_pill_html(*, extra_class: str = "") -> str:
    """Return a neutral empty-state pill."""
    classes = "streamlit-scanner-pill tone-neutral"
    if extra_class:
        classes = f"{classes} {extra_class}"
    return f'<span class="{classes}">&mdash;</span>'


def scanner_text_html(label: str | None, tone: str | None = None) -> str:
    """Return colored scanner text, or a muted dash when no label is available."""
    if not label:
        return scanner_dash_html()
    return f'<span class="streamlit-scanner-text tone-{scanner_tone_class(tone)}">{escape(label)}</span>'


def scanner_titled_text_html(label: str | None, tone: str | None = None, *, title: str | None = None) -> str:
    """Return colored scanner text with the full source label preserved in a title."""
    if not label:
        return scanner_dash_html()
    title_attr = f' title="{escape(title)}"' if title else ""
    return f'<span class="streamlit-scanner-text tone-{scanner_tone_class(tone)}"{title_attr}>{escape(label)}</span>'


def scanner_score_tone(score: int | None) -> str:
    """Return scanner setup-score tone."""
    if score is None:
        return "neutral"
    if score >= 7:
        return "strong"
    if score >= 5:
        return "good"
    if score >= 3:
        return "watch"
    return "danger"


def scanner_score_html(score: int | None) -> str:
    """Return visible setup score with a background fill."""
    if score is None:
        return scanner_empty_pill_html(extra_class="streamlit-scanner-score")
    number = max(0, min(8, int(score)))
    width = round((number / 8) * 100, 1)
    tone = scanner_score_tone(number)
    return (
        f'<span class="streamlit-scanner-score tone-{tone}" style="--score-width:{width}%;" '
        f'title="{number}/8 setup score" aria-label="{number} out of 8 setup score">'
        f"<span>{number}/8</span>"
        "</span>"
    )


def scanner_confidence_tone(value: int | None) -> str:
    """Return tone for support/resistance confidence."""
    if value is None:
        return "neutral"
    if value >= 80:
        return "strong"
    if value >= 65:
        return "good"
    if value >= 50:
        return "watch"
    return "danger"


def scanner_confidence_html(value: int | None) -> str:
    """Return support/resistance confidence pill."""
    if value is None:
        return scanner_empty_pill_html()
    return scanner_pill_html(str(value), scanner_confidence_tone(value), title=f"{value} confidence")


def scanner_risk_reward_tone(value: float | None) -> str:
    """Return tone for risk/reward."""
    if value is None:
        return "neutral"
    if value >= 3:
        return "strong"
    if value >= 2:
        return "good"
    if value >= 1:
        return "watch"
    return "danger"


def scanner_risk_reward_html(value: float | None) -> str:
    """Return risk/reward pill."""
    if value is None:
        return scanner_empty_pill_html()
    label = f"{value:.1f}R"
    return scanner_pill_html(label, scanner_risk_reward_tone(value), title=f"{label} risk/reward")


def scanner_lows_held_html(value: int | None) -> str:
    """Return lows-held pill."""
    if not value:
        return scanner_empty_pill_html()
    tone = "strong" if value >= 3 else "good" if value >= 2 else "watch"
    return scanner_pill_html(f"{value}x", tone, title=f"{value} lows held")


def scanner_range_html(value: str | None) -> str:
    """Return range-compression symbol."""
    if not value:
        return scanner_empty_pill_html()
    symbol = "T" if value == "Tight" else "W" if value == "Wide" else "0"
    tone = "good" if value == "Tight" else "danger" if value == "Wide" else "neutral"
    return scanner_pill_html(symbol, tone, extra_class="streamlit-scanner-symbol", title=value)


def scanner_momentum_html(value: str | None) -> str:
    """Return momentum symbol."""
    if not value:
        return scanner_empty_pill_html()
    if value == "Turning Up":
        symbol, tone = "++", "strong"
    elif value == "Ticking Up":
        symbol, tone = "+", "good"
    elif value == "Still Falling":
        symbol, tone = "--", "danger"
    else:
        symbol, tone = "0", "neutral"
    return scanner_pill_html(symbol, tone, extra_class="streamlit-scanner-symbol", title=value)


def scanner_metric_combo_html(value: str | None, symbol: str, tone: str, title: str | None) -> str:
    """Return a numeric value with a compact status symbol."""
    if not value:
        return scanner_dash_html()
    full_title = title or value
    return (
        f'<span class="streamlit-scanner-metric-combo" title="{escape(full_title)}" aria-label="{escape(full_title)}">'
        f"<span>{escape(value)}</span>"
        f'{scanner_pill_html(symbol, tone, extra_class="streamlit-scanner-symbol", title=full_title)}'
        "</span>"
    )


def scanner_signal_html(value: str | None) -> str:
    """Return compact signal text."""
    if not value:
        return scanner_dash_html()
    if value.startswith("Reclaimed "):
        return scanner_titled_text_html(f"+ {value.replace('Reclaimed ', '')}", "strong", title=value)
    if value.startswith("Rejecting "):
        return scanner_titled_text_html(f"- {value.replace('Rejecting ', '')}", "danger", title=value)
    return scanner_titled_text_html(value, scanner_signal_tone(value), title=value)


def scanner_vwap_tone(percent: float | None, label: str | None) -> str:
    """Return VWAP extension tone."""
    text = label or ""
    if percent is None:
        return "neutral"
    if "Chase" in text or "Below" in text or percent < -0.75:
        return "danger"
    if "Extended" in text or percent >= 0.75:
        return "watch"
    if "Near" in text or percent < 0:
        return "info"
    return "good"


def scanner_vwap_symbol(percent: float | None, label: str | None) -> str:
    """Return compact VWAP state symbol."""
    text = label or ""
    if percent is None:
        return "0"
    if "Chase" in text or "Extended" in text or percent >= 0.75:
        return "!"
    if "Below" in text or percent < -0.75:
        return "-"
    if "Near" in text or "Inline" in text or percent < 0:
        return "0"
    return "+"


def scanner_vwap_html(percent: float | None, label: str | None) -> str:
    """Return VWAP percent with compact status symbol."""
    if percent is None:
        return scanner_text_html(label, "neutral") if label else scanner_dash_html()
    return scanner_metric_combo_html(
        f"{percent:+.2f}%",
        scanner_vwap_symbol(percent, label),
        scanner_vwap_tone(percent, label),
        label or "VWAP extension",
    )


def scanner_relative_strength_tone(percent: float | None, label: str | None) -> str:
    """Return relative-strength tone."""
    text = label or ""
    if percent is None:
        return "neutral"
    if "Strong" in text and "↑↑" in text:
        return "strong"
    if "Strong" in text:
        return "good"
    if "Weak" in text:
        return "danger"
    return "neutral"


def scanner_relative_strength_symbol(percent: float | None, label: str | None) -> str:
    """Return compact relative-strength symbol."""
    text = label or ""
    if percent is None:
        return "0"
    if "Very Weak" in text or "↓↓" in text or percent <= -2:
        return "--"
    if "Weak" in text or percent < -0.75:
        return "-"
    if "↑↑" in text or percent >= 2:
        return "++"
    if "Strong" in text or percent > 0.75:
        return "+"
    return "0"


def scanner_relative_strength_html(percent: float | None, label: str | None) -> str:
    """Return relative-strength percent with compact status symbol."""
    if percent is None:
        return scanner_text_html(label, "neutral") if label else scanner_dash_html()
    return scanner_metric_combo_html(
        f"{percent:+.2f}%",
        scanner_relative_strength_symbol(percent, label),
        scanner_relative_strength_tone(percent, label),
        label or "Relative strength inline",
    )


def scanner_signal_tone(value: str | None) -> str:
    """Return reclaim/rejection signal tone."""
    text = value or ""
    if text.startswith("Reclaimed"):
        return "strong"
    if text.startswith("Rejecting"):
        return "danger"
    return "neutral"


def scanner_setup_distance_tone(value: float | None) -> str:
    """Return tone for distance from setup level."""
    if value is None:
        return "neutral"
    distance = abs(value)
    if distance <= 0.25:
        return "strong"
    if distance <= 0.5:
        return "good"
    if distance <= 1:
        return "watch"
    return "neutral"


def scanner_off_high_tone(value: float | None) -> str:
    """Return tone for distance from session high."""
    if value is None:
        return "neutral"
    if value > 0:
        return "strong"
    if -3 <= value <= -0.5:
        return "good"
    if -0.5 < value <= 0:
        return "watch"
    return "danger"


def scanner_percent_html(value: float | None, tone: str | None) -> str:
    """Return colored percent text."""
    if value is None:
        return scanner_dash_html()
    return scanner_text_html(f"{value:.2f}%", tone)


def scanner_plain_html(value: object) -> str:
    """Return escaped plain scanner cell text."""
    if value is None or value == "":
        return scanner_dash_html()
    return escape(str(value))


def scanner_zone_html(zone: str | None, reason: str | None) -> str:
    """Return support/resistance zone markup with an optional evidence subline."""
    if not zone:
        return scanner_dash_html()
    reason_html = f'<span class="streamlit-scanner-reason">{escape(reason)}</span>' if reason else ""
    return f'<span class="streamlit-scanner-zone">{escape(zone)}</span>{reason_html}'


def scanner_data_notes_html(report: ScannerResponse) -> str:
    """Return escaped scanner data notes markup."""
    notes = [(row.ticker, note) for row in report.setup_rows for note in row.data_notes]
    if not notes:
        return ""
    items = "".join(f"<li><strong>{escape(ticker)}:</strong> {escape(note)}</li>" for ticker, note in notes)
    label = "scanner data note" if len(notes) == 1 else "scanner data notes"
    return (
        '<details class="streamlit-scanner-data-notes">'
        f"<summary>{len(notes)} {label}</summary>"
        f"<ul>{items}</ul>"
        "</details>"
    )


def scanner_setup_table_html(report: ScannerResponse, *, include_notes: bool = True) -> str:
    """Return an app-owned HTML setup scanner table with reliable visual cues."""
    columns = [
        ("score", "Score", "Setup score", "align-center"),
        ("ticker", "Ticker", "Ticker", ""),
        ("price", "Price", "Current price", "align-right"),
        ("signal", "Sig", "Signal", ""),
        ("vwap", "VWAP", "VWAP extension", "align-center"),
        ("rs-spy", "RS SPY", "Relative strength versus SPY", "align-center"),
        ("rs-sector", "RS Sec", "Relative strength versus sector ETF", "align-center"),
        ("support", "Support", "Best support", "wrap"),
        ("support-confidence", "S Conf", "Support confidence", "align-center"),
        ("resistance", "Resist", "Best resistance", "wrap"),
        ("resistance-confidence", "R Conf", "Resistance confidence", "align-center"),
        ("risk-reward", "R/R", "Risk/reward", "align-center"),
        ("setup-level", "Setup", "Setup level", ""),
        ("setup-distance", "Away", "Distance from setup level", "align-right"),
        ("lows-held", "Lows", "Lows held", "align-center"),
        ("range", "Range", "Range compression", "align-center"),
        ("off-high", "High", "Distance from high", "align-right"),
        ("momentum", "Mom", "Momentum", "align-center"),
    ]
    def cell_class(key: str, css_class: str) -> str:
        return " ".join(part for part in (f"streamlit-scanner-cell-{key}", css_class) if part)

    header_html = "".join(
        f'<th class="{cell_class(key, css_class)}" title="{escape(title)}">{escape(label)}</th>'
        for key, label, title, css_class in columns
    )
    body_rows: list[str] = []
    for row in report.setup_rows:
        score_tone = scanner_score_tone(row.score)
        cells = [
            ("score", "align-center", scanner_score_html(row.score)),
            ("ticker", "", f'<span class="streamlit-scanner-ticker">{escape(row.ticker)}</span>'),
            ("price", "align-right", scanner_plain_html(fmt(row.price))),
            ("signal", "", scanner_signal_html(row.signal)),
            ("vwap", "align-center", scanner_vwap_html(row.vwap_extension_percent, row.vwap_extension_label)),
            ("rs-spy", "align-center", scanner_relative_strength_html(row.rs_vs_spy_percent, row.rs_vs_spy_label)),
            ("rs-sector", "align-center", scanner_relative_strength_html(row.rs_vs_sector_percent, row.rs_vs_sector_label)),
            ("support", "wrap", scanner_zone_html(row.best_support, row.support_reason)),
            ("support-confidence", "align-center", scanner_confidence_html(row.support_confidence)),
            ("resistance", "wrap", scanner_zone_html(row.best_resistance, row.resistance_reason)),
            ("resistance-confidence", "align-center", scanner_confidence_html(row.resistance_confidence)),
            ("risk-reward", "align-center", scanner_risk_reward_html(row.risk_reward)),
            ("setup-level", "", scanner_plain_html(row.setup_level)),
            ("setup-distance", "align-right", scanner_percent_html(row.setup_distance_percent, scanner_setup_distance_tone(row.setup_distance_percent))),
            ("lows-held", "align-center", scanner_lows_held_html(row.lows_held)),
            ("range", "align-center", scanner_range_html(row.range_compression)),
            ("off-high", "align-right", scanner_percent_html(row.off_high_percent, scanner_off_high_tone(row.off_high_percent))),
            ("momentum", "align-center", scanner_momentum_html(row.momentum)),
        ]
        cell_html = "".join(f'<td class="{cell_class(key, css_class)}">{cell}</td>' for key, css_class, cell in cells)
        body_rows.append(f'<tr class="tone-{score_tone}">{cell_html}</tr>')
        if row.warnings:
            warnings = " ".join(escape(warning) for warning in row.warnings)
            body_rows.append(
                f'<tr class="streamlit-scanner-warning-row"><td colspan="{len(columns)}">'
                f"<strong>{escape(row.ticker)}:</strong> {warnings}</td></tr>"
            )
    return (
        '<div class="streamlit-scanner-table-wrap">'
        '<table class="streamlit-scanner-table">'
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
        "</div>"
        f"{scanner_data_notes_html(report) if include_notes else ''}"
    )


def scanner_card_metric_html(label: str, value: str, *, wide: bool = False) -> str:
    """Return one metric tile for Streamlit scanner cards."""
    wide_class = " wide" if wide else ""
    return (
        f'<div class="streamlit-scanner-card-metric{wide_class}">'
        f"<span>{escape(label)}</span>"
        f"<div>{value}</div>"
        "</div>"
    )


def scanner_setup_cards_html(report: ScannerResponse) -> str:
    """Return responsive card markup for setup scanner rows."""
    cards: list[str] = []
    for row in report.setup_rows:
        tone = scanner_score_tone(row.score)
        warning_html = ""
        if row.warnings:
            warnings = " ".join(escape(warning) for warning in row.warnings)
            warning_html = f'<p class="streamlit-scanner-card-warning"><strong>{escape(row.ticker)}:</strong> {warnings}</p>'
        cards.append(
            '<article class="streamlit-scanner-card '
            f'tone-{tone}">'
            '<header class="streamlit-scanner-card-header">'
            f"<div><h3>{escape(row.ticker)}</h3><span>{escape(fmt(row.price))}</span></div>"
            f"{scanner_score_html(row.score)}"
            "</header>"
            '<div class="streamlit-scanner-card-primary">'
            f'{scanner_card_metric_html("Signal", scanner_signal_html(row.signal), wide=True)}'
            f'{scanner_card_metric_html("R/R", scanner_risk_reward_html(row.risk_reward))}'
            f'{scanner_card_metric_html("Setup", scanner_plain_html(row.setup_level))}'
            f'{scanner_card_metric_html("Away", scanner_percent_html(row.setup_distance_percent, scanner_setup_distance_tone(row.setup_distance_percent)))}'
            "</div>"
            '<div class="streamlit-scanner-card-zones">'
            f'{scanner_card_metric_html("Support", scanner_zone_html(row.best_support, row.support_reason), wide=True)}'
            f'{scanner_card_metric_html("S Conf", scanner_confidence_html(row.support_confidence))}'
            f'{scanner_card_metric_html("Resist", scanner_zone_html(row.best_resistance, row.resistance_reason), wide=True)}'
            f'{scanner_card_metric_html("R Conf", scanner_confidence_html(row.resistance_confidence))}'
            "</div>"
            '<div class="streamlit-scanner-card-secondary">'
            f'{scanner_card_metric_html("VWAP", scanner_vwap_html(row.vwap_extension_percent, row.vwap_extension_label))}'
            f'{scanner_card_metric_html("RS SPY", scanner_relative_strength_html(row.rs_vs_spy_percent, row.rs_vs_spy_label))}'
            f'{scanner_card_metric_html("RS Sec", scanner_relative_strength_html(row.rs_vs_sector_percent, row.rs_vs_sector_label))}'
            f'{scanner_card_metric_html("Lows", scanner_lows_held_html(row.lows_held))}'
            f'{scanner_card_metric_html("Range", scanner_range_html(row.range_compression))}'
            f'{scanner_card_metric_html("High", scanner_percent_html(row.off_high_percent, scanner_off_high_tone(row.off_high_percent)))}'
            f'{scanner_card_metric_html("Mom", scanner_momentum_html(row.momentum))}'
            "</div>"
            f"{warning_html}"
            "</article>"
        )
    return '<div class="streamlit-scanner-card-list">' + "".join(cards) + "</div>"


def scanner_setup_html(report: ScannerResponse, scanner_view: str = "auto") -> str:
    """Return scanner setup markup for the selected responsive view."""
    view = normalize_scanner_view(scanner_view)
    return (
        f'<div class="streamlit-scanner-render view-{view}">'
        '<section class="streamlit-scanner-table-panel">'
        f"{scanner_setup_table_html(report, include_notes=False)}"
        "</section>"
        '<section class="streamlit-scanner-card-panel">'
        f"{scanner_setup_cards_html(report)}"
        "</section>"
        "</div>"
        f"{scanner_data_notes_html(report)}"
    )


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


def sector_analytics_frame(report: SectorAnalyticsResponse) -> pd.DataFrame:
    """Build a display frame for sector trend analytics."""
    return pd.DataFrame(
        [
            {
                "Sector": row.sector,
                "ETF": row.etf or "-",
                "Weight": f"{row.weight_percent:.1f}%",
                "Tickers": ", ".join(row.tickers),
                "Avg Day": signed_pct_fmt(row.average_day_change_percent),
                "ETF Day": signed_pct_fmt(row.sector_etf_day_change_percent),
                "RS vs SPY": signed_pct_fmt(row.average_rs_vs_spy_percent),
                "RS vs Sec": signed_pct_fmt(row.average_rs_vs_sector_percent),
                "Setup": f"{row.average_setup_score:.2f}" if row.average_setup_score is not None else "-",
                "Strong": row.strong_setup_count,
                "Pattern": f"{row.average_pattern_consistency_percent:.2f}%"
                if row.average_pattern_consistency_percent is not None
                else "-",
                "Avg Dip": pct_fmt(row.average_dip_percent),
                "Recovery": signed_pct_fmt(row.average_recovery_percent),
                "Low Times": ", ".join(row.common_low_times) or "-",
                "Read": row.recommendation_tone,
            }
            for row in report.sector_rows
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


def ensure_streamlit_settings() -> None:
    """Initialize Streamlit session settings from persisted state."""
    if st.session_state.get("streamlit_settings_loaded"):
        return
    settings = load_streamlit_settings()
    st.session_state.active_view = settings["default_view"]
    st.session_state.report_layout = settings["report_layout"]
    st.session_state.level_filter = settings["level_filter"]
    st.session_state.level_weights = settings["level_weights"]
    st.session_state.scanner_view = settings["scanner_view"]
    st.session_state["global-chart-type"] = settings["chart_type"]
    st.session_state.chart_range = settings["chart_range"]
    st.session_state.chart_interval = settings["chart_interval"]
    st.session_state.auto_load_saved_watchlist = settings["auto_load"]
    st.session_state.auto_refresh_enabled = settings["auto_refresh"]
    st.session_state.news_per_ticker = settings["news_per_ticker"]
    st.session_state.streamlit_settings_loaded = True


def current_streamlit_settings() -> dict[str, Any]:
    """Return normalized settings from the current Streamlit session."""
    chart_range = normalize_chart_range(st.session_state.get("chart_range"))
    return normalize_streamlit_settings(
        {
            "default_view": st.session_state.get("active_view", LEVELS_VIEW),
            "report_layout": st.session_state.get("report_layout", DEFAULT_REPORT_LAYOUT),
            "level_filter": st.session_state.get("level_filter", DEFAULT_LEVEL_FILTER),
            "level_weights": st.session_state.get("level_weights", {}),
            "scanner_view": st.session_state.get("scanner_view", STREAMLIT_DEFAULT_SETTINGS["scanner_view"]),
            "chart_type": st.session_state.get("global-chart-type", "Line"),
            "chart_range": chart_range,
            "chart_interval": st.session_state.get("chart_interval", CHART_DEFAULT_INTERVAL_BY_RANGE[chart_range]),
            "auto_load": st.session_state.get("auto_load_saved_watchlist", True),
            "auto_refresh": st.session_state.get("auto_refresh_enabled", True),
            "news_per_ticker": st.session_state.get("news_per_ticker", NEWS_EXPANDED_HEADLINE_COUNT),
        }
    )


def persist_session_settings() -> None:
    """Persist current Streamlit settings without changing the saved watchlist."""
    save_streamlit_settings(current_streamlit_settings())


def persist_session_watchlist() -> None:
    """Persist the current Streamlit session watchlist."""
    st.session_state.watchlist_tickers = normalize_ticker_list(list(st.session_state.watchlist_tickers))
    save_streamlit_watchlist(list(st.session_state.watchlist_tickers))


def streamlit_level_weight_slug(label: str) -> str:
    """Return a stable widget-key slug for a level weight label."""
    slug = "".join(char.lower() if char.isalnum() else "_" for char in label).strip("_")
    return "_".join(part for part in slug.split("_") if part)


def streamlit_level_weight_widget_key(label: str, kind: str) -> str:
    """Return the Streamlit widget key for one level weight control."""
    return f"streamlit_level_weight_{kind}_{streamlit_level_weight_slug(label)}"


def sync_streamlit_level_weight(label: str, source_key: str) -> None:
    """Persist a custom level weight and sync its paired widget."""
    defaults = level_type_weight_defaults()
    if label not in defaults:
        return
    weight = normalize_level_weight(st.session_state.get(source_key))
    if weight is None:
        return

    next_weights = normalize_level_weights(st.session_state.get("level_weights", {}))
    if weight == defaults[label]:
        next_weights.pop(label, None)
    else:
        next_weights[label] = weight
    st.session_state.level_weights = next_weights

    slider_key = streamlit_level_weight_widget_key(label, "slider")
    number_key = streamlit_level_weight_widget_key(label, "number")
    st.session_state[slider_key] = weight
    st.session_state[number_key] = weight
    persist_session_settings()


def reset_streamlit_level_weights() -> None:
    """Reset Streamlit level weights to backend defaults."""
    st.session_state.level_weights = {}
    for label, default_weight in level_type_weight_defaults().items():
        st.session_state[streamlit_level_weight_widget_key(label, "slider")] = default_weight
        st.session_state[streamlit_level_weight_widget_key(label, "number")] = default_weight
    persist_session_settings()


def render_streamlit_advanced_controls() -> None:
    """Render report-only level weight controls in the Streamlit sidebar."""
    ensure_streamlit_settings()
    st.session_state.level_weights = normalize_level_weights(st.session_state.get("level_weights", {}))
    defaults = level_type_weight_defaults()
    active_weights = active_streamlit_level_weights()

    with st.expander("Advanced Controls", expanded=False):
        st.button(
            "Reset weights",
            key="streamlit-level-weights-reset",
            use_container_width=True,
            disabled=not bool(st.session_state.level_weights),
            on_click=reset_streamlit_level_weights,
        )
        for label, default_weight in defaults.items():
            weight = active_weights[label]
            slider_key = streamlit_level_weight_widget_key(label, "slider")
            number_key = streamlit_level_weight_widget_key(label, "number")
            st.session_state.setdefault(slider_key, weight)
            st.session_state.setdefault(number_key, weight)
            if st.session_state[slider_key] != weight:
                st.session_state[slider_key] = weight
            if st.session_state[number_key] != weight:
                st.session_state[number_key] = weight

            slider_col, number_col = st.columns([3, 1], vertical_alignment="center")
            with slider_col:
                st.slider(
                    label,
                    min_value=LEVEL_WEIGHT_MIN,
                    max_value=LEVEL_WEIGHT_MAX,
                    step=1,
                    key=slider_key,
                    on_change=sync_streamlit_level_weight,
                    args=(label, slider_key),
                )
            with number_col:
                st.number_input(
                    "Weight",
                    min_value=LEVEL_WEIGHT_MIN,
                    max_value=LEVEL_WEIGHT_MAX,
                    step=1,
                    key=number_key,
                    label_visibility="collapsed",
                    on_change=sync_streamlit_level_weight,
                    args=(label, number_key),
                )
            current_weight = active_streamlit_level_weights()[label]
            if current_weight == default_weight:
                st.caption(f"Default {default_weight}")
            else:
                st.caption(f"Custom, default {default_weight}")


def render_streamlit_settings_panel() -> None:
    """Render persistent Streamlit preferences in a right-side overlay panel."""
    ensure_streamlit_settings()
    settings = current_streamlit_settings()
    st.session_state.settings_default_view = settings["default_view"]
    st.session_state.settings_report_layout = settings["report_layout"]
    st.session_state.settings_level_filter = settings["level_filter"]
    st.session_state.settings_scanner_view = settings["scanner_view"]
    st.session_state.settings_chart_type = settings["chart_type"]
    st.session_state.settings_chart_range = settings["chart_range"]
    st.session_state.settings_chart_interval = settings["chart_interval"]
    st.session_state.settings_auto_load = settings["auto_load"]
    st.session_state.settings_auto_refresh = settings["auto_refresh"]
    st.session_state.settings_news_per_ticker = settings["news_per_ticker"]

    with st.container():
        st.markdown('<span class="streamlit-settings-panel-marker"></span>', unsafe_allow_html=True)
        title_col, collapse_col = st.columns([1, 0.24], vertical_alignment="center")
        with title_col:
            st.markdown('<h2 class="streamlit-settings-title">Settings</h2>', unsafe_allow_html=True)
        with collapse_col:
            st.button(
                "<<",
                key="streamlit-settings-collapse",
                help="Collapse settings",
                use_container_width=True,
                on_click=close_streamlit_settings_panel,
            )
        st.selectbox(
            "Default view",
            STREAMLIT_VIEWS,
            key="settings_default_view",
        )
        st.toggle("Auto-load saved watchlist", key="settings_auto_load")
        st.toggle("Auto-refresh every minute", key="settings_auto_refresh")
        st.selectbox(
            "Report view",
            report_layout_options(),
            format_func=report_layout_label,
            key="settings_report_layout",
        )
        st.selectbox(
            "Level filter",
            LEVEL_FILTER_OPTIONS,
            format_func=level_filter_label,
            key="settings_level_filter",
        )
        st.selectbox(
            "Scanner view",
            SCANNER_VIEW_OPTIONS,
            format_func=lambda value: SCANNER_VIEW_LABELS.get(value, value),
            key="settings_scanner_view",
        )
        st.radio("Chart type", CHART_TYPE_OPTIONS, horizontal=True, key="settings_chart_type")
        chart_range = st.selectbox(
            "Chart range",
            CHART_RANGE_OPTIONS,
            key="settings_chart_range",
            format_func=format_chart_option,
        )
        interval_options = CHART_INTERVALS_BY_RANGE[chart_range]
        if st.session_state.settings_chart_interval not in interval_options:
            st.session_state.settings_chart_interval = CHART_DEFAULT_INTERVAL_BY_RANGE[chart_range]
        st.selectbox("Chart interval", interval_options, key="settings_chart_interval")
        st.slider(
            "Headlines per ticker",
            min_value=1,
            max_value=NEWS_MAX_HEADLINE_COUNT,
            key="settings_news_per_ticker",
        )

    changed = (
        settings["default_view"] != st.session_state.settings_default_view
        or settings["report_layout"] != st.session_state.settings_report_layout
        or settings["level_filter"] != st.session_state.settings_level_filter
        or settings["scanner_view"] != st.session_state.settings_scanner_view
        or settings["chart_type"] != st.session_state.settings_chart_type
        or settings["chart_range"] != st.session_state.settings_chart_range
        or settings["chart_interval"] != st.session_state.settings_chart_interval
        or settings["auto_load"] != st.session_state.settings_auto_load
        or settings["auto_refresh"] != st.session_state.settings_auto_refresh
        or settings["news_per_ticker"] != st.session_state.settings_news_per_ticker
    )
    if not changed:
        return

    st.session_state.active_view = st.session_state.settings_default_view
    st.session_state.report_layout = st.session_state.settings_report_layout
    st.session_state.level_filter = st.session_state.settings_level_filter
    st.session_state.scanner_view = normalize_scanner_view(st.session_state.settings_scanner_view)
    st.session_state["global-chart-type"] = st.session_state.settings_chart_type
    st.session_state.chart_range = st.session_state.settings_chart_range
    st.session_state.chart_interval = st.session_state.settings_chart_interval
    st.session_state.auto_load_saved_watchlist = bool(st.session_state.settings_auto_load)
    st.session_state.auto_refresh_enabled = bool(st.session_state.settings_auto_refresh)
    st.session_state.news_per_ticker = normalize_news_count(st.session_state.settings_news_per_ticker)
    if settings["news_per_ticker"] != st.session_state.news_per_ticker:
        bump_streamlit_refresh_token("Refreshing news", datasets=("news",))
    if (
        settings["chart_type"] != st.session_state["global-chart-type"]
        or settings["chart_range"] != st.session_state.chart_range
        or settings["chart_interval"] != st.session_state.chart_interval
    ):
        bump_streamlit_refresh_token("Refreshing charts", datasets=("chart",))
    persist_session_settings()
    st.rerun()


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
    st.button("Add", type="primary", use_container_width=True, on_click=add_pending_tickers)
    if st.session_state.get("watchlist_validation_message"):
        st.warning(str(st.session_state.watchlist_validation_message))

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
    render_streamlit_advanced_controls()
    return tuple(st.session_state.watchlist_tickers)


def load_streamlit_data(tickers: tuple[str, ...], metrics: tuple[MetricName, ...], refresh_token: int) -> None:
    """Load all Streamlit datasets for the current watchlist."""
    st.session_state.report = build_report(tickers, metrics, refresh_token=refresh_token)
    st.session_state.scanner = build_scanner(tickers, refresh_token=refresh_token)
    record_streamlit_score_history(st.session_state.report, st.session_state.scanner)
    st.session_state.sector_analytics = build_sector_analytics(tickers, refresh_token=refresh_token)
    st.session_state.market_snapshot = build_market_snapshot(tickers, refresh_token=refresh_token)
    st.session_state.news = build_news(
        tickers,
        per_ticker=normalize_news_count(st.session_state.get("news_per_ticker", NEWS_EXPANDED_HEADLINE_COUNT)),
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
    if st.session_state.get("sector_analytics") is not None:
        loaded.append("sector_analytics")
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
        record_streamlit_score_history(report=st.session_state.report)

    def load_scanner() -> None:
        st.session_state.scanner = build_scanner(tickers, refresh_token=dataset_refresh_token("scanner"))
        record_streamlit_score_history(scanner=st.session_state.scanner)

    def load_analytics() -> None:
        st.session_state.sector_analytics = build_sector_analytics(
            tickers,
            refresh_token=dataset_refresh_token("sector_analytics"),
        )

    def load_headlines() -> None:
        st.session_state.news = build_news(
            tickers,
            per_ticker=normalize_news_count(st.session_state.get("news_per_ticker", NEWS_EXPANDED_HEADLINE_COUNT)),
            refresh_token=dataset_refresh_token("news"),
        )

    def load_snapshot() -> None:
        st.session_state.market_snapshot = build_market_snapshot(tickers, refresh_token=dataset_refresh_token("market_snapshot"))

    all_steps: dict[str, RefreshStep] = {
        "report": ("Calculating levels...", load_levels),
        "scanner": ("Running scanner...", load_scanner),
        "sector_analytics": ("Refreshing sector analytics...", load_analytics),
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
    if view == ANALYTICS_VIEW:
        return ("sector_analytics",)
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
    persist_session_settings()
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
    selected = str(
        st.selectbox(
            "View",
            report_layout_options(),
            format_func=report_layout_label,
            key="report_layout",
        )
    )
    persist_session_settings()
    return selected


def render_level_filter_selector() -> str:
    """Render and persist the Streamlit Levels card filter selector."""
    st.session_state.level_filter = normalize_level_filter(st.session_state.get("level_filter", DEFAULT_LEVEL_FILTER))
    selected = str(
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
    st.session_state.score_level_basis = selected
    persist_session_settings()
    return selected


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
    metrics_by_ticker = {metric.ticker: metric for metric in normalize_equity_metrics(report.metrics)}
    metrics_by_ticker.update({metric.ticker: metric for metric in normalize_equity_metrics(updates)})
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
    score_slot: Any | None = None,
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

        render_metric_grid(
            visible_metrics,
            report_layout,
            level_filter=level_filter,
            level_type_weights=active_streamlit_level_weights(),
        )

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
                use_container_width=True,
                )

    if complete and chart_slot is not None:
        chart_slot.empty()
        with chart_slot.container():
            if visible_metrics:
                chart_type, chart_range, chart_interval = render_streamlit_chart_controls()
                render_chart_history(
                    report,
                    chart_range,
                    chart_interval,
                    chart_type,
                    refresh_token=dataset_refresh_token("chart"),
                    visible_tickers=tuple(metric.ticker for metric in visible_metrics),
                )
            elif report_search:
                st.caption("Charts hidden because the ticker search has no matches.")

    if complete and score_slot is not None:
        score_slot.empty()
        with score_slot.container():
            render_score_analytics(
                report,
                visible_tickers=tuple(metric.ticker for metric in visible_metrics),
                search_query=report_search,
            )


def render_report_panel_in_slot(
    slot: Any,
    report: GenerateResponse,
    *,
    complete: bool,
    total_tickers: int | None = None,
    chart_slot: Any | None = None,
    score_slot: Any | None = None,
) -> None:
    """Replace the report placeholder with the latest report render."""
    slot.empty()
    with slot.container():
        render_report_panel(
            report,
            complete=complete,
            total_tickers=total_tickers,
            chart_slot=chart_slot,
            score_slot=score_slot,
        )


def render_scanner_panel_in_slot(slot: Any, scanner: ScannerResponse) -> None:
    """Replace the scanner placeholder with the rendered scanner table."""
    slot.empty()
    with slot.container():
        with st.container(border=True):
            st.subheader("Scanner")
            render_scanner(scanner)


def load_levels_and_scanner_progressively(
    tickers: tuple[str, ...],
    metrics: tuple[MetricName, ...],
    report_slot: Any,
    scanner_slot: Any,
    refresh_slot: Any,
    chart_slot: Any | None = None,
    score_slot: Any | None = None,
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
    if score_slot is not None:
        score_slot.empty()

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
            metrics=normalize_equity_metrics(
                market_data.build_metrics(list(batch), list(selected_metrics), include_earnings=False)
            ),
        )

    def load_scanner_batch(batch: tuple[str, ...], refresh_token: int) -> ScannerResponse:
        del refresh_token
        return normalize_scanner_response(
            scanner.build_scanner(list(batch), include_setup=True, include_patterns=False, include_earnings=False)
        )

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
                partial_metrics.extend(normalize_equity_metrics(event.report.metrics))
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
                scanner_responses.append(normalize_scanner_response(event.scanner))
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
            final_scanner = ScannerService.replace_setup_rows(
                tickers,
                normalize_scanner_response(final_scanner),
                [normalize_scanner_response(scanner_update)],
            )
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
    record_streamlit_score_history(final_report, final_scanner)
    return final_report, final_scanner


def main() -> None:
    """Run the Streamlit application."""
    view = render_app_chrome()
    refresh_banner_slot = st.empty()
    if st.session_state.get("settings_panel_open"):
        render_streamlit_settings_panel()

    with st.sidebar:
        st.header("Controls")
        tickers = render_streamlit_watchlist_controls()

    if "report" not in st.session_state:
        st.session_state.report = None
    if "news" not in st.session_state:
        st.session_state.news = None
    if "scanner" not in st.session_state:
        st.session_state.scanner = None
    if "sector_analytics" not in st.session_state:
        st.session_state.sector_analytics = None
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

    auto_refresh_enabled = bool(st.session_state.get("auto_refresh_enabled", True))
    auto_load_enabled = bool(st.session_state.get("auto_load_saved_watchlist", True))
    render_auto_refresh_fragment(bool(tickers) and auto_refresh_enabled, view)
    refresh_token = int(st.session_state.streamlit_refresh_token)
    manual_refresh_loaded = False

    autoload_metrics = tuple(DEFAULT_METRICS)
    try:
        autoload_request = GenerateRequest(tickers=list(tickers), metrics=list(autoload_metrics))
    except ValidationError:
        autoload_request = None
    if not auto_load_enabled and not st.session_state.get("auto_refresh_pending_datasets"):
        autoload_request = None

    if view == LEVELS_VIEW:
        with st.container():
            heading_col, action_col = st.columns([2.2, 1], vertical_alignment="center")
            with heading_col:
                st.markdown('<span class="view-hero-marker"></span>', unsafe_allow_html=True)
                st.title("Investment Trading Levels")
            with action_col:
                generate = st.button("Run Levels + Scanner", type="primary", use_container_width=True)
            levels_status_slot = st.empty()
            if st.session_state.levels_status:
                levels_status_slot.success(st.session_state.levels_status)
        refresh_news = False
        refresh_analytics = False
        scanner_slot = st.empty()
        report_slot = st.empty()
        chart_slot = st.empty()
        score_slot = st.empty()
    elif view == ANALYTICS_VIEW:
        with st.container():
            heading_col, action_col = st.columns([2.2, 1], vertical_alignment="center")
            with heading_col:
                st.markdown('<span class="view-hero-marker"></span>', unsafe_allow_html=True)
                st.title("Sector Analytics")
            with action_col:
                refresh_analytics = st.button("Refresh Analytics", type="primary", use_container_width=True)
        generate = False
        refresh_news = False
        report_slot = None
        chart_slot = None
        score_slot = None
        scanner_slot = None
    else:
        with st.container():
            heading_col, action_col = st.columns([2.2, 1], vertical_alignment="center")
            with heading_col:
                st.markdown('<span class="view-hero-marker"></span>', unsafe_allow_html=True)
                st.title("Stock News")
            with action_col:
                refresh_news = st.button("Refresh News", type="primary", use_container_width=True)
        generate = False
        refresh_analytics = False
        report_slot = None
        chart_slot = None
        score_slot = None
        scanner_slot = None

    if generate:
        try:
            request = GenerateRequest(tickers=list(tickers), metrics=list(DEFAULT_METRICS))
        except ValidationError as exc:
            st.error(exc.errors()[0]["msg"])
            return

        refresh_token = bump_streamlit_refresh_token("Running levels and scanner", datasets=("report", "scanner"))
        load_levels_and_scanner_progressively(
            tuple(request.tickers),
            tuple(request.metrics),
            report_slot,
            scanner_slot,
            refresh_banner_slot,
            chart_slot,
            score_slot,
        )
        mark_streamlit_data_current(tuple(request.tickers), tuple(request.metrics), datasets=("report", "scanner"))
        st.session_state.levels_status = ""
        manual_refresh_loaded = True

    if refresh_news:
        try:
            request = NewsRequest(
                tickers=list(tickers),
                per_ticker=normalize_news_count(st.session_state.get("news_per_ticker", NEWS_EXPANDED_HEADLINE_COUNT)),
            )
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
        manual_refresh_loaded = True

    if refresh_analytics:
        try:
            request = ScannerRequest(tickers=list(tickers))
        except ValidationError as exc:
            st.error(exc.errors()[0]["msg"])
            return

        refresh_token = bump_streamlit_refresh_token("Refreshing sector analytics", datasets=("sector_analytics",))

        def refresh_sector_analytics() -> None:
            st.session_state.sector_analytics = build_sector_analytics(
                tuple(request.tickers),
                refresh_token=dataset_refresh_token("sector_analytics"),
            )

        run_refresh_steps(
            refresh_banner_slot,
            "Refreshing sector analytics",
            [("Refreshing sector analytics...", refresh_sector_analytics)],
        )
        mark_streamlit_data_current(
            tuple(request.tickers),
            autoload_metrics,
            refresh_token,
            datasets=("sector_analytics",),
        )
        manual_refresh_loaded = True

    if autoload_request is not None:
        autoload_tickers = tuple(autoload_request.tickers)
        autoload_metrics_tuple = tuple(autoload_request.metrics)
        pending_auto_refresh_datasets = tuple(st.session_state.pop("auto_refresh_pending_datasets", ()))
        autoload_datasets = merge_streamlit_datasets(
            streamlit_autoload_datasets(view),
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
                    score_slot,
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
    elif not manual_refresh_loaded:
        st.session_state.report = None
        st.session_state.scanner = None
        st.session_state.sector_analytics = None
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

    if view == ANALYTICS_VIEW:
        analytics: SectorAnalyticsResponse | None = st.session_state.sector_analytics
        if analytics is None:
            return
        render_sector_analytics(analytics)
        return

    report: GenerateResponse | None = st.session_state.report
    if report is not None and report_slot is not None:
        render_report_panel_in_slot(report_slot, report, complete=True, chart_slot=chart_slot, score_slot=score_slot)

    scanner: ScannerResponse | None = st.session_state.scanner
    if scanner is not None and scanner_slot is not None:
        render_scanner_panel_in_slot(scanner_slot, scanner)


if __name__ == "__main__":
    main()
