"""Setup scanner and intraday pattern analysis services."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TypedDict
from zoneinfo import ZoneInfo

import pandas as pd

from app.models import (
    EarningsGap,
    PatternDayDetail,
    PatternHeatmapRow,
    PatternSummaryRow,
    ScannerResponse,
    ScannerSetupRow,
    SectorAnalyticsRecommendation,
    SectorAnalyticsResponse,
    SectorAnalyticsRow,
)
from app.services.market_data import EASTERN, MARKET_CLOSE, MARKET_OPEN, MarketDataService
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
    ) -> SectorAnalyticsResponse:
        """Return sector aggregates plus intraday pattern analysis for a watchlist."""
        watchlist = [ticker.upper().strip() for ticker in tickers if ticker.strip()]
        warnings: list[str] = []
        sector_inputs: list[tuple[ScannerLevelData, ScannerSetupRow]] = []
        pattern_summary: list[PatternSummaryRow] = []
        pattern_heatmap: list[PatternHeatmapRow] = []
        pattern_details: list[PatternDayDetail] = []

        self.market_data.prefetch_scanner_downloads(watchlist, include_setup=True, include_patterns=True)

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

        sector_rows = self._sector_rows(watchlist, sector_inputs, pattern_summary)
        recommendations = self._sector_recommendations(sector_rows, len(watchlist))
        takeaways = self._sector_takeaways(sector_rows) + self._takeaways(pattern_summary)
        return SectorAnalyticsResponse(
            generated_at=datetime.now(timezone.utc),
            watchlist=watchlist,
            sector_rows=sector_rows,
            pattern_summary=sorted(pattern_summary, key=lambda row: (row.sector, row.ticker)),
            pattern_buckets=BUCKETS_ET,
            pattern_bucket_labels=BUCKET_LABELS,
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
        warnings: list[str] = []
        pattern_buckets: list[str] = []
        pattern_bucket_labels: list[str] = []

        for response in responses:
            setup_rows.extend(response.setup_rows)
            pattern_summary.extend(response.pattern_summary)
            pattern_heatmap.extend(response.pattern_heatmap)
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
    ) -> str:
        if (
            (average_rs_vs_spy is not None and average_rs_vs_spy > 0)
            or (average_setup_score is not None and average_setup_score >= 5)
            or (average_recovery is not None and average_recovery >= 0.5)
        ):
            return "focus"
        if (
            average_rs_vs_spy is not None
            and average_rs_vs_spy < 0
            and (average_setup_score is None or average_setup_score < 3)
            and (average_recovery is None or average_recovery < 0.25)
        ):
            return "wait"
        return "watch"

    @staticmethod
    def _sector_recommendation_text(row: SectorAnalyticsRow) -> str:
        if row.recommendation_tone == "focus":
            return (
                f"{row.sector} is showing better readiness through relative strength, setup quality, "
                "or pattern recovery across the covered tickers."
            )
        if row.recommendation_tone == "wait":
            return (
                f"{row.sector} is lagging on relative strength and does not yet show broad setup confirmation."
            )
        return f"{row.sector} is mixed; keep it on watch until relative strength or setup quality becomes clearer."

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
        sector = self._sector_etf(symbol)[1]
        avg_bucket = [
            round(sum(values) / len(values), 2) if values else None
            for values in (bucket_values[bucket] for bucket in BUCKETS_ET)
        ]
        summary = PatternSummaryRow(
            sector=sector,
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
        heatmap = PatternHeatmapRow(ticker=symbol, sector=sector, values=avg_bucket)
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
