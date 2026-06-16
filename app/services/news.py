"""News retrieval for watchlist and broad market headlines."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import os
import re
import time
from typing import Any
from urllib.parse import urlparse, urlencode
from urllib.request import Request, urlopen

import yfinance as yf

from app.models import NewsArticle, NewsCategory, NewsResponse, TickerNews


@dataclass(frozen=True)
class NewsSettings:
    """Provider settings for news retrieval."""

    finnhub_api_key: str | None = None
    finnhub_base_url: str = "https://finnhub.io/api/v1"
    finnhub_company_news_days: int = 14
    request_timeout: int = 10

    @classmethod
    def from_environment(cls) -> "NewsSettings":
        """Build settings from environment variables."""
        api_key = os.getenv("FINNHUB_API_KEY")
        return cls(finnhub_api_key=api_key.strip() if api_key else None)


class NewsService:
    """Fetch and normalize news from configured providers."""

    CACHE_TTL_SECONDS = 300

    CATEGORY_KEYWORDS: dict[NewsCategory, tuple[str, ...]] = {
        "rating_changes": (
            "upgrade",
            "upgrades",
            "upgraded",
            "downgrade",
            "downgrades",
            "downgraded",
            "price target",
            "target price",
            "analyst rating",
            "initiates",
            "initiated",
            "reiterates",
            "reiterated",
            "maintains",
            "raises target",
            "cuts target",
            "outperform",
            "underperform",
            "overweight",
            "underweight",
        ),
        "contracts": (
            "contract",
            "contracts",
            "deal",
            "deals",
            "partnership",
            "partnerships",
            "agreement",
            "agreements",
            "order",
            "orders",
            "supply agreement",
            "customer win",
            "awarded",
            "wins order",
            "signs",
            "signed",
            "collaboration",
        ),
        "earnings": (
            "earnings",
            "eps",
            "revenue",
            "revenues",
            "guidance",
            "quarterly results",
            "quarter results",
            "q1 results",
            "q2 results",
            "q3 results",
            "q4 results",
            "profit",
            "profits",
            "loss",
            "losses",
            "beats estimates",
            "misses estimates",
        ),
    }

    def __init__(self, settings: NewsSettings | None = None) -> None:
        self.settings = settings or NewsSettings.from_environment()
        self._general_cache: dict[tuple[object, ...], tuple[float, list[NewsArticle]]] = {}
        self._ticker_cache: dict[tuple[object, ...], tuple[float, TickerNews]] = {}

    def build_news(self, tickers: list[str], per_ticker: int = 5, general_count: int = 8) -> NewsResponse:
        """Return general market news plus per-ticker watchlist news."""
        normalized_tickers = [ticker.upper().strip() for ticker in tickers]
        warnings: list[str] = []
        return NewsResponse(
            generated_at=datetime.now(timezone.utc),
            watchlist=normalized_tickers,
            general_market=self._cached_general_market_news(general_count, warnings),
            ticker_news=[
                self._cached_ticker_news(ticker, per_ticker)
                for ticker in normalized_tickers
            ],
            warnings=warnings,
        )

    def _cached_general_market_news(self, count: int, warnings: list[str]) -> list[NewsArticle]:
        key = ("general", count, bool(self.settings.finnhub_api_key))
        cached = self._general_cache.get(key)
        if cached is not None and cached[0] > time.monotonic():
            return [article.model_copy(deep=True) for article in cached[1]]
        articles = self._general_market_news(count, warnings)
        self._general_cache[key] = (time.monotonic() + self.CACHE_TTL_SECONDS, [article.model_copy(deep=True) for article in articles])
        return articles

    def _cached_ticker_news(self, ticker: str, count: int) -> TickerNews:
        key = (ticker.upper().strip(), count, bool(self.settings.finnhub_api_key))
        cached = self._ticker_cache.get(key)
        if cached is not None and cached[0] > time.monotonic():
            return cached[1].model_copy(deep=True)
        result = self._ticker_news(ticker, count)
        self._ticker_cache[key] = (time.monotonic() + self.CACHE_TTL_SECONDS, result.model_copy(deep=True))
        return result

    def _general_market_news(self, count: int, warnings: list[str]) -> list[NewsArticle]:
        if self.settings.finnhub_api_key:
            try:
                articles = self._normalize_finnhub_articles(
                    self._fetch_finnhub("news", {"category": "general"}),
                    limit=count,
                )
                if articles:
                    return articles
            except Exception as exc:
                warnings.append(f"Finnhub general market news was unavailable: {exc}")

        errors: list[str] = []
        for query in ["stock market", "S&P 500", "Dow Jones Nasdaq"]:
            try:
                search = yf.Search(
                    query,
                    max_results=0,
                    news_count=count,
                    lists_count=0,
                    include_cb=False,
                    raise_errors=False,
                )
            except Exception as exc:
                errors.append(str(exc))
                continue

            articles = self._normalize_articles(getattr(search, "news", []), limit=count)
            if articles:
                return articles

        if errors:
            warnings.append(f"General market news was unavailable: {errors[-1]}")
        else:
            warnings.append("No general market news was returned by the data source.")
        return []

    def _ticker_news(self, ticker: str, count: int) -> TickerNews:
        warnings: list[str] = []
        if self.settings.finnhub_api_key:
            try:
                articles = self._normalize_finnhub_articles(
                    self._fetch_finnhub(
                        "company-news",
                        {
                            "symbol": ticker,
                            "from": (date.today() - timedelta(days=self.settings.finnhub_company_news_days)).isoformat(),
                            "to": date.today().isoformat(),
                        },
                    ),
                    limit=count,
                )
                if articles:
                    return TickerNews(ticker=ticker, articles=articles)
            except Exception as exc:
                warnings.append(f"Finnhub news was unavailable for {ticker}: {exc}")

        try:
            raw_articles = yf.Ticker(ticker).get_news(count=count)
        except Exception as exc:
            warnings.append(f"News was unavailable for {ticker}: {exc}")
            raw_articles = []

        articles = self._normalize_articles(raw_articles, limit=count)
        if not articles and not warnings:
            warnings.append(f"No recent news was returned for {ticker}.")
        return TickerNews(ticker=ticker, articles=articles, warnings=warnings)

    def _fetch_finnhub(self, endpoint: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if not self.settings.finnhub_api_key:
            return []

        query = urlencode({**params, "token": self.settings.finnhub_api_key})
        url = f"{self.settings.finnhub_base_url.rstrip('/')}/{endpoint.lstrip('/')}?{query}"
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=self.settings.request_timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data if isinstance(data, list) else []

    @classmethod
    def _normalize_articles(cls, raw_articles: list[dict[str, Any]], limit: int) -> list[NewsArticle]:
        articles: list[NewsArticle] = []
        seen: set[str] = set()
        for raw in raw_articles:
            article = cls._normalize_article(raw)
            if article is None:
                continue
            key = article.url or article.title
            if key in seen:
                continue
            seen.add(key)
            articles.append(article)
            if len(articles) == limit:
                break
        return articles

    @classmethod
    def _normalize_article(cls, raw: dict[str, Any]) -> NewsArticle | None:
        content = raw.get("content") if isinstance(raw.get("content"), dict) else raw
        title = cls._string(content.get("title") or raw.get("title"))
        if not title:
            return None

        provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}
        summary = cls._string(content.get("summary") or content.get("description") or raw.get("summary"))
        return NewsArticle(
            title=title,
            url=cls._url(content.get("canonicalUrl")) or cls._url(content.get("clickThroughUrl")) or cls._url(raw.get("link")),
            publisher=cls._string(provider.get("displayName") or raw.get("publisher")),
            published_at=cls._published_at(content.get("pubDate") or content.get("displayTime") or raw.get("providerPublishTime")),
            summary=summary,
            thumbnail_url=cls._thumbnail_url(content.get("thumbnail") or raw.get("thumbnail")),
            related_tickers=cls._related_tickers(raw.get("relatedTickers") or content.get("relatedTickers")),
            category=cls._classify_article(title, summary),
        )

    @classmethod
    def _normalize_finnhub_articles(cls, raw_articles: list[dict[str, Any]], limit: int) -> list[NewsArticle]:
        articles: list[NewsArticle] = []
        seen: set[str] = set()
        for raw in raw_articles:
            title = cls._string(raw.get("headline") or raw.get("title"))
            if not title:
                continue
            summary = cls._string(raw.get("summary"))
            article = NewsArticle(
                title=title,
                url=cls._url(raw.get("url") or raw.get("link")),
                publisher=cls._string(raw.get("source")),
                published_at=cls._published_at(raw.get("datetime")),
                summary=summary,
                thumbnail_url=cls._url(raw.get("image")),
                related_tickers=cls._related_tickers(raw.get("related")),
                category=cls._classify_article(title, summary),
            )
            key = article.url or article.title
            if key in seen:
                continue
            seen.add(key)
            articles.append(article)
            if len(articles) == limit:
                break
        return articles

    @classmethod
    def _classify_article(cls, title: str, summary: str | None = None) -> NewsCategory:
        """Group headlines into trader-friendly buckets from provider text."""
        haystack = f" {title} {summary or ''} ".casefold()
        for category, keywords in cls.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                needle = keyword.casefold()
                if " " in needle:
                    if needle in haystack:
                        return category
                    continue
                if re.search(rf"\b{re.escape(needle)}\b", haystack):
                    return category
        return "general"

    @staticmethod
    def _string(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _url(cls, value: object) -> str | None:
        if isinstance(value, dict):
            value = value.get("url")
        url = cls._string(value)
        if not url:
            return None
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        return url

    @classmethod
    def _thumbnail_url(cls, value: object) -> str | None:
        if not isinstance(value, dict):
            return None
        original = cls._url(value.get("originalUrl"))
        if original:
            return original
        resolutions = value.get("resolutions")
        if isinstance(resolutions, list) and resolutions:
            return cls._url(resolutions[0])
        return None

    @staticmethod
    def _published_at(value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    @staticmethod
    def _related_tickers(value: object) -> list[str]:
        if isinstance(value, str):
            candidates = value.replace(",", " ").split()
        elif isinstance(value, list):
            candidates = [str(item) for item in value]
        else:
            return []
        tickers: list[str] = []
        for item in candidates:
            ticker = item.upper().strip()
            if ticker and ticker not in tickers:
                tickers.append(ticker)
        return tickers
