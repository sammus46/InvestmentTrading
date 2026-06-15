import sys
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from app.models import EarningsGap, Ohlc
from app.services import market_data
from app.services.market_data import MarketDataService, MarketDataSettings
from app.services.providers import YFinanceProvider

EASTERN = ZoneInfo("America/New_York")


class FakeProvider:
    def __init__(self, *, ticker=None, download_frame: pd.DataFrame | None = None) -> None:
        self.ticker_obj = ticker
        self.download_frame = download_frame if download_frame is not None else pd.DataFrame()
        self.downloads: list[dict[str, object]] = []

    def download(self, symbol, *, period, interval, prepost, start=None, end=None):
        self.downloads.append(
            {
                "symbol": symbol,
                "period": period,
                "interval": interval,
                "prepost": prepost,
                "start": start,
                "end": end,
            }
        )
        return self.download_frame

    def fast_price(self, symbol):
        return None

    def finnhub_quote(self, symbol, api_key):
        return None

    def ticker(self, symbol):
        return self.ticker_obj

    def sector(self, symbol):
        return None


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


def test_today_session_calculations_ignore_prior_available_day():
    today = datetime.now(EASTERN).date()
    yesterday = today - timedelta(days=1)
    index = pd.DatetimeIndex(
        [
            datetime.combine(yesterday, time(4, 0), tzinfo=EASTERN),
            datetime.combine(yesterday, time(9, 30), tzinfo=EASTERN),
        ]
    )
    intraday = pd.DataFrame(
        {
            "Open": [9.0, 10.0],
            "High": [12.0, 15.0],
            "Low": [8.0, 9.0],
            "Close": [11.0, 14.0],
            "Volume": [100, 200],
        },
        index=index,
    )
    warnings: list[str] = []

    service = MarketDataService()

    assert service._today_regular_session(intraday).empty
    assert service._today_premarket_range(intraday, warnings).bars == 0
    assert service._opening_range(intraday, warnings).bars == 0


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

    assert levels.highs == [20.0, 15.0]
    assert levels.lows == [7.0, 8.0]


def test_swing_levels_keep_first_sorted_merged_levels():
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

    assert levels.highs == [121.0, 110.0]
    assert levels.lows == [45.0, 76.0]


def test_earnings_gap_uses_earnings_open_and_prior_close():
    today = datetime.now(EASTERN).date()
    earnings_day = today - timedelta(days=5)
    prior_day = earnings_day - timedelta(days=1)

    class FakeTicker:
        @property
        def earnings_dates(self):
            return pd.DataFrame(
                {"EPS Estimate": [1.0]},
                index=pd.DatetimeIndex([datetime.combine(earnings_day, time(12, 0), tzinfo=EASTERN)]),
            )

    daily = pd.DataFrame(
        {
            "Open": [90.0, 110.0],
            "Close": [100.0, 120.0],
        },
        index=pd.DatetimeIndex([prior_day, earnings_day]),
    )

    gap = MarketDataService(provider=FakeProvider(ticker=FakeTicker()))._earnings_gap("AAPL", daily, [])

    assert gap.date == earnings_day
    assert gap.gap == 10.0
    assert gap.gap_percent == 10.0
    assert gap.open == 110.0
    assert gap.previous_close == 100.0
    assert gap.is_stale is False


def test_earnings_gap_suppresses_levels_older_than_30_days():
    today = datetime.now(EASTERN).date()
    earnings_day = today - timedelta(days=45)

    class FakeTicker:
        @property
        def earnings_dates(self):
            return pd.DataFrame(
                {"EPS Estimate": [1.0]},
                index=pd.DatetimeIndex([datetime.combine(earnings_day, time(12, 0), tzinfo=EASTERN)]),
            )

    daily = pd.DataFrame(
        {
            "Open": [90.0, 110.0],
            "Close": [100.0, 120.0],
        },
        index=pd.DatetimeIndex([earnings_day - timedelta(days=1), earnings_day]),
    )

    gap = MarketDataService(provider=FakeProvider(ticker=FakeTicker()))._earnings_gap("AAPL", daily, [])

    assert gap.date == earnings_day
    assert gap.gap is None
    assert gap.open is None
    assert gap.previous_close is None
    assert gap.is_stale is True


def test_earnings_gap_suppresses_provider_stderr(capsys):
    class FakeTicker:
        @property
        def earnings_dates(self):
            print("SPY: No earnings dates found, symbol may be delisted", file=sys.stderr)
            return pd.DataFrame()

    daily = pd.DataFrame(
        {
            "Open": [100.0],
            "Close": [101.0],
        },
        index=pd.DatetimeIndex(["2026-05-15"]),
    )
    warnings: list[str] = []

    gap = MarketDataService(provider=FakeProvider(ticker=FakeTicker()))._earnings_gap("SPY", daily, warnings)

    assert gap.date is None
    assert "No earnings dates" in warnings[0]
    assert "No earnings dates found" not in capsys.readouterr().err


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


def test_download_uses_adjusted_yfinance_history(monkeypatch):
    captured = {}

    def fake_download(symbol, **query):
        captured["symbol"] = symbol
        captured["query"] = query
        return pd.DataFrame({"Close": [100.0]}, index=pd.DatetimeIndex(["2026-06-01"]))

    monkeypatch.setattr("app.services.providers.yf.download", fake_download)

    frame = YFinanceProvider().download("AAPL", period="1d", interval="1d", prepost=False)

    assert not frame.empty
    assert captured["symbol"] == "AAPL"
    assert captured["query"]["auto_adjust"] is True


def test_technical_levels_bundle_adam_display_values():
    today = datetime.now(EASTERN).date()
    dates = pd.date_range(today - timedelta(days=220), periods=220, freq="D")
    daily = pd.DataFrame(
        {
            "Open": [float(value) for value in range(1, 221)],
            "High": [float(value + 1) for value in range(1, 221)],
            "Low": [float(value - 1) for value in range(1, 221)],
            "Close": [float(value) for value in range(1, 221)],
        },
        index=dates,
    )
    minute = pd.DataFrame(
        {
            "High": [101.0, 102.0],
            "Low": [99.0, 100.0],
            "Close": [100.0, 101.0],
            "Volume": [100, 300],
        },
        index=pd.DatetimeIndex(
            [
                datetime.combine(today, time(9, 30), tzinfo=EASTERN),
                datetime.combine(today, time(9, 31), tzinfo=EASTERN),
            ]
        ),
    )
    five_minute = pd.DataFrame(
        {"Close": [float(value) for value in range(1, 21)]},
        index=pd.DatetimeIndex(
            [datetime.combine(today, time(9, 30), tzinfo=EASTERN) + timedelta(minutes=5 * index) for index in range(20)]
        ),
    )
    previous = Ohlc(high=221.0, low=219.0, close=220.0)
    earnings = EarningsGap(open=110.0, previous_close=100.0)

    levels = MarketDataService()._technical_levels(
        symbol="AAPL",
        daily=daily,
        minute=minute,
        five_minute=five_minute,
        previous_day=previous,
        earnings_gap=earnings,
        warnings=[],
    )

    assert levels.current_price == 101.0
    assert levels.today_vwap == 100.75
    assert levels.pivot == 220.0
    assert levels.r1 == 221.0
    assert levels.s1 == 219.0
    assert levels.ema_20_5m is not None
    assert levels.earnings_open == 110.0
    assert levels.pre_earnings_close == 100.0


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
    assert (downloads[0][4] - downloads[0][3]).days == 400
    assert [point.close for point in metric.price_history] == [11.0]
    assert [point.close for point in metric.intraday_history] == [11.5]


def test_build_metrics_uses_provider_download_interface():
    frame = pd.DataFrame(
        {"Open": [10.0], "High": [12.0], "Low": [9.0], "Close": [11.0], "Volume": [100]},
        index=pd.DatetimeIndex(["2026-05-15"]),
    )
    provider = FakeProvider(download_frame=frame)

    [metric] = MarketDataService(provider=provider).build_metrics(["aapl"], ["previous_day"])

    assert metric.ticker == "AAPL"
    assert metric.previous_day.close == 11.0
    assert [(call["period"], call["interval"], call["prepost"]) for call in provider.downloads] == [
        (None, "1d", False),
        ("5d", "5m", True),
    ]


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


def test_chart_ohlc_points_filter_regular_session_and_round_values():
    today = datetime.now(EASTERN).date()
    frame = pd.DataFrame(
        {
            "Open": [9.111, 10.125, 11.0],
            "High": [9.5, 10.678, 11.5],
            "Low": [8.5, 9.876, 10.5],
            "Close": [9.25, 10.444, 11.25],
        },
        index=pd.DatetimeIndex(
            [
                datetime.combine(today, time(8, 0), tzinfo=EASTERN),
                datetime.combine(today, time(9, 30), tzinfo=EASTERN),
                datetime.combine(today, time(16, 5), tzinfo=EASTERN),
            ]
        ),
    )

    points = MarketDataService()._chart_ohlc_points(frame, "5m", [])

    assert len(points) == 1
    assert points[0].open == 10.12
    assert points[0].high == 10.68
    assert points[0].low == 9.88
    assert points[0].close == 10.44


def test_chart_ohlc_points_keep_weekly_and_monthly_date_bars():
    frame = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [110.0],
            "Low": [95.0],
            "Close": [105.0],
        },
        index=pd.DatetimeIndex(["2026-06-01"]),
    )

    weekly = MarketDataService()._chart_ohlc_points(frame, "1wk", [])
    monthly = MarketDataService()._chart_ohlc_points(frame, "1mo", [])

    assert weekly[0].close == 105.0
    assert monthly[0].close == 105.0


def test_build_chart_history_preserves_ticker_order_and_download_mapping(monkeypatch):
    downloads = []
    today = datetime.now(EASTERN).date()

    def fake_download(symbol, period, interval, prepost, start=None, end=None):
        downloads.append((symbol, period, interval, prepost))
        return pd.DataFrame(
            {
                "Open": [100.0],
                "High": [102.0],
                "Low": [99.0],
                "Close": [101.0],
            },
            index=pd.DatetimeIndex([datetime.combine(today, time(9, 30), tzinfo=EASTERN)]),
        )

    monkeypatch.setattr(MarketDataService, "_download", staticmethod(fake_download))

    response = MarketDataService().build_chart_history(["msft", "aapl"], "5D", "15m")

    assert [chart.ticker for chart in response.charts] == ["MSFT", "AAPL"]
    assert [(symbol, period, interval, prepost) for symbol, period, interval, prepost in downloads] == [
        ("MSFT", "5d", "15m", False),
        ("AAPL", "5d", "15m", False),
    ]
    assert response.charts[0].points[0].close == 101.0


def test_build_chart_history_supports_expanded_range_interval_mapping(monkeypatch):
    downloads = []

    def fake_download(symbol, period, interval, prepost, start=None, end=None):
        downloads.append((symbol, period, interval, prepost))
        return pd.DataFrame(
            {
                "Open": [100.0],
                "High": [102.0],
                "Low": [99.0],
                "Close": [101.0],
            },
            index=pd.DatetimeIndex(["2026-06-01"]),
        )

    monkeypatch.setattr(MarketDataService, "_download", staticmethod(fake_download))

    response = MarketDataService().build_chart_history(["aapl"], "5Y", "1mo")

    assert downloads == [("AAPL", "5y", "1mo", False)]
    assert response.charts[0].points[0].close == 101.0


def test_chart_date_window_uses_to_date_calendar_starts():
    now = datetime(2026, 6, 11, 12, 0, tzinfo=EASTERN)

    wtd_start, _ = MarketDataService._chart_date_window("WTD", now)
    mtd_start, _ = MarketDataService._chart_date_window("MTD", now)
    qtd_start, _ = MarketDataService._chart_date_window("QTD", now)

    assert wtd_start.astimezone(EASTERN).date().isoformat() == "2026-06-08"
    assert mtd_start.astimezone(EASTERN).date().isoformat() == "2026-06-01"
    assert qtd_start.astimezone(EASTERN).date().isoformat() == "2026-04-01"


def test_build_chart_history_uses_date_window_for_to_date_ranges(monkeypatch):
    downloads = []
    start = datetime(2026, 4, 1, tzinfo=timezone.utc)
    end = datetime(2026, 6, 12, tzinfo=timezone.utc)

    def fake_download(symbol, period, interval, prepost, start=None, end=None):
        downloads.append((symbol, period, interval, prepost, start, end))
        return pd.DataFrame(
            {
                "Open": [100.0],
                "High": [102.0],
                "Low": [99.0],
                "Close": [101.0],
            },
            index=pd.DatetimeIndex([datetime(2026, 6, 11, 9, 30, tzinfo=EASTERN)]),
        )

    monkeypatch.setattr(MarketDataService, "_download", staticmethod(fake_download))
    monkeypatch.setattr(MarketDataService, "_chart_date_window", staticmethod(lambda chart_range: (start, end)))

    response = MarketDataService().build_chart_history(["aapl"], "QTD", "1h")

    assert downloads == [("AAPL", None, "1h", False, start, end)]
    assert response.charts[0].points[0].close == 101.0


def test_build_chart_history_surfaces_provider_failures(monkeypatch):
    def fake_download(symbol, period, interval, prepost, start=None, end=None):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(MarketDataService, "_download", staticmethod(fake_download))

    response = MarketDataService().build_chart_history(["AAPL"], "1D", "5m")

    assert response.charts[0].points == []
    assert "rate limited" in response.charts[0].warnings[0]
    assert response.warnings == response.charts[0].warnings
