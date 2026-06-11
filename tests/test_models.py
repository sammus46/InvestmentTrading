from app.models import GenerateRequest, NewsRequest


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
