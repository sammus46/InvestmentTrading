"""Pydantic schemas for the equity levels API."""

from __future__ import annotations

from datetime import date as Date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MetricName = Literal[
    "previous_day",
    "premarket",
    "previous_session_vwap_5m",
    "fifty_two_week",
    "earnings_gap",
    "first_five_minutes",
    "swing_levels",
    "bollinger_bands",
    "technical_levels",
]
NewsCategory = Literal["rating_changes", "contracts", "earnings", "general"]
ChartRange = Literal["1D", "WTD", "5D", "MTD", "1M", "QTD", "3M", "6M", "YTD", "1Y", "2Y", "5Y"]
ChartInterval = Literal["1m", "2m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"]
DisplayRowKind = Literal["price", "percent", "date", "text"]
DisplayRowEmphasis = Literal["normal", "priority", "current"]
ReportLayoutName = Literal["grid", "price_ladder", "compact", "compare"]

CHART_INTERVALS_BY_RANGE: dict[ChartRange, tuple[ChartInterval, ...]] = {
    "1D": ("1m", "2m", "5m", "15m", "30m", "1h"),
    "WTD": ("1m", "2m", "5m", "15m", "30m", "1h"),
    "5D": ("1m", "2m", "5m", "15m", "30m", "1h"),
    "MTD": ("5m", "15m", "30m", "1h", "1d"),
    "1M": ("5m", "15m", "30m", "1h", "1d"),
    "QTD": ("1h", "1d", "1wk"),
    "3M": ("1h", "1d", "1wk"),
    "6M": ("1h", "1d", "1wk"),
    "YTD": ("1d", "1wk", "1mo"),
    "1Y": ("1d", "1wk", "1mo"),
    "2Y": ("1d", "1wk", "1mo"),
    "5Y": ("1d", "1wk", "1mo"),
}

CHART_DEFAULT_INTERVAL_BY_RANGE: dict[ChartRange, ChartInterval] = {
    "1D": "5m",
    "WTD": "5m",
    "5D": "5m",
    "MTD": "15m",
    "1M": "15m",
    "QTD": "1h",
    "3M": "1h",
    "6M": "1d",
    "YTD": "1d",
    "1Y": "1d",
    "2Y": "1wk",
    "5Y": "1mo",
}

DEFAULT_METRICS: tuple[MetricName, ...] = (
    "previous_day",
    "premarket",
    "previous_session_vwap_5m",
    "fifty_two_week",
    "earnings_gap",
    "first_five_minutes",
    "swing_levels",
    "bollinger_bands",
    "technical_levels",
)


class GenerateRequest(BaseModel):
    """Request payload containing one or more ticker symbols and selected metrics."""

    tickers: Annotated[list[str], Field(min_length=1, max_length=50)]
    metrics: list[MetricName] = Field(default_factory=lambda: list(DEFAULT_METRICS), min_length=1)

    @field_validator("tickers", mode="before")
    @classmethod
    def split_ticker_input(cls, value: object) -> list[str]:
        """Accept either a list or comma/space/newline separated ticker text."""
        if isinstance(value, str):
            candidates = value.replace(",", " ").split()
        elif isinstance(value, list):
            candidates = [str(item) for item in value]
        else:
            raise ValueError("tickers must be a list or delimited string")

        cleaned: list[str] = []
        for candidate in candidates:
            ticker = candidate.strip().upper()
            if ticker and ticker not in cleaned:
                cleaned.append(ticker)
        if not cleaned:
            raise ValueError("at least one ticker is required")
        return cleaned

    @field_validator("metrics", mode="before")
    @classmethod
    def normalize_metrics(cls, value: object) -> list[MetricName]:
        """Deduplicate selected metric names while preserving client order."""
        candidates = list(DEFAULT_METRICS) if value is None else value
        if isinstance(candidates, str):
            candidates = candidates.replace(",", " ").split()
        if not isinstance(candidates, list):
            raise ValueError("metrics must be a list or delimited string")

        cleaned: list[MetricName] = []
        allowed = set(DEFAULT_METRICS)
        for candidate in candidates:
            metric = str(candidate).strip()
            if metric not in allowed:
                raise ValueError(f"unsupported metric: {metric}")
            if metric not in cleaned:
                cleaned.append(metric)  # type: ignore[arg-type]
        if not cleaned:
            raise ValueError("at least one metric is required")
        return cleaned


class MetricDefinition(BaseModel):
    """Frontend-facing metadata for one selectable metric."""

    id: MetricName
    label: str
    group: str
    default: bool = True
    order: int


class DisplayRow(BaseModel):
    """Formatted report display value for web, Streamlit, and PDF renderers."""

    label: str
    value: str | None = None
    values: list[str] = Field(default_factory=list)
    kind: DisplayRowKind = "text"
    numeric_value: float | None = None
    numeric_values: list[float] = Field(default_factory=list)
    emphasis: DisplayRowEmphasis = "normal"


class DisplaySection(BaseModel):
    """Formatted report display section with scalar rows and level lists."""

    title: str
    rows: list[DisplayRow] = Field(default_factory=list)
    lists: list[DisplayRow] = Field(default_factory=list)


class ChartRangeConfig(BaseModel):
    """Frontend-facing chart interval configuration for one range."""

    intervals: list[ChartInterval]
    default_interval: ChartInterval


class ReportLayoutDefinition(BaseModel):
    """Frontend-facing metadata for one report layout option."""

    id: ReportLayoutName
    label: str
    description: str
    order: int
    default: bool = False


class AppConfigResponse(BaseModel):
    """Configuration values shared by backend and browser clients."""

    metrics: list[MetricDefinition]
    chart_ranges: dict[ChartRange, ChartRangeConfig]
    report_layouts: list[ReportLayoutDefinition] = Field(default_factory=list)
    default_report_layout: ReportLayoutName = "grid"


class Ohlc(BaseModel):
    """Open/high/low/close pricing for a session."""

    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None


class PremarketRange(BaseModel):
    """Premarket high/low and sample count."""

    high: float | None = None
    low: float | None = None
    bars: int = 0


class OpeningRange(BaseModel):
    """Opening regular-session high/low and sample count."""

    high: float | None = None
    low: float | None = None
    bars: int = 0
    minutes: int = 5


class FiftyTwoWeekRange(BaseModel):
    """Completed-session 52-week high/low range."""

    high: float | None = None
    low: float | None = None


class EarningsGap(BaseModel):
    """Most recent earnings date and opening gap from the prior close."""

    date: Date | None = None
    gap: float | None = None
    gap_percent: float | None = None
    open: float | None = None
    previous_close: float | None = None
    is_stale: bool = False


class SwingLevels(BaseModel):
    """Major daily swing high/low price levels."""

    highs: list[float] = Field(default_factory=list)
    lows: list[float] = Field(default_factory=list)
    window: int = 10
    merge_percent: float = 0.003


class BollingerLevels(BaseModel):
    """Daily Bollinger Band levels."""

    upper: float | None = None
    middle: float | None = None
    lower: float | None = None
    period: int = 20
    standard_deviations: float = 2.0


class TechnicalLevels(BaseModel):
    """Adam-aligned technical and formula levels for the report table."""

    current_price: float | None = None
    today_vwap: float | None = None
    one_month_high: float | None = None
    one_month_low: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_20_daily: float | None = None
    ema_9_5m: float | None = None
    ema_20_5m: float | None = None
    pivot: float | None = None
    r1: float | None = None
    s1: float | None = None
    r2: float | None = None
    s2: float | None = None
    fib_618: float | None = None
    fib_500: float | None = None
    fib_382: float | None = None
    earnings_open: float | None = None
    pre_earnings_close: float | None = None


class PricePoint(BaseModel):
    """Daily close used by web and PDF charts."""

    date: Date
    close: float


class IntradayPricePoint(BaseModel):
    """Intraday close used by web charts and market snapshot sparklines."""

    timestamp: datetime
    close: float


class ChartOhlcPoint(BaseModel):
    """OHLC bar used by broker-style web charts."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float


class EquityMetrics(BaseModel):
    """Calculated metrics for a single equity."""

    ticker: str
    selected_metrics: list[MetricName] = Field(default_factory=lambda: list(DEFAULT_METRICS))
    previous_day: Ohlc
    premarket: PremarketRange
    previous_session_vwap_5m: float | None = None
    fifty_two_week: FiftyTwoWeekRange
    earnings_gap: EarningsGap
    first_five_minutes: OpeningRange
    swing_levels: SwingLevels
    bollinger_bands: BollingerLevels
    technical_levels: TechnicalLevels
    price_history: list[PricePoint] = Field(default_factory=list)
    intraday_history: list[IntradayPricePoint] = Field(default_factory=list)
    data_timestamp: datetime
    warnings: list[str] = Field(default_factory=list)
    display_sections: list[DisplaySection] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    """Metrics report response."""

    generated_at: datetime
    metrics: list[EquityMetrics]


class ScannerRequest(BaseModel):
    """Request payload for setup and intraday pattern scanning."""

    tickers: Annotated[list[str], Field(min_length=1, max_length=50)]
    include_setup: bool = True
    include_patterns: bool = True
    pattern_lookback_days: int = Field(default=30, ge=5, le=58)

    @field_validator("tickers", mode="before")
    @classmethod
    def split_ticker_input(cls, value: object) -> list[str]:
        """Accept either a list or comma/space/newline separated ticker text."""
        return GenerateRequest.split_ticker_input(value)


class ScannerSetupRow(BaseModel):
    """One ticker row in the setup scanner."""

    ticker: str
    price: float | None = None
    score: int | None = None
    signal: str | None = None
    vwap_extension_label: str | None = None
    vwap_extension_percent: float | None = None
    rs_vs_spy_label: str | None = None
    rs_vs_spy_percent: float | None = None
    rs_vs_sector_label: str | None = None
    rs_vs_sector_percent: float | None = None
    best_support: str | None = None
    support_confidence: int | None = None
    support_reason: str | None = None
    best_resistance: str | None = None
    resistance_confidence: int | None = None
    resistance_reason: str | None = None
    risk_reward: float | None = None
    setup_level: str | None = None
    setup_distance_percent: float | None = None
    consecutive_bars: int | None = None
    lows_held: int | None = None
    range_compression: str | None = None
    off_high_percent: float | None = None
    momentum: str | None = None
    warnings: list[str] = Field(default_factory=list)
    data_notes: list[str] = Field(default_factory=list)


class PatternSummaryRow(BaseModel):
    """Summary of recurring intraday dip behavior for one ticker."""

    sector: str = "Other"
    ticker: str
    total_days: int
    dip_days: int
    consistency_percent: int
    average_dip_percent: float
    average_recovery_percent: float
    common_low_time: str | None = None
    top_low_times: list[str] = Field(default_factory=list)


class PatternHeatmapRow(BaseModel):
    """Average percent-from-open values by 5-minute time bucket."""

    ticker: str
    sector: str = "Other"
    values: list[float | None] = Field(default_factory=list)


class PatternDayDetail(BaseModel):
    """Day-by-day intraday pattern details for one ticker."""

    ticker: str
    date: Date
    morning_low_percent: float
    morning_low_time: str
    recovery_to_close_percent: float
    dip_in_window: bool
    day_low_percent: float
    day_low_time: str
    close_from_open_percent: float


class ScannerResponse(BaseModel):
    """Setup scanner and intraday pattern analysis response."""

    generated_at: datetime
    watchlist: list[str]
    setup_rows: list[ScannerSetupRow] = Field(default_factory=list)
    pattern_summary: list[PatternSummaryRow] = Field(default_factory=list)
    pattern_buckets: list[str] = Field(default_factory=list)
    pattern_bucket_labels: list[str] = Field(default_factory=list)
    pattern_heatmap: list[PatternHeatmapRow] = Field(default_factory=list)
    pattern_details: list[PatternDayDetail] = Field(default_factory=list)
    takeaways: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class NewsRequest(BaseModel):
    """Request payload for watchlist and market news."""

    tickers: Annotated[list[str], Field(min_length=1, max_length=50)]
    per_ticker: int = Field(default=5, ge=1, le=20)
    general_count: int = Field(default=8, ge=1, le=20)

    @field_validator("tickers", mode="before")
    @classmethod
    def split_ticker_input(cls, value: object) -> list[str]:
        """Accept either a list or comma/space/newline separated ticker text."""
        return GenerateRequest.split_ticker_input(value)


class NewsArticle(BaseModel):
    """Normalized news article data returned by the configured market data provider."""

    title: str
    url: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    summary: str | None = None
    thumbnail_url: str | None = None
    related_tickers: list[str] = Field(default_factory=list)
    category: NewsCategory = "general"


class TickerNews(BaseModel):
    """News articles and provider warnings for one ticker."""

    ticker: str
    articles: list[NewsArticle] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class NewsResponse(BaseModel):
    """Watchlist and general market news response."""

    generated_at: datetime
    watchlist: list[str]
    general_market: list[NewsArticle] = Field(default_factory=list)
    ticker_news: list[TickerNews] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MarketSnapshotRequest(BaseModel):
    """Request payload for major market and watchlist performance snapshots."""

    tickers: Annotated[list[str], Field(min_length=1, max_length=50)]

    @field_validator("tickers", mode="before")
    @classmethod
    def split_ticker_input(cls, value: object) -> list[str]:
        """Accept either a list or comma/space/newline separated ticker text."""
        return GenerateRequest.split_ticker_input(value)


class MarketSnapshotRow(BaseModel):
    """Latest day-to-date performance for one market instrument or ticker."""

    symbol: str
    label: str
    price: float | None = None
    previous_close: float | None = None
    change: float | None = None
    change_percent: float | None = None
    sparkline: list[IntradayPricePoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MarketSnapshotResponse(BaseModel):
    """Major market and watchlist day-to-date performance snapshot."""

    generated_at: datetime
    market: list[MarketSnapshotRow] = Field(default_factory=list)
    watchlist: list[MarketSnapshotRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ChartHistoryRequest(BaseModel):
    """Request payload for broker-style OHLC chart history."""

    tickers: Annotated[list[str], Field(min_length=1, max_length=50)]
    range: ChartRange = "1D"
    interval: ChartInterval = "5m"

    @field_validator("tickers", mode="before")
    @classmethod
    def split_ticker_input(cls, value: object) -> list[str]:
        """Accept either a list or comma/space/newline separated ticker text."""
        return GenerateRequest.split_ticker_input(value)

    @model_validator(mode="after")
    def validate_range_interval(self) -> "ChartHistoryRequest":
        """Reject range/interval combinations that yfinance does not reliably support."""
        if self.interval not in CHART_INTERVALS_BY_RANGE[self.range]:
            supported = ", ".join(CHART_INTERVALS_BY_RANGE[self.range])
            raise ValueError(f"unsupported interval {self.interval} for range {self.range}; use one of: {supported}")
        return self


class TickerChartHistory(BaseModel):
    """OHLC chart history for one ticker."""

    ticker: str
    range: ChartRange
    interval: ChartInterval
    points: list[ChartOhlcPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ChartHistoryResponse(BaseModel):
    """Broker-style chart history response."""

    generated_at: datetime
    range: ChartRange
    interval: ChartInterval
    charts: list[TickerChartHistory] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
