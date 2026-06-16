import time
from datetime import datetime, timedelta, timezone

from app.models import NewsArticle, TickerNews
from app.services.news import NewsService, NewsSettings


def quiet_settings(**overrides):
    values = {"background_enrichment_enabled": False}
    values.update(overrides)
    return NewsSettings(**values)


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
    assert article.category == "general"


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
    assert article.category == "general"


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
    assert article.category == "general"


def test_normalize_article_drops_unsafe_urls():
    article = NewsService._normalize_article(
        {
            "title": "Unsafe link",
            "link": "javascript:alert(1)",
            "thumbnail": {"originalUrl": "data:text/html,<b>x</b>"},
        }
    )

    assert article is not None
    assert article.url is None
    assert article.thumbnail_url is None


def test_normalize_finnhub_article_drops_unsafe_urls():
    [article] = NewsService._normalize_finnhub_articles(
        [
            {
                "headline": "Unsafe Finnhub link",
                "url": "data:text/html,<b>x</b>",
                "image": "javascript:alert(1)",
            }
        ],
        limit=1,
    )

    assert article.url is None
    assert article.thumbnail_url is None


def test_classify_article_groups_rating_changes():
    assert NewsService._classify_article("Apple upgraded as analyst raises price target") == "rating_changes"
    assert NewsService._classify_article("Tesla downgraded after margin concerns") == "rating_changes"


def test_classify_article_groups_contract_announcements():
    assert NewsService._classify_article("Nvidia wins new cloud contract") == "contracts"
    assert NewsService._classify_article("Microsoft announces AI partnership", "The companies signed a new deal.") == "contracts"


def test_classify_article_groups_earnings_reports():
    assert NewsService._classify_article("Meta earnings beat expectations") == "earnings"
    assert NewsService._classify_article("AMD lifts guidance as revenue improves") == "earnings"


def test_classify_article_defaults_to_general():
    assert NewsService._classify_article("Markets rise as investors await Fed decision") == "general"


def test_build_news_prefers_finnhub_when_configured(monkeypatch):
    def fake_fetch(self, endpoint, params):
        if endpoint == "news":
            return [{"headline": "Market headline", "url": "https://example.com/market"}]
        assert endpoint == "company-news"
        return [{"headline": f"{params['symbol']} headline", "url": f"https://example.com/{params['symbol']}"}]

    monkeypatch.setattr(NewsService, "_fetch_finnhub", fake_fetch)

    response = NewsService(quiet_settings(finnhub_api_key="test")).build_news(["AAPL"], per_ticker=2, general_count=3)

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

    response = NewsService(quiet_settings()).build_news(["AAPL", "MSFT"], per_ticker=2, general_count=3)

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

    response = NewsService(quiet_settings(finnhub_api_key="test")).build_news(["AAPL"], per_ticker=2, general_count=3)

    assert [item.title for item in response.general_market] == ["Yahoo market"]
    assert response.ticker_news[0].articles[0].title == "Yahoo AAPL"


def test_build_news_reuses_cached_provider_results(monkeypatch):
    calls = {"general": 0, "ticker": 0}

    def fake_general(self, count, warnings):
        calls["general"] += 1
        return [NewsArticle(title=f"Market {calls['general']}")]

    def fake_ticker(self, ticker, count):
        calls["ticker"] += 1
        return TickerNews(ticker=ticker, articles=[NewsArticle(title=f"{ticker} {calls['ticker']}")])

    monkeypatch.setattr(NewsService, "_general_market_news", fake_general)
    monkeypatch.setattr(NewsService, "_ticker_news", fake_ticker)

    service = NewsService(quiet_settings())
    first = service.build_news(["AAPL"], per_ticker=2, general_count=3)
    second = service.build_news(["AAPL"], per_ticker=2, general_count=3)

    assert calls == {"general": 1, "ticker": 1}
    assert first.general_market[0].title == second.general_market[0].title
    assert first.ticker_news[0].articles[0].title == second.ticker_news[0].articles[0].title


def test_rank_ticker_articles_filters_generic_headlines_and_prefers_direct_matches():
    service = NewsService(quiet_settings())
    now = datetime.now(timezone.utc)
    articles = [
        NewsArticle(title="Stock market today: Dow and Nasdaq wait for Fed decision", published_at=now),
        NewsArticle(title="Apple shares jump after new AI product event", published_at=now - timedelta(hours=2)),
        NewsArticle(title="Analyst upgrades $AAPL and raises price target", published_at=now - timedelta(hours=4)),
        NewsArticle(title="Microsoft signs new cloud deal", related_tickers=["MSFT"], published_at=now),
    ]

    ranked = service._rank_ticker_articles("AAPL", articles, count=3, provider_specific=True)

    assert [article.title for article in ranked] == [
        "Analyst upgrades $AAPL and raises price target",
        "Apple shares jump after new AI product event",
    ]
    assert ranked[0].relevance_score is not None
    assert ranked[0].impact_score is not None


def test_cached_ticker_news_merges_completed_enrichment_without_reordering():
    service = NewsService(quiet_settings())
    original = TickerNews(
        ticker="AAPL",
        articles=[
            NewsArticle(title="Apple shares move after event", url="https://example.com/apple"),
            NewsArticle(title="AAPL upgraded by analyst", url="https://example.com/aapl-upgrade"),
        ],
    )
    enriched_second = original.articles[1].model_copy(
        update={"category": "rating_changes", "analysis_status": "analyzed", "impact_score": 42.0}
    )
    service._ticker_cache[("AAPL", 2, False)] = (time.monotonic() + 60, original)
    service._analysis_cache[service._analysis_key("AAPL", original.articles[1])] = (time.monotonic() + 60, enriched_second)

    merged = service._cached_ticker_news("AAPL", 2)

    assert [article.title for article in merged.articles] == [
        "Apple shares move after event",
        "AAPL upgraded by analyst",
    ]
    assert merged.articles[1].category == "rating_changes"
    assert merged.articles[1].analysis_status == "analyzed"


def test_enqueue_enrichment_dedupes_pending_articles():
    class FakeExecutor:
        def __init__(self):
            self.calls = []

        def submit(self, *args):
            self.calls.append(args)

    service = NewsService(NewsSettings(background_enrichment_enabled=True))
    fake_executor = FakeExecutor()
    service._executor = fake_executor
    group = TickerNews(ticker="AAPL", articles=[NewsArticle(title="AAPL headline", url="https://example.com/aapl")])

    service._enqueue_enrichment(group, {"remaining": 0})
    service._enqueue_enrichment(group, {"remaining": 0})

    assert len(fake_executor.calls) == 1


def test_body_enrichment_recategorizes_and_scores_importance(monkeypatch):
    service = NewsService(quiet_settings())
    monkeypatch.setattr(
        service,
        "_fetch_article_body",
        lambda url: "Nvidia reported earnings that beat estimates and lifted full-year guidance for AI chip revenue.",
    )
    article = NewsArticle(title="Nvidia shares rise after update", url="https://example.com/nvidia")

    enriched = service._enrich_article("NVDA", article)

    assert enriched.analysis_status == "analyzed"
    assert enriched.category == "earnings"
    assert enriched.impact_score is not None and enriched.impact_score > 20
    assert enriched.relevance_score is not None and enriched.relevance_score >= service.MIN_RELEVANCE_SCORE


def test_llm_analysis_respects_refresh_and_ticker_caps(monkeypatch):
    class SyncExecutor:
        def submit(self, fn, *args):
            fn(*args)

    calls = []

    def fake_llm(ticker, article, body):
        calls.append(article.title)
        return {
            "category": "contracts",
            "impact_score": 88,
            "relevance_score": 91,
            "category_confidence": 0.9,
            "analysis_reason": "Fake capped LLM analysis.",
        }

    service = NewsService(
        NewsSettings(
            background_enrichment_enabled=True,
            llm_enabled=True,
            llm_max_articles_per_refresh=1,
            llm_max_articles_per_ticker=1,
        ),
        llm_analyzer=fake_llm,
    )
    service._executor = SyncExecutor()
    monkeypatch.setattr(service, "_fetch_article_body", lambda url: "Apple signed a large enterprise partnership agreement.")
    group = TickerNews(
        ticker="AAPL",
        articles=[
            NewsArticle(title="AAPL first", url="https://example.com/one"),
            NewsArticle(title="AAPL second", url="https://example.com/two"),
        ],
    )

    service._enqueue_enrichment(group, {"remaining": 1})

    enriched = [
        service._analysis_cache[service._analysis_key("AAPL", article)][1]
        for article in group.articles
    ]
    assert calls == ["AAPL first"]
    assert enriched[0].analysis_reason == "Fake capped LLM analysis."
    assert enriched[1].analysis_reason == "Article body analyzed with deterministic scoring."


def test_body_enrichment_handles_fetch_failures(monkeypatch):
    service = NewsService(quiet_settings())

    def fail_fetch(url):
        raise RuntimeError("blocked")

    monkeypatch.setattr(service, "_fetch_article_body", fail_fetch)

    enriched = service._enrich_article("AAPL", NewsArticle(title="AAPL headline", url="https://example.com/aapl"))

    assert enriched.analysis_status == "failed"
    assert "blocked" in (enriched.analysis_reason or "")
