from datetime import timezone

from app.services.news import NewsService


def test_normalize_article_accepts_ticker_news_shape():
    article = NewsService._normalize_article(
        {
            "content": {
                "title": "Apple shares move after event",
                "summary": "Investors weigh the company's latest product announcements.",
                "pubDate": "2026-06-09T14:30:00Z",
                "provider": {"displayName": "Yahoo Finance"},
                "canonicalUrl": {"url": "https://finance.yahoo.com/apple-event"},
                "thumbnail": {"originalUrl": "https://example.com/apple.jpg"},
            }
        }
    )

    assert article is not None
    assert article.title == "Apple shares move after event"
    assert article.url == "https://finance.yahoo.com/apple-event"
    assert article.publisher == "Yahoo Finance"
    assert article.published_at is not None
    assert article.published_at.tzinfo == timezone.utc
    assert article.thumbnail_url == "https://example.com/apple.jpg"


def test_normalize_article_accepts_search_news_shape():
    article = NewsService._normalize_article(
        {
            "title": "Stock market today",
            "publisher": "Investor's Business Daily",
            "link": "https://finance.yahoo.com/market-today",
            "providerPublishTime": 1781012952,
            "relatedTickers": ["^GSPC", "AAPL", "AAPL"],
            "thumbnail": {
                "resolutions": [
                    {"url": "https://example.com/market.jpg", "width": 140, "height": 140}
                ]
            },
        }
    )

    assert article is not None
    assert article.title == "Stock market today"
    assert article.publisher == "Investor's Business Daily"
    assert article.url == "https://finance.yahoo.com/market-today"
    assert article.related_tickers == ["^GSPC", "AAPL"]
    assert article.thumbnail_url == "https://example.com/market.jpg"


def test_build_news_returns_warnings_without_failing(monkeypatch):
    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def get_news(self, count=10):
            if self.symbol == "MSFT":
                raise RuntimeError("rate limited")
            return [{"title": f"{self.symbol} headline", "link": f"https://example.com/{self.symbol}"}]

    class FakeSearch:
        news = [{"title": "Market headline", "link": "https://example.com/market"}]

        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr("app.services.news.yf.Ticker", FakeTicker)
    monkeypatch.setattr("app.services.news.yf.Search", FakeSearch)

    response = NewsService().build_news(["AAPL", "MSFT"], per_ticker=2, general_count=3)

    assert [item.title for item in response.general_market] == ["Market headline"]
    assert response.ticker_news[0].articles[0].title == "AAPL headline"
    assert response.ticker_news[1].ticker == "MSFT"
    assert response.ticker_news[1].warnings == ["News was unavailable for MSFT: rate limited"]
