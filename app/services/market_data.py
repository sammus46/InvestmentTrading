"""Market data retrieval and metric calculations.

The provider intentionally lives behind a small service class so another free or
paid data source can replace yfinance without touching API routes or UI code.
"""

from __future__ import annotations

import io
import os
from contextlib import redirect_stderr
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

import pandas as pd

from app.models import (
    ChartHistoryResponse,
    ChartInterval,
    ChartOhlcPoint,
    ChartRange,
    DEFAULT_METRICS,
    BollingerLevels,
    EarningsGap,
    EquityMetrics,
    FiftyTwoWeekRange,
    IntradayPricePoint,
    MarketSnapshotResponse,
    MarketSnapshotRow,
    Ohlc,
    MetricName,
    PricePoint,
    OpeningRange,
    PremarketRange,
    SwingLevels,
    TechnicalLevels,
    TickerChartHistory,
)
from app.services import calculations
from app.services.display import build_metric_display_sections
from app.services.providers import MarketDataProvider, YFinanceProvider

EASTERN = calculations.EASTERN
MARKET_OPEN = calculations.MARKET_OPEN
MARKET_CLOSE = calculations.MARKET_CLOSE
PREMARKET_OPEN = calculations.PREMARKET_OPEN

MARKET_SNAPSHOT_INSTRUMENTS: tuple[tuple[str, str], ...] = (
    ("^GSPC", "S&P 500"),
    ("^DJI", "Dow 30"),
    ("^IXIC", "Nasdaq"),
    ("^RUT", "Russell 2000"),
    ("^VIX", "VIX"),
    ("GC=F", "Gold"),
    ("BTC-USD", "Bitcoin USD"),
    ("BZ=F", "Brent Crude Oil"),
)

CHART_DATE_TO_DATE_RANGES = {"WTD", "MTD", "QTD"}

CHART_DOWNLOAD_CONFIG: dict[tuple[ChartRange, ChartInterval], tuple[str | None, str]] = {
    ("1D", "1m"): ("1d", "1m"),
    ("1D", "2m"): ("1d", "2m"),
    ("1D", "5m"): ("1d", "5m"),
    ("1D", "15m"): ("1d", "15m"),
    ("1D", "30m"): ("1d", "30m"),
    ("1D", "1h"): ("1d", "1h"),
    ("WTD", "1m"): (None, "1m"),
    ("WTD", "2m"): (None, "2m"),
    ("WTD", "5m"): (None, "5m"),
    ("WTD", "15m"): (None, "15m"),
    ("WTD", "30m"): (None, "30m"),
    ("WTD", "1h"): (None, "1h"),
    ("5D", "1m"): ("5d", "1m"),
    ("5D", "2m"): ("5d", "2m"),
    ("5D", "5m"): ("5d", "5m"),
    ("5D", "15m"): ("5d", "15m"),
    ("5D", "30m"): ("5d", "30m"),
    ("5D", "1h"): ("5d", "1h"),
    ("MTD", "5m"): (None, "5m"),
    ("MTD", "15m"): (None, "15m"),
    ("MTD", "30m"): (None, "30m"),
    ("MTD", "1h"): (None, "1h"),
    ("MTD", "1d"): (None, "1d"),
    ("1M", "5m"): ("1mo", "5m"),
    ("1M", "15m"): ("1mo", "15m"),
    ("1M", "30m"): ("1mo", "30m"),
    ("1M", "1h"): ("1mo", "1h"),
    ("1M", "1d"): ("1mo", "1d"),
    ("QTD", "1h"): (None, "1h"),
    ("QTD", "1d"): (None, "1d"),
    ("QTD", "1wk"): (None, "1wk"),
    ("3M", "1h"): ("3mo", "1h"),
    ("3M", "1d"): ("3mo", "1d"),
    ("3M", "1wk"): ("3mo", "1wk"),
    ("6M", "1h"): ("6mo", "1h"),
    ("6M", "1d"): ("6mo", "1d"),
    ("6M", "1wk"): ("6mo", "1wk"),
    ("YTD", "1d"): ("ytd", "1d"),
    ("YTD", "1wk"): ("ytd", "1wk"),
    ("YTD", "1mo"): ("ytd", "1mo"),
    ("1Y", "1d"): ("1y", "1d"),
    ("1Y", "1wk"): ("1y", "1wk"),
    ("1Y", "1mo"): ("1y", "1mo"),
    ("2Y", "1d"): ("2y", "1d"),
    ("2Y", "1wk"): ("2y", "1wk"),
    ("2Y", "1mo"): ("2y", "1mo"),
    ("5Y", "1d"): ("5y", "1d"),
    ("5Y", "1wk"): ("5y", "1wk"),
    ("5Y", "1mo"): ("5y", "1mo"),
}


@dataclass(frozen=True)
class MarketDataSettings:
    """Tunable calculation settings for generated levels."""

    bollinger_period: int = 20
    bollinger_standard_deviations: float = 2.0
    daily_history_days: int = 400
    intraday_history_period: str = "5d"
    intraday_interval: str = "5m"
    opening_history_period: str = "1d"
    opening_interval: str = "1m"
    opening_range_minutes: int = 5
    swing_window: int = 10
    max_swing_levels: int = 5
    level_merge_percent: float = 0.003
    chart_history_days: int = 365
    scanner_daily_history_days: int = 400
    pattern_history_period: str = "58d"
    earnings_gap_max_age_days: int = 30


class MarketDataService:
    """Fetch equity data from yfinance and calculate price levels."""

    def __init__(self, settings: MarketDataSettings | None = None, provider: MarketDataProvider | None = None) -> None:
        self.settings = settings or MarketDataSettings()
        self.provider = provider or YFinanceProvider()

    def build_metrics(
        self,
        tickers: list[str],
        metrics: list[MetricName] | None = None,
        *,
        include_history: bool = False,
    ) -> list[EquityMetrics]:
        """Generate metric rows for the requested tickers and selected metrics."""
        selected = metrics or list(DEFAULT_METRICS)
        symbols = [ticker.upper().strip() for ticker in tickers if ticker.strip()]
        self._prefetch_metric_downloads(symbols, selected, include_history=include_history)
        return [self._build_metric(ticker, selected, include_history=include_history) for ticker in tickers]

    def build_market_snapshot(self, tickers: list[str]) -> MarketSnapshotResponse:
        """Return major market and watchlist day-to-date performance."""
        warnings: list[str] = []
        symbols = [symbol for symbol, _ in MARKET_SNAPSHOT_INSTRUMENTS]
        symbols.extend(ticker.upper().strip() for ticker in tickers if ticker.strip())
        self._prefetch_snapshot_downloads(symbols)
        market = [
            self._snapshot_row(symbol=symbol, label=label, warnings=warnings)
            for symbol, label in MARKET_SNAPSHOT_INSTRUMENTS
        ]
        watchlist = [
            self._snapshot_row(symbol=ticker.upper().strip(), label=ticker.upper().strip(), warnings=warnings)
            for ticker in tickers
            if ticker.strip()
        ]
        return MarketSnapshotResponse(
            generated_at=datetime.now(timezone.utc),
            market=market,
            watchlist=watchlist,
            warnings=warnings,
        )

    def build_chart_history(
        self,
        tickers: list[str],
        chart_range: ChartRange,
        interval: ChartInterval,
    ) -> ChartHistoryResponse:
        """Return OHLC chart data for broker-style line and candle charts."""
        warnings: list[str] = []
        self._prefetch_chart_downloads([ticker.upper().strip() for ticker in tickers if ticker.strip()], chart_range, interval)
        charts = [
            self._chart_history_row(ticker.upper().strip(), chart_range, interval, warnings)
            for ticker in tickers
            if ticker.strip()
        ]
        return ChartHistoryResponse(
            generated_at=datetime.now(timezone.utc),
            range=chart_range,
            interval=interval,
            charts=charts,
            warnings=warnings,
        )

    def _build_metric(
        self,
        ticker: str,
        selected_metrics: list[MetricName],
        *,
        include_history: bool = False,
    ) -> EquityMetrics:
        warnings: list[str] = []
        symbol = ticker.upper().strip()

        selected = set(selected_metrics)
        needs_daily = bool(
            {
                "previous_day",
                "fifty_two_week",
                "earnings_gap",
                "swing_levels",
                "bollinger_bands",
                "technical_levels",
            }
            & selected
        ) or include_history
        needs_intraday = bool({"previous_session_vwap_5m", "technical_levels"} & selected) or include_history
        needs_opening_intraday = bool({"premarket", "first_five_minutes", "technical_levels"} & selected)

        daily = (
            self._download_daily_history(symbol)
            if needs_daily
            else pd.DataFrame()
        )
        intraday = (
            self._download(
                symbol,
                period=self.settings.intraday_history_period,
                interval=self.settings.intraday_interval,
                prepost=True,
            )
            if needs_intraday
            else pd.DataFrame()
        )
        opening_intraday = (
            self._download(
                symbol,
                period=self.settings.opening_history_period,
                interval=self.settings.opening_interval,
                prepost=True,
            )
            if needs_opening_intraday
            else pd.DataFrame()
        )

        previous_day_source = (
            self._previous_day_ohlc(daily, warnings)
            if {"previous_day", "technical_levels"} & selected
            else Ohlc()
        )
        previous_day = previous_day_source if "previous_day" in selected else Ohlc()
        bollinger = self._bollinger_bands(daily, warnings) if "bollinger_bands" in selected else BollingerLevels()
        fifty_two_week = (
            self._fifty_two_week_range(daily, warnings) if "fifty_two_week" in selected else FiftyTwoWeekRange()
        )
        earnings_source = (
            self._earnings_gap(symbol, daily, warnings)
            if {"earnings_gap", "technical_levels"} & selected
            else EarningsGap()
        )
        earnings_gap = earnings_source if "earnings_gap" in selected else EarningsGap()
        previous_session = (
            self._previous_regular_session(intraday, warnings)
            if "previous_session_vwap_5m" in selected
            else pd.DataFrame()
        )
        premarket = (
            self._today_premarket_range(opening_intraday, warnings)
            if "premarket" in selected
            else PremarketRange()
        )
        first_five_minutes = (
            self._opening_range(opening_intraday, warnings)
            if "first_five_minutes" in selected
            else OpeningRange(minutes=self.settings.opening_range_minutes)
        )
        vwap = self._vwap(previous_session, warnings) if "previous_session_vwap_5m" in selected else None
        swing_levels = self._swing_levels(daily, warnings) if "swing_levels" in selected else SwingLevels()
        technical_levels = (
            self._technical_levels(
                symbol=symbol,
                daily=daily,
                minute=opening_intraday,
                five_minute=intraday,
                previous_day=previous_day_source,
                earnings_gap=earnings_source,
                warnings=warnings,
            )
            if "technical_levels" in selected
            else TechnicalLevels()
        )
        price_history = self._price_history(daily, warnings) if include_history else []
        intraday_history = self._intraday_price_history(intraday, warnings) if include_history else []

        if daily.empty and intraday.empty and opening_intraday.empty and any(
            [needs_daily, needs_intraday, needs_opening_intraday]
        ):
            warnings.append("No price data returned. Verify the ticker symbol or try again later.")

        metric = EquityMetrics(
            ticker=symbol,
            selected_metrics=selected_metrics,
            previous_day=previous_day,
            premarket=premarket,
            previous_session_vwap_5m=vwap,
            fifty_two_week=fifty_two_week,
            earnings_gap=earnings_gap,
            first_five_minutes=first_five_minutes,
            swing_levels=swing_levels,
            bollinger_bands=bollinger,
            technical_levels=technical_levels,
            price_history=price_history,
            intraday_history=intraday_history,
            data_timestamp=datetime.now(timezone.utc),
            warnings=warnings,
        )
        metric.display_sections = build_metric_display_sections(metric)
        return metric


    def _download_daily_history(self, symbol: str, days: int | None = None) -> pd.DataFrame:
        start, end = self._daily_history_window(days or self.settings.daily_history_days)
        return self._download(symbol, period=None, interval="1d", prepost=False, start=start, end=end)

    @staticmethod
    def _daily_history_window(days: int) -> tuple[datetime, datetime]:
        end = datetime.combine(datetime.now(timezone.utc).date() + timedelta(days=1), time.min, tzinfo=timezone.utc)
        return end - timedelta(days=days), end

    def download_scanner_daily_history(self, symbol: str) -> pd.DataFrame:
        """Return daily bars with enough history for scanner indicators."""
        return self._download_daily_history(symbol, days=self.settings.scanner_daily_history_days)

    def download_today_minute_history(self, symbol: str) -> pd.DataFrame:
        """Return latest 1-minute bars including extended hours."""
        return self._download(symbol, period="1d", interval="1m", prepost=True)

    def download_five_minute_history(self, symbol: str, period: str | None = None) -> pd.DataFrame:
        """Return 5-minute bars for setup and pattern scanning."""
        return self._download(symbol, period=period or self.settings.intraday_history_period, interval="5m", prepost=False)

    def download_pattern_history(self, symbol: str) -> pd.DataFrame:
        """Return 5-minute history for recurring intraday pattern analysis."""
        return self._download(
            symbol,
            period=self.settings.pattern_history_period,
            interval="5m",
            prepost=False,
        )

    def ticker_sector(self, symbol: str) -> str | None:
        """Return sector metadata for scanner relative-strength grouping."""
        return self.provider.sector(symbol)

    def current_price(self, symbol: str, minute_frame: pd.DataFrame, warnings: list[str]) -> float | None:
        """Return the freshest available price using configured provider fallbacks."""
        return self._current_price(symbol, minute_frame, warnings)

    def previous_day_ohlc(self, daily: pd.DataFrame, warnings: list[str]) -> Ohlc:
        """Return previous completed-session OHLC levels."""
        return self._previous_day_ohlc(daily, warnings)

    def monthly_range(self, daily: pd.DataFrame, warnings: list[str]) -> tuple[float | None, float | None]:
        """Return the past 22 completed-session high and low."""
        return self._monthly_range(daily, warnings)

    def previous_regular_session(self, intraday: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
        """Return previous completed regular-session intraday bars."""
        return self._previous_regular_session(intraday, warnings)

    def today_regular_session(self, intraday: pd.DataFrame) -> pd.DataFrame:
        """Return today's regular-session intraday bars."""
        return self._today_regular_session(intraday)

    def today_premarket_range(self, intraday: pd.DataFrame, warnings: list[str]) -> PremarketRange:
        """Return today's premarket high/low range."""
        return self._today_premarket_range(intraday, warnings)

    def opening_range(self, intraday: pd.DataFrame, warnings: list[str]) -> OpeningRange:
        """Return today's configured opening high/low range."""
        return self._opening_range(intraday, warnings)

    def vwap(self, session: pd.DataFrame, warnings: list[str]) -> float | None:
        """Calculate VWAP for a prepared OHLCV session."""
        return self._vwap(session, warnings)

    def today_vwap(self, intraday: pd.DataFrame, warnings: list[str]) -> float | None:
        """Calculate VWAP from today's regular-session bars."""
        return self._today_vwap(intraday, warnings)

    def sma(self, daily: pd.DataFrame, period: int, warnings: list[str]) -> float | None:
        """Calculate a completed-session SMA."""
        return self._sma(daily, period, warnings)

    def daily_ema(self, daily: pd.DataFrame, period: int, warnings: list[str]) -> float | None:
        """Calculate a completed-session daily EMA."""
        return self._daily_ema(daily, period, warnings)

    def intraday_ema(self, intraday: pd.DataFrame, period: int, warnings: list[str]) -> float | None:
        """Calculate an intraday EMA from today's regular-session bars."""
        return self._intraday_ema(intraday, period, warnings)

    def pivot_points(self, previous_day: Ohlc) -> dict[str, float | None]:
        """Return classic floor trader pivot points from prior day H/L/C."""
        return self._pivot_points(previous_day)

    def fibonacci_levels(self, high: float | None, low: float | None) -> dict[str, float | None]:
        """Return common retracement levels over a high/low range."""
        return self._fibonacci_levels(high, low)

    def earnings_gap(self, symbol: str, daily: pd.DataFrame, warnings: list[str]) -> EarningsGap:
        """Return recent earnings gap levels."""
        return self._earnings_gap(symbol, daily, warnings)

    def swing_levels(self, daily: pd.DataFrame, warnings: list[str]) -> SwingLevels:
        """Return major completed-session swing levels."""
        return self._swing_levels(daily, warnings)

    @staticmethod
    def pct_from(price: float | None, level: float | None) -> float | None:
        """Return percent distance from a level."""
        return MarketDataService._pct_from(price, level)

    @staticmethod
    def regular_session(frame: pd.DataFrame) -> pd.DataFrame:
        """Return regular-session bars from an already indexed frame."""
        localized = MarketDataService._with_eastern_index(frame)
        return localized.between_time(MARKET_OPEN, MARKET_CLOSE, inclusive="left")

    def _prefetch_metric_downloads(
        self,
        symbols: list[str],
        selected_metrics: list[MetricName],
        *,
        include_history: bool,
    ) -> None:
        if not self._can_prefetch() or not symbols:
            return
        selected = set(selected_metrics)
        needs_daily = bool(
            {
                "previous_day",
                "fifty_two_week",
                "earnings_gap",
                "swing_levels",
                "bollinger_bands",
                "technical_levels",
            }
            & selected
        ) or include_history
        needs_intraday = bool({"previous_session_vwap_5m", "technical_levels"} & selected) or include_history
        needs_opening_intraday = bool({"premarket", "first_five_minutes", "technical_levels"} & selected)
        if needs_daily:
            start, end = self._daily_history_window(self.settings.daily_history_days)
            self._download_many(symbols, period=None, interval="1d", prepost=False, start=start, end=end)
        if needs_intraday:
            self._download_many(
                symbols,
                period=self.settings.intraday_history_period,
                interval=self.settings.intraday_interval,
                prepost=True,
            )
        if needs_opening_intraday:
            self._download_many(
                symbols,
                period=self.settings.opening_history_period,
                interval=self.settings.opening_interval,
                prepost=True,
            )

    def _prefetch_snapshot_downloads(self, symbols: list[str]) -> None:
        if not self._can_prefetch() or not symbols:
            return
        ordered = list(dict.fromkeys(symbols))
        self._download_many(ordered, period="1d", interval="5m", prepost=True)
        start, end = self._daily_history_window(10)
        self._download_many(ordered, period=None, interval="1d", prepost=False, start=start, end=end)

    def _prefetch_chart_downloads(self, symbols: list[str], chart_range: ChartRange, interval: ChartInterval) -> None:
        if not self._can_prefetch() or not symbols:
            return
        period, provider_interval = CHART_DOWNLOAD_CONFIG[(chart_range, interval)]
        if chart_range in CHART_DATE_TO_DATE_RANGES:
            start, end = self._chart_date_window(chart_range)
            self._download_many(symbols, period=None, interval=provider_interval, prepost=False, start=start, end=end)
            return
        self._download_many(symbols, period=period, interval=provider_interval, prepost=False)

    def _can_prefetch(self) -> bool:
        return (
            MarketDataService._download is ORIGINAL_MARKET_DATA_DOWNLOAD
            and callable(getattr(self.provider, "download_many", None))
        )

    def _download_many(
        self,
        symbols: list[str],
        *,
        period: str | None,
        interval: str,
        prepost: bool,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict[str, pd.DataFrame]:
        downloader = getattr(self.provider, "download_many", None)
        if callable(downloader):
            return downloader(symbols, period=period, interval=interval, prepost=prepost, start=start, end=end)
        return {
            symbol: self._download(symbol, period=period, interval=interval, prepost=prepost, start=start, end=end)
            for symbol in symbols
        }

    def _snapshot_row(self, symbol: str, label: str, warnings: list[str]) -> MarketSnapshotRow:
        row_warnings: list[str] = []
        try:
            intraday = self._download(symbol, period="1d", interval="5m", prepost=True)
        except Exception as exc:
            intraday = pd.DataFrame()
            row_warnings.append(f"Intraday snapshot data was unavailable for {label}: {exc}")
        try:
            daily = self._download_daily_history(symbol, days=10)
        except Exception as exc:
            daily = pd.DataFrame()
            row_warnings.append(f"Daily snapshot data was unavailable for {label}: {exc}")
        sparkline = self._snapshot_sparkline(intraday)
        price = sparkline[-1].close if sparkline else self._latest_close(intraday)
        previous_close = self._previous_completed_close(daily)
        change = round(price - previous_close, 2) if price is not None and previous_close not in (None, 0) else None
        change_percent = self._pct_from(price, previous_close) if price is not None and previous_close not in (None, 0) else None

        if price is None:
            row_warnings.append(f"No latest price was returned for {label}.")
        if previous_close is None:
            row_warnings.append(f"No previous close was returned for {label}.")
        if not sparkline:
            row_warnings.append(f"No intraday sparkline data was returned for {label}.")
        warnings.extend(row_warnings)
        return MarketSnapshotRow(
            symbol=symbol,
            label=label,
            price=price,
            previous_close=previous_close,
            change=change,
            change_percent=change_percent,
            sparkline=sparkline,
            warnings=row_warnings,
        )

    def _chart_history_row(
        self,
        symbol: str,
        chart_range: ChartRange,
        interval: ChartInterval,
        warnings: list[str],
    ) -> TickerChartHistory:
        row_warnings: list[str] = []
        try:
            frame = self._chart_history_download(symbol, chart_range, interval)
        except Exception as exc:
            frame = pd.DataFrame()
            row_warnings.append(f"Chart history was unavailable for {symbol}: {exc}")

        points = self._chart_ohlc_points(frame, interval, row_warnings)
        if not points and not row_warnings:
            row_warnings.append(f"No chart history was returned for {symbol}.")
        warnings.extend(row_warnings)
        return TickerChartHistory(
            ticker=symbol,
            range=chart_range,
            interval=interval,
            points=points,
            warnings=row_warnings,
        )

    def _chart_history_download(
        self,
        symbol: str,
        chart_range: ChartRange,
        interval: ChartInterval,
    ) -> pd.DataFrame:
        period, provider_interval = CHART_DOWNLOAD_CONFIG[(chart_range, interval)]
        if chart_range in CHART_DATE_TO_DATE_RANGES:
            start, end = self._chart_date_window(chart_range)
            return self._download(symbol, period=None, interval=provider_interval, prepost=False, start=start, end=end)
        return self._download(symbol, period=period, interval=provider_interval, prepost=False)

    @staticmethod
    def _chart_date_window(chart_range: ChartRange, now: datetime | None = None) -> tuple[datetime, datetime]:
        """Return an Eastern-calendar start/end window for to-date chart ranges."""
        current = now or datetime.now(EASTERN)
        if current.tzinfo is None:
            current = current.replace(tzinfo=EASTERN)
        current = current.astimezone(EASTERN)

        if chart_range == "WTD":
            start_date = current.date() - timedelta(days=current.weekday())
        elif chart_range == "MTD":
            start_date = current.date().replace(day=1)
        elif chart_range == "QTD":
            quarter_start_month = ((current.month - 1) // 3) * 3 + 1
            start_date = current.date().replace(month=quarter_start_month, day=1)
        else:
            raise ValueError(f"{chart_range} does not use a date-to-date chart window")

        start = datetime.combine(start_date, time.min, tzinfo=EASTERN)
        end = datetime.combine(current.date() + timedelta(days=1), time.min, tzinfo=EASTERN)
        return start.astimezone(timezone.utc), end.astimezone(timezone.utc)

    def _price_history(self, daily: pd.DataFrame, warnings: list[str]) -> list[PricePoint]:
        """Return recent completed daily closes for frontend and PDF charts."""
        if daily.empty:
            warnings.append("Daily data was unavailable for chart history.")
            return []

        completed = daily.dropna(subset=["Close"])
        completed = self._exclude_current_eastern_day(completed)
        if completed.empty:
            warnings.append("Daily data did not include completed sessions for chart history.")
            return []

        recent = completed.tail(self.settings.chart_history_days)
        index = pd.DatetimeIndex(recent.index)
        if index.tz is not None:
            index = index.tz_convert(EASTERN)

        points: list[PricePoint] = []
        for session_date, close in zip(index.date, recent["Close"].astype(float), strict=False):
            points.append(PricePoint(date=session_date, close=round(float(close), 2)))
        return points

    def _intraday_price_history(self, intraday: pd.DataFrame, warnings: list[str]) -> list[IntradayPricePoint]:
        """Return latest regular-session 5-minute closes for frontend charts."""
        if intraday.empty:
            warnings.append("Intraday data was unavailable for 5-minute chart history.")
            return []

        session = self._today_regular_session(intraday).dropna(subset=["Close"])
        if session.empty:
            warnings.append("Intraday data did not include regular-session bars for 5-minute chart history.")
            return []
        return self._intraday_points(session)

    def _snapshot_sparkline(self, intraday: pd.DataFrame) -> list[IntradayPricePoint]:
        if intraday.empty:
            return []
        localized = self._with_eastern_index(intraday)
        latest = self._latest_session_bars(localized).dropna(subset=["Close"])
        if latest.empty:
            return []
        return self._intraday_points(latest)

    @staticmethod
    def _intraday_points(frame: pd.DataFrame) -> list[IntradayPricePoint]:
        index = pd.DatetimeIndex(frame.index)
        if index.tz is None:
            index = index.tz_localize(timezone.utc)
        points: list[IntradayPricePoint] = []
        for stamp, close in zip(index, frame["Close"].astype(float), strict=False):
            points.append(IntradayPricePoint(timestamp=stamp.to_pydatetime(), close=round(float(close), 2)))
        return points

    def _chart_ohlc_points(
        self,
        frame: pd.DataFrame,
        interval: ChartInterval,
        warnings: list[str],
    ) -> list[ChartOhlcPoint]:
        """Normalize provider OHLC bars for frontend charts."""
        required = ["Open", "High", "Low", "Close"]
        if frame.empty:
            warnings.append("Chart history data was unavailable.")
            return []
        if not set(required).issubset(frame.columns):
            warnings.append("Chart history bars were incomplete.")
            return []

        chart_frame = frame
        if interval not in {"1d", "1wk", "1mo"}:
            chart_frame = self._with_eastern_index(chart_frame)
            chart_frame = chart_frame.between_time(MARKET_OPEN, MARKET_CLOSE, inclusive="left")
        chart_frame = chart_frame.dropna(subset=required)
        if chart_frame.empty:
            warnings.append("Chart history did not include usable regular-session bars.")
            return []

        index = pd.DatetimeIndex(chart_frame.index)
        if index.tz is None:
            index = index.tz_localize(timezone.utc)
        chart_frame = chart_frame.copy()
        chart_frame.index = index

        points: list[ChartOhlcPoint] = []
        for stamp, row in chart_frame.iterrows():
            points.append(
                ChartOhlcPoint(
                    timestamp=pd.Timestamp(stamp).to_pydatetime(),
                    open=round(float(row["Open"]), 2),
                    high=round(float(row["High"]), 2),
                    low=round(float(row["Low"]), 2),
                    close=round(float(row["Close"]), 2),
                )
            )
        return points

    @staticmethod
    def _latest_close(frame: pd.DataFrame) -> float | None:
        if frame.empty or "Close" not in frame.columns:
            return None
        closes = frame["Close"].dropna().astype(float)
        return round(float(closes.iloc[-1]), 2) if not closes.empty else None

    @staticmethod
    def _previous_completed_close(daily: pd.DataFrame) -> float | None:
        if daily.empty or "Close" not in daily.columns:
            return None
        completed = daily.dropna(subset=["Close"])
        completed = MarketDataService._exclude_current_eastern_day(completed)
        if completed.empty:
            completed = daily.dropna(subset=["Close"])
        if completed.empty:
            return None
        return round(float(completed["Close"].astype(float).iloc[-1]), 2)

    def _download(
        self,
        symbol: str,
        period: str | None,
        interval: str,
        prepost: bool,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        return self.provider.download(
            symbol,
            period=period,
            interval=interval,
            prepost=prepost,
            start=start,
            end=end,
        )

    def _current_price(self, symbol: str, minute_frame: pd.DataFrame, warnings: list[str]) -> float | None:
        """Return the freshest available price using free-data fallbacks."""
        if not minute_frame.empty and "Close" in minute_frame.columns:
            closes = minute_frame["Close"].dropna().astype(float)
            if not closes.empty:
                return round(float(closes.iloc[-1]), 2)

        try:
            price = self.provider.fast_price(symbol)
            if price:
                return round(float(price), 2)
        except Exception as exc:
            warnings.append(f"Fast price lookup was unavailable for {symbol}: {exc}")

        api_key = os.getenv("FINNHUB_API_KEY", "")
        if not api_key:
            return None
        try:
            price = self.provider.finnhub_quote(symbol, api_key)
            if price:
                return round(float(price), 2)
        except Exception as exc:
            warnings.append(f"Finnhub quote was unavailable for {symbol}: {exc}")
        return None

    @staticmethod
    def _previous_day_ohlc(daily: pd.DataFrame, warnings: list[str]) -> Ohlc:
        return calculations.previous_day_ohlc(daily, warnings)

    @staticmethod
    def _exclude_current_eastern_day(frame: pd.DataFrame) -> pd.DataFrame:
        """Remove today's row so previous-day levels do not drift during market hours."""
        return calculations.exclude_current_eastern_day(frame)

    def _bollinger_bands(self, daily: pd.DataFrame, warnings: list[str]) -> BollingerLevels:
        period = self.settings.bollinger_period
        deviations = self.settings.bollinger_standard_deviations
        if daily.empty or len(daily.dropna(subset=["Close"])) < period:
            warnings.append(f"At least {period} daily closes are required for Bollinger Bands.")
            return BollingerLevels(period=period, standard_deviations=deviations)

        closes = daily["Close"].dropna().astype(float)
        rolling_mean = closes.rolling(period).mean().iloc[-1]
        rolling_std = closes.rolling(period).std().iloc[-1]
        return BollingerLevels(
            upper=round(float(rolling_mean + deviations * rolling_std), 2),
            middle=round(float(rolling_mean), 2),
            lower=round(float(rolling_mean - deviations * rolling_std), 2),
            period=period,
            standard_deviations=deviations,
        )

    @staticmethod
    def _fifty_two_week_range(daily: pd.DataFrame, warnings: list[str]) -> FiftyTwoWeekRange:
        return calculations.fifty_two_week_range(daily, warnings)

    @staticmethod
    def _monthly_range(daily: pd.DataFrame, warnings: list[str]) -> tuple[float | None, float | None]:
        """Return the past 22 completed-session high and low."""
        return calculations.monthly_range(daily, warnings)

    def _earnings_gap(self, symbol: str, daily: pd.DataFrame, warnings: list[str]) -> EarningsGap:
        if daily.empty:
            warnings.append("Daily data was unavailable for earnings gap calculations.")
            return EarningsGap()

        try:
            earnings_dates_loader = getattr(self.provider, "earnings_dates", None)
            if callable(earnings_dates_loader):
                earnings_dates = earnings_dates_loader(symbol)
            else:
                with redirect_stderr(io.StringIO()):
                    earnings_dates = self.provider.ticker(symbol).earnings_dates
        except Exception as exc:
            warnings.append(f"Earnings dates were unavailable: {exc}")
            return EarningsGap()

        if earnings_dates is None or earnings_dates.empty:
            warnings.append("No earnings dates were returned by the data source.")
            return EarningsGap()

        index = pd.DatetimeIndex(earnings_dates.index)
        if index.tz is None:
            index = index.tz_localize(timezone.utc)
        index = index.tz_convert(EASTERN)
        past_earnings = earnings_dates.copy()
        past_earnings.index = index
        today = datetime.now(EASTERN).date()
        past_earnings = past_earnings[past_earnings.index.date < today]
        if past_earnings.empty:
            warnings.append("No completed earnings dates were returned by the data source.")
            return EarningsGap()

        earnings_date = past_earnings.sort_index(ascending=False).index[0].date()
        if (today - earnings_date).days > self.settings.earnings_gap_max_age_days:
            warnings.append(
                f"Most recent earnings date {earnings_date.isoformat()} is older than "
                f"{self.settings.earnings_gap_max_age_days} days; earnings gap levels were suppressed."
            )
            return EarningsGap(date=earnings_date, is_stale=True)

        completed = daily.dropna(subset=["Open", "Close"]).copy()
        completed_index = pd.DatetimeIndex(completed.index)
        if completed_index.tz is not None:
            completed_index = completed_index.tz_convert(EASTERN)
        completed["_session_date"] = completed_index.date
        rows = completed[completed["_session_date"] == earnings_date]
        if rows.empty:
            warnings.append(f"Earnings date {earnings_date.isoformat()} was not present in daily bars.")
            return EarningsGap(date=earnings_date)

        earnings_position = int(completed.index.get_indexer_for([rows.index[0]])[0])
        if earnings_position == 0:
            warnings.append("Earnings gap could not be calculated because the prior close was unavailable.")
            return EarningsGap(date=earnings_date)

        previous_close = float(completed.iloc[earnings_position - 1]["Close"])
        earnings_open = float(rows.iloc[0]["Open"])
        if previous_close == 0:
            warnings.append("Earnings gap could not be calculated because the prior close was zero.")
            return EarningsGap(date=earnings_date)

        gap = earnings_open - previous_close
        return EarningsGap(
            date=earnings_date,
            gap=round(gap, 2),
            gap_percent=round((gap / previous_close) * 100, 2),
            open=round(earnings_open, 2),
            previous_close=round(previous_close, 2),
        )

    def _previous_regular_session(self, intraday: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
        if intraday.empty:
            warnings.append("Intraday data was unavailable for VWAP calculations.")
            return intraday

        localized = self._with_eastern_index(intraday)
        regular = localized.between_time(MARKET_OPEN, MARKET_CLOSE, inclusive="left")
        regular = self._exclude_current_eastern_day(regular)
        if regular.empty:
            warnings.append("No completed regular-session 5 minute bars were returned.")
            return regular

        session_dates = list(dict.fromkeys(regular.index.date))
        previous_date = session_dates[-1]
        return regular[regular.index.date == previous_date]

    def _today_regular_session(self, intraday: pd.DataFrame) -> pd.DataFrame:
        """Return today's regular-session bars only."""
        if intraday.empty:
            return intraday
        localized = self._with_eastern_index(intraday)
        today_bars = self._today_session_bars(localized)
        return today_bars.between_time(MARKET_OPEN, MARKET_CLOSE, inclusive="left")

    def _today_premarket_range(self, intraday: pd.DataFrame, warnings: list[str]) -> PremarketRange:
        if intraday.empty:
            warnings.append("Intraday 1 minute data was unavailable for premarket calculations.")
            return PremarketRange()

        localized = self._with_eastern_index(intraday)
        today_bars = self._today_session_bars(localized)
        premarket = today_bars.between_time(PREMARKET_OPEN, MARKET_OPEN, inclusive="left")
        if premarket.empty:
            warnings.append("No premarket bars were returned by the data source for today.")
            return PremarketRange()

        return PremarketRange(
            high=round(float(premarket["High"].max()), 2),
            low=round(float(premarket["Low"].min()), 2),
            bars=int(len(premarket)),
        )

    def _opening_range(self, intraday: pd.DataFrame, warnings: list[str]) -> OpeningRange:
        minutes = self.settings.opening_range_minutes
        if intraday.empty:
            warnings.append("Intraday 1 minute data was unavailable for first-five-minute calculations.")
            return OpeningRange(minutes=minutes)

        localized = self._with_eastern_index(intraday)
        today_bars = self._today_session_bars(localized)
        if today_bars.empty:
            warnings.append("No intraday bars were returned for today's opening range.")
            return OpeningRange(minutes=minutes)

        end_hour = MARKET_OPEN.hour
        end_minute = MARKET_OPEN.minute + minutes
        end_time = time(end_hour + end_minute // 60, end_minute % 60)
        opening = today_bars.between_time(MARKET_OPEN, end_time, inclusive="left")
        if opening.empty:
            warnings.append("No first-five-minute regular-session bars were returned for today.")
            return OpeningRange(minutes=minutes)

        return OpeningRange(
            high=round(float(opening["High"].max()), 2),
            low=round(float(opening["Low"].min()), 2),
            bars=int(len(opening)),
            minutes=minutes,
        )

    @staticmethod
    def _latest_session_bars(frame: pd.DataFrame) -> pd.DataFrame:
        return calculations.latest_session_bars(frame)

    @staticmethod
    def _today_session_bars(frame: pd.DataFrame) -> pd.DataFrame:
        return calculations.today_session_bars(frame)

    @staticmethod
    def _vwap(session: pd.DataFrame, warnings: list[str]) -> float | None:
        return calculations.vwap(session, warnings)

    def _today_vwap(self, intraday: pd.DataFrame, warnings: list[str]) -> float | None:
        """Calculate VWAP from the latest regular-session 1-minute bars."""
        session = self._today_regular_session(intraday)
        if session.empty:
            warnings.append("No regular-session intraday bars were returned for today's VWAP.")
            return None
        return self._vwap(session, warnings)

    @staticmethod
    def _sma(daily: pd.DataFrame, period: int, warnings: list[str]) -> float | None:
        return calculations.sma(daily, period, warnings)

    @staticmethod
    def _daily_ema(daily: pd.DataFrame, period: int, warnings: list[str]) -> float | None:
        return calculations.daily_ema(daily, period, warnings)

    def _intraday_ema(self, intraday: pd.DataFrame, period: int, warnings: list[str]) -> float | None:
        if intraday.empty:
            warnings.append(f"At least {period} intraday closes are required for {period} EMA.")
            return None

        regular = self._today_regular_session(intraday).dropna(subset=["Close"])
        if regular.empty:
            warnings.append(f"At least {period} intraday closes are required for {period} EMA.")
            return None

        closes = regular["Close"].dropna().astype(float)
        if len(closes) < period:
            warnings.append(f"At least {period} intraday closes are required for {period} EMA.")
            return None
        return round(float(closes.ewm(span=period, adjust=False).mean().iloc[-1]), 2)

    def _technical_levels(
        self,
        *,
        symbol: str,
        daily: pd.DataFrame,
        minute: pd.DataFrame,
        five_minute: pd.DataFrame,
        previous_day: Ohlc,
        earnings_gap: EarningsGap,
        warnings: list[str],
    ) -> TechnicalLevels:
        monthly_high, monthly_low = self._monthly_range(daily, warnings)
        pivots = self._pivot_points(previous_day)
        fibs = self._fibonacci_levels(monthly_high, monthly_low)
        return TechnicalLevels(
            current_price=self._current_price(symbol, minute, warnings),
            today_vwap=self._today_vwap(minute, warnings),
            one_month_high=monthly_high,
            one_month_low=monthly_low,
            sma_50=self._sma(daily, 50, warnings),
            sma_200=self._sma(daily, 200, warnings),
            ema_20_daily=self._daily_ema(daily, 20, warnings),
            ema_9_5m=self._intraday_ema(five_minute, 9, warnings),
            ema_20_5m=self._intraday_ema(five_minute, 20, warnings),
            pivot=pivots["pivot"],
            r1=pivots["r1"],
            s1=pivots["s1"],
            r2=pivots["r2"],
            s2=pivots["s2"],
            fib_618=fibs["fib_618"],
            fib_500=fibs["fib_500"],
            fib_382=fibs["fib_382"],
            earnings_open=earnings_gap.open,
            pre_earnings_close=earnings_gap.previous_close,
        )

    @staticmethod
    def _pivot_points(previous_day: Ohlc) -> dict[str, float | None]:
        """Return classic floor trader pivot points from prior day H/L/C."""
        return calculations.pivot_points(previous_day)

    @staticmethod
    def _fibonacci_levels(high: float | None, low: float | None) -> dict[str, float | None]:
        """Return common retracement levels over a high/low range."""
        return calculations.fibonacci_levels(high, low)

    @staticmethod
    def _pct_from(price: float | None, level: float | None) -> float | None:
        return calculations.pct_from(price, level)

    def _swing_levels(self, daily: pd.DataFrame, warnings: list[str]) -> SwingLevels:
        window = self.settings.swing_window
        max_levels = self.settings.max_swing_levels
        merge_percent = self.settings.level_merge_percent
        if daily.empty:
            warnings.append("Daily data was unavailable for swing level calculations.")
            return SwingLevels(window=window, merge_percent=merge_percent)

        completed = daily.dropna(subset=["High", "Low"])
        completed = self._exclude_current_eastern_day(completed)
        if len(completed) < (window * 2) + 1:
            warnings.append(f"At least {(window * 2) + 1} completed daily bars are required for swing levels.")
            return SwingLevels(window=window, merge_percent=merge_percent)

        span = (window * 2) + 1
        highs = completed["High"].astype(float)
        lows = completed["Low"].astype(float)
        swing_highs = [
            round(float(value), 2)
            for value in highs[highs.eq(highs.rolling(span, center=True).max())].tolist()
        ]
        swing_lows = [
            round(float(value), 2)
            for value in lows[lows.eq(lows.rolling(span, center=True).min())].tolist()
        ]

        return SwingLevels(
            highs=self._merge_levels(
                swing_highs,
                max_levels=max_levels,
                merge_percent=merge_percent,
                descending=True,
            ),
            lows=self._merge_levels(
                swing_lows,
                max_levels=max_levels,
                merge_percent=merge_percent,
                descending=False,
            ),
            window=window,
            merge_percent=merge_percent,
        )

    @staticmethod
    def _merge_levels(levels: list[float], max_levels: int, merge_percent: float, descending: bool) -> list[float]:
        return calculations.merge_levels(levels, max_levels, merge_percent, descending)

    @staticmethod
    def _with_eastern_index(frame: pd.DataFrame) -> pd.DataFrame:
        return calculations.with_eastern_index(frame)


ORIGINAL_MARKET_DATA_DOWNLOAD = MarketDataService._download
