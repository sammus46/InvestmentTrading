"""Market data retrieval and metric calculations.

The provider intentionally lives behind a small service class so another free or
paid data source can replace yfinance without touching API routes or UI code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from app.models import (
    BollingerLevels,
    EarningsGap,
    EquityMetrics,
    FiftyTwoWeekRange,
    Ohlc,
    OpeningRange,
    PremarketRange,
    SwingLevels,
)

EASTERN = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
PREMARKET_OPEN = time(4, 0)


@dataclass(frozen=True)
class MarketDataSettings:
    """Tunable calculation settings for generated levels."""

    bollinger_period: int = 20
    bollinger_standard_deviations: float = 2.0
    daily_history_period: str = "1y"
    intraday_history_period: str = "5d"
    intraday_interval: str = "5m"
    opening_history_period: str = "1d"
    opening_interval: str = "1m"
    opening_range_minutes: int = 5
    swing_window: int = 10
    max_swing_levels: int = 5
    level_merge_percent: float = 0.003


class MarketDataService:
    """Fetch equity data from yfinance and calculate price levels."""

    def __init__(self, settings: MarketDataSettings | None = None) -> None:
        self.settings = settings or MarketDataSettings()

    def build_metrics(self, tickers: list[str]) -> list[EquityMetrics]:
        """Generate metric rows for the requested tickers."""
        return [self._build_metric(ticker) for ticker in tickers]

    def _build_metric(self, ticker: str) -> EquityMetrics:
        warnings: list[str] = []
        symbol = ticker.upper().strip()

        daily = self._download(symbol, period=self.settings.daily_history_period, interval="1d", prepost=False)
        intraday = self._download(
            symbol,
            period=self.settings.intraday_history_period,
            interval=self.settings.intraday_interval,
            prepost=True,
        )
        opening_intraday = self._download(
            symbol,
            period=self.settings.opening_history_period,
            interval=self.settings.opening_interval,
            prepost=True,
        )

        previous_day = self._previous_day_ohlc(daily, warnings)
        bollinger = self._bollinger_bands(daily, warnings)
        fifty_two_week = self._fifty_two_week_range(daily, warnings)
        earnings_gap = self._earnings_gap(symbol, daily, warnings)
        previous_session = self._previous_regular_session(intraday, warnings)
        premarket = self._today_premarket_range(opening_intraday, warnings)
        first_five_minutes = self._opening_range(opening_intraday, warnings)
        vwap = self._vwap(previous_session, warnings)
        swing_levels = self._swing_levels(daily, warnings)

        if daily.empty and intraday.empty and opening_intraday.empty:
            warnings.append("No price data returned. Verify the ticker symbol or try again later.")

        return EquityMetrics(
            ticker=symbol,
            previous_day=previous_day,
            premarket=premarket,
            previous_session_vwap_5m=vwap,
            fifty_two_week=fifty_two_week,
            earnings_gap=earnings_gap,
            first_five_minutes=first_five_minutes,
            swing_levels=swing_levels,
            bollinger_bands=bollinger,
            data_timestamp=datetime.now(timezone.utc),
            warnings=warnings,
        )

    @staticmethod
    def _download(symbol: str, period: str, interval: str, prepost: bool) -> pd.DataFrame:
        frame = yf.download(
            symbol,
            period=period,
            interval=interval,
            prepost=prepost,
            progress=False,
            auto_adjust=False,
            threads=False,
        )
        if frame.empty:
            return frame
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        return frame.dropna(how="all")

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
            open=round(float(row["Open"]), 4),
            high=round(float(row["High"]), 4),
            low=round(float(row["Low"]), 4),
            close=round(float(row["Close"]), 4),
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
            upper=round(float(rolling_mean + deviations * rolling_std), 4),
            middle=round(float(rolling_mean), 4),
            lower=round(float(rolling_mean - deviations * rolling_std), 4),
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
            high=round(float(completed["High"].astype(float).max()), 4),
            low=round(float(completed["Low"].astype(float).min()), 4),
        )

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
            gap=round(gap, 4),
            gap_percent=round((gap / previous_close) * 100, 4),
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

    def _today_premarket_range(self, intraday: pd.DataFrame, warnings: list[str]) -> PremarketRange:
        if intraday.empty:
            warnings.append("Intraday 1 minute data was unavailable for premarket calculations.")
            return PremarketRange()

        localized = self._with_eastern_index(intraday)
        today = datetime.now(EASTERN).date()
        today_bars = localized[localized.index.date == today]
        premarket = today_bars.between_time(PREMARKET_OPEN, MARKET_OPEN, inclusive="left")
        if premarket.empty:
            warnings.append("No premarket bars were returned for today by the data source.")
            return PremarketRange()

        return PremarketRange(
            high=round(float(premarket["High"].max()), 4),
            low=round(float(premarket["Low"].min()), 4),
            bars=int(len(premarket)),
        )

    def _opening_range(self, intraday: pd.DataFrame, warnings: list[str]) -> OpeningRange:
        minutes = self.settings.opening_range_minutes
        if intraday.empty:
            warnings.append("Intraday 1 minute data was unavailable for first-five-minute calculations.")
            return OpeningRange(minutes=minutes)

        localized = self._with_eastern_index(intraday)
        today = datetime.now(EASTERN).date()
        today_bars = localized[localized.index.date == today]
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
            high=round(float(opening["High"].max()), 4),
            low=round(float(opening["Low"].min()), 4),
            bars=int(len(opening)),
            minutes=minutes,
        )

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
        return round(float((typical_price * volume).sum() / total_volume), 4)

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
                swing_highs.append(round(float(highs[index]), 4))
            if lows[index] == lows[lower_bound:upper_bound].min():
                swing_lows.append(round(float(lows[index]), 4))

        return SwingLevels(
            highs=self._merge_levels(swing_highs, max_levels=max_levels, merge_percent=merge_percent, descending=True),
            lows=self._merge_levels(swing_lows, max_levels=max_levels, merge_percent=merge_percent, descending=False),
            window=window,
            merge_percent=merge_percent,
        )

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
