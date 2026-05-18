import pandas as pd

from app.services.market_data import MarketDataService


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
