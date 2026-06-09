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
    assert zones[0]["score"] == 63


def test_score_level_confidence_counts_reactions():
    service = ScannerService()
    session = intraday_frame()

    score, evidence = service._score_level_confidence("Prev Low", 10.0, 10.5, session, "support", 0.75)

    assert score >= 45
    assert any("held" in item for item in evidence)


def test_analyze_setup_scores_level_hold_and_momentum():
    service = ScannerService()
    data = {"price": 10.5, "today_vwap": 10.25, "prev_l": 10.0, "pm_high": 10.6, "pm_low": 9.8}

    setup = service._analyze_setup(data, intraday_frame())

    assert setup is not None
    assert setup["score"] >= 1
    assert setup["nearest_name"] in {"PM High", "VWAP", "Prev Low", "PM Low"}


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
