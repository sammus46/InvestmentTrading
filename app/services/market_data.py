"""Market data retrieval and metric calculations.

The provider intentionally lives behind a small service class so another free or
paid data source can replace yfinance without touching API routes or UI code.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from app.models import (
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
)

EASTERN = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
PREMARKET_OPEN = time(4, 0)

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


@dataclass(frozen=True)
class MarketDataSettings:
    """Tunable calculation settings for generated levels."""

    bollinger_period: int = 20
    bollinger_standard_deviations: float = 2.0
    daily_history_days: int = 365
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


class MarketDataService:
    """Fetch equity data from yfinance and calculate price levels."""

    def __init__(self, settings: MarketDataSettings | None = None) -> None:
        self.settings = settings or MarketDataSettings()

    def build_metrics(self, tickers: list[str], metrics: list[MetricName] | None = None) -> list[EquityMetrics]:
        """Generate metric rows for the requested tickers and selected metrics."""
        selected = metrics or list(DEFAULT_METRICS)
        return [self._build_metric(ticker, selected) for ticker in tickers]

    def build_market_snapshot(self, tickers: list[str]) -> MarketSnapshotResponse:
        """Return major market and watchlist day-to-date performance."""
        warnings: list[str] = []
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

    def _build_metric(self, ticker: str, selected_metrics: list[MetricName]) -> EquityMetrics:
        warnings: list[str] = []
        symbol = ticker.upper().strip()

        needs_daily = True
        needs_intraday = True
        needs_opening_intraday = bool({"premarket", "first_five_minutes"} & set(selected_metrics))

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

        previous_day = self._previous_day_ohlc(daily, warnings) if "previous_day" in selected_metrics else Ohlc()
        bollinger = self._bollinger_bands(daily, warnings) if "bollinger_bands" in selected_metrics else BollingerLevels()
        fifty_two_week = (
            self._fifty_two_week_range(daily, warnings) if "fifty_two_week" in selected_metrics else FiftyTwoWeekRange()
        )
        earnings_gap = self._earnings_gap(symbol, daily, warnings) if "earnings_gap" in selected_metrics else EarningsGap()
        previous_session = (
            self._previous_regular_session(intraday, warnings)
            if "previous_session_vwap_5m" in selected_metrics
            else pd.DataFrame()
        )
        premarket = (
            self._today_premarket_range(opening_intraday, warnings)
            if "premarket" in selected_metrics
            else PremarketRange()
        )
        first_five_minutes = (
            self._opening_range(opening_intraday, warnings)
            if "first_five_minutes" in selected_metrics
            else OpeningRange(minutes=self.settings.opening_range_minutes)
        )
        vwap = self._vwap(previous_session, warnings) if "previous_session_vwap_5m" in selected_metrics else None
        swing_levels = self._swing_levels(daily, warnings) if "swing_levels" in selected_metrics else SwingLevels()
        price_history = self._price_history(daily, warnings)
        intraday_history = self._intraday_price_history(intraday, warnings)

        if daily.empty and intraday.empty and opening_intraday.empty and any(
            [needs_daily, needs_intraday, needs_opening_intraday]
        ):
            warnings.append("No price data returned. Verify the ticker symbol or try again later.")

        return EquityMetrics(
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
            price_history=price_history,
            intraday_history=intraday_history,
            data_timestamp=datetime.now(timezone.utc),
            warnings=warnings,
        )


    def _download_daily_history(self, symbol: str, days: int | None = None) -> pd.DataFrame:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days or self.settings.daily_history_days)
        return self._download(symbol, period=None, interval="1d", prepost=False, start=start, end=end)

    def download_scanner_daily_history(self, symbol: str) -> pd.DataFrame:
        """Return daily bars with enough history for scanner indicators."""
        return self._download_daily_history(symbol, days=self.settings.scanner_daily_history_days)

    def download_today_minute_history(self, symbol: str) -> pd.DataFrame:
        """Return latest 1-minute bars including extended hours."""
        return self._download(symbol, period="1d", interval="1m", prepost=True)

    def download_five_minute_history(self, symbol: str, period: str | None = None) -> pd.DataFrame:
        """Return 5-minute bars for setup and pattern scanning."""
        return self._download(symbol, period=period or self.settings.intraday_history_period, interval="5m", prepost=False)

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

    @staticmethod
    def _download(
        symbol: str,
        period: str | None,
        interval: str,
        prepost: bool,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        query = {
            "interval": interval,
            "prepost": prepost,
            "progress": False,
            "auto_adjust": False,
            "threads": False,
        }
        if period is not None:
            query["period"] = period
        if start is not None:
            query["start"] = start
        if end is not None:
            query["end"] = end

        frame = yf.download(symbol, **query)
        if frame.empty:
            return frame
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        return frame.dropna(how="all")

    def _current_price(self, symbol: str, minute_frame: pd.DataFrame, warnings: list[str]) -> float | None:
        """Return the freshest available price using free-data fallbacks."""
        if not minute_frame.empty and "Close" in minute_frame.columns:
            closes = minute_frame["Close"].dropna().astype(float)
            if not closes.empty:
                return round(float(closes.iloc[-1]), 2)

        try:
            price = yf.Ticker(symbol).fast_info.get("last_price")
            if price:
                return round(float(price), 2)
        except Exception as exc:
            warnings.append(f"Fast price lookup was unavailable for {symbol}: {exc}")

        api_key = os.getenv("FINNHUB_API_KEY", "")
        if not api_key:
            return None
        try:
            query = urlencode({"symbol": symbol, "token": api_key})
            with urlopen(f"https://finnhub.io/api/v1/quote?{query}", timeout=8) as response:
                data = json.loads(response.read().decode("utf-8"))
            price = data.get("c")
            if price:
                return round(float(price), 2)
        except Exception as exc:
            warnings.append(f"Finnhub quote was unavailable for {symbol}: {exc}")
        return None

    @staticmethod
    def _previous_day_ohlc(daily: pd.DataFrame, warnings: list[str]) -> Ohlc:
        if daily.empty:
            warnings.append("Daily OHLC data was unavailable.")
            return Ohlc()

        completed = daily.dropna(subset=["Open", "High", "Low", "Close"])
        completed = MarketDataService._exclude_current_eastern_day(completed)
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

    @staticmethod
    def _exclude_current_eastern_day(frame: pd.DataFrame) -> pd.DataFrame:
        """Remove today's row so previous-day levels do not drift during market hours."""
        if frame.empty:
            return frame
        index = pd.DatetimeIndex(frame.index)
        if index.tz is not None:
            index = index.tz_convert(EASTERN)
        today = datetime.now(EASTERN).date()
        return frame[index.date < today]

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
        if daily.empty:
            warnings.append("Daily data was unavailable for the 52-week range.")
            return FiftyTwoWeekRange()

        completed = daily.dropna(subset=["High", "Low"])
        completed = MarketDataService._exclude_current_eastern_day(completed)
        if completed.empty:
            warnings.append("Daily data did not include completed sessions for the 52-week range.")
            return FiftyTwoWeekRange()

        return FiftyTwoWeekRange(
            high=round(float(completed["High"].astype(float).max()), 2),
            low=round(float(completed["Low"].astype(float).min()), 2),
        )

    @staticmethod
    def _monthly_range(daily: pd.DataFrame, warnings: list[str]) -> tuple[float | None, float | None]:
        """Return the past 22 completed-session high and low."""
        if daily.empty:
            warnings.append("Daily data was unavailable for the 1-month range.")
            return None, None
        completed = daily.dropna(subset=["High", "Low"])
        completed = MarketDataService._exclude_current_eastern_day(completed).tail(22)
        if completed.empty:
            warnings.append("Daily data did not include completed sessions for the 1-month range.")
            return None, None
        return round(float(completed["High"].astype(float).max()), 2), round(float(completed["Low"].astype(float).min()), 2)

    @staticmethod
    def _earnings_gap(symbol: str, daily: pd.DataFrame, warnings: list[str]) -> EarningsGap:
        if daily.empty:
            warnings.append("Daily data was unavailable for earnings gap calculations.")
            return EarningsGap()

        try:
            earnings_dates = yf.Ticker(symbol).earnings_dates
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
        """Return latest available regular-session bars from today-like intraday data."""
        if intraday.empty:
            return intraday
        localized = self._with_eastern_index(intraday)
        latest = self._latest_session_bars(localized)
        return latest.between_time(MARKET_OPEN, MARKET_CLOSE, inclusive="left")

    def _today_premarket_range(self, intraday: pd.DataFrame, warnings: list[str]) -> PremarketRange:
        if intraday.empty:
            warnings.append("Intraday 1 minute data was unavailable for premarket calculations.")
            return PremarketRange()

        localized = self._with_eastern_index(intraday)
        today_bars = self._latest_session_bars(localized)
        premarket = today_bars.between_time(PREMARKET_OPEN, MARKET_OPEN, inclusive="left")
        if premarket.empty:
            warnings.append("No premarket bars were returned by the data source for the latest available session.")
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
        today_bars = self._latest_session_bars(localized)
        if today_bars.empty:
            warnings.append("No intraday bars were returned for the latest available opening range.")
            return OpeningRange(minutes=minutes)

        end_hour = MARKET_OPEN.hour
        end_minute = MARKET_OPEN.minute + minutes
        end_time = time(end_hour + end_minute // 60, end_minute % 60)
        opening = today_bars.between_time(MARKET_OPEN, end_time, inclusive="left")
        if opening.empty:
            warnings.append("No first-five-minute regular-session bars were returned for the latest available session.")
            return OpeningRange(minutes=minutes)

        return OpeningRange(
            high=round(float(opening["High"].max()), 2),
            low=round(float(opening["Low"].min()), 2),
            bars=int(len(opening)),
            minutes=minutes,
        )

    @staticmethod
    def _latest_session_bars(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        session_dates = sorted(set(pd.DatetimeIndex(frame.index).date))
        if not session_dates:
            return frame.iloc[0:0]
        return frame[frame.index.date == session_dates[-1]]

    @staticmethod
    def _vwap(session: pd.DataFrame, warnings: list[str]) -> float | None:
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

    def _today_vwap(self, intraday: pd.DataFrame, warnings: list[str]) -> float | None:
        """Calculate VWAP from the latest regular-session 1-minute bars."""
        session = self._today_regular_session(intraday)
        if session.empty:
            warnings.append("No regular-session intraday bars were returned for today's VWAP.")
            return None
        return self._vwap(session, warnings)

    @staticmethod
    def _sma(daily: pd.DataFrame, period: int, warnings: list[str]) -> float | None:
        completed = MarketDataService._exclude_current_eastern_day(daily.dropna(subset=["Close"])) if not daily.empty else daily
        if completed.empty or len(completed) < period:
            warnings.append(f"At least {period} completed daily closes are required for {period} SMA.")
            return None
        return round(float(completed["Close"].astype(float).tail(period).mean()), 2)

    @staticmethod
    def _daily_ema(daily: pd.DataFrame, period: int, warnings: list[str]) -> float | None:
        completed = MarketDataService._exclude_current_eastern_day(daily.dropna(subset=["Close"])) if not daily.empty else daily
        if completed.empty or len(completed) < period:
            warnings.append(f"At least {period} completed daily closes are required for {period} EMA.")
            return None
        return round(float(completed["Close"].astype(float).ewm(span=period, adjust=False).mean().iloc[-1]), 2)

    def _intraday_ema(self, intraday: pd.DataFrame, period: int, warnings: list[str]) -> float | None:
        if intraday.empty:
            warnings.append(f"At least {period} intraday closes are required for {period} EMA.")
            return None

        localized = self._with_eastern_index(intraday)
        regular = localized.between_time(MARKET_OPEN, MARKET_CLOSE, inclusive="left").dropna(subset=["Close"])
        if regular.empty:
            warnings.append(f"At least {period} intraday closes are required for {period} EMA.")
            return None

        latest = self._latest_session_bars(regular)
        closes = latest["Close"].dropna().astype(float) if len(latest.dropna(subset=["Close"])) >= period else regular["Close"].dropna().astype(float)
        if len(closes) < period:
            warnings.append(f"At least {period} intraday closes are required for {period} EMA.")
            return None
        return round(float(closes.ewm(span=period, adjust=False).mean().iloc[-1]), 2)

    @staticmethod
    def _pivot_points(previous_day: Ohlc) -> dict[str, float | None]:
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

    @staticmethod
    def _fibonacci_levels(high: float | None, low: float | None) -> dict[str, float | None]:
        """Return common retracement levels over a high/low range."""
        if high is None or low is None or high <= low:
            return {"fib_382": None, "fib_500": None, "fib_618": None}
        spread = high - low
        return {
            "fib_382": round(low + 0.382 * spread, 2),
            "fib_500": round(low + 0.500 * spread, 2),
            "fib_618": round(low + 0.618 * spread, 2),
        }

    @staticmethod
    def _pct_from(price: float | None, level: float | None) -> float | None:
        if price is None or level is None or level == 0:
            return None
        return round(((price - level) / level) * 100, 2)

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

        highs = completed["High"].astype(float).to_numpy()
        lows = completed["Low"].astype(float).to_numpy()
        swing_highs: list[float] = []
        swing_lows: list[float] = []

        for index in range(window, len(completed) - window):
            lower_bound = index - window
            upper_bound = index + window + 1
            if highs[index] == highs[lower_bound:upper_bound].max():
                swing_highs.append(round(float(highs[index]), 2))
            if lows[index] == lows[lower_bound:upper_bound].min():
                swing_lows.append(round(float(lows[index]), 2))

        latest_close = self._latest_completed_close(completed)
        return SwingLevels(
            highs=self._select_swing_levels(
                swing_highs,
                max_levels=max_levels,
                merge_percent=merge_percent,
                descending=False,
                latest_close=latest_close,
            ),
            lows=self._select_swing_levels(
                swing_lows,
                max_levels=max_levels,
                merge_percent=merge_percent,
                descending=True,
                latest_close=latest_close,
            ),
            window=window,
            merge_percent=merge_percent,
        )

    @classmethod
    def _select_swing_levels(
        cls,
        levels: list[float],
        max_levels: int,
        merge_percent: float,
        descending: bool,
        latest_close: float | None,
    ) -> list[float]:
        merged = cls._merge_levels(levels, max_levels=len(levels), merge_percent=merge_percent, descending=descending)
        if latest_close is None:
            return merged[:max_levels]

        nearest = sorted(merged, key=lambda level: (abs(level - latest_close), level))[:max_levels]
        return sorted(nearest, reverse=descending)

    @staticmethod
    def _latest_completed_close(completed: pd.DataFrame) -> float | None:
        if "Close" not in completed.columns:
            return None
        closes = completed["Close"].dropna().astype(float)
        if closes.empty:
            return None
        return float(closes.iloc[-1])

    @staticmethod
    def _merge_levels(levels: list[float], max_levels: int, merge_percent: float, descending: bool) -> list[float]:
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

    @staticmethod
    def _with_eastern_index(frame: pd.DataFrame) -> pd.DataFrame:
        localized = frame.copy()
        index = pd.DatetimeIndex(localized.index)
        if index.tz is None:
            index = index.tz_localize(timezone.utc)
        localized.index = index.tz_convert(EASTERN)
        return localized
