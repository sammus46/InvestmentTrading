"""Pure price-level calculation helpers.

These functions intentionally avoid provider APIs and application orchestration
so scanner, report, and future providers can share the same calculation rules.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from app.models import FiftyTwoWeekRange, Ohlc

EASTERN = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
PREMARKET_OPEN = time(4, 0)


def with_eastern_index(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of a price frame indexed in US/Eastern time."""
    localized = frame.copy()
    index = pd.DatetimeIndex(localized.index)
    if index.tz is None:
        index = index.tz_localize(timezone.utc)
    localized.index = index.tz_convert(EASTERN)
    return localized


def exclude_current_eastern_day(frame: pd.DataFrame) -> pd.DataFrame:
    """Remove today's Eastern-calendar row from completed-session calculations."""
    if frame.empty:
        return frame
    index = pd.DatetimeIndex(frame.index)
    if index.tz is not None:
        index = index.tz_convert(EASTERN)
    today = datetime.now(EASTERN).date()
    return frame[index.date < today]


def latest_session_bars(frame: pd.DataFrame) -> pd.DataFrame:
    """Return bars from the newest session date present in a frame."""
    if frame.empty:
        return frame
    session_dates = sorted(set(pd.DatetimeIndex(frame.index).date))
    if not session_dates:
        return frame.iloc[0:0]
    return frame[frame.index.date == session_dates[-1]]


def today_session_bars(frame: pd.DataFrame) -> pd.DataFrame:
    """Return bars from today's Eastern-calendar session."""
    if frame.empty:
        return frame
    today = datetime.now(EASTERN).date()
    return frame[pd.DatetimeIndex(frame.index).date == today]


def previous_day_ohlc(daily: pd.DataFrame, warnings: list[str]) -> Ohlc:
    """Return previous completed-session OHLC levels."""
    if daily.empty:
        warnings.append("Daily OHLC data was unavailable.")
        return Ohlc()

    completed = daily.dropna(subset=["Open", "High", "Low", "Close"])
    completed = exclude_current_eastern_day(completed)
    if completed.empty:
        warnings.append("Daily OHLC data did not include a previous completed session.")
        return Ohlc()

    row = completed.iloc[-1]
    return Ohlc(
        open=round(float(row["Open"]), 2),
        high=round(float(row["High"]), 2),
        low=round(float(row["Low"]), 2),
        close=round(float(row["Close"]), 2),
    )


def fifty_two_week_range(daily: pd.DataFrame, warnings: list[str]) -> FiftyTwoWeekRange:
    """Return completed-session 52-week high/low levels."""
    if daily.empty:
        warnings.append("Daily data was unavailable for the 52-week range.")
        return FiftyTwoWeekRange()

    completed = daily.dropna(subset=["High", "Low"])
    completed = exclude_current_eastern_day(completed)
    if completed.empty:
        warnings.append("Daily data did not include completed sessions for the 52-week range.")
        return FiftyTwoWeekRange()

    return FiftyTwoWeekRange(
        high=round(float(completed["High"].astype(float).max()), 2),
        low=round(float(completed["Low"].astype(float).min()), 2),
    )


def monthly_range(daily: pd.DataFrame, warnings: list[str]) -> tuple[float | None, float | None]:
    """Return the past 22 completed-session high and low."""
    if daily.empty:
        warnings.append("Daily data was unavailable for the 1-month range.")
        return None, None
    completed = daily.dropna(subset=["High", "Low"])
    completed = exclude_current_eastern_day(completed).tail(22)
    if completed.empty:
        warnings.append("Daily data did not include completed sessions for the 1-month range.")
        return None, None
    return round(float(completed["High"].astype(float).max()), 2), round(float(completed["Low"].astype(float).min()), 2)


def vwap(session: pd.DataFrame, warnings: list[str]) -> float | None:
    """Calculate volume-weighted average price from OHLCV bars."""
    if session.empty:
        return None
    required = {"High", "Low", "Close", "Volume"}
    if not required.issubset(session.columns):
        warnings.append("VWAP could not be calculated because intraday bars were incomplete.")
        return None

    priced = session.dropna(subset=["High", "Low", "Close", "Volume"])
    volume = priced["Volume"].astype(float)
    total_volume = float(volume.sum())
    if priced.empty or total_volume == 0:
        warnings.append("VWAP could not be calculated because volume was zero or missing.")
        return None

    typical_price = (priced["High"].astype(float) + priced["Low"].astype(float) + priced["Close"].astype(float)) / 3
    return round(float((typical_price * volume).sum() / total_volume), 2)


def sma(daily: pd.DataFrame, period: int, warnings: list[str]) -> float | None:
    """Calculate a completed-session simple moving average."""
    completed = exclude_current_eastern_day(daily.dropna(subset=["Close"])) if not daily.empty else daily
    if completed.empty or len(completed) < period:
        warnings.append(f"At least {period} completed daily closes are required for {period} SMA.")
        return None
    return round(float(completed["Close"].astype(float).tail(period).mean()), 2)


def daily_ema(daily: pd.DataFrame, period: int, warnings: list[str]) -> float | None:
    """Calculate a completed-session exponential moving average."""
    completed = exclude_current_eastern_day(daily.dropna(subset=["Close"])) if not daily.empty else daily
    if completed.empty or len(completed) < period:
        warnings.append(f"At least {period} completed daily closes are required for {period} EMA.")
        return None
    return round(float(completed["Close"].astype(float).ewm(span=period, adjust=False).mean().iloc[-1]), 2)


def pivot_points(previous_day: Ohlc) -> dict[str, float | None]:
    """Return classic floor trader pivot points from prior day H/L/C."""
    if previous_day.high is None or previous_day.low is None or previous_day.close is None:
        return {"pivot": None, "r1": None, "s1": None, "r2": None, "s2": None}
    pivot = round((previous_day.high + previous_day.low + previous_day.close) / 3, 2)
    return {
        "pivot": pivot,
        "r1": round(2 * pivot - previous_day.low, 2),
        "s1": round(2 * pivot - previous_day.high, 2),
        "r2": round(pivot + (previous_day.high - previous_day.low), 2),
        "s2": round(pivot - (previous_day.high - previous_day.low), 2),
    }


def fibonacci_levels(high: float | None, low: float | None) -> dict[str, float | None]:
    """Return common retracement levels over a high/low range."""
    if high is None or low is None or high <= low:
        return {"fib_382": None, "fib_500": None, "fib_618": None}
    spread = high - low
    return {
        "fib_382": round(low + 0.382 * spread, 2),
        "fib_500": round(low + 0.500 * spread, 2),
        "fib_618": round(low + 0.618 * spread, 2),
    }


def pct_from(price: float | None, level: float | None) -> float | None:
    """Return percent distance from a level."""
    if price is None or level is None or level == 0:
        return None
    return round(((price - level) / level) * 100, 2)


def merge_levels(levels: list[float], max_levels: int, merge_percent: float, descending: bool) -> list[float]:
    """Sort and merge nearby price levels."""
    ordered = sorted(set(levels), reverse=descending)
    merged: list[float] = []
    for level in ordered:
        if not merged:
            merged.append(level)
            continue
        previous = merged[-1]
        if previous == 0 or abs(level - previous) / abs(previous) > merge_percent:
            merged.append(level)
        if len(merged) == max_levels:
            break
    return merged
