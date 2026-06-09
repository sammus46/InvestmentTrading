"""News retrieval for watchlist and broad market headlines."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import yfinance as yf

from app.models import NewsArticle, NewsResponse, TickerNews


class NewsService:
    """Fetch and normalize news from yfinance/Yahoo Finance."""

    def build_news(self, tickers: list[str], per_ticker: int = 5, general_count: int = 8) -> NewsResponse:
        """Return general market news plus per-ticker watchlist news."""
        normalized_tickers = [ticker.upper().strip() for ticker in tickers]
        warnings: list[str] = []
        return NewsResponse(
            generated_at=datetime.now(timezone.utc),
            watchlist=normalized_tickers,
            general_market=self._general_market_news(general_count, warnings),
            ticker_news=[
                self._ticker_news(ticker, per_ticker)
                for ticker in normalized_tickers
            ],
            warnings=warnings,
        )

    def _general_market_news(self, count: int, warnings: list[str]) -> list[NewsArticle]:
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
        try:
            raw_articles = yf.Ticker(ticker).get_news(count=count)
        except Exception as exc:
            warnings.append(f"News was unavailable for {ticker}: {exc}")
            raw_articles = []

        articles = self._normalize_articles(raw_articles, limit=count)
        if not articles and not warnings:
            warnings.append(f"No recent news was returned for {ticker}.")
        return TickerNews(ticker=ticker, articles=articles, warnings=warnings)

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
        return NewsArticle(
            title=title,
            url=cls._url(content.get("canonicalUrl")) or cls._url(content.get("clickThroughUrl")) or cls._string(raw.get("link")),
            publisher=cls._string(provider.get("displayName") or raw.get("publisher")),
            published_at=cls._published_at(content.get("pubDate") or content.get("displayTime") or raw.get("providerPublishTime")),
            summary=cls._string(content.get("summary") or content.get("description") or raw.get("summary")),
            thumbnail_url=cls._thumbnail_url(content.get("thumbnail") or raw.get("thumbnail")),
            related_tickers=cls._related_tickers(raw.get("relatedTickers") or content.get("relatedTickers")),
        )

    @staticmethod
    def _string(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _url(cls, value: object) -> str | None:
        if isinstance(value, dict):
            return cls._string(value.get("url"))
        return cls._string(value)

    @classmethod
    def _thumbnail_url(cls, value: object) -> str | None:
        if not isinstance(value, dict):
            return None
        original = cls._string(value.get("originalUrl"))
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
        if not isinstance(value, list):
            return []
        tickers: list[str] = []
        for item in value:
            ticker = str(item).upper().strip()
            if ticker and ticker not in tickers:
                tickers.append(ticker)
        return tickers
