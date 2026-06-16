"""Market data provider interfaces and yfinance-backed implementation."""

from __future__ import annotations

import contextlib
import io
import json
from datetime import datetime
import time
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd
import yfinance as yf


class MarketDataProvider(Protocol):
    """Provider abstraction for quote and OHLCV data."""

    def download(
        self,
        symbol: str,
        *,
        period: str | None,
        interval: str,
        prepost: bool,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Download OHLCV data."""

    def download_many(
        self,
        symbols: list[str],
        *,
        period: str | None,
        interval: str,
        prepost: bool,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Download OHLCV data for multiple symbols with one provider query."""

    def fast_price(self, symbol: str) -> float | None:
        """Return a fast latest-price lookup when available."""

    def finnhub_quote(self, symbol: str, api_key: str) -> float | None:
        """Return latest Finnhub quote price."""

    def ticker(self, symbol: str):
        """Return provider ticker handle for metadata endpoints."""

    def sector(self, symbol: str) -> str | None:
        """Return provider sector metadata when available."""

    def earnings_dates(self, symbol: str) -> pd.DataFrame | None:
        """Return provider earnings date metadata when available."""


class YFinanceProvider:
    """Default provider backed by yfinance plus optional Finnhub quote fallback."""

    INTRADAY_CACHE_TTL_SECONDS = 60
    DAILY_CACHE_TTL_SECONDS = 900
    METADATA_CACHE_TTL_SECONDS = 86400

    def __init__(self) -> None:
        self._download_cache: dict[tuple[object, ...], tuple[float, pd.DataFrame]] = {}
        self._sector_cache: dict[str, tuple[float, str | None]] = {}
        self._earnings_dates_cache: dict[str, tuple[float, pd.DataFrame | None]] = {}

    def download(
        self,
        symbol: str,
        *,
        period: str | None,
        interval: str,
        prepost: bool,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        key = self._download_cache_key(symbol, period, interval, prepost, start, end)
        cached = self._cached_download(key)
        if cached is not None:
            return cached

        frame = self._download_uncached(symbol, period=period, interval=interval, prepost=prepost, start=start, end=end)
        self._store_download(key, frame, interval)
        return frame.copy()

    def download_many(
        self,
        symbols: list[str],
        *,
        period: str | None,
        interval: str,
        prepost: bool,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict[str, pd.DataFrame]:
        ordered = list(dict.fromkeys(symbol.upper().strip() for symbol in symbols if symbol.strip()))
        results: dict[str, pd.DataFrame] = {}
        missing: list[str] = []
        for symbol in ordered:
            key = self._download_cache_key(symbol, period, interval, prepost, start, end)
            cached = self._cached_download(key)
            if cached is None:
                missing.append(symbol)
            else:
                results[symbol] = cached

        if not missing:
            return results
        if len(missing) == 1:
            symbol = missing[0]
            results[symbol] = self.download(symbol, period=period, interval=interval, prepost=prepost, start=start, end=end)
            return results

        query = self._download_query(period=period, interval=interval, prepost=prepost, start=start, end=end)
        query["threads"] = True
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                batch = yf.download(" ".join(missing), group_by="ticker", **query)
        except Exception:
            for symbol in missing:
                results[symbol] = self.download(symbol, period=period, interval=interval, prepost=prepost, start=start, end=end)
            return results

        unpacked = self._unpack_batch_download(batch, missing)
        for symbol in missing:
            frame = unpacked.get(symbol, pd.DataFrame())
            key = self._download_cache_key(symbol, period, interval, prepost, start, end)
            self._store_download(key, frame, interval)
            results[symbol] = frame.copy()
        return results

    def _download_uncached(
        self,
        symbol: str,
        *,
        period: str | None,
        interval: str,
        prepost: bool,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        query = self._download_query(period=period, interval=interval, prepost=prepost, start=start, end=end)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            frame = yf.download(symbol, **query)
        return self._clean_download_frame(frame)

    @staticmethod
    def _download_query(
        *,
        period: str | None,
        interval: str,
        prepost: bool,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict[str, object]:
        query = {
            "interval": interval,
            "prepost": prepost,
            "progress": False,
            "auto_adjust": True,
            "threads": False,
        }
        if period is not None:
            query["period"] = period
        if start is not None:
            query["start"] = start
        if end is not None:
            query["end"] = end
        return query

    @classmethod
    def _clean_download_frame(cls, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        return frame.dropna(how="all")

    @classmethod
    def _unpack_batch_download(cls, frame: pd.DataFrame, symbols: list[str]) -> dict[str, pd.DataFrame]:
        if frame.empty:
            return {symbol: pd.DataFrame() for symbol in symbols}
        if not isinstance(frame.columns, pd.MultiIndex):
            return {symbols[0]: cls._clean_download_frame(frame)} if len(symbols) == 1 else {
                symbol: pd.DataFrame() for symbol in symbols
            }

        level_zero = {str(value).upper(): value for value in frame.columns.get_level_values(0)}
        level_one = {str(value).upper(): value for value in frame.columns.get_level_values(1)}
        results: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            if symbol.upper() in level_zero:
                symbol_frame = frame[level_zero[symbol.upper()]]
            elif symbol.upper() in level_one:
                symbol_frame = frame.xs(level_one[symbol.upper()], axis=1, level=1)
            else:
                symbol_frame = pd.DataFrame()
            results[symbol] = cls._clean_download_frame(symbol_frame)
        return results

    def _cached_download(self, key: tuple[object, ...]) -> pd.DataFrame | None:
        entry = self._download_cache.get(key)
        if entry is None:
            return None
        expires_at, frame = entry
        if expires_at <= time.monotonic():
            self._download_cache.pop(key, None)
            return None
        return frame.copy()

    def _store_download(self, key: tuple[object, ...], frame: pd.DataFrame, interval: str) -> None:
        ttl = self.DAILY_CACHE_TTL_SECONDS if interval in {"1d", "1wk", "1mo"} else self.INTRADAY_CACHE_TTL_SECONDS
        self._download_cache[key] = (time.monotonic() + ttl, frame.copy())

    @staticmethod
    def _download_cache_key(
        symbol: str,
        period: str | None,
        interval: str,
        prepost: bool,
        start: datetime | None,
        end: datetime | None,
    ) -> tuple[object, ...]:
        def normalized_stamp(value: datetime | None) -> str | None:
            if value is None:
                return None
            return value.date().isoformat() if interval in {"1d", "1wk", "1mo"} else value.isoformat()

        return (
            symbol.upper().strip(),
            period,
            interval,
            prepost,
            normalized_stamp(start),
            normalized_stamp(end),
        )

    def fast_price(self, symbol: str) -> float | None:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            price = yf.Ticker(symbol).fast_info.get("last_price")
        return float(price) if price else None

    def finnhub_quote(self, symbol: str, api_key: str) -> float | None:
        query = urlencode({"symbol": symbol, "token": api_key})
        with urlopen(f"https://finnhub.io/api/v1/quote?{query}", timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
        price = data.get("c")
        return float(price) if price else None

    def ticker(self, symbol: str):
        return yf.Ticker(symbol)

    def sector(self, symbol: str) -> str | None:
        cache_key = symbol.upper().strip()
        entry = self._sector_cache.get(cache_key)
        if entry is not None and entry[0] > time.monotonic():
            return entry[1]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            sector = yf.Ticker(symbol).info.get("sector")
        value = str(sector) if sector else None
        self._sector_cache[cache_key] = (time.monotonic() + self.METADATA_CACHE_TTL_SECONDS, value)
        return value

    def earnings_dates(self, symbol: str) -> pd.DataFrame | None:
        cache_key = symbol.upper().strip()
        entry = self._earnings_dates_cache.get(cache_key)
        if entry is not None and entry[0] > time.monotonic():
            return entry[1].copy() if entry[1] is not None else None
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            dates = yf.Ticker(symbol).earnings_dates
        self._earnings_dates_cache[cache_key] = (
            time.monotonic() + self.METADATA_CACHE_TTL_SECONDS,
            dates.copy() if dates is not None else None,
        )
        return dates
