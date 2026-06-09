"""Setup scanner and intraday pattern analysis services."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from app.models import (
    PatternDayDetail,
    PatternHeatmapRow,
    PatternSummaryRow,
    ScannerResponse,
    ScannerSetupRow,
)
from app.services.market_data import EASTERN, MARKET_CLOSE, MARKET_OPEN, MarketDataService

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

LEVEL_TYPE_WEIGHTS = {
    "VWAP (Today)": 30,
    "PM High": 28,
    "PM Low": 28,
    "Prev High": 26,
    "Prev Low": 26,
    "5-Min High": 22,
    "5-Min Low": 22,
    "1-Month High": 20,
    "1-Month Low": 20,
    "VWAP (Prev Session)": 18,
    "Prev Close": 16,
    "200 SMA (Daily)": 16,
    "50 SMA (Daily)": 14,
    "9 EMA (5-Min)": 14,
    "20 EMA (Daily)": 12,
    "20 EMA (5-Min)": 12,
    "Pivot": 10,
    "R1 (Pivot)": 10,
    "S1 (Pivot)": 10,
    "R2 (Pivot)": 8,
    "S2 (Pivot)": 8,
    "Earnings Gap Open": 8,
    "Pre-Earnings Close": 8,
    "Fib 61.8%": 8,
    "Fib 50.0%": 7,
    "Fib 38.2%": 6,
}

SIGNAL_PRIORITY = ["VWAP", "PM High", "Prev High", "Prev Low", "R1", "S1", "9 EMA", "Pivot"]


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


@dataclass
class TickerScanData:
    """Intermediate scanner data for one ticker."""

    symbol: str
    data: dict[str, object]
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
        pattern_lookback_days: int = LOOKBACK_DAYS,
    ) -> ScannerResponse:
        """Return setup scanner rows and optional intraday pattern analysis."""
        watchlist = [ticker.upper().strip() for ticker in tickers if ticker.strip()]
        warnings: list[str] = []
        setup_rows: list[ScannerSetupRow] = []
        pattern_summary: list[PatternSummaryRow] = []
        pattern_heatmap: list[PatternHeatmapRow] = []
        pattern_details: list[PatternDayDetail] = []

        benchmark_cache: dict[str, float | None] = {}
        if include_setup:
            for symbol in watchlist:
                try:
                    scan_data = self._load_ticker_data(symbol, benchmark_cache)
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

    def _load_ticker_data(self, symbol: str, benchmark_cache: dict[str, float | None]) -> TickerScanData:
        warnings: list[str] = []
        daily = self.market_data.download_scanner_daily_history(symbol)
        minute = self.market_data.download_today_minute_history(symbol)
        five_minute = self.market_data.download_five_minute_history(symbol)

        previous = self.market_data._previous_day_ohlc(daily, warnings)
        monthly_high, monthly_low = self.market_data._monthly_range(daily, warnings)
        previous_session = self.market_data._previous_regular_session(five_minute, warnings)
        pivots = self.market_data._pivot_points(previous)
        fibs = self.market_data._fibonacci_levels(monthly_high, monthly_low)
        earnings = self.market_data._earnings_gap(symbol, daily, warnings)
        price = self.market_data._current_price(symbol, minute, warnings)
        today_vwap = self.market_data._today_vwap(minute, warnings)
        previous_vwap = self.market_data._vwap(previous_session, warnings)
        premarket = self.market_data._today_premarket_range(minute, warnings)
        opening = self.market_data._opening_range(minute, warnings)
        etf, sector = self._sector_etf(symbol)

        stock_pct = self.market_data._pct_from(price, previous.close)
        spy_pct = self._benchmark_pct("SPY", benchmark_cache)
        sector_pct = self._benchmark_pct(etf, benchmark_cache) if etf else None

        data: dict[str, object] = {
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
            "sma_50": self.market_data._sma(daily, 50, warnings),
            "sma_200": self.market_data._sma(daily, 200, warnings),
            "ema_20_daily": self.market_data._daily_ema(daily, 20, warnings),
            "ema_9_5m": self.market_data._intraday_ema(five_minute, 9, warnings),
            "ema_20_5m": self.market_data._intraday_ema(five_minute, 20, warnings),
            "pivot": pivots["pivot"],
            "r1": pivots["r1"],
            "s1": pivots["s1"],
            "r2": pivots["r2"],
            "s2": pivots["s2"],
            "fib_382": fibs["fib_382"],
            "fib_500": fibs["fib_500"],
            "fib_618": fibs["fib_618"],
            "earn_open": None,
            "earn_prev_close": None,
            "earn_gap": earnings.gap,
            "sector": sector,
            "etf": etf,
            "stock_pct": stock_pct,
            "rs_vs_spy": round(stock_pct - spy_pct, 2) if stock_pct is not None and spy_pct is not None else None,
            "rs_vs_sector": round(stock_pct - sector_pct, 2)
            if stock_pct is not None and sector_pct is not None
            else None,
        }
        data["vwap_ext"] = self.market_data._pct_from(price, today_vwap or previous_vwap)
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
        previous = self.market_data._previous_day_ohlc(daily, warnings)
        price = self.market_data._current_price(symbol, minute, warnings)
        cache[symbol] = self.market_data._pct_from(price, previous.close)
        return cache[symbol]

    @staticmethod
    def _sector_etf(symbol: str) -> tuple[str | None, str]:
        etf = TICKER_ETF.get(symbol)
        if etf:
            sector = next((name for name, sector_etf in SECTOR_ETF.items() if sector_etf == etf), "")
            return etf, sector or "Other"
        return None, "Other"

    def _setup_row(self, scan_data: TickerScanData) -> ScannerSetupRow:
        data = scan_data.data
        setup = data.get("setup") if isinstance(data.get("setup"), dict) else None
        sr = data.get("sr") if isinstance(data.get("sr"), dict) else {}
        signal = data.get("signal") if isinstance(data.get("signal"), str) else None
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
            warnings=scan_data.warnings,
        )

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

    def _best_support_resistance(self, data: dict[str, object], five_minute: pd.DataFrame) -> dict[str, object]:
        price = self._float(data.get("price"))
        if price is None:
            return {}
        session = self.market_data._today_regular_session(five_minute)
        atr_pct = self._atr_5m_pct(five_minute)
        zone_tol = min(max(0.25, atr_pct * 100), 1.5)
        react_tol = min(max(0.20, atr_pct * 100 * 0.75), 1.0)

        level_map = self._scanner_level_map(data)
        support_candidates: list[dict[str, object]] = []
        resistance_candidates: list[dict[str, object]] = []
        for name, raw_value in level_map.items():
            value = self._float(raw_value)
            if value is None or value <= 0:
                continue
            side = "support" if value < price else "resistance"
            score, evidence = self._score_level_confidence(name, value, price, session, side, react_tol)
            entry = {"name": name, "value": value, "score": score, "evidence": evidence}
            if side == "support":
                support_candidates.append(entry)
            else:
                resistance_candidates.append(entry)

        support_zones = [zone for zone in self._group_levels_into_zones(support_candidates, zone_tol) if zone["high"] < price]
        resistance_zones = [zone for zone in self._group_levels_into_zones(resistance_candidates, zone_tol) if zone["low"] > price]
        best_support = max(support_zones, key=lambda zone: zone["score"], default=None)
        best_resistance = max(resistance_zones, key=lambda zone: zone["score"], default=None)
        support_score = int(best_support["score"]) if best_support else 0
        resistance_score = int(best_resistance["score"]) if best_resistance else 0
        min_confidence = 50

        room_up = (
            self.market_data._pct_from(price, self._float(best_resistance["low"]))
            if best_resistance and resistance_score >= min_confidence
            else None
        )
        risk_down = (
            self.market_data._pct_from(price, self._float(best_support["high"]))
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
    def _scanner_level_map(data: dict[str, object]) -> dict[str, object]:
        return {
            "VWAP (Today)": data.get("today_vwap"),
            "VWAP (Prev Session)": data.get("vwap"),
            "PM High": data.get("pm_high"),
            "PM Low": data.get("pm_low"),
            "Prev High": data.get("prev_h"),
            "Prev Low": data.get("prev_l"),
            "Prev Close": data.get("prev_c"),
            "5-Min High": data.get("f5_high"),
            "5-Min Low": data.get("f5_low"),
            "9 EMA (5-Min)": data.get("ema_9_5m"),
            "20 EMA (5-Min)": data.get("ema_20_5m"),
            "50 SMA (Daily)": data.get("sma_50"),
            "200 SMA (Daily)": data.get("sma_200"),
            "20 EMA (Daily)": data.get("ema_20_daily"),
            "Pivot": data.get("pivot"),
            "R1 (Pivot)": data.get("r1"),
            "S1 (Pivot)": data.get("s1"),
            "R2 (Pivot)": data.get("r2"),
            "S2 (Pivot)": data.get("s2"),
            "1-Month High": data.get("monthly_h"),
            "1-Month Low": data.get("monthly_l"),
            "Fib 61.8%": data.get("fib_618"),
            "Fib 50.0%": data.get("fib_500"),
            "Fib 38.2%": data.get("fib_382"),
            "Earnings Gap Open": data.get("earn_open"),
            "Pre-Earnings Close": data.get("earn_prev_close"),
        }

    def _atr_5m_pct(self, five_minute: pd.DataFrame) -> float:
        if five_minute.empty:
            return 0.003
        try:
            session = self.market_data._today_regular_session(five_minute)
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
        reactions = 0
        last_reaction = None
        for index, row in session.iterrows():
            if side == "support":
                if abs(float(row["Low"]) - level) <= tolerance and float(row["Close"]) > level * 0.9985:
                    reactions += 1
                    last_reaction = index
            elif abs(float(row["High"]) - level) <= tolerance and float(row["Close"]) < level * 1.0015:
                reactions += 1
                last_reaction = index
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
        score = LEVEL_TYPE_WEIGHTS.get(name, 5)
        evidence: list[str] = []
        distance_pct = abs((price - value) / value) * 100
        if distance_pct <= 0.25:
            score += 20
        elif distance_pct <= 0.50:
            score += 15
        elif distance_pct <= 1.00:
            score += 10
        elif distance_pct <= 2.00:
            score += 5
        else:
            score -= 10

        reactions, recency = self._count_level_reactions(session, value, side, tol_pct)
        score += recency
        verb = "held" if side == "support" else "rejected"
        if reactions >= 3:
            score += 25
            evidence.append(f"{verb} {reactions}x")
        elif reactions == 2:
            score += 18
            evidence.append(f"{verb} 2x")
        elif reactions == 1:
            score += 8
            evidence.append(f"{verb} 1x")
        return min(max(score, 0), 100), evidence

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
            zone["score"] = min(base_score + 8 * (len(members) - 1), 100)
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

    def _detect_reclaim_rejection(self, data: dict[str, object], five_minute: pd.DataFrame) -> str | None:
        session = self.market_data._today_regular_session(five_minute)
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
            "9 EMA": data.get("ema_9_5m"),
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

    def _analyze_setup(self, data: dict[str, object], five_minute: pd.DataFrame) -> dict[str, object] | None:
        price = self._float(data.get("price"))
        if price is None:
            return None
        session = self.market_data._today_regular_session(five_minute)
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
            pct = abs(self.market_data._pct_from(price, value) or 999)
            if value is not None and pct < nearest_pct:
                nearest_name = name
                nearest_value = value
                nearest_pct = pct
        if nearest_value is None or nearest_name is None:
            return None

        consecutive = 0
        for _, row in session.iloc[::-1].iterrows():
            distances = [
                abs(((float(row["High"]) - nearest_value) / nearest_value) * 100),
                abs(((float(row["Low"]) - nearest_value) / nearest_value) * 100),
                abs(((float(row["Close"]) - nearest_value) / nearest_value) * 100),
            ]
            if min(distances) <= 0.25:
                consecutive += 1
            else:
                break

        hold_count = 0
        for _, row in session.tail(10).iterrows():
            low_pct = ((float(row["Low"]) - nearest_value) / nearest_value) * 100
            close_pct = ((float(row["Close"]) - nearest_value) / nearest_value) * 100
            if abs(low_pct) <= 0.25 and close_pct > 0:
                hold_count += 1

        last_three = session.tail(3)
        avg_recent = (last_three["High"].astype(float) - last_three["Low"].astype(float)).mean()
        avg_session = (session["High"].astype(float) - session["Low"].astype(float)).mean()
        is_tight = (avg_recent / avg_session) < 0.65 if avg_session > 0 else False
        session_high = float(session["High"].astype(float).max())
        off_high_pct = self.market_data._pct_from(price, session_high)
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
        frame = self.market_data._download(
            symbol,
            period=self.market_data.settings.pattern_history_period,
            interval="5m",
            prepost=False,
        )
        if frame.empty:
            return None
        localized = self.market_data._with_eastern_index(frame)
        regular = localized.between_time(MARKET_OPEN, MARKET_CLOSE, inclusive="left")
        trading_days = sorted(set(regular.index.date))[-lookback_days:]
        if len(trading_days) < 5:
            return None

        bucket_values: dict[str, list[float]] = {bucket: [] for bucket in BUCKETS_ET}
        details: list[PatternDayDetail] = []
        for session_date in trading_days:
            bars = regular[regular.index.date == session_date].copy()
            if len(bars) < 10:
                continue
            open_price = float(bars.iloc[0]["Open"])
            if open_price <= 0:
                continue
            bars["pct"] = ((bars["Close"].astype(float) - open_price) / open_price) * 100
            for bucket in BUCKETS_ET:
                slot = bars[bars.index.strftime("%H:%M") == bucket]
                if not slot.empty:
                    bucket_values[bucket].append(float(slot["pct"].iloc[0]))

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
