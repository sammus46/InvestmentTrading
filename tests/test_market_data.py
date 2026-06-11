from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from app.services import market_data
from app.services.market_data import MarketDataService, MarketDataSettings

EASTERN = ZoneInfo("America/New_York")


def test_vwap_uses_typical_price_weighted_by_volume():
    session = pd.DataFrame(
        {
            "High": [12.0, 14.0],
            "Low": [10.0, 12.0],
            "Close": [11.0, 13.0],
            "Volume": [100, 300],
        }
    )

    assert MarketDataService._vwap(session, []) == 12.5


def test_bollinger_bands_use_latest_rolling_window():
    closes = list(range(1, 31))
    daily = pd.DataFrame({"Close": closes})
    service = MarketDataService()

    bands = service._bollinger_bands(daily, [])

    latest_window = pd.Series(closes[-20:])
    expected_middle = latest_window.mean()
    expected_std = latest_window.std()
    assert bands.middle == round(float(expected_middle), 2)
    assert bands.upper == round(float(expected_middle + 2 * expected_std), 2)
    assert bands.lower == round(float(expected_middle - 2 * expected_std), 2)


def test_with_eastern_index_treats_naive_intraday_data_as_utc():
    frame = pd.DataFrame({"Close": [100.0]}, index=pd.DatetimeIndex(["2024-01-02 14:30:00"]))

    localized = MarketDataService._with_eastern_index(frame)

    timestamp = localized.index[0]
    assert timestamp.tzinfo is not None
    assert timestamp.hour == 9
    assert timestamp.minute == 30
    assert str(localized.index.tz) == "America/New_York"


def test_previous_regular_session_excludes_today_partial_session():
    today = datetime.now(EASTERN).date()
    previous = today - timedelta(days=1)
    index = pd.DatetimeIndex(
        [
            datetime.combine(previous, time(9, 30), tzinfo=EASTERN),
            datetime.combine(previous, time(9, 35), tzinfo=EASTERN),
            datetime.combine(today, time(9, 30), tzinfo=EASTERN),
        ]
    )
    intraday = pd.DataFrame(
        {
            "High": [10.0, 11.0, 20.0],
            "Low": [9.0, 10.0, 19.0],
            "Close": [9.5, 10.5, 19.5],
            "Volume": [100, 200, 300],
        },
        index=index,
    )

    session = MarketDataService()._previous_regular_session(intraday, [])

    assert list(session.index.date) == [previous, previous]
    assert session["High"].tolist() == [10.0, 11.0]


def test_fifty_two_week_range_uses_completed_sessions_only():
    today = datetime.now(EASTERN).date()
    daily = pd.DataFrame(
        {
            "High": [10.0, 20.0, 999.0],
            "Low": [5.0, 7.0, 1.0],
        },
        index=pd.DatetimeIndex([today - timedelta(days=2), today - timedelta(days=1), today]),
    )

    levels = MarketDataService._fifty_two_week_range(daily, [])

    assert levels.high == 20.0
    assert levels.low == 5.0


def test_today_premarket_range_uses_four_to_market_open_window():
    today = datetime.now(EASTERN).date()
    index = pd.DatetimeIndex(
        [
            datetime.combine(today, time(3, 59), tzinfo=EASTERN),
            datetime.combine(today, time(4, 0), tzinfo=EASTERN),
            datetime.combine(today, time(9, 29), tzinfo=EASTERN),
            datetime.combine(today, time(9, 30), tzinfo=EASTERN),
        ]
    )
    intraday = pd.DataFrame(
        {
            "High": [99.0, 10.0, 12.0, 100.0],
            "Low": [1.0, 8.0, 9.0, 2.0],
        },
        index=index,
    )

    premarket = MarketDataService()._today_premarket_range(intraday, [])

    assert premarket.high == 12.0
    assert premarket.low == 8.0
    assert premarket.bars == 2


def test_opening_range_uses_first_five_regular_session_minutes():
    today = datetime.now(EASTERN).date()
    index = pd.DatetimeIndex(
        [
            datetime.combine(today, time(9, 30), tzinfo=EASTERN),
            datetime.combine(today, time(9, 31), tzinfo=EASTERN),
            datetime.combine(today, time(9, 34), tzinfo=EASTERN),
            datetime.combine(today, time(9, 35), tzinfo=EASTERN),
        ]
    )
    intraday = pd.DataFrame(
        {
            "High": [10.0, 14.0, 12.0, 99.0],
            "Low": [8.0, 9.0, 7.0, 1.0],
        },
        index=index,
    )

    opening = MarketDataService()._opening_range(intraday, [])

    assert opening.high == 14.0
    assert opening.low == 7.0
    assert opening.bars == 3
    assert opening.minutes == 5


def test_swing_levels_find_and_merge_daily_support_resistance():
    service = MarketDataService(MarketDataSettings(swing_window=1, level_merge_percent=0.003, max_swing_levels=5))
    daily = pd.DataFrame(
        {
            "High": [10.0, 15.0, 11.0, 12.0, 20.0, 13.0],
            "Low": [9.0, 8.0, 10.0, 7.0, 11.0, 12.0],
        },
        index=pd.date_range("2026-05-08", periods=6, freq="D"),
    )

    levels = service._swing_levels(daily, [])

    assert levels.highs == [15.0, 20.0]
    assert levels.lows == [8.0, 7.0]


def test_swing_levels_prefer_levels_nearest_latest_close():
    service = MarketDataService(MarketDataSettings(swing_window=1, level_merge_percent=0.003, max_swing_levels=2))
    daily = pd.DataFrame(
        {
            "High": [51.0, 60.0, 53.0, 90.0, 82.0, 110.0, 104.0, 121.0, 118.0],
            "Low": [49.0, 45.0, 50.0, 78.0, 76.0, 100.0, 98.0, 112.0, 116.0],
            "Close": [50.0, 55.0, 52.0, 86.0, 80.0, 106.0, 100.0, 119.0, 118.0],
        },
        index=pd.date_range("2026-05-01", periods=9, freq="D"),
    )

    levels = service._swing_levels(daily, [])

    assert levels.highs == [110.0, 121.0]
    assert levels.lows == [98.0, 76.0]


def test_earnings_gap_uses_earnings_open_and_prior_close(monkeypatch):
    class FakeTicker:
        @property
        def earnings_dates(self):
            return pd.DataFrame(
                {"EPS Estimate": [1.0]},
                index=pd.DatetimeIndex([datetime(2026, 5, 15, 12, 0, tzinfo=EASTERN)]),
            )

    monkeypatch.setattr("app.services.market_data.yf.Ticker", lambda symbol: FakeTicker())
    daily = pd.DataFrame(
        {
            "Open": [90.0, 110.0],
            "Close": [100.0, 120.0],
        },
        index=pd.DatetimeIndex(["2026-05-14", "2026-05-15"]),
    )

    gap = MarketDataService._earnings_gap("AAPL", daily, [])

    assert gap.date == datetime(2026, 5, 15).date()
    assert gap.gap == 10.0
    assert gap.gap_percent == 10.0


def test_latest_session_bars_use_newest_available_date():
    index = pd.DatetimeIndex(
        [
            datetime(2026, 5, 15, 4, 0, tzinfo=EASTERN),
            datetime(2026, 5, 15, 9, 30, tzinfo=EASTERN),
            datetime(2026, 5, 14, 4, 0, tzinfo=EASTERN),
        ]
    )
    intraday = pd.DataFrame({"High": [10.0, 11.0, 9.0], "Low": [8.0, 9.0, 7.0]}, index=index)

    latest = MarketDataService._latest_session_bars(intraday)

    assert list(latest.index.date) == [datetime(2026, 5, 15).date(), datetime(2026, 5, 15).date()]


def test_monthly_range_uses_last_22_completed_sessions():
    today = datetime.now(EASTERN).date()
    dates = pd.date_range(today - timedelta(days=30), periods=30, freq="D")
    daily = pd.DataFrame(
        {
            "High": list(range(10, 40)),
            "Low": list(range(1, 31)),
        },
        index=dates,
    )

    high, low = MarketDataService._monthly_range(daily, [])

    completed = daily[pd.DatetimeIndex(daily.index).date < today].tail(22)
    assert high == float(completed["High"].max())
    assert low == float(completed["Low"].min())


def test_sma_daily_ema_pivots_and_fibonacci_levels():
    daily = pd.DataFrame({"Close": [float(value) for value in range(1, 31)]})
    warnings: list[str] = []

    assert MarketDataService._sma(daily, 10, warnings) == 25.5
    assert MarketDataService._daily_ema(daily, 10, warnings) == round(float(daily["Close"].ewm(span=10, adjust=False).mean().iloc[-1]), 2)

    pivots = MarketDataService._pivot_points(previous_day=type("Previous", (), {"high": 12.0, "low": 8.0, "close": 10.0})())
    assert pivots == {"pivot": 10.0, "r1": 12.0, "s1": 8.0, "r2": 14.0, "s2": 6.0}

    fibs = MarketDataService._fibonacci_levels(20.0, 10.0)
    assert fibs == {"fib_382": 13.82, "fib_500": 15.0, "fib_618": 16.18}


def test_current_price_uses_latest_minute_close_before_fallback():
    minute = pd.DataFrame({"Close": [100.0, None, 105.5]})

    price = MarketDataService()._current_price("AAPL", minute, [])

    assert price == 105.5


def test_build_metrics_skips_unselected_downloads(monkeypatch):
    downloads = []

    def fake_download(symbol, period, interval, prepost, start=None, end=None):
        downloads.append((period, interval, prepost, start, end))
        if interval == "5m":
            today = datetime.now(EASTERN).date()
            return pd.DataFrame(
                {"Open": [10.0], "High": [12.0], "Low": [9.0], "Close": [11.5], "Volume": [100]},
                index=pd.DatetimeIndex([datetime.combine(today, time(9, 30), tzinfo=EASTERN)]),
            )
        return pd.DataFrame({"Open": [10.0], "High": [12.0], "Low": [9.0], "Close": [11.0]}, index=pd.DatetimeIndex(["2026-05-15"]))

    monkeypatch.setattr(MarketDataService, "_download", staticmethod(fake_download))

    [metric] = MarketDataService().build_metrics(["AAPL"], ["previous_day"])

    assert metric.selected_metrics == ["previous_day"]
    assert metric.previous_day.close == 11.0
    assert [(period, interval, prepost) for period, interval, prepost, _, _ in downloads] == [
        (None, "1d", False),
        ("5d", "5m", True),
    ]
    assert downloads[0][3] is not None
    assert downloads[0][4] is not None
    assert (downloads[0][4] - downloads[0][3]).days == 365
    assert [point.close for point in metric.price_history] == [11.0]
    assert [point.close for point in metric.intraday_history] == [11.5]


def test_price_history_uses_latest_completed_daily_closes():
    today = datetime.now(EASTERN).date()
    first = today - timedelta(days=2)
    second = today - timedelta(days=1)
    service = MarketDataService(MarketDataSettings(chart_history_days=2))
    daily = pd.DataFrame(
        {"Close": [10.12345, 11.0, 999.0]},
        index=pd.DatetimeIndex([first, second, today]),
    )

    history = service._price_history(daily, [])

    assert [point.date for point in history] == [first, second]
    assert [point.close for point in history] == [10.12, 11.0]


def test_intraday_price_history_uses_latest_regular_session():
    today = datetime.now(EASTERN).date()
    yesterday = today - timedelta(days=1)
    index = pd.DatetimeIndex(
        [
            datetime.combine(yesterday, time(9, 30), tzinfo=EASTERN),
            datetime.combine(today, time(9, 30), tzinfo=EASTERN),
            datetime.combine(today, time(9, 35), tzinfo=EASTERN),
            datetime.combine(today, time(16, 5), tzinfo=EASTERN),
        ]
    )
    intraday = pd.DataFrame({"Close": [98.0, 100.0, 101.5, 102.0]}, index=index)

    history = MarketDataService()._intraday_price_history(intraday, [])

    assert [point.close for point in history] == [100.0, 101.5]


def test_market_snapshot_preserves_configured_order_and_calculates_change(monkeypatch):
    monkeypatch.setattr(market_data, "MARKET_SNAPSHOT_INSTRUMENTS", (("SPY", "S&P 500"), ("QQQ", "Nasdaq")))
    today = datetime.now(EASTERN).date()
    yesterday = today - timedelta(days=1)

    def fake_download(symbol, period, interval, prepost, start=None, end=None):
        if interval == "1d":
            return pd.DataFrame(
                {"Close": [100.0, 110.0]},
                index=pd.DatetimeIndex([yesterday, today]),
            )
        return pd.DataFrame(
            {"Close": [110.0, 112.0]},
            index=pd.DatetimeIndex(
                [
                    datetime.combine(today, time(9, 30), tzinfo=EASTERN),
                    datetime.combine(today, time(9, 35), tzinfo=EASTERN),
                ]
            ),
        )

    monkeypatch.setattr(MarketDataService, "_download", staticmethod(fake_download))

    snapshot = MarketDataService().build_market_snapshot(["aapl"])

    assert [row.label for row in snapshot.market] == ["S&P 500", "Nasdaq"]
    assert [row.symbol for row in snapshot.watchlist] == ["AAPL"]
    assert snapshot.watchlist[0].price == 112.0
    assert snapshot.watchlist[0].previous_close == 100.0
    assert snapshot.watchlist[0].change == 12.0
    assert snapshot.watchlist[0].change_percent == 12.0
