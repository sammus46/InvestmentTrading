"""Pydantic schemas for the equity levels API."""

from __future__ import annotations

from datetime import date as Date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

MetricName = Literal[
    "previous_day",
    "premarket",
    "previous_session_vwap_5m",
    "fifty_two_week",
    "earnings_gap",
    "first_five_minutes",
    "swing_levels",
    "bollinger_bands",
]

DEFAULT_METRICS: tuple[MetricName, ...] = (
    "previous_day",
    "premarket",
    "previous_session_vwap_5m",
    "fifty_two_week",
    "earnings_gap",
    "first_five_minutes",
    "swing_levels",
    "bollinger_bands",
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
    data_timestamp: datetime
    warnings: list[str] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    """Metrics report response."""

    generated_at: datetime
    metrics: list[EquityMetrics]
