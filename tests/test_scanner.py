from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from app.main import generate_scanner
from app.models import ScannerRequest, ScannerResponse, ScannerSetupRow
from app.services.market_data import MarketDataService
from app.services.scanner import ScannerService

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
            "Earnings dates were unavailable: provider timeout",
            "Fast price lookup was unavailable for ABC: rate limited",
        ]
    )

    assert visible == ["Fast price lookup was unavailable for ABC: rate limited"]
    assert notes == [
        "At least 200 completed daily closes are required for 200 SMA.",
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
    monkeypatch.setattr(service.market_data, "_download", lambda *args, **kwargs: frame)

    result = service._pattern_analysis("AAPL", 8)

    assert result is not None
    summary, heatmap, details = result
    assert summary.ticker == "AAPL"
    assert summary.consistency_percent == 100
    assert len(heatmap.values) == len(service.build_scanner(["AAPL"], include_setup=False).pattern_buckets)
    assert details


def test_scanner_endpoint_uses_shared_watchlist(monkeypatch):
    class FakeScanner:
        def build_scanner(self, tickers, include_setup=True, include_patterns=True, pattern_lookback_days=30):
            return ScannerResponse(
                generated_at=datetime.now(EASTERN),
                watchlist=tickers,
                setup_rows=[ScannerSetupRow(ticker=tickers[0], score=5)],
            )

    monkeypatch.setattr("app.main.scanner_service", FakeScanner())
    response = generate_scanner(ScannerRequest(tickers="aapl msft"))

    assert response.watchlist == ["AAPL", "MSFT"]
    assert response.setup_rows[0].ticker == "AAPL"
