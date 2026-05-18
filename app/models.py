"""Pydantic schemas for the equity levels API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class GenerateRequest(BaseModel):
    """Request payload containing one or more ticker symbols."""

    tickers: Annotated[list[str], Field(min_length=1, max_length=50)]

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
    previous_day: Ohlc
    premarket: PremarketRange
    previous_session_vwap_5m: float | None = None
    bollinger_bands: BollingerLevels
    data_timestamp: datetime
    warnings: list[str] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    """Metrics report response."""

    generated_at: datetime
    metrics: list[EquityMetrics]
