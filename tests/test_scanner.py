from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import app.services.scanner as scanner_module
from app.main import generate_scanner, generate_sector_analytics
from app.models import (
    ChartHistoryResponse,
    ChartOhlcPoint,
    PatternDayDetail,
    PatternHeatmapRow,
    PatternSummaryRow,
    ScannerRequest,
    ScannerResponse,
    ScannerSetupRow,
    SectorAnalyticsRequest,
    SectorAnalyticsResponse,
    SectorAnalyticsRow,
    TickerChartHistory,
)
from app.services.market_data import MarketDataService
from app.services.scanner import BUCKETS_ET, ScannerService

EASTERN = ZoneInfo("America/New_York")


def intraday_frame() -> pd.DataFrame:
    today = datetime.now(EASTERN).date()
    index = pd.DatetimeIndex(
        [
            datetime.combine(today, time(9, 30), tzinfo=EASTERN),
            datetime.combine(today, time(9, 35), tzinfo=EASTERN),
            datetime.combine(today, time(9, 40), tzinfo=EASTERN),
            datetime.combine(today, time(9, 45), tzinfo=EASTERN),
            datetime.combine(today, time(9, 50), tzinfo=EASTERN),
        ]
    )
    return pd.DataFrame(
        {
            "Open": [10.0, 10.1, 10.0, 10.2, 10.3],
            "High": [10.2, 10.3, 10.25, 10.4, 10.6],
            "Low": [9.95, 10.0, 10.0, 10.1, 10.2],
            "Close": [10.1, 10.0, 10.2, 10.3, 10.5],
            "Volume": [100, 120, 150, 180, 200],
        },
        index=index,
    )


def test_group_levels_into_zones_adds_confluence_score():
    service = ScannerService()
    levels = [
        {"name": "VWAP (Today)", "value": 10.00, "score": 50, "evidence": ["held 1x"]},
        {"name": "Prev High", "value": 10.03, "score": 55, "evidence": []},
        {"name": "PM High", "value": 11.0, "score": 40, "evidence": []},
    ]

    zones = service._group_levels_into_zones(levels, tolerance_pct=0.5)

    assert len(zones) == 2
    assert zones[0]["names"] == ["VWAP (Today)", "Prev High"]
    assert zones[0]["score"] == 60


def test_score_level_confidence_counts_reactions():
    service = ScannerService()
    session = intraday_frame()

    score, evidence = service._score_level_confidence("Prev Low", 10.0, 10.04, session, "support", 0.75)

    assert score >= 45
    assert any("held" in item for item in evidence)


def test_analyze_setup_scores_level_hold_and_momentum():
    service = ScannerService()
    data = {"price": 10.5, "today_vwap": 10.25, "prev_l": 10.0, "pm_high": 10.6, "pm_low": 9.8}

    setup = service._analyze_setup(data, intraday_frame())

    assert setup is not None
    assert setup["score"] >= 1
    assert setup["nearest_name"] in {"PM High", "VWAP", "Prev Low", "PM Low"}


def test_analyze_setup_vectorized_counts_match_level_touch_rules():
    service = ScannerService()
    today = datetime.now(EASTERN).date()
    index = pd.DatetimeIndex(
        [datetime.combine(today, time(9, 30), tzinfo=EASTERN) + timedelta(minutes=offset * 5) for offset in range(5)]
    )
    frame = pd.DataFrame(
        {
            "Open": [10.30, 10.05, 10.10, 10.20, 10.25],
            "High": [10.50, 10.20, 10.25, 10.30, 10.35],
            "Low": [10.30, 9.99, 10.01, 10.02, 10.02],
            "Close": [10.40, 10.10, 10.10, 10.20, 10.30],
            "Volume": [100, 100, 100, 100, 100],
        },
        index=index,
    )
    data = {"price": 10.1, "today_vwap": 10.0}

    setup = service._analyze_setup(data, frame)

    assert setup is not None
    assert setup["nearest_name"] == "VWAP"
    assert setup["consec"] == 4
    assert setup["hold_count"] == 4
    assert setup["momentum"] == "Turning Up"


def test_analyze_setup_matches_adam_scoring_components():
    service = ScannerService()
    today = datetime.now(EASTERN).date()
    index = pd.DatetimeIndex(
        [datetime.combine(today, time(9, 30), tzinfo=EASTERN) + timedelta(minutes=offset * 5) for offset in range(8)]
    )
    frame = pd.DataFrame(
        {
            "Open": [100.7, 100.9, 100.8, 100.6, 100.45, 100.02, 100.06, 100.12],
            "High": [101.2, 101.0, 100.95, 100.75, 100.55, 100.14, 100.18, 100.24],
            "Low": [99.5, 99.6, 99.4, 99.5, 100.35, 99.94, 99.96, 99.98],
            "Close": [100.8, 100.4, 100.6, 100.5, 100.45, 100.05, 100.10, 100.20],
            "Volume": [100, 120, 130, 140, 150, 160, 170, 180],
        },
        index=index,
    )
    data = {
        "price": 100.2,
        "today_vwap": 100.0,
        "vwap": 98.0,
        "prev_h": 103.0,
        "prev_l": 97.0,
        "pm_high": 102.0,
        "pm_low": 96.0,
        "monthly_h": 110.0,
        "monthly_l": 90.0,
    }

    setup = service._analyze_setup(data, frame)

    assert setup is not None
    assert setup["nearest_name"] == "VWAP"
    assert setup["nearest_val"] == 100.0
    assert setup["nearest_pct"] == 0.2
    assert setup["consec"] == 3
    assert setup["hold_count"] == 3
    assert setup["level_held"] is True
    assert bool(setup["is_tight"]) is True
    assert round(float(setup["off_high_pct"]), 2) == -0.99
    assert bool(setup["good_pullback"]) is True
    assert setup["momentum"] == "Turning Up"
    assert setup["score"] == 8


def test_intraday_ema_requires_today_regular_session_bars():
    service = MarketDataService()
    today = datetime.now(EASTERN).date()
    yesterday = today - timedelta(days=1)
    index = []
    closes = []
    for day, count in [(yesterday, 20), (today, 5)]:
        for offset in range(count):
            index.append(datetime.combine(day, time(9, 30), tzinfo=EASTERN) + timedelta(minutes=offset * 5))
            closes.append(float(len(closes) + 1))
    frame = pd.DataFrame({"Close": closes}, index=pd.DatetimeIndex(index))
    warnings: list[str] = []

    ema = service._intraday_ema(frame, 20, warnings)

    assert ema is None
    assert warnings == ["At least 20 intraday closes are required for 20 EMA."]


def test_scanner_candidate_map_excludes_display_only_levels_and_includes_swings():
    data = {
        "today_vwap": 100.0,
        "ema_9_5m": 99.9,
        "ema_20_5m": 99.8,
        "ema_20_daily": 99.7,
        "fib_618": 99.6,
        "r2": 101.0,
        "s2": 98.0,
        "earn_open": 97.0,
        "earn_prev_close": 96.0,
        "swing_highs": [105.0, 106.0, 107.0, 108.0],
        "swing_lows": [95.0, 94.0, 93.0, 92.0],
    }

    level_map = ScannerService._scanner_level_map(data)

    assert "VWAP (Today)" in level_map
    assert "9 EMA (5-Min)" not in level_map
    assert "20 EMA (5-Min)" not in level_map
    assert "20 EMA (Daily)" not in level_map
    assert "Fib 61.8%" not in level_map
    assert "R2 (Pivot)" not in level_map
    assert "S2 (Pivot)" not in level_map
    assert "Earnings Gap Open" not in level_map
    assert list(name for name in level_map if name.startswith("Daily Swing High")) == [
        "Daily Swing High 1",
        "Daily Swing High 2",
        "Daily Swing High 3",
    ]
    assert list(name for name in level_map if name.startswith("Daily Swing Low")) == [
        "Daily Swing Low 1",
        "Daily Swing Low 2",
        "Daily Swing Low 3",
    ]


def test_display_only_levels_do_not_create_scanner_support_or_resistance():
    service = ScannerService()
    data = {
        "price": 100.0,
        "ema_9_5m": 99.9,
        "ema_20_5m": 100.1,
        "ema_20_daily": 100.2,
        "fib_618": 99.8,
        "r2": 100.3,
        "s2": 99.7,
        "earn_open": 99.6,
        "earn_prev_close": 100.4,
    }

    result = service._best_support_resistance(data, intraday_frame())

    assert result["support_zone"] == "No clean support"
    assert result["resistance_zone"] == "No clean resistance"


def test_daily_swing_levels_can_feed_scanner_support():
    service = ScannerService()
    today = datetime.now(EASTERN).date()
    level = 99.8
    frame = pd.DataFrame(
        {
            "Open": [100.0, 100.0, 100.2],
            "High": [99.9, 100.45, 100.5],
            "Low": [99.78, 100.0, 100.1],
            "Close": [99.85, 100.35, 100.4],
            "Volume": [100, 100, 100],
        },
        index=pd.DatetimeIndex(
            [
                datetime.combine(today, time(9, 30), tzinfo=EASTERN),
                datetime.combine(today, time(9, 35), tzinfo=EASTERN),
                datetime.combine(today, time(9, 40), tzinfo=EASTERN),
            ]
        ),
    )
    data = {"price": 100.0, "swing_lows": [level]}

    result = service._best_support_resistance(data, frame)

    assert result["support_zone"] == "$99.80"
    assert "Daily Swing Low 1" in str(result["support_reason"])


def test_previous_session_vwap_is_demoted_after_11am(monkeypatch):
    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            today = datetime.now(EASTERN).date()
            return datetime.combine(today, time(12, 0), tzinfo=tz or EASTERN)

    monkeypatch.setattr("app.services.scanner.datetime", FakeDateTime)
    service = ScannerService()
    today = datetime.now(EASTERN).date()
    frame = pd.DataFrame(
        {
            "Open": [100.0, 100.0, 100.2],
            "High": [100.0, 100.45, 100.5],
            "Low": [99.85, 100.0, 100.1],
            "Close": [99.9, 100.35, 100.4],
            "Volume": [100, 100, 100],
        },
        index=pd.DatetimeIndex(
            [
                datetime.combine(today, time(9, 30), tzinfo=EASTERN),
                datetime.combine(today, time(9, 35), tzinfo=EASTERN),
                datetime.combine(today, time(9, 40), tzinfo=EASTERN),
            ]
        ),
    )

    result = service._best_support_resistance({"price": 100.0, "vwap": 99.9}, frame)

    assert result["support_score"] == 30
    assert result["support_zone"] == "No clean support"


def test_scanner_splits_optional_data_notes_from_visible_warnings():
    visible, notes = ScannerService._split_scanner_messages(
        [
            "At least 200 completed daily closes are required for 200 SMA.",
            "No regular-session intraday bars were returned for today's VWAP.",
            "No premarket bars were returned by the data source for today.",
            "No intraday bars were returned for today's opening range.",
            "At least 21 completed daily bars are required for swing levels.",
            "Earnings dates were unavailable: provider timeout",
            "Fast price lookup was unavailable for ABC: rate limited",
        ]
    )

    assert visible == ["Fast price lookup was unavailable for ABC: rate limited"]
    assert notes == [
        "At least 200 completed daily closes are required for 200 SMA.",
        "No regular-session intraday bars were returned for today's VWAP.",
        "No premarket bars were returned by the data source for today.",
        "No intraday bars were returned for today's opening range.",
        "At least 21 completed daily bars are required for swing levels.",
        "Earnings dates were unavailable: provider timeout",
    ]


def test_pattern_analysis_builds_summary_heatmap_and_details(monkeypatch):
    service = ScannerService(MarketDataService())
    start = datetime.now(EASTERN).date() - timedelta(days=8)
    index = []
    rows = []
    for day_offset in range(8):
        day = start + timedelta(days=day_offset)
        for minute_offset in range(0, 390, 5):
            stamp = datetime.combine(day, time(9, 30), tzinfo=EASTERN) + timedelta(minutes=minute_offset)
            index.append(stamp)
            close = 100.0 - 1.0 if time(11, 0) <= stamp.time() <= time(12, 55) else 100.5
            rows.append({"Open": 100.0, "High": max(100.6, close), "Low": min(99.0, close), "Close": close})
    frame = pd.DataFrame(rows, index=pd.DatetimeIndex(index))
    monkeypatch.setattr(service.market_data, "download_pattern_history", lambda symbol: frame)

    result = service._pattern_analysis("AAPL", 8)

    assert result is not None
    summary, heatmap, details = result
    assert summary.ticker == "AAPL"
    assert summary.consistency_percent == 100
    assert len(heatmap.values) == len(BUCKETS_ET)
    assert details


def test_sector_rows_group_tickers_and_compute_averages():
    rows = ScannerService._sector_rows(
        ["AAPL", "MSFT", "TSLA"],
        [
            (
                {
                    "ticker": "AAPL",
                    "sector": "Technology",
                    "etf": "XLK",
                    "stock_pct": 1.0,
                    "sector_pct": 0.3,
                    "rs_vs_spy": 0.6,
                    "rs_vs_sector": 0.7,
                },
                ScannerSetupRow(ticker="AAPL", score=6),
            ),
            (
                {
                    "ticker": "MSFT",
                    "sector": "Technology",
                    "etf": "XLK",
                    "stock_pct": 2.0,
                    "sector_pct": 0.3,
                    "rs_vs_spy": 1.4,
                    "rs_vs_sector": 1.7,
                },
                ScannerSetupRow(ticker="MSFT", score=4),
            ),
            (
                {
                    "ticker": "TSLA",
                    "sector": "Consumer Cyclical",
                    "etf": "XLY",
                    "stock_pct": -1.0,
                    "sector_pct": -0.4,
                    "rs_vs_spy": -1.2,
                    "rs_vs_sector": -0.6,
                },
                ScannerSetupRow(ticker="TSLA", score=2),
            ),
        ],
        [
            PatternSummaryRow(
                sector="Technology",
                ticker="AAPL",
                total_days=10,
                dip_days=6,
                consistency_percent=60,
                average_dip_percent=-0.8,
                average_recovery_percent=0.7,
                top_low_times=["10:00 AM MT (2x)"],
            )
        ],
    )

    technology = next(row for row in rows if row.sector == "Technology")

    assert technology.ticker_count == 2
    assert technology.weight_percent == 66.7
    assert technology.average_day_change_percent == 1.5
    assert technology.average_rs_vs_spy_percent == 1.0
    assert technology.average_setup_score == 5.0
    assert technology.strong_setup_count == 1
    assert technology.average_pattern_consistency_percent == 60.0
    assert technology.common_low_times == ["10:00 AM MT (2x)"]


def test_sector_trends_normalize_and_enrich_rows():
    timestamps = [
        datetime(2026, 6, 1, 14, 30, tzinfo=timezone.utc),
        datetime(2026, 6, 2, 14, 30, tzinfo=timezone.utc),
    ]

    class FakeMarketData:
        def build_chart_history(self, symbols, chart_range, interval):
            closes = {
                "AAPL": (100, 115),
                "MSFT": (100, 95),
                "XLK": (100, 108),
                "SPY": (100, 102),
            }
            charts = []
            for symbol in symbols:
                first, second = closes.get(symbol, (100, 101))
                charts.append(
                    TickerChartHistory(
                        ticker=symbol,
                        range=chart_range,
                        interval=interval,
                        points=[
                            ChartOhlcPoint(timestamp=timestamps[0], open=first, high=first, low=first, close=first),
                            ChartOhlcPoint(timestamp=timestamps[1], open=second, high=second, low=second, close=second),
                        ],
                    )
                )
            return ChartHistoryResponse(
                generated_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
                range=chart_range,
                interval=interval,
                charts=charts,
            )

    service = ScannerService(FakeMarketData())  # type: ignore[arg-type]
    row = SectorAnalyticsRow(
        sector="Technology",
        etf="XLK",
        ticker_count=2,
        weight_percent=100.0,
        tickers=["AAPL", "MSFT"],
        recommendation_text="",
    )

    sector_series, benchmark_series, macro_series, theme_series, warnings = service._build_sector_trends(
        ["AAPL", "MSFT"],
        [row],
        "3M",
        "1d",
    )

    assert warnings == []
    assert row.trend_change_percent == 5.0
    assert row.sector_etf_trend_change_percent == 8.0
    assert row.trend_rs_vs_spy_percent == 3.0
    assert row.up_ticker_count == 1
    assert row.down_ticker_count == 1
    assert row.leader_tickers == ["AAPL", "MSFT"]
    assert row.laggard_tickers == ["MSFT", "AAPL"]
    assert {series.kind for series in sector_series} == {"watchlist_sector", "sector_etf"}
    assert {series.kind for series in theme_series} == {"watchlist_theme", "theme_basket"}
    assert next(series for series in theme_series if series.kind == "theme_basket").theme == "Mega-cap Tech"
    assert benchmark_series[0].symbol == "SPY"
    assert macro_series


def test_sector_trends_include_capped_theme_basket_context_and_dedupe_symbols(monkeypatch):
    timestamps = [
        datetime(2026, 6, 1, 14, 30, tzinfo=timezone.utc),
        datetime(2026, 6, 2, 14, 30, tzinfo=timezone.utc),
    ]

    monkeypatch.setattr(
        scanner_module,
        "THEME_TREND_BASKETS",
        {"Space": ("RKLB", "ASTS", "BKSY", "LUNR", "RDW")},
    )
    monkeypatch.setattr(scanner_module, "THEME_TREND_BASKET_LIMIT", 4)

    class FakeMarketData:
        symbols: list[str] = []

        def build_chart_history(self, symbols, chart_range, interval):
            self.symbols = list(symbols)
            return ChartHistoryResponse(
                generated_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
                range=chart_range,
                interval=interval,
                charts=[
                    TickerChartHistory(
                        ticker=symbol,
                        range=chart_range,
                        interval=interval,
                        points=[
                            ChartOhlcPoint(timestamp=timestamps[0], open=100, high=100, low=100, close=100),
                            ChartOhlcPoint(timestamp=timestamps[1], open=101, high=101, low=101, close=101),
                        ],
                    )
                    for symbol in symbols
                ],
            )

    fake_market_data = FakeMarketData()
    service = ScannerService(fake_market_data)  # type: ignore[arg-type]
    row = SectorAnalyticsRow(
        sector="Industrials",
        etf="XLI",
        ticker_count=2,
        weight_percent=100.0,
        tickers=["RKLB", "BKSY"],
        recommendation_text="",
    )

    _, _, _, theme_series, warnings = service._build_sector_trends(
        ["RKLB", "BKSY"],
        [row],
        "3M",
        "1d",
    )

    assert warnings == []
    assert fake_market_data.symbols.count("RKLB") == 1
    assert fake_market_data.symbols.count("BKSY") == 1
    assert "ASTS" in fake_market_data.symbols
    assert "LUNR" in fake_market_data.symbols
    assert "RDW" not in fake_market_data.symbols
    assert len(fake_market_data.symbols) == len(set(fake_market_data.symbols))
    assert next(series for series in theme_series if series.kind == "watchlist_theme").theme == "Space"
    assert next(series for series in theme_series if series.kind == "theme_basket").label == "Space Basket"


def test_sector_trends_keep_theme_basket_failures_as_warnings(monkeypatch):
    timestamps = [
        datetime(2026, 6, 1, 14, 30, tzinfo=timezone.utc),
        datetime(2026, 6, 2, 14, 30, tzinfo=timezone.utc),
    ]

    monkeypatch.setattr(scanner_module, "THEME_TREND_BASKETS", {"Space": ("RKLB", "ASTS")})

    class FakeMarketData:
        def build_chart_history(self, symbols, chart_range, interval):
            charts = [
                TickerChartHistory(
                    ticker=symbol,
                    range=chart_range,
                    interval=interval,
                    points=[
                        ChartOhlcPoint(timestamp=timestamps[0], open=100, high=100, low=100, close=100),
                        ChartOhlcPoint(timestamp=timestamps[1], open=101, high=101, low=101, close=101),
                    ],
                )
                for symbol in symbols
                if symbol != "ASTS"
            ]
            return ChartHistoryResponse(
                generated_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
                range=chart_range,
                interval=interval,
                charts=charts,
            )

    service = ScannerService(FakeMarketData())  # type: ignore[arg-type]
    row = SectorAnalyticsRow(
        sector="Industrials",
        etf="XLI",
        ticker_count=1,
        weight_percent=100.0,
        tickers=["RKLB"],
        recommendation_text="",
    )

    _, _, _, theme_series, warnings = service._build_sector_trends(["RKLB"], [row], "3M", "1d")

    assert any("No trend chart was returned for ASTS" in warning for warning in warnings)
    assert next(series for series in theme_series if series.kind == "theme_basket").change_percent == 1.0


def test_sector_analytics_keeps_valid_response_when_prefetch_raises(monkeypatch):
    service = ScannerService()

    def raise_prefetch(tickers, include_setup=True, include_patterns=True):
        del tickers, include_setup, include_patterns
        raise TypeError("batch download failed")

    def raise_load_ticker_data(symbol, benchmark_cache, include_earnings=False):
        del benchmark_cache, include_earnings
        raise RuntimeError(f"{symbol} setup unavailable")

    monkeypatch.setattr(service.market_data, "prefetch_scanner_downloads", raise_prefetch)
    monkeypatch.setattr(service, "_load_ticker_data", raise_load_ticker_data)
    monkeypatch.setattr(service, "_pattern_analysis", lambda symbol, lookback_days: None)
    monkeypatch.setattr(service, "_build_sector_trends", lambda *args: ([], [], [], [], []))

    response = service.build_sector_analytics(["AAPL"], trend_range="3M", trend_interval="1d")

    assert response.watchlist == ["AAPL"]
    assert response.sector_rows == []
    assert "Sector analytics prefetch failed: TypeError: batch download failed" in response.warnings
    assert "Sector setup analytics failed for AAPL: AAPL setup unavailable" in response.warnings


def test_sector_analytics_keeps_sector_rows_when_trend_post_processing_raises(monkeypatch):
    row = SectorAnalyticsRow(
        sector="Technology",
        etf="XLK",
        ticker_count=1,
        weight_percent=100.0,
        tickers=["AAPL"],
        recommendation_text="",
    )

    class MalformedChartHistoryMarketData:
        def prefetch_scanner_downloads(self, tickers, include_setup=True, include_patterns=True):
            del tickers, include_setup, include_patterns

        def build_chart_history(self, symbols, chart_range, interval):
            del symbols, chart_range, interval

            class BadResponse:
                warnings: list[str] = []
                charts = None

            return BadResponse()

    service = ScannerService(MalformedChartHistoryMarketData())  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_load_ticker_data", lambda symbol, benchmark_cache, include_earnings=False: (_ for _ in ()).throw(RuntimeError("skip setup")))
    monkeypatch.setattr(service, "_pattern_analysis", lambda symbol, lookback_days: None)
    monkeypatch.setattr(service, "_sector_rows", lambda watchlist, sector_inputs, pattern_summary: [row])

    response = service.build_sector_analytics(["AAPL"], trend_range="3M", trend_interval="1d")

    assert response.sector_rows == [row]
    assert response.sector_trend_series == []
    assert response.theme_trend_series == []
    assert any("Trend processing failed for sector analytics: TypeError" in warning for warning in response.warnings)


def test_theme_overrides_group_space_names_without_changing_sector():
    assert ScannerService()._sector_etf("RKLB") == ("XLI", "Industrials")
    assert ScannerService._ticker_theme("RKLB", "Industrials") == "Space"
    assert ScannerService._ticker_theme("AAPL", "Technology") == "Mega-cap Tech"
    assert ScannerService._ticker_theme("UNH", "Healthcare") == "Healthcare"


def test_theme_heatmap_rows_average_finite_bucket_values():
    rows = ScannerService._theme_heatmap_rows(
        [
            PatternHeatmapRow(ticker="RKLB", sector="Industrials", theme="Space", values=[-1.0, None, 0.5]),
            PatternHeatmapRow(ticker="ASTS", sector="Communication Services", theme="Space", values=[-3.0, 1.0, None]),
            PatternHeatmapRow(ticker="AAPL", sector="Technology", theme="Mega-cap Tech", values=[2.0, 3.0, 4.0]),
        ]
    )

    space = next(row for row in rows if row.theme == "Space")

    assert space.ticker_count == 2
    assert space.tickers == ["ASTS", "RKLB"]
    assert space.values == [-2.0, 1.0, 0.5]
    assert rows[0].theme == "Space"


def test_sector_recommendations_include_concentration_and_tones():
    rows = ScannerService._sector_rows(
        ["AAPL", "MSFT", "TSLA"],
        [
            ({"ticker": "AAPL", "sector": "Technology", "rs_vs_spy": 0.5}, ScannerSetupRow(ticker="AAPL", score=4)),
            ({"ticker": "MSFT", "sector": "Technology", "rs_vs_spy": 0.1}, ScannerSetupRow(ticker="MSFT", score=4)),
            ({"ticker": "TSLA", "sector": "Consumer Cyclical", "rs_vs_spy": -1.0}, ScannerSetupRow(ticker="TSLA", score=2)),
        ],
        [
            PatternSummaryRow(
                sector="Consumer Cyclical",
                ticker="TSLA",
                total_days=10,
                dip_days=3,
                consistency_percent=30,
                average_dip_percent=-0.5,
                average_recovery_percent=0.1,
            )
        ],
    )

    recommendations = ScannerService._sector_recommendations(rows, 3)
    tones = {item.sector: item.tone for item in recommendations if item.sector}

    assert recommendations[0].tone == "note"
    assert recommendations[0].sector == "Technology"
    assert tones["Technology"] == "focus"
    assert tones["Consumer Cyclical"] == "wait"


def test_merge_scanner_responses_sorts_and_preserves_output_shape():
    generated_at = datetime(2026, 6, 15, tzinfo=timezone.utc)
    first = ScannerResponse(
        generated_at=generated_at,
        watchlist=["MSFT", "AAPL"],
        setup_rows=[
            ScannerSetupRow(ticker="MSFT", score=3),
            ScannerSetupRow(ticker="AAPL", score=8),
        ],
        pattern_summary=[
            PatternSummaryRow(
                sector="Technology",
                ticker="MSFT",
                total_days=10,
                dip_days=5,
                consistency_percent=50,
                average_dip_percent=-0.7,
                average_recovery_percent=0.3,
            )
        ],
        pattern_heatmap=[PatternHeatmapRow(ticker="MSFT", sector="Technology", values=[0.1])],
        pattern_details=[
            PatternDayDetail(
                ticker="MSFT",
                date=date(2026, 6, 12),
                morning_low_percent=-0.5,
                morning_low_time="10:00",
                recovery_to_close_percent=0.2,
                dip_in_window=True,
                day_low_percent=-0.6,
                day_low_time="10:05",
                close_from_open_percent=0.1,
            )
        ],
        warnings=["MSFT warning"],
    )
    second = ScannerResponse(
        generated_at=generated_at + timedelta(minutes=1),
        watchlist=["NVDA", "TSLA"],
        setup_rows=[
            ScannerSetupRow(ticker="NVDA", score=8),
            ScannerSetupRow(ticker="TSLA", score=None),
        ],
        pattern_summary=[
            PatternSummaryRow(
                sector="Consumer Cyclical",
                ticker="TSLA",
                total_days=10,
                dip_days=7,
                consistency_percent=70,
                average_dip_percent=-1.2,
                average_recovery_percent=0.8,
                top_low_times=["10:15 (3x)"],
            )
        ],
        pattern_heatmap=[PatternHeatmapRow(ticker="TSLA", sector="Consumer Cyclical", values=[-0.2])],
        pattern_details=[
            PatternDayDetail(
                ticker="TSLA",
                date=date(2026, 6, 12),
                morning_low_percent=-1.0,
                morning_low_time="10:15",
                recovery_to_close_percent=0.8,
                dip_in_window=True,
                day_low_percent=-1.1,
                day_low_time="10:20",
                close_from_open_percent=0.3,
            )
        ],
        warnings=["TSLA warning"],
    )

    merged = ScannerService.merge_responses(("MSFT", "AAPL", "NVDA", "TSLA"), [first, second])

    assert merged.generated_at == generated_at + timedelta(minutes=1)
    assert merged.watchlist == ["MSFT", "AAPL", "NVDA", "TSLA"]
    assert [row.ticker for row in merged.setup_rows] == ["AAPL", "NVDA", "MSFT", "TSLA"]
    assert [row.ticker for row in merged.pattern_summary] == ["TSLA", "MSFT"]
    assert [row.ticker for row in merged.pattern_heatmap] == ["TSLA", "MSFT"]
    assert [detail.ticker for detail in merged.pattern_details] == ["MSFT", "TSLA"]
    assert merged.warnings == ["MSFT warning", "TSLA warning"]
    assert merged.pattern_buckets == BUCKETS_ET
    assert any(takeaway.startswith("TSLA: 70% consistency") for takeaway in merged.takeaways)
    assert merged.takeaways[-1] == "Average consistency across scanned tickers: 60% of days had a 9-11am MT dip."


def test_replace_setup_rows_preserves_pattern_outputs():
    generated_at = datetime(2026, 6, 15, tzinfo=timezone.utc)
    base = ScannerResponse(
        generated_at=generated_at,
        watchlist=["AAPL", "MSFT"],
        setup_rows=[ScannerSetupRow(ticker="AAPL", score=2), ScannerSetupRow(ticker="MSFT", score=4)],
        pattern_summary=[
            PatternSummaryRow(
                sector="Technology",
                ticker="AAPL",
                total_days=10,
                dip_days=6,
                consistency_percent=60,
                average_dip_percent=-0.7,
                average_recovery_percent=0.3,
            )
        ],
        pattern_heatmap=[PatternHeatmapRow(ticker="AAPL", sector="Technology", values=[0.1])],
        warnings=["base warning"],
    )
    update = ScannerResponse(
        generated_at=generated_at + timedelta(minutes=1),
        watchlist=["AAPL"],
        setup_rows=[ScannerSetupRow(ticker="AAPL", score=8)],
        warnings=["update warning"],
    )

    merged = ScannerService.replace_setup_rows(("AAPL", "MSFT"), base, [update])

    assert merged.generated_at == generated_at + timedelta(minutes=1)
    assert [row.ticker for row in merged.setup_rows] == ["AAPL", "MSFT"]
    assert [row.score for row in merged.setup_rows] == [8, 4]
    assert merged.pattern_summary == base.pattern_summary
    assert merged.pattern_heatmap == base.pattern_heatmap
    assert merged.warnings == ["base warning", "update warning"]


def test_scanner_endpoint_uses_shared_watchlist(monkeypatch):
    class FakeScanner:
        def build_scanner(
            self,
            tickers,
            include_setup=True,
            include_patterns=True,
            include_earnings=True,
            pattern_lookback_days=30,
        ):
            del include_setup, include_patterns, include_earnings, pattern_lookback_days
            return ScannerResponse(
                generated_at=datetime.now(EASTERN),
                watchlist=tickers,
                setup_rows=[ScannerSetupRow(ticker=tickers[0], score=5)],
            )

    class FakeScoreHistory:
        def record_setup_scores(self, rows):
            self.rows = rows
            return []

    monkeypatch.setattr("app.main.scanner_service", FakeScanner())
    monkeypatch.setattr("app.main.score_history_service", FakeScoreHistory())
    response = generate_scanner(ScannerRequest(tickers="aapl msft"))

    assert response.watchlist == ["AAPL", "MSFT"]
    assert response.setup_rows[0].ticker == "AAPL"


def test_sector_analytics_endpoint_uses_shared_watchlist(monkeypatch):
    class FakeScanner:
        def build_sector_analytics(self, tickers, pattern_lookback_days=30, trend_range="3M", trend_interval="1d"):
            del pattern_lookback_days
            self.trend_range = trend_range
            self.trend_interval = trend_interval
            return SectorAnalyticsResponse(
                generated_at=datetime.now(EASTERN),
                watchlist=tickers,
            )

    fake = FakeScanner()
    monkeypatch.setattr("app.main.scanner_service", fake)
    response = generate_sector_analytics(SectorAnalyticsRequest(tickers="aapl msft", trend_range="1Y", trend_interval="1wk"))

    assert response.watchlist == ["AAPL", "MSFT"]
    assert fake.trend_range == "1Y"
    assert fake.trend_interval == "1wk"


def test_scanner_can_request_setup_without_patterns(monkeypatch):
    service = ScannerService()
    monkeypatch.setattr(service.market_data, "prefetch_scanner_downloads", lambda tickers, include_setup=True, include_patterns=True: None)
    monkeypatch.setattr(service, "_load_ticker_data", lambda symbol, benchmark_cache, include_earnings=True: symbol)
    monkeypatch.setattr(service, "_setup_row", lambda scan_data: ScannerSetupRow(ticker=scan_data, score=5))

    response = service.build_scanner(["AAPL"], include_setup=True, include_patterns=False)

    assert response.setup_rows[0].ticker == "AAPL"
    assert response.pattern_summary == []
    assert response.pattern_heatmap == []


def test_scanner_does_not_depend_on_market_data_private_methods():
    source = Path("app/services/scanner.py").read_text(encoding="utf-8")

    assert "market_data._" not in source
