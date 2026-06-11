from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models import (
    ChartHistoryRequest,
    ChartOhlcPoint,
    IntradayPricePoint,
    MarketSnapshotRequest,
    MarketSnapshotRow,
    NewsRequest,
    TickerChartHistory,
    GenerateRequest,
)


def test_generate_request_accepts_delimited_tickers():
    request = GenerateRequest(tickers="aapl, msft\nNVDA aapl")

    assert request.tickers == ["AAPL", "MSFT", "NVDA"]


def test_generate_request_accepts_and_deduplicates_metric_selection():
    request = GenerateRequest(tickers="aapl", metrics="previous_day previous_day swing_levels")

    assert request.metrics == ["previous_day", "swing_levels"]


def test_news_request_reuses_watchlist_normalization():
    request = NewsRequest(tickers="aapl, msft\nAAPL")

    assert request.tickers == ["AAPL", "MSFT"]


def test_news_request_accepts_expanded_headline_count():
    request = NewsRequest(tickers="aapl", per_ticker=20)

    assert request.per_ticker == 20


def test_market_snapshot_request_reuses_watchlist_normalization():
    request = MarketSnapshotRequest(tickers="spy, qqq\nSPY")

    assert request.tickers == ["SPY", "QQQ"]


def test_market_snapshot_row_accepts_intraday_sparkline_points():
    point = IntradayPricePoint(timestamp=datetime(2026, 6, 11, 14, 30, tzinfo=timezone.utc), close=101.25)
    row = MarketSnapshotRow(symbol="SPY", label="SPY", price=101.25, sparkline=[point])

    assert row.sparkline[0].close == 101.25


def test_chart_history_request_normalizes_tickers_and_accepts_supported_combo():
    request = ChartHistoryRequest(tickers="msft aapl\nMSFT", range="6M", interval="1wk")

    assert request.tickers == ["MSFT", "AAPL"]
    assert request.range == "6M"
    assert request.interval == "1wk"


def test_chart_history_request_accepts_expanded_short_interval():
    request = ChartHistoryRequest(tickers="aapl", range="1D", interval="1m")

    assert request.range == "1D"
    assert request.interval == "1m"


def test_chart_history_request_accepts_to_date_ranges():
    assert ChartHistoryRequest(tickers="aapl", range="WTD", interval="5m").range == "WTD"
    assert ChartHistoryRequest(tickers="aapl", range="MTD", interval="15m").range == "MTD"
    assert ChartHistoryRequest(tickers="aapl", range="QTD", interval="1h").range == "QTD"


def test_chart_history_request_rejects_unsupported_combo():
    with pytest.raises(ValidationError):
        ChartHistoryRequest(tickers="aapl", range="1Y", interval="5m")


def test_ticker_chart_history_accepts_ohlc_points():
    point = ChartOhlcPoint(
        timestamp=datetime(2026, 6, 11, 14, 30, tzinfo=timezone.utc),
        open=100.0,
        high=102.0,
        low=99.0,
        close=101.25,
    )
    chart = TickerChartHistory(ticker="AAPL", range="1D", interval="5m", points=[point])

    assert chart.points[0].high == 102.0
