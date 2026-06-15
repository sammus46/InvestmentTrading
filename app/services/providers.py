"""Market data provider interfaces and yfinance-backed implementation."""

from __future__ import annotations

import contextlib
import io
import json
from datetime import datetime
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

    def fast_price(self, symbol: str) -> float | None:
        """Return a fast latest-price lookup when available."""

    def finnhub_quote(self, symbol: str, api_key: str) -> float | None:
        """Return latest Finnhub quote price."""

    def ticker(self, symbol: str):
        """Return provider ticker handle for metadata endpoints."""

    def sector(self, symbol: str) -> str | None:
        """Return provider sector metadata when available."""


class YFinanceProvider:
    """Default provider backed by yfinance plus optional Finnhub quote fallback."""

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

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            frame = yf.download(symbol, **query)
        if frame.empty:
            return frame
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        return frame.dropna(how="all")

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
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            sector = yf.Ticker(symbol).info.get("sector")
        return str(sector) if sector else None
