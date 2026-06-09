from datetime import timezone

from app.services.news import NewsService, NewsSettings


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


def test_normalize_finnhub_article_shape():
    [article] = NewsService._normalize_finnhub_articles(
        [
            {
                "headline": "Market breadth improves",
                "url": "https://example.com/breadth",
                "source": "Finnhub",
                "datetime": 1781012952,
                "summary": "Advancers led decliners across US exchanges.",
                "image": "https://example.com/breadth.jpg",
                "related": "SPY, QQQ AAPL",
            }
        ],
        limit=1,
    )

    assert article.title == "Market breadth improves"
    assert article.url == "https://example.com/breadth"
    assert article.publisher == "Finnhub"
    assert article.summary == "Advancers led decliners across US exchanges."
    assert article.thumbnail_url == "https://example.com/breadth.jpg"
    assert article.related_tickers == ["SPY", "QQQ", "AAPL"]


def test_build_news_prefers_finnhub_when_configured(monkeypatch):
    def fake_fetch(self, endpoint, params):
        if endpoint == "news":
            return [{"headline": "Market headline", "url": "https://example.com/market"}]
        assert endpoint == "company-news"
        return [{"headline": f"{params['symbol']} headline", "url": f"https://example.com/{params['symbol']}"}]

    monkeypatch.setattr(NewsService, "_fetch_finnhub", fake_fetch)

    response = NewsService(NewsSettings(finnhub_api_key="test")).build_news(["AAPL"], per_ticker=2, general_count=3)

    assert [item.title for item in response.general_market] == ["Market headline"]
    assert response.ticker_news[0].articles[0].title == "AAPL headline"
    assert response.warnings == []
    assert response.ticker_news[0].warnings == []


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

    response = NewsService(NewsSettings()).build_news(["AAPL", "MSFT"], per_ticker=2, general_count=3)

    assert [item.title for item in response.general_market] == ["Market headline"]
    assert response.ticker_news[0].articles[0].title == "AAPL headline"
    assert response.ticker_news[1].ticker == "MSFT"
    assert response.ticker_news[1].warnings == ["News was unavailable for MSFT: rate limited"]


def test_build_news_falls_back_to_yahoo_when_finnhub_is_empty(monkeypatch):
    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def get_news(self, count=10):
            return [{"title": f"Yahoo {self.symbol}", "link": f"https://example.com/yahoo/{self.symbol}"}]

    class FakeSearch:
        news = [{"title": "Yahoo market", "link": "https://example.com/yahoo/market"}]

        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(NewsService, "_fetch_finnhub", lambda self, endpoint, params: [])
    monkeypatch.setattr("app.services.news.yf.Ticker", FakeTicker)
    monkeypatch.setattr("app.services.news.yf.Search", FakeSearch)

    response = NewsService(NewsSettings(finnhub_api_key="test")).build_news(["AAPL"], per_ticker=2, general_count=3)

    assert [item.title for item in response.general_market] == ["Yahoo market"]
    assert response.ticker_news[0].articles[0].title == "Yahoo AAPL"
