"""Setup scanner and intraday pattern analysis services."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import TypedDict
from zoneinfo import ZoneInfo

import pandas as pd

from app.models import (
    ChartInterval,
    ChartRange,
    EarningsGap,
    PatternDayDetail,
    PatternHeatmapRow,
    PatternSummaryRow,
    ScannerResponse,
    ScannerSetupRow,
    SectorAnalyticsRecommendation,
    SectorAnalyticsResponse,
    SectorAnalyticsRow,
    SectorTrendPoint,
    SectorTrendSeries,
    ThemeHeatmapRow,
    TickerChartHistory,
)
from app.services.market_data import EASTERN, MARKET_CLOSE, MARKET_OPEN, MARKET_SNAPSHOT_INSTRUMENTS, MarketDataService
from app.services.display import level_type_weight

MOUNTAIN = ZoneInfo("America/Denver")
LOOKBACK_DAYS = 30

SECTOR_ETF = {
    "Technology": "XLK",
    "Energy": "XLE",
    "Financials": "XLF",
    "Financial Services": "XLF",
    "Healthcare": "XLV",
    "Health Care": "XLV",
    "Consumer Cyclical": "XLY",
    "Consumer Discretionary": "XLY",
    "Consumer Defensive": "XLP",
    "Consumer Staples": "XLP",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
}

TICKER_ETF = {
    "PWR": "XLI",
    "NVT": "XLI",
    "BKSY": "XLK",
    "RKLB": "XLI",
    "STRL": "XLI",
    "NVDA": "XLK",
    "MU": "XLK",
    "GEV": "XLI",
    "MYRG": "XLI",
    "ASTS": "XLC",
    "FIX": "XLI",
    "PLTR": "XLK",
    "AAPL": "XLK",
    "MSFT": "XLK",
    "AMD": "XLK",
    "GOOGL": "XLC",
    "META": "XLC",
    "AMZN": "XLY",
    "TSLA": "XLY",
    "JPM": "XLF",
    "GS": "XLF",
    "XOM": "XLE",
    "CVX": "XLE",
    "UNH": "XLV",
    "JNJ": "XLV",
    "HD": "XLY",
    "SPY": "SPY",
    "QQQ": "QQQ",
}

THEME_OVERRIDES = {
    "RKLB": "Space",
    "BKSY": "Space",
    "ASTS": "Space",
    "LUNR": "Space",
    "RDW": "Space",
    "PL": "Space",
    "SPIR": "Space",
    "IRDM": "Space",
    "GSAT": "Space",
    "VSAT": "Space",
    "SATL": "Space",
    "SIDU": "Space",
    "MNTS": "Space",
    "LLAP": "Space",
    "NVDA": "Semiconductors",
    "AMD": "Semiconductors",
    "MU": "Semiconductors",
    "AVGO": "Semiconductors",
    "TSM": "Semiconductors",
    "ASML": "Semiconductors",
    "INTC": "Semiconductors",
    "QCOM": "Semiconductors",
    "ARM": "Semiconductors",
    "MRVL": "Semiconductors",
    "LRCX": "Semiconductors",
    "AMAT": "Semiconductors",
    "AAPL": "Mega-cap Tech",
    "MSFT": "Mega-cap Tech",
    "GOOGL": "Mega-cap Tech",
    "META": "Mega-cap Tech",
    "AMZN": "Mega-cap Tech",
    "XOM": "Energy",
    "CVX": "Energy",
    "OXY": "Energy",
    "SLB": "Energy",
    "JPM": "Financials",
    "GS": "Financials",
    "BAC": "Financials",
    "MS": "Financials",
    "WFC": "Financials",
    "PWR": "Infrastructure",
    "NVT": "Infrastructure",
    "STRL": "Infrastructure",
    "GEV": "Infrastructure",
    "MYRG": "Infrastructure",
    "FIX": "Infrastructure",
}

THEME_TREND_BASKET_LIMIT = 8
THEME_TREND_BASKETS: dict[str, tuple[str, ...]] = {
    "Space": ("RKLB", "ASTS", "BKSY", "LUNR", "RDW", "PL", "IRDM", "GSAT"),
    "Semiconductors": ("NVDA", "AMD", "MU", "AVGO", "TSM", "ASML", "QCOM", "ARM"),
    "Mega-cap Tech": ("AAPL", "MSFT", "GOOGL", "META", "AMZN"),
    "Infrastructure": ("PWR", "NVT", "STRL", "GEV", "MYRG", "FIX"),
    "Energy": ("XOM", "CVX", "OXY", "SLB"),
    "Financials": ("JPM", "GS", "BAC", "MS", "WFC"),
}

SIGNAL_PRIORITY = ["VWAP", "PM High", "Prev High", "Prev Low", "R1", "S1", "Pivot"]


def _build_buckets() -> tuple[list[str], list[str]]:
    current = datetime(2000, 1, 1, MARKET_OPEN.hour, MARKET_OPEN.minute)
    end = datetime(2000, 1, 1, MARKET_CLOSE.hour, MARKET_CLOSE.minute)
    buckets: list[str] = []
    labels: list[str] = []
    while current < end:
        buckets.append(current.strftime("%H:%M"))
        labels.append(current.strftime("%I:%M %p ET").lstrip("0"))
        current += timedelta(minutes=5)
    return buckets, labels


BUCKETS_ET, BUCKET_LABELS = _build_buckets()


class SetupAnalysis(TypedDict):
    """Typed setup-scoring result used before serializing scanner rows."""

    nearest_name: str
    nearest_val: float
    nearest_pct: float
    consec: int
    hold_count: int
    level_held: bool
    is_tight: bool
    off_high_pct: float | None
    good_pullback: bool
    momentum: str
    score: int


class SupportResistanceResult(TypedDict, total=False):
    """Typed support/resistance scoring result."""

    support_zone: str
    support_score: int
    support_reason: str | None
    resistance_zone: str
    resistance_score: int
    resistance_reason: str | None
    room_up_pct: float | None
    risk_down_pct: float | None
    rr: float | None


class ScannerLevelData(TypedDict, total=False):
    """Intermediate level and signal data for one ticker scan."""

    ticker: str
    price: float | None
    prev_h: float | None
    prev_l: float | None
    prev_c: float | None
    pm_high: float | None
    pm_low: float | None
    f5_high: float | None
    f5_low: float | None
    monthly_h: float | None
    monthly_l: float | None
    today_vwap: float | None
    vwap: float | None
    sma_50: float | None
    sma_200: float | None
    ema_20_daily: float | None
    ema_9_5m: float | None
    ema_20_5m: float | None
    pivot: float | None
    r1: float | None
    s1: float | None
    r2: float | None
    s2: float | None
    fib_382: float | None
    fib_500: float | None
    fib_618: float | None
    earn_open: float | None
    earn_prev_close: float | None
    earn_gap: float | None
    swing_highs: list[float]
    swing_lows: list[float]
    sector: str
    theme: str
    etf: str | None
    stock_pct: float | None
    sector_pct: float | None
    rs_vs_spy: float | None
    rs_vs_sector: float | None
    vwap_ext: float | None
    setup: SetupAnalysis | None
    signal: str | None
    sr: SupportResistanceResult


@dataclass
class TickerScanData:
    """Intermediate scanner data for one ticker."""

    symbol: str
    data: ScannerLevelData
    daily: pd.DataFrame
    minute: pd.DataFrame
    five_minute: pd.DataFrame
    warnings: list[str]


class ScannerService:
    """Build setup scanner and intraday pattern analysis reports."""

    def __init__(self, market_data: MarketDataService | None = None) -> None:
        self.market_data = market_data or MarketDataService()

    def build_scanner(
        self,
        tickers: list[str],
        *,
        include_setup: bool = True,
        include_patterns: bool = True,
        include_earnings: bool = True,
        pattern_lookback_days: int = LOOKBACK_DAYS,
    ) -> ScannerResponse:
        """Return setup scanner rows and optional intraday pattern analysis."""
        watchlist = [ticker.upper().strip() for ticker in tickers if ticker.strip()]
        warnings: list[str] = []
        setup_rows: list[ScannerSetupRow] = []
        pattern_summary: list[PatternSummaryRow] = []
        pattern_heatmap: list[PatternHeatmapRow] = []
        pattern_details: list[PatternDayDetail] = []

        self.market_data.prefetch_scanner_downloads(
            watchlist,
            include_setup=include_setup,
            include_patterns=include_patterns,
        )

        benchmark_cache: dict[str, float | None] = {}
        if include_setup:
            for symbol in watchlist:
                try:
                    scan_data = self._load_ticker_data(symbol, benchmark_cache, include_earnings=include_earnings)
                    setup_rows.append(self._setup_row(scan_data))
                except Exception as exc:
                    warnings.append(f"Scanner failed for {symbol}: {exc}")
                    setup_rows.append(ScannerSetupRow(ticker=symbol, warnings=[str(exc)]))

        if include_patterns:
            for symbol in watchlist:
                try:
                    result = self._pattern_analysis(symbol, pattern_lookback_days)
                    if result is None:
                        warnings.append(f"No pattern data was returned for {symbol}.")
                        continue
                    summary, heatmap, details = result
                    pattern_summary.append(summary)
                    pattern_heatmap.append(heatmap)
                    pattern_details.extend(details)
                except Exception as exc:
                    warnings.append(f"Pattern analysis failed for {symbol}: {exc}")

        return ScannerResponse(
            generated_at=datetime.now(timezone.utc),
            watchlist=watchlist,
            setup_rows=sorted(setup_rows, key=lambda row: row.score or -1, reverse=True),
            pattern_summary=sorted(pattern_summary, key=lambda row: (row.sector, row.ticker)),
            pattern_buckets=BUCKETS_ET,
            pattern_bucket_labels=BUCKET_LABELS,
            theme_heatmap=self._theme_heatmap_rows(pattern_heatmap),
            pattern_heatmap=sorted(pattern_heatmap, key=lambda row: (row.sector, row.ticker)),
            pattern_details=pattern_details,
            takeaways=self._takeaways(pattern_summary),
            warnings=warnings,
        )

    def build_sector_analytics(
        self,
        tickers: list[str],
        *,
        pattern_lookback_days: int = LOOKBACK_DAYS,
        trend_range: ChartRange = "3M",
        trend_interval: ChartInterval = "1d",
    ) -> SectorAnalyticsResponse:
        """Return sector aggregates plus intraday pattern analysis for a watchlist."""
        watchlist = [ticker.upper().strip() for ticker in tickers if ticker.strip()]
        warnings: list[str] = []
        sector_inputs: list[tuple[ScannerLevelData, ScannerSetupRow]] = []
        pattern_summary: list[PatternSummaryRow] = []
        pattern_heatmap: list[PatternHeatmapRow] = []
        pattern_details: list[PatternDayDetail] = []

        try:
            self.market_data.prefetch_scanner_downloads(watchlist, include_setup=True, include_patterns=True)
        except Exception as exc:
            warnings.append(f"Sector analytics prefetch failed: {type(exc).__name__}: {exc}")

        benchmark_cache: dict[str, float | None] = {}
        for symbol in watchlist:
            try:
                scan_data = self._load_ticker_data(symbol, benchmark_cache, include_earnings=False)
                sector_inputs.append((scan_data.data, self._setup_row(scan_data)))
            except Exception as exc:
                warnings.append(f"Sector setup analytics failed for {symbol}: {exc}")

            try:
                result = self._pattern_analysis(symbol, pattern_lookback_days)
                if result is None:
                    warnings.append(f"No pattern data was returned for {symbol}.")
                    continue
                summary, heatmap, details = result
                pattern_summary.append(summary)
                pattern_heatmap.append(heatmap)
                pattern_details.extend(details)
            except Exception as exc:
                warnings.append(f"Pattern analysis failed for {symbol}: {exc}")

        try:
            sector_rows = self._sector_rows(watchlist, sector_inputs, pattern_summary)
        except Exception as exc:
            sector_rows = []
            warnings.append(f"Sector row aggregation failed: {type(exc).__name__}: {exc}")

        try:
            (
                sector_trend_series,
                benchmark_trend_series,
                macro_trend_series,
                theme_trend_series,
                trend_warnings,
            ) = self._build_sector_trends(
                watchlist,
                sector_rows,
                trend_range,
                trend_interval,
            )
            warnings.extend(trend_warnings)
        except Exception as exc:
            sector_trend_series = []
            benchmark_trend_series = []
            macro_trend_series = []
            theme_trend_series = []
            warnings.append(f"Trend analytics failed: {type(exc).__name__}: {exc}")

        try:
            recommendations = self._sector_recommendations(sector_rows, len(watchlist))
        except Exception as exc:
            recommendations = []
            warnings.append(f"Sector recommendations failed: {type(exc).__name__}: {exc}")

        takeaways: list[str] = []
        try:
            takeaways.extend(self._sector_takeaways(sector_rows))
        except Exception as exc:
            warnings.append(f"Sector takeaways failed: {type(exc).__name__}: {exc}")
        try:
            takeaways.extend(self._takeaways(pattern_summary))
        except Exception as exc:
            warnings.append(f"Pattern takeaways failed: {type(exc).__name__}: {exc}")
        return SectorAnalyticsResponse(
            generated_at=datetime.now(timezone.utc),
            watchlist=watchlist,
            trend_range=trend_range,
            trend_interval=trend_interval,
            sector_rows=sector_rows,
            sector_trend_series=sector_trend_series,
            theme_trend_series=theme_trend_series,
            benchmark_trend_series=benchmark_trend_series,
            macro_trend_series=macro_trend_series,
            pattern_summary=sorted(pattern_summary, key=lambda row: (row.sector, row.ticker)),
            pattern_buckets=BUCKETS_ET,
            pattern_bucket_labels=BUCKET_LABELS,
            theme_heatmap=self._theme_heatmap_rows(pattern_heatmap),
            pattern_heatmap=sorted(pattern_heatmap, key=lambda row: (row.sector, row.ticker)),
            pattern_details=pattern_details,
            recommendations=recommendations,
            takeaways=takeaways,
            warnings=warnings,
        )

    @classmethod
    def merge_responses(cls, tickers: list[str] | tuple[str, ...], responses: list[ScannerResponse]) -> ScannerResponse:
        """Merge partial scanner responses into the standard scanner shape."""
        watchlist = list(dict.fromkeys(ticker.upper().strip() for ticker in tickers if ticker.strip()))
        ticker_order = {ticker: index for index, ticker in enumerate(watchlist)}
        generated_at = max((response.generated_at for response in responses), default=datetime.now(timezone.utc))
        setup_rows: list[ScannerSetupRow] = []
        pattern_summary: list[PatternSummaryRow] = []
        pattern_heatmap: list[PatternHeatmapRow] = []
        pattern_details: list[PatternDayDetail] = []
        theme_heatmap: list[ThemeHeatmapRow] = []
        warnings: list[str] = []
        pattern_buckets: list[str] = []
        pattern_bucket_labels: list[str] = []

        for response in responses:
            setup_rows.extend(response.setup_rows)
            pattern_summary.extend(response.pattern_summary)
            pattern_heatmap.extend(response.pattern_heatmap)
            theme_heatmap.extend(response.theme_heatmap)
            pattern_details.extend(response.pattern_details)
            warnings.extend(response.warnings)
            if response.pattern_buckets and not pattern_buckets:
                pattern_buckets = list(response.pattern_buckets)
            if response.pattern_bucket_labels and not pattern_bucket_labels:
                pattern_bucket_labels = list(response.pattern_bucket_labels)

        ordered_details = [
            detail
            for _, detail in sorted(
                enumerate(pattern_details),
                key=lambda item: (ticker_order.get(item[1].ticker, len(ticker_order)), item[0]),
            )
        ]

        return ScannerResponse(
            generated_at=generated_at,
            watchlist=watchlist,
            setup_rows=sorted(
                setup_rows,
                key=lambda row: (-(row.score if row.score is not None else -1), ticker_order.get(row.ticker, len(ticker_order))),
            ),
            pattern_summary=sorted(pattern_summary, key=lambda row: (row.sector or "", row.ticker)),
            pattern_buckets=pattern_buckets or list(BUCKETS_ET),
            pattern_bucket_labels=pattern_bucket_labels or list(BUCKET_LABELS),
            theme_heatmap=theme_heatmap or cls._theme_heatmap_rows(pattern_heatmap),
            pattern_heatmap=sorted(pattern_heatmap, key=lambda row: (row.sector or "", row.ticker)),
            pattern_details=ordered_details,
            takeaways=cls._takeaways(pattern_summary),
            warnings=warnings,
        )

    @classmethod
    def replace_setup_rows(
        cls,
        tickers: list[str] | tuple[str, ...],
        base: ScannerResponse,
        updates: list[ScannerResponse],
    ) -> ScannerResponse:
        """Return scanner response with setup rows replaced by newer partial setup rows."""
        watchlist = list(dict.fromkeys(ticker.upper().strip() for ticker in tickers if ticker.strip()))
        ticker_order = {ticker: index for index, ticker in enumerate(watchlist)}
        rows_by_ticker = {row.ticker: row for row in base.setup_rows}
        warnings = list(base.warnings)
        generated_at = base.generated_at
        for response in updates:
            generated_at = max(generated_at, response.generated_at)
            rows_by_ticker.update({row.ticker: row for row in response.setup_rows})
            warnings.extend(response.warnings)
        setup_rows = sorted(
            rows_by_ticker.values(),
            key=lambda row: (-(row.score if row.score is not None else -1), ticker_order.get(row.ticker, len(ticker_order))),
        )
        return base.model_copy(
            update={
                "generated_at": generated_at,
                "setup_rows": setup_rows,
                "warnings": list(dict.fromkeys(warnings)),
            }
        )

    def _load_ticker_data(
        self,
        symbol: str,
        benchmark_cache: dict[str, float | None],
        *,
        include_earnings: bool = True,
    ) -> TickerScanData:
        warnings: list[str] = []
        daily = self.market_data.download_scanner_daily_history(symbol)
        minute = self.market_data.download_today_minute_history(symbol)
        five_minute = self.market_data.download_five_minute_history(symbol)

        previous = self.market_data.previous_day_ohlc(daily, warnings)
        monthly_high, monthly_low = self.market_data.monthly_range(daily, warnings)
        previous_session = self.market_data.previous_regular_session(five_minute, warnings)
        pivots = self.market_data.pivot_points(previous)
        fibs = self.market_data.fibonacci_levels(monthly_high, monthly_low)
        earnings = self.market_data.earnings_gap(symbol, daily, warnings) if include_earnings else EarningsGap()
        price = self.market_data.current_price(symbol, minute, warnings)
        today_vwap = self.market_data.today_vwap(minute, warnings)
        previous_vwap = self.market_data.vwap(previous_session, warnings)
        premarket = self.market_data.today_premarket_range(minute, warnings)
        opening = self.market_data.opening_range(minute, warnings)
        swing_levels = self.market_data.swing_levels(daily, warnings)
        etf, sector = self._sector_etf(symbol)
        theme = self._ticker_theme(symbol, sector)

        stock_pct = self.market_data.pct_from(price, previous.close)
        spy_pct = self._benchmark_pct("SPY", benchmark_cache)
        sector_pct = self._benchmark_pct(etf, benchmark_cache) if etf else None

        data: ScannerLevelData = {
            "ticker": symbol,
            "price": price,
            "prev_h": previous.high,
            "prev_l": previous.low,
            "prev_c": previous.close,
            "pm_high": premarket.high,
            "pm_low": premarket.low,
            "f5_high": opening.high,
            "f5_low": opening.low,
            "monthly_h": monthly_high,
            "monthly_l": monthly_low,
            "today_vwap": today_vwap,
            "vwap": previous_vwap,
            "sma_50": self.market_data.sma(daily, 50, warnings),
            "sma_200": self.market_data.sma(daily, 200, warnings),
            "ema_20_daily": self.market_data.daily_ema(daily, 20, warnings),
            "ema_9_5m": self.market_data.intraday_ema(five_minute, 9, warnings),
            "ema_20_5m": self.market_data.intraday_ema(five_minute, 20, warnings),
            "pivot": pivots["pivot"],
            "r1": pivots["r1"],
            "s1": pivots["s1"],
            "r2": pivots["r2"],
            "s2": pivots["s2"],
            "fib_382": fibs["fib_382"],
            "fib_500": fibs["fib_500"],
            "fib_618": fibs["fib_618"],
            "earn_open": earnings.open,
            "earn_prev_close": earnings.previous_close,
            "earn_gap": earnings.gap,
            "swing_highs": swing_levels.highs,
            "swing_lows": swing_levels.lows,
            "sector": sector,
            "theme": theme,
            "etf": etf,
            "stock_pct": stock_pct,
            "sector_pct": sector_pct,
            "rs_vs_spy": round(stock_pct - spy_pct, 2) if stock_pct is not None and spy_pct is not None else None,
            "rs_vs_sector": round(stock_pct - sector_pct, 2)
            if stock_pct is not None and sector_pct is not None
            else None,
        }
        data["vwap_ext"] = self.market_data.pct_from(price, today_vwap or previous_vwap)
        data["setup"] = self._analyze_setup(data, five_minute)
        data["signal"] = self._detect_reclaim_rejection(data, five_minute)
        data["sr"] = self._best_support_resistance(data, five_minute)
        return TickerScanData(symbol=symbol, data=data, daily=daily, minute=minute, five_minute=five_minute, warnings=warnings)

    def _benchmark_pct(self, symbol: str | None, cache: dict[str, float | None]) -> float | None:
        if symbol is None:
            return None
        if symbol in cache:
            return cache[symbol]
        warnings: list[str] = []
        daily = self.market_data.download_scanner_daily_history(symbol)
        minute = self.market_data.download_today_minute_history(symbol)
        previous = self.market_data.previous_day_ohlc(daily, warnings)
        price = self.market_data.current_price(symbol, minute, warnings)
        cache[symbol] = self.market_data.pct_from(price, previous.close)
        return cache[symbol]

    def _sector_etf(self, symbol: str) -> tuple[str | None, str]:
        etf = TICKER_ETF.get(symbol)
        if etf:
            sector = next((name for name, sector_etf in SECTOR_ETF.items() if sector_etf == etf), "")
            return etf, sector or "Other"
        try:
            sector = str(self.market_data.ticker_sector(symbol) or "")
            etf = SECTOR_ETF.get(sector)
            if etf:
                return etf, sector
        except Exception:
            pass
        return None, "Other"

    @staticmethod
    def _ticker_theme(symbol: str, sector: str | None = None) -> str:
        """Return the user-facing analytics theme for a ticker."""
        clean_symbol = symbol.upper().strip()
        return THEME_OVERRIDES.get(clean_symbol) or sector or "Other"

    def _setup_row(self, scan_data: TickerScanData) -> ScannerSetupRow:
        data = scan_data.data
        setup = data.get("setup") if isinstance(data.get("setup"), dict) else None
        sr = data.get("sr") if isinstance(data.get("sr"), dict) else {}
        signal = data.get("signal") if isinstance(data.get("signal"), str) else None
        warnings, data_notes = self._split_scanner_messages(scan_data.warnings)
        return ScannerSetupRow(
            ticker=scan_data.symbol,
            price=self._float(data.get("price")),
            score=int(setup["score"]) if setup else None,
            signal=signal,
            vwap_extension_label=self._vwap_extension_label(self._float(data.get("vwap_ext"))),
            vwap_extension_percent=self._float(data.get("vwap_ext")),
            rs_vs_spy_label=self._rs_label(self._float(data.get("rs_vs_spy"))),
            rs_vs_spy_percent=self._float(data.get("rs_vs_spy")),
            rs_vs_sector_label=self._rs_label(self._float(data.get("rs_vs_sector"))),
            rs_vs_sector_percent=self._float(data.get("rs_vs_sector")),
            best_support=str(sr.get("support_zone")) if sr.get("support_zone") else None,
            support_confidence=int(sr.get("support_score") or 0) or None,
            support_reason=str(sr.get("support_reason")) if sr.get("support_reason") else None,
            best_resistance=str(sr.get("resistance_zone")) if sr.get("resistance_zone") else None,
            resistance_confidence=int(sr.get("resistance_score") or 0) or None,
            resistance_reason=str(sr.get("resistance_reason")) if sr.get("resistance_reason") else None,
            risk_reward=self._float(sr.get("rr")),
            setup_level=f"{setup['nearest_name']} ${setup['nearest_val']:.2f}" if setup else None,
            setup_distance_percent=self._float(setup.get("nearest_pct")) if setup else None,
            consecutive_bars=int(setup["consec"]) if setup else None,
            lows_held=int(setup["hold_count"]) if setup else None,
            range_compression="Tight" if setup and setup["is_tight"] else "Wide" if setup else None,
            off_high_percent=self._float(setup.get("off_high_pct")) if setup else None,
            momentum=str(setup["momentum"]) if setup else None,
            warnings=warnings,
            data_notes=data_notes,
        )

    @classmethod
    def _sector_rows(
        cls,
        watchlist: list[str],
        setup_inputs: list[tuple[ScannerLevelData, ScannerSetupRow]],
        pattern_summary: list[PatternSummaryRow],
    ) -> list[SectorAnalyticsRow]:
        patterns_by_sector: dict[str, list[PatternSummaryRow]] = {}
        for row in pattern_summary:
            patterns_by_sector.setdefault(row.sector or "Other", []).append(row)

        grouped: dict[str, list[tuple[ScannerLevelData, ScannerSetupRow]]] = {}
        for data, setup_row in setup_inputs:
            grouped.setdefault(str(data.get("sector") or "Other"), []).append((data, setup_row))

        for sector, patterns in patterns_by_sector.items():
            grouped.setdefault(sector, [])

        rows: list[SectorAnalyticsRow] = []
        total = max(len(watchlist), 1)
        for sector, entries in grouped.items():
            tickers = [str(data.get("ticker") or setup_row.ticker) for data, setup_row in entries]
            if not tickers:
                tickers = sorted({row.ticker for row in patterns_by_sector.get(sector, [])})
            patterns = patterns_by_sector.get(sector, [])
            common_low_times = cls._common_low_times(patterns)
            average_setup_score = cls._avg([setup_row.score for _, setup_row in entries])
            average_rs_vs_spy = cls._avg([cls._float(data.get("rs_vs_spy")) for data, _ in entries])
            average_rs_vs_sector = cls._avg([cls._float(data.get("rs_vs_sector")) for data, _ in entries])
            average_recovery = cls._avg([row.average_recovery_percent for row in patterns])
            row = SectorAnalyticsRow(
                sector=sector,
                etf=next((str(data.get("etf")) for data, _ in entries if data.get("etf")), None),
                ticker_count=len(tickers),
                weight_percent=round((len(tickers) / total) * 100, 1),
                tickers=tickers,
                average_day_change_percent=cls._avg([cls._float(data.get("stock_pct")) for data, _ in entries]),
                sector_etf_day_change_percent=cls._avg([cls._float(data.get("sector_pct")) for data, _ in entries]),
                average_rs_vs_spy_percent=average_rs_vs_spy,
                average_rs_vs_sector_percent=average_rs_vs_sector,
                average_setup_score=average_setup_score,
                strong_setup_count=sum(1 for _, setup_row in entries if setup_row.score is not None and setup_row.score >= 5),
                average_pattern_consistency_percent=cls._avg([row.consistency_percent for row in patterns]),
                average_dip_percent=cls._avg([row.average_dip_percent for row in patterns]),
                average_recovery_percent=average_recovery,
                common_low_times=common_low_times,
                recommendation_tone=cls._sector_tone(average_rs_vs_spy, average_setup_score, average_recovery),
                recommendation_text="",
            )
            row.recommendation_text = cls._sector_recommendation_text(row)
            rows.append(row)
        return sorted(rows, key=lambda row: (-row.weight_percent, row.sector))

    @classmethod
    def _theme_heatmap_rows(cls, rows: list[PatternHeatmapRow]) -> list[ThemeHeatmapRow]:
        """Aggregate ticker-level intraday heatmap rows into user-facing themes."""
        grouped: dict[str, list[PatternHeatmapRow]] = {}
        for row in rows:
            grouped.setdefault(row.theme or row.sector or "Other", []).append(row)

        heatmap_rows: list[ThemeHeatmapRow] = []
        for theme, theme_rows in grouped.items():
            max_len = max((len(row.values) for row in theme_rows), default=0)
            values: list[float | None] = []
            for index in range(max_len):
                bucket_values = [
                    row.values[index]
                    for row in theme_rows
                    if index < len(row.values) and row.values[index] is not None
                ]
                values.append(cls._avg(bucket_values))
            tickers = sorted({row.ticker for row in theme_rows})
            heatmap_rows.append(
                ThemeHeatmapRow(
                    theme=theme,
                    ticker_count=len(tickers),
                    tickers=tickers,
                    values=values,
                )
            )
        return sorted(heatmap_rows, key=lambda row: (-row.ticker_count, row.theme))

    def _build_sector_trends(
        self,
        watchlist: list[str],
        sector_rows: list[SectorAnalyticsRow],
        trend_range: ChartRange,
        trend_interval: ChartInterval,
    ) -> tuple[
        list[SectorTrendSeries],
        list[SectorTrendSeries],
        list[SectorTrendSeries],
        list[SectorTrendSeries],
        list[str],
    ]:
        """Return normalized sector, theme, benchmark, and macro trend series."""
        if not watchlist:
            return [], [], [], [], []

        sector_etfs = [row.etf for row in sector_rows if row.etf]
        theme_groups = self._watchlist_theme_groups(watchlist, sector_rows)
        theme_basket_symbols = [
            symbol
            for theme in theme_groups
            for symbol in self._theme_basket_symbols(theme)
        ]
        macro_symbols = [symbol for symbol, _ in MARKET_SNAPSHOT_INSTRUMENTS]
        symbols = list(dict.fromkeys([*watchlist, *sector_etfs, *theme_basket_symbols, "SPY", *macro_symbols]))
        warnings: list[str] = []

        try:
            response = self.market_data.build_chart_history(symbols, trend_range, trend_interval)
        except Exception as exc:
            return [], [], [], [], [f"Trend history was unavailable for sector analytics: {exc}"]

        try:
            warnings.extend(response.warnings)
            charts = {chart.ticker: chart for chart in response.charts}
            symbol_series = {
                symbol: self._trend_series_from_chart(
                    charts.get(symbol),
                    kind="watchlist_theme" if symbol in watchlist else "theme_basket",
                    symbol=symbol,
                    label=symbol,
                    trend_range=trend_range,
                    trend_interval=trend_interval,
                )
                for symbol in symbols
            }
            for symbol in list(dict.fromkeys([*watchlist, *theme_basket_symbols])):
                warnings.extend(symbol_series.get(symbol, SectorTrendSeries(
                    kind="theme_basket",
                    symbol=symbol,
                    label=symbol,
                    range=trend_range,
                    interval=trend_interval,
                )).warnings)

            ticker_series = {ticker: symbol_series[ticker] for ticker in watchlist if ticker in symbol_series}
            ticker_changes = {ticker: series.change_percent for ticker, series in ticker_series.items()}

            benchmark = self._trend_series_from_chart(
                charts.get("SPY"),
                kind="benchmark",
                symbol="SPY",
                label="SPY Benchmark",
                trend_range=trend_range,
                trend_interval=trend_interval,
            )
            warnings.extend(benchmark.warnings)

            sector_series: list[SectorTrendSeries] = []
            for row in sector_rows:
                aggregate = self._aggregate_sector_trend(row, ticker_series, trend_range, trend_interval)
                sector_series.append(aggregate)

                etf_series: SectorTrendSeries | None = None
                if row.etf:
                    etf_series = self._trend_series_from_chart(
                        charts.get(row.etf),
                        kind="sector_etf",
                        symbol=row.etf,
                        label=f"{row.sector} ETF ({row.etf})",
                        trend_range=trend_range,
                        trend_interval=trend_interval,
                        sector=row.sector,
                    )
                    sector_series.append(etf_series)
                    warnings.extend(etf_series.warnings)

                self._enrich_sector_row_from_trends(row, aggregate, etf_series, benchmark, ticker_changes)

            macro_series: list[SectorTrendSeries] = []
            for symbol, label in MARKET_SNAPSHOT_INSTRUMENTS:
                series = self._trend_series_from_chart(
                    charts.get(symbol),
                    kind="macro",
                    symbol=symbol,
                    label=label,
                    trend_range=trend_range,
                    trend_interval=trend_interval,
                )
                macro_series.append(series)
                warnings.extend(series.warnings)

            theme_series = self._build_theme_trends(
                theme_groups,
                symbol_series,
                trend_range,
                trend_interval,
            )
            for series in theme_series:
                warnings.extend(series.warnings)

            return sector_series, [benchmark], macro_series, theme_series, list(dict.fromkeys(warnings))
        except Exception as exc:
            warnings.append(f"Trend processing failed for sector analytics: {type(exc).__name__}: {exc}")
            return [], [], [], [], list(dict.fromkeys(warnings))

    @classmethod
    def _watchlist_theme_groups(
        cls,
        watchlist: list[str],
        sector_rows: list[SectorAnalyticsRow],
    ) -> dict[str, list[str]]:
        """Group watchlist tickers by user-facing analytics theme."""
        ticker_sector = {
            ticker: row.sector
            for row in sector_rows
            for ticker in row.tickers
        }
        groups: dict[str, list[str]] = {}
        for ticker in watchlist:
            theme = cls._ticker_theme(ticker, ticker_sector.get(ticker))
            groups.setdefault(theme, []).append(ticker)
        return groups

    @staticmethod
    def _theme_basket_symbols(theme: str) -> list[str]:
        """Return capped representative symbols for broader theme trend context."""
        return list(dict.fromkeys(THEME_TREND_BASKETS.get(theme, ())))[:THEME_TREND_BASKET_LIMIT]

    @classmethod
    def _build_theme_trends(
        cls,
        theme_groups: dict[str, list[str]],
        symbol_series: dict[str, SectorTrendSeries],
        trend_range: ChartRange,
        trend_interval: ChartInterval,
    ) -> list[SectorTrendSeries]:
        """Return watchlist and broader basket trend lines for covered themes."""
        theme_series: list[SectorTrendSeries] = []
        for theme, tickers in theme_groups.items():
            theme_series.append(
                cls._aggregate_theme_trend(
                    theme,
                    tickers,
                    symbol_series,
                    trend_range,
                    trend_interval,
                    kind="watchlist_theme",
                    label=f"{theme} Watchlist",
                )
            )
            basket_symbols = cls._theme_basket_symbols(theme)
            if basket_symbols:
                theme_series.append(
                    cls._aggregate_theme_trend(
                        theme,
                        basket_symbols,
                        symbol_series,
                        trend_range,
                        trend_interval,
                        kind="theme_basket",
                        label=f"{theme} Basket",
                    )
                )
        return theme_series

    @classmethod
    def _trend_series_from_chart(
        cls,
        chart: TickerChartHistory | None,
        *,
        kind: str,
        symbol: str,
        label: str,
        trend_range: ChartRange,
        trend_interval: ChartInterval,
        sector: str | None = None,
        theme: str | None = None,
    ) -> SectorTrendSeries:
        """Normalize one OHLC chart to percent change from its first valid close."""
        warnings: list[str] = []
        if chart is None:
            return SectorTrendSeries(
                kind=kind,  # type: ignore[arg-type]
                symbol=symbol,
                label=label,
                range=trend_range,
                interval=trend_interval,
                sector=sector,
                theme=theme,
                warnings=[f"No trend chart was returned for {label}."],
            )

        warnings.extend(chart.warnings)
        first_close = next((cls._finite_float(point.close) for point in chart.points if cls._finite_float(point.close)), None)
        if first_close is None or first_close == 0:
            warnings.append(f"No valid trend close was returned for {label}.")
            first_close = None

        points: list[SectorTrendPoint] = []
        for point in chart.points:
            close = cls._finite_float(point.close)
            change = round(((close - first_close) / first_close) * 100, 2) if close is not None and first_close else None
            points.append(SectorTrendPoint(timestamp=point.timestamp, close=close, change_percent=change))

        return SectorTrendSeries(
            kind=kind,  # type: ignore[arg-type]
            symbol=symbol,
            label=label,
            range=trend_range,
            interval=trend_interval,
            sector=sector,
            theme=theme,
            points=points,
            change_percent=cls._last_change_percent(points),
            warnings=warnings,
        )

    @classmethod
    def _aggregate_sector_trend(
        cls,
        row: SectorAnalyticsRow,
        ticker_series: dict[str, SectorTrendSeries],
        trend_range: ChartRange,
        trend_interval: ChartInterval,
    ) -> SectorTrendSeries:
        """Average normalized ticker trend points into one watchlist-sector line."""
        values_by_timestamp: dict[datetime, list[float]] = {}
        for ticker in row.tickers:
            for point in ticker_series.get(ticker, SectorTrendSeries(
                kind="watchlist_sector",
                symbol=ticker,
                label=ticker,
                range=trend_range,
                interval=trend_interval,
            )).points:
                if point.change_percent is not None:
                    values_by_timestamp.setdefault(point.timestamp, []).append(point.change_percent)

        points = [
            SectorTrendPoint(timestamp=timestamp, change_percent=cls._avg(values))
            for timestamp, values in sorted(values_by_timestamp.items())
        ]
        return SectorTrendSeries(
            kind="watchlist_sector",
            symbol=row.sector,
            label=f"{row.sector} Watchlist",
            range=trend_range,
            interval=trend_interval,
            sector=row.sector,
            points=points,
            change_percent=cls._last_change_percent(points),
            warnings=[] if points else [f"No trend points were available for {row.sector} watchlist tickers."],
        )

    @classmethod
    def _aggregate_theme_trend(
        cls,
        theme: str,
        symbols: list[str],
        symbol_series: dict[str, SectorTrendSeries],
        trend_range: ChartRange,
        trend_interval: ChartInterval,
        *,
        kind: str,
        label: str,
    ) -> SectorTrendSeries:
        """Average normalized ticker trend points into one theme line."""
        values_by_timestamp: dict[datetime, list[float]] = {}
        for symbol in symbols:
            fallback = SectorTrendSeries(
                kind=kind,  # type: ignore[arg-type]
                symbol=symbol,
                label=symbol,
                range=trend_range,
                interval=trend_interval,
                theme=theme,
            )
            for point in symbol_series.get(symbol, fallback).points:
                if point.change_percent is not None:
                    values_by_timestamp.setdefault(point.timestamp, []).append(point.change_percent)

        points = [
            SectorTrendPoint(timestamp=timestamp, change_percent=cls._avg(values))
            for timestamp, values in sorted(values_by_timestamp.items())
        ]
        source = "watchlist tickers" if kind == "watchlist_theme" else "basket tickers"
        return SectorTrendSeries(
            kind=kind,  # type: ignore[arg-type]
            symbol=theme,
            label=label,
            range=trend_range,
            interval=trend_interval,
            theme=theme,
            points=points,
            change_percent=cls._last_change_percent(points),
            warnings=[] if points else [f"No trend points were available for {theme} {source}."],
        )

    @classmethod
    def _enrich_sector_row_from_trends(
        cls,
        row: SectorAnalyticsRow,
        aggregate: SectorTrendSeries,
        etf_series: SectorTrendSeries | None,
        benchmark: SectorTrendSeries,
        ticker_changes: dict[str, float | None],
    ) -> None:
        """Stamp longer-range trend metrics onto an existing sector aggregate row."""
        row.trend_change_percent = aggregate.change_percent
        row.sector_etf_trend_change_percent = etf_series.change_percent if etf_series else None
        row.trend_rs_vs_spy_percent = (
            round(aggregate.change_percent - benchmark.change_percent, 2)
            if aggregate.change_percent is not None and benchmark.change_percent is not None
            else None
        )

        ranked = [
            (ticker, change)
            for ticker in row.tickers
            if (change := ticker_changes.get(ticker)) is not None
        ]
        row.up_ticker_count = sum(1 for _, change in ranked if change > 0)
        row.down_ticker_count = sum(1 for _, change in ranked if change < 0)
        row.leader_tickers = [ticker for ticker, _ in sorted(ranked, key=lambda item: item[1], reverse=True)[:3]]
        row.laggard_tickers = [ticker for ticker, _ in sorted(ranked, key=lambda item: item[1])[:3]]
        row.recommendation_tone = cls._sector_tone(
            row.average_rs_vs_spy_percent,
            row.average_setup_score,
            row.average_recovery_percent,
            row.trend_rs_vs_spy_percent,
        )
        row.recommendation_text = cls._sector_recommendation_text(row)

    @staticmethod
    def _finite_float(value: object) -> float | None:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @classmethod
    def _last_change_percent(cls, points: list[SectorTrendPoint]) -> float | None:
        for point in reversed(points):
            if point.change_percent is not None:
                return point.change_percent
        return None

    @classmethod
    def _sector_recommendations(
        cls,
        sector_rows: list[SectorAnalyticsRow],
        watchlist_count: int,
    ) -> list[SectorAnalyticsRecommendation]:
        recommendations: list[SectorAnalyticsRecommendation] = []
        for row in sector_rows:
            recommendations.append(
                SectorAnalyticsRecommendation(
                    tone=row.recommendation_tone,
                    sector=row.sector,
                    title=f"{row.sector}: {row.recommendation_tone.title()}",
                    message=row.recommendation_text,
                    tickers=row.tickers,
                )
            )
        if watchlist_count:
            concentrated = [row for row in sector_rows if row.weight_percent > 50]
            for row in concentrated:
                recommendations.insert(
                    0,
                    SectorAnalyticsRecommendation(
                        tone="note",
                        sector=row.sector,
                        title=f"{row.sector} concentration",
                        message=(
                            f"{row.sector} represents {row.weight_percent:.1f}% of the watchlist, "
                            "so broad sector moves may dominate the list."
                        ),
                        tickers=row.tickers,
                    ),
                )
        return recommendations

    @classmethod
    def _sector_takeaways(cls, sector_rows: list[SectorAnalyticsRow]) -> list[str]:
        if not sector_rows:
            return []
        strongest = max(sector_rows, key=lambda row: row.average_rs_vs_spy_percent if row.average_rs_vs_spy_percent is not None else -999)
        most_concentrated = max(sector_rows, key=lambda row: row.weight_percent)
        takeaways = [
            f"{most_concentrated.sector} has the largest watchlist weight at {most_concentrated.weight_percent:.1f}%.",
        ]
        if strongest.average_rs_vs_spy_percent is not None:
            takeaways.append(
                f"{strongest.sector} has the strongest average watchlist RS vs SPY at {strongest.average_rs_vs_spy_percent:+.2f}%."
            )
        trend_leaders = [row for row in sector_rows if row.trend_rs_vs_spy_percent is not None]
        if trend_leaders:
            strongest_trend = max(trend_leaders, key=lambda row: row.trend_rs_vs_spy_percent or -999)
            takeaways.append(
                f"{strongest_trend.sector} leads SPY over the selected trend range by {strongest_trend.trend_rs_vs_spy_percent:+.2f}%."
            )
        return takeaways

    @staticmethod
    def _avg(values: list[float | int | None]) -> float | None:
        numbers = [float(value) for value in values if value is not None]
        return round(sum(numbers) / len(numbers), 2) if numbers else None

    @staticmethod
    def _sector_tone(
        average_rs_vs_spy: float | None,
        average_setup_score: float | None,
        average_recovery: float | None,
        trend_rs_vs_spy: float | None = None,
    ) -> str:
        if (
            (average_rs_vs_spy is not None and average_rs_vs_spy > 0)
            or (trend_rs_vs_spy is not None and trend_rs_vs_spy > 0.75)
            or (average_setup_score is not None and average_setup_score >= 5)
            or (average_recovery is not None and average_recovery >= 0.5)
        ):
            return "focus"
        if (
            ((average_rs_vs_spy is not None and average_rs_vs_spy < 0)
            or (trend_rs_vs_spy is not None and trend_rs_vs_spy < -0.75))
            and (average_setup_score is None or average_setup_score < 3)
            and (average_recovery is None or average_recovery < 0.25)
        ):
            return "wait"
        return "watch"

    @staticmethod
    def _sector_recommendation_text(row: SectorAnalyticsRow) -> str:
        trend = (
            f" Longer trend RS versus SPY is {row.trend_rs_vs_spy_percent:+.2f}%."
            if row.trend_rs_vs_spy_percent is not None
            else ""
        )
        participation = (
            f" Participation: {row.up_ticker_count} up, {row.down_ticker_count} down."
            if row.up_ticker_count or row.down_ticker_count
            else ""
        )
        if row.recommendation_tone == "focus":
            return (
                f"{row.sector} is showing better readiness through relative strength, setup quality, "
                f"or pattern recovery across the covered tickers.{trend}{participation}"
            )
        if row.recommendation_tone == "wait":
            return (
                f"{row.sector} is lagging on relative strength and does not yet show broad setup confirmation."
                f"{trend}{participation}"
            )
        return f"{row.sector} is mixed; relative strength or setup quality is not broadly confirmed yet.{trend}{participation}"

    @staticmethod
    def _common_low_times(rows: list[PatternSummaryRow]) -> list[str]:
        counter: Counter[str] = Counter()
        for row in rows:
            for item in row.top_low_times:
                label, _, count_text = item.partition(" (")
                try:
                    count = int(count_text.rstrip("x)")) if count_text else 1
                except ValueError:
                    count = 1
                counter[label] += count
        return [f"{time} ({count}x)" for time, count in counter.most_common(3)]

    @classmethod
    def _split_scanner_messages(cls, warnings: list[str]) -> tuple[list[str], list[str]]:
        visible: list[str] = []
        notes: list[str] = []
        for warning in warnings:
            if cls._is_optional_data_note(warning):
                notes.append(warning)
            else:
                visible.append(warning)
        return visible, notes

    @staticmethod
    def _is_optional_data_note(message: str) -> bool:
        optional_fragments = (
            "completed daily closes are required",
            "intraday closes are required",
            "Daily data was unavailable for earnings gap calculations",
            "Earnings dates were unavailable",
            "No earnings dates were returned",
            "No completed earnings dates were returned",
            "was not present in daily bars",
            "Earnings gap could not be calculated",
            "earnings gap levels were suppressed",
            "regular-session intraday bars were returned for today's VWAP",
            "premarket bars were returned by the data source for today",
            "intraday bars were returned for today's opening range",
            "completed daily bars are required for swing levels",
        )
        return any(fragment in message for fragment in optional_fragments)

    @staticmethod
    def _float(value: object) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _vwap_extension_label(ext_pct: float | None) -> str | None:
        if ext_pct is None:
            return None
        if ext_pct >= 2.0:
            return f"+{ext_pct:.1f}% Chase"
        if ext_pct >= 0.75:
            return f"+{ext_pct:.1f}% Extended"
        if ext_pct >= 0:
            return f"+{ext_pct:.1f}% Healthy"
        if ext_pct >= -0.75:
            return f"{ext_pct:.1f}% Near"
        return f"{ext_pct:.1f}% Below"

    @staticmethod
    def _rs_label(rs_pct: float | None) -> str | None:
        if rs_pct is None:
            return None
        if rs_pct >= 2.0:
            return f"+{rs_pct:.1f}% Strong"
        if rs_pct >= 0.5:
            return f"+{rs_pct:.1f}% Strong"
        if rs_pct >= -0.5:
            return f"{rs_pct:+.1f}% Inline"
        if rs_pct >= -2.0:
            return f"{rs_pct:.1f}% Weak"
        return f"{rs_pct:.1f}% Very Weak"

    def _best_support_resistance(self, data: ScannerLevelData, five_minute: pd.DataFrame) -> SupportResistanceResult:
        price = self._float(data.get("price"))
        if price is None:
            return {}
        session = self.market_data.today_regular_session(five_minute)
        atr_pct = self._atr_5m_pct(five_minute)
        zone_tol = min(max(0.50, atr_pct * 100 * 1.0), 1.5)
        react_tol = min(max(0.20, atr_pct * 100 * 0.75), 1.0)
        now_et = datetime.now(EASTERN)
        hour_et = now_et.hour + now_et.minute / 60
        demote_previous_vwap = hour_et > 11

        level_map = self._scanner_level_map(data)
        support_candidates: list[dict[str, object]] = []
        resistance_candidates: list[dict[str, object]] = []
        for name, raw_value in level_map.items():
            value = self._float(raw_value)
            if value is None or value <= 0:
                continue
            side = "support" if value < price else "resistance"
            score, evidence = self._score_level_confidence(name, value, price, session, side, react_tol)
            if name == "VWAP (Prev Session)" and demote_previous_vwap:
                score = min(score, 30)
            entry = {"name": name, "value": value, "score": score, "evidence": evidence}
            if side == "support":
                support_candidates.append(entry)
            else:
                resistance_candidates.append(entry)

        support_zones = [
            zone
            for zone in self._group_levels_into_zones(support_candidates, zone_tol)
            if zone["high"] < price and 0 <= self._zone_distance_pct(zone, price, "support") <= 8.0
        ]
        resistance_zones = [
            zone
            for zone in self._group_levels_into_zones(resistance_candidates, zone_tol)
            if zone["low"] > price and 0 <= self._zone_distance_pct(zone, price, "resistance") <= 8.0
        ]
        best_support = max(support_zones, key=lambda zone: zone["score"], default=None)
        best_resistance = max(resistance_zones, key=lambda zone: zone["score"], default=None)
        support_score = int(best_support["score"]) if best_support else 0
        resistance_score = int(best_resistance["score"]) if best_resistance else 0
        min_confidence = 50

        room_up = (
            self.market_data.pct_from(price, self._float(best_resistance["low"]))
            if best_resistance and resistance_score >= min_confidence
            else None
        )
        risk_down = (
            self.market_data.pct_from(price, self._float(best_support["high"]))
            if best_support and support_score >= min_confidence
            else None
        )
        risk_reward = round(abs(room_up) / abs(risk_down), 1) if room_up and risk_down and risk_down < 0 else None

        return {
            "support_zone": self._format_zone(best_support) if best_support and support_score >= min_confidence else "No clean support",
            "support_score": support_score,
            "support_reason": self._format_zone_reason(best_support) if best_support and support_score >= min_confidence else None,
            "resistance_zone": self._format_zone(best_resistance)
            if best_resistance and resistance_score >= min_confidence
            else "No clean resistance",
            "resistance_score": resistance_score,
            "resistance_reason": self._format_zone_reason(best_resistance)
            if best_resistance and resistance_score >= min_confidence
            else None,
            "room_up_pct": room_up,
            "risk_down_pct": risk_down,
            "rr": risk_reward,
        }

    @staticmethod
    def _scanner_level_map(data: ScannerLevelData) -> dict[str, object]:
        levels: dict[str, object] = {
            "VWAP (Today)": data.get("today_vwap"),
            "VWAP (Prev Session)": data.get("vwap"),
            "PM High": data.get("pm_high"),
            "PM Low": data.get("pm_low"),
            "Prev High": data.get("prev_h"),
            "Prev Low": data.get("prev_l"),
            "Prev Close": data.get("prev_c"),
            "5-Min High": data.get("f5_high"),
            "5-Min Low": data.get("f5_low"),
            "50 SMA (Daily)": data.get("sma_50"),
            "200 SMA (Daily)": data.get("sma_200"),
            "1-Month High": data.get("monthly_h"),
            "1-Month Low": data.get("monthly_l"),
            "Pivot": data.get("pivot"),
            "R1 (Pivot)": data.get("r1"),
            "S1 (Pivot)": data.get("s1"),
        }
        for index, level in enumerate(data.get("swing_highs") or [], start=1):
            if index > 3:
                break
            levels[f"Daily Swing High {index}"] = level
        for index, level in enumerate(data.get("swing_lows") or [], start=1):
            if index > 3:
                break
            levels[f"Daily Swing Low {index}"] = level
        return levels

    @staticmethod
    def _zone_distance_pct(zone: dict[str, object], price: float, side: str) -> float:
        if side == "support":
            high = float(zone["high"])
            return abs(((price - high) / high) * 100) if high else 999.0
        return abs(((float(zone["low"]) - price) / price) * 100) if price else 999.0

    def _atr_5m_pct(self, five_minute: pd.DataFrame) -> float:
        if five_minute.empty:
            return 0.003
        try:
            session = self.market_data.today_regular_session(five_minute)
            bars = session if len(session) >= 5 else five_minute.tail(30)
            if bars.empty:
                return 0.003
            atr = (bars["High"].astype(float) - bars["Low"].astype(float)).mean()
            price = float(bars["Close"].astype(float).iloc[-1])
            return float(atr / price) if price > 0 else 0.003
        except Exception:
            return 0.003

    @staticmethod
    def _count_level_reactions(session: pd.DataFrame, level: float, side: str, tol_pct: float) -> tuple[int, int]:
        if session.empty or not level:
            return 0, 0
        tolerance = level * (tol_pct / 100)
        depart_tolerance = tolerance * 2.0
        reactions = 0
        last_reaction = None
        state = "waiting"

        for index, row in session.iterrows():
            close = float(row["Close"])
            low = float(row["Low"])
            high = float(row["High"])
            if side == "support":
                near_level = low <= level + tolerance
                if state == "waiting" and near_level:
                    state = "interacting"
                elif state == "interacting":
                    still_near = abs(close - level) <= tolerance * 2
                    if still_near or near_level:
                        continue
                    if close > level + depart_tolerance:
                        reactions += 1
                        last_reaction = index
                    state = "waiting"
            else:
                near_level = high >= level - tolerance
                if state == "waiting" and near_level:
                    state = "interacting"
                elif state == "interacting":
                    still_near = abs(close - level) <= tolerance * 2
                    if still_near or near_level:
                        continue
                    if close < level - depart_tolerance:
                        reactions += 1
                        last_reaction = index
                    state = "waiting"
        if last_reaction is None:
            return reactions, 0
        try:
            minutes_ago = (datetime.now(EASTERN) - last_reaction).total_seconds() / 60
        except Exception:
            return reactions, 8
        if minutes_ago <= 15:
            return reactions, 25
        if minutes_ago <= 30:
            return reactions, 20
        if minutes_ago <= 120:
            return reactions, 15
        return reactions, 8

    def _score_level_confidence(
        self,
        name: str,
        value: float,
        price: float,
        session: pd.DataFrame,
        side: str,
        tol_pct: float,
    ) -> tuple[int, list[str]]:
        score = self._level_weight(name)
        evidence: list[str] = []
        distance_pct = abs((price - value) / value) * 100
        if distance_pct <= 0.25:
            score += 15
        elif distance_pct <= 0.50:
            score += 12
        elif distance_pct <= 1.00:
            score += 8
        elif distance_pct <= 2.00:
            score += 4
        else:
            score -= 5

        reactions, recency = self._count_level_reactions(session, value, side, tol_pct)
        score += min(recency, 15)
        verb = "held" if side == "support" else "rejected"
        if reactions >= 3:
            score += 30
            evidence.append(f"{verb} {reactions}x")
        elif reactions == 2:
            score += 20
            evidence.append(f"{verb} 2x")
        elif reactions == 1:
            score += 10
            evidence.append(f"{verb} 1x")
        return min(max(score, 0), 92), evidence

    @staticmethod
    def _level_weight(name: str) -> int:
        return level_type_weight(name)

    @staticmethod
    def _group_levels_into_zones(levels: list[dict[str, object]], tolerance_pct: float) -> list[dict[str, object]]:
        zones: list[dict[str, object]] = []
        for level in sorted(levels, key=lambda item: float(item["value"])):
            placed = False
            for zone in zones:
                members = zone["members"]
                midpoint = sum(float(member["value"]) for member in members) / len(members)
                if abs((float(level["value"]) - midpoint) / midpoint) * 100 <= tolerance_pct:
                    members.append(level)
                    zone["low"] = min(float(zone["low"]), float(level["value"]))
                    zone["high"] = max(float(zone["high"]), float(level["value"]))
                    placed = True
                    break
            if not placed:
                zones.append({"low": float(level["value"]), "high": float(level["value"]), "members": [level]})
        for zone in zones:
            members = zone["members"]
            base_score = max(int(member["score"]) for member in members)
            zone["score"] = min(base_score + 5 * (len(members) - 1), 92)
            zone["names"] = [str(member["name"]) for member in members]
            zone["evidence"] = sorted({evidence for member in members for evidence in member["evidence"]})
        return zones

    @staticmethod
    def _format_zone(zone: dict[str, object] | None) -> str | None:
        if not zone:
            return None
        low = float(zone["low"])
        high = float(zone["high"])
        if round(low, 2) == round(high, 2):
            return f"${low:.2f}"
        return f"${low:.2f}-${high:.2f}"

    @staticmethod
    def _format_zone_reason(zone: dict[str, object] | None) -> str | None:
        if not zone:
            return None
        names = [str(name) for name in zone["names"][:3]]
        evidence = [str(item) for item in zone["evidence"][:2]]
        return f"{', '.join(names)} ({', '.join(evidence)})" if evidence else ", ".join(names)

    def _detect_reclaim_rejection(self, data: ScannerLevelData, five_minute: pd.DataFrame) -> str | None:
        session = self.market_data.today_regular_session(five_minute)
        if len(session) < 5:
            return None
        last_five = session.tail(5)
        latest_close = float(last_five["Close"].iloc[-1])
        latest_open = float(last_five["Open"].iloc[-1])
        is_green = latest_close > latest_open
        is_red = latest_close < latest_open
        levels = {
            "VWAP": data.get("today_vwap"),
            "PM High": data.get("pm_high"),
            "Prev High": data.get("prev_h"),
            "Prev Low": data.get("prev_l"),
            "R1": data.get("r1"),
            "S1": data.get("s1"),
            "Pivot": data.get("pivot"),
        }
        reclaims: list[str] = []
        rejections: list[str] = []
        for name, raw_level in levels.items():
            level = self._float(raw_level)
            if level is None:
                continue
            if (last_five["Close"].iloc[:-1].astype(float) < level).any() and latest_close > level and is_green:
                reclaims.append(name)
            if (last_five["High"].astype(float) > level).any() and latest_close < level and is_red:
                rejections.append(name)

        reclaim = self._best_signal(reclaims)
        rejection = self._best_signal(rejections)
        if reclaim and rejection:
            return f"Reclaimed {reclaim}" if SIGNAL_PRIORITY.index(reclaim) <= SIGNAL_PRIORITY.index(rejection) else f"Rejecting {rejection}"
        if reclaim:
            return f"Reclaimed {reclaim}"
        if rejection:
            return f"Rejecting {rejection}"
        return None

    @staticmethod
    def _best_signal(signals: list[str]) -> str | None:
        for priority in SIGNAL_PRIORITY:
            if priority in signals:
                return priority
        return signals[0] if signals else None

    def _analyze_setup(self, data: ScannerLevelData, five_minute: pd.DataFrame) -> SetupAnalysis | None:
        price = self._float(data.get("price"))
        if price is None:
            return None
        session = self.market_data.today_regular_session(five_minute)
        if len(session) < 3:
            return None
        level_map = {
            "VWAP": data.get("today_vwap"),
            "Prev VWAP": data.get("vwap"),
            "Prev High": data.get("prev_h"),
            "Prev Low": data.get("prev_l"),
            "PM High": data.get("pm_high"),
            "PM Low": data.get("pm_low"),
            "1-Mo High": data.get("monthly_h"),
            "1-Mo Low": data.get("monthly_l"),
        }
        nearest_name = None
        nearest_value = None
        nearest_pct = 999.0
        for name, raw_value in level_map.items():
            value = self._float(raw_value)
            pct = abs(self.market_data.pct_from(price, value) or 999)
            if value is not None and pct < nearest_pct:
                nearest_name = name
                nearest_value = value
                nearest_pct = pct
        if nearest_value is None or nearest_name is None:
            return None

        proximity = (((session[["High", "Low", "Close"]].astype(float) - nearest_value) / nearest_value) * 100).abs()
        near_level = proximity.min(axis=1).le(0.25)
        reversed_near_level = near_level.iloc[::-1].to_numpy()
        misses = (~reversed_near_level).nonzero()[0]
        consecutive = int(misses[0]) if len(misses) else int(len(reversed_near_level))

        tail = session.tail(10)
        low_pct = ((tail["Low"].astype(float) - nearest_value) / nearest_value) * 100
        close_pct = ((tail["Close"].astype(float) - nearest_value) / nearest_value) * 100
        hold_count = int((low_pct.abs().le(0.25) & close_pct.gt(0)).sum())

        last_three = session.tail(3)
        avg_recent = (last_three["High"].astype(float) - last_three["Low"].astype(float)).mean()
        avg_session = (session["High"].astype(float) - session["Low"].astype(float)).mean()
        is_tight = (avg_recent / avg_session) < 0.65 if avg_session > 0 else False
        session_high = float(session["High"].astype(float).max())
        off_high_pct = self.market_data.pct_from(price, session_high)
        good_pullback = off_high_pct is not None and -3.0 <= off_high_pct <= -0.5
        closes = session["Close"].astype(float).to_numpy()
        c1, c2, c3 = closes[-3], closes[-2], closes[-1]
        if c3 > c2 and c2 >= c1:
            momentum = "Turning Up"
        elif c3 > c2 and c2 < c1:
            momentum = "Ticking Up"
        elif c3 < c2:
            momentum = "Still Falling"
        else:
            momentum = "Flat"

        score = 0
        if nearest_pct <= 0.25:
            score += 2
        elif nearest_pct <= 0.5:
            score += 1
        if consecutive >= 3:
            score += 1
        if hold_count >= 2:
            score += 2
        elif hold_count == 1:
            score += 1
        if is_tight:
            score += 1
        if "Up" in momentum:
            score += 1
        if good_pullback:
            score += 1
        return {
            "nearest_name": nearest_name,
            "nearest_val": nearest_value,
            "nearest_pct": round(nearest_pct, 2),
            "consec": consecutive,
            "hold_count": hold_count,
            "level_held": hold_count >= 2,
            "is_tight": is_tight,
            "off_high_pct": off_high_pct,
            "good_pullback": good_pullback,
            "momentum": momentum,
            "score": min(score, 8),
        }

    def _pattern_analysis(
        self,
        symbol: str,
        lookback_days: int,
    ) -> tuple[PatternSummaryRow, PatternHeatmapRow, list[PatternDayDetail]] | None:
        frame = self.market_data.download_pattern_history(symbol)
        if frame.empty:
            return None
        regular = self.market_data.regular_session(frame)
        grouped_sessions = {
            session_date: bars.drop(columns=["_session_date"])
            for session_date, bars in regular.assign(_session_date=regular.index.date).groupby("_session_date", sort=True)
        }
        trading_days = sorted(grouped_sessions)[-lookback_days:]
        if len(trading_days) < 5:
            return None

        sector = self._sector_etf(symbol)[1]
        theme = self._ticker_theme(symbol, sector)
        bucket_values: dict[str, list[float]] = {bucket: [] for bucket in BUCKETS_ET}
        details: list[PatternDayDetail] = []
        for session_date in trading_days:
            bars = grouped_sessions[session_date].copy()
            if len(bars) < 10:
                continue
            open_price = float(bars.iloc[0]["Open"])
            if open_price <= 0:
                continue
            bars["pct"] = ((bars["Close"].astype(float) - open_price) / open_price) * 100
            bucket_pct = (
                bars.assign(_bucket=bars.index.strftime("%H:%M"))
                .drop_duplicates("_bucket")
                .set_index("_bucket")["pct"]
                .reindex(BUCKETS_ET)
                .dropna()
            )
            for bucket, pct in bucket_pct.items():
                bucket_values[str(bucket)].append(float(pct))

            morning = bars.between_time("11:00", "12:55")
            if morning.empty:
                continue
            day_low_index = bars["pct"].idxmin()
            morning_low_index = morning["pct"].idxmin()
            morning_low_pct = round(float(morning["pct"].min()), 2)
            close_pct = round(float(bars.iloc[-1]["pct"]), 2)
            details.append(
                PatternDayDetail(
                    ticker=symbol,
                    sector=sector,
                    theme=theme,
                    date=session_date,
                    morning_low_percent=morning_low_pct,
                    morning_low_time=morning_low_index.astimezone(MOUNTAIN).strftime("%I:%M %p MT").lstrip("0"),
                    recovery_to_close_percent=round(close_pct - morning_low_pct, 2),
                    dip_in_window=morning_low_pct < -0.25,
                    day_low_percent=round(float(bars["pct"].min()), 2),
                    day_low_time=day_low_index.astimezone(MOUNTAIN).strftime("%I:%M %p MT").lstrip("0"),
                    close_from_open_percent=close_pct,
                )
            )
        if not details:
            return None

        dip_details = [detail for detail in details if detail.dip_in_window]
        top_times = [f"{time} ({count}x)" for time, count in Counter(detail.morning_low_time for detail in dip_details).most_common(3)]
        avg_bucket = [
            round(sum(values) / len(values), 2) if values else None
            for values in (bucket_values[bucket] for bucket in BUCKETS_ET)
        ]
        summary = PatternSummaryRow(
            sector=sector,
            theme=theme,
            ticker=symbol,
            total_days=len(details),
            dip_days=len(dip_details),
            consistency_percent=round((len(dip_details) / len(details)) * 100),
            average_dip_percent=round(sum(detail.morning_low_percent for detail in dip_details) / len(dip_details), 2)
            if dip_details
            else 0.0,
            average_recovery_percent=round(
                sum(detail.recovery_to_close_percent for detail in dip_details) / len(dip_details), 2
            )
            if dip_details
            else 0.0,
            common_low_time=top_times[0].split(" (", 1)[0] if top_times else None,
            top_low_times=top_times,
        )
        heatmap = PatternHeatmapRow(ticker=symbol, sector=sector, theme=theme, values=avg_bucket)
        return summary, heatmap, details

    @staticmethod
    def _takeaways(summary_rows: list[PatternSummaryRow]) -> list[str]:
        if not summary_rows:
            return []
        takeaways: list[str] = []
        strong = sorted(
            [row for row in summary_rows if row.consistency_percent >= 60],
            key=lambda row: row.consistency_percent,
            reverse=True,
        )
        for row in strong[:5]:
            times = ", ".join(row.top_low_times) or "no common low time"
            takeaways.append(
                f"{row.ticker}: {row.consistency_percent}% consistency, avg dip "
                f"{row.average_dip_percent:.2f}%, avg recovery {row.average_recovery_percent:+.2f}%, {times}."
            )
        average = round(sum(row.consistency_percent for row in summary_rows) / len(summary_rows))
        takeaways.append(f"Average consistency across scanned tickers: {average}% of days had a 9-11am MT dip.")
        return takeaways
