from app.models import GenerateRequest


def test_generate_request_accepts_delimited_tickers():
    request = GenerateRequest(tickers="aapl, msft\nNVDA aapl")

    assert request.tickers == ["AAPL", "MSFT", "NVDA"]


def test_generate_request_accepts_and_deduplicates_metric_selection():
    request = GenerateRequest(tickers="aapl", metrics="previous_day previous_day swing_levels")

    assert request.metrics == ["previous_day", "swing_levels"]
