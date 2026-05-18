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

from app.models import BollingerLevels, EquityMetrics, Ohlc, PremarketRange

EASTERN = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
PREMARKET_OPEN = time(4, 0)


@dataclass(frozen=True)
class MarketDataSettings:
    """Tunable calculation settings for generated levels."""

    bollinger_period: int = 20
    bollinger_standard_deviations: float = 2.0
    daily_history_period: str = "3mo"
    intraday_history_period: str = "5d"
    intraday_interval: str = "5m"


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

        previous_day = self._previous_day_ohlc(daily, warnings)
        bollinger = self._bollinger_bands(daily, warnings)
        previous_session = self._previous_regular_session(intraday, warnings)
        premarket = self._latest_premarket_range(intraday, warnings)
        vwap = self._vwap(previous_session, warnings)

        if daily.empty and intraday.empty:
            warnings.append("No price data returned. Verify the ticker symbol or try again later.")

        return EquityMetrics(
            ticker=symbol,
            previous_day=previous_day,
            premarket=premarket,
            previous_session_vwap_5m=vwap,
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
        """Remove today's row so previous-day OHLC does not drift during market hours."""
        if frame.empty:
            return frame
        index = pd.DatetimeIndex(frame.index)
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

    def _previous_regular_session(self, intraday: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
        if intraday.empty:
            warnings.append("Intraday data was unavailable for VWAP and premarket calculations.")
            return intraday

        localized = self._with_eastern_index(intraday)
        regular = localized.between_time(MARKET_OPEN, MARKET_CLOSE, inclusive="left")
        if regular.empty:
            warnings.append("No regular-session 5 minute bars were returned.")
            return regular

        session_dates = list(dict.fromkeys(regular.index.date))
        previous_date = session_dates[-1]
        return regular[regular.index.date == previous_date]

    def _latest_premarket_range(self, intraday: pd.DataFrame, warnings: list[str]) -> PremarketRange:
        if intraday.empty:
            return PremarketRange()

        localized = self._with_eastern_index(intraday)
        premarket = localized.between_time(PREMARKET_OPEN, MARKET_OPEN, inclusive="left")
        if premarket.empty:
            warnings.append("No premarket bars were returned by the data source.")
            return PremarketRange()

        latest_date = premarket.index.date[-1]
        latest = premarket[premarket.index.date == latest_date]
        return PremarketRange(
            high=round(float(latest["High"].max()), 4),
            low=round(float(latest["Low"].min()), 4),
            bars=int(len(latest)),
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

    @staticmethod
    def _with_eastern_index(frame: pd.DataFrame) -> pd.DataFrame:
        localized = frame.copy()
        index = pd.DatetimeIndex(localized.index)
        if index.tz is None:
            index = index.tz_localize(timezone.utc)
        localized.index = index.tz_convert(EASTERN)
        return localized
