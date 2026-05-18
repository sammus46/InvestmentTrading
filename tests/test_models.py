from app.models import GenerateRequest


def test_generate_request_accepts_delimited_tickers():
    request = GenerateRequest(tickers="aapl, msft\nNVDA aapl")

    assert request.tickers == ["AAPL", "MSFT", "NVDA"]
