from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd

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
    assert bands.middle == round(float(expected_middle), 4)
    assert bands.upper == round(float(expected_middle + 2 * expected_std), 4)
    assert bands.lower == round(float(expected_middle - 2 * expected_std), 4)


def test_with_eastern_index_treats_naive_intraday_data_as_utc():
    frame = pd.DataFrame({"Close": [100.0]}, index=pd.DatetimeIndex(["2024-01-02 14:30:00"]))

    localized = MarketDataService._with_eastern_index(frame)

    timestamp = localized.index[0]
    assert timestamp.tzinfo is not None
    assert timestamp.hour == 9
    assert timestamp.minute == 30
    assert str(localized.index.tz) == "America/New_York"


def test_previous_regular_session_excludes_today_partial_session():
    index = pd.DatetimeIndex(
        [
            datetime(2026, 5, 15, 9, 30, tzinfo=EASTERN),
            datetime(2026, 5, 15, 9, 35, tzinfo=EASTERN),
            datetime(2026, 5, 18, 9, 30, tzinfo=EASTERN),
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

    assert list(session.index.date) == [datetime(2026, 5, 15).date(), datetime(2026, 5, 15).date()]
    assert session["High"].tolist() == [10.0, 11.0]


def test_fifty_two_week_range_uses_completed_sessions_only():
    daily = pd.DataFrame(
        {
            "High": [10.0, 20.0, 999.0],
            "Low": [5.0, 7.0, 1.0],
        },
        index=pd.DatetimeIndex(["2026-05-14", "2026-05-15", "2026-05-18"]),
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

    assert levels.highs == [20.0, 15.0]
    assert levels.lows == [7.0, 8.0]


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
