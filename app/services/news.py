"""News retrieval for watchlist and broad market headlines."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
import re
from threading import Lock
import time
from typing import Any, Callable
from urllib.parse import urlparse, urlencode
from urllib.request import Request, urlopen

from lxml import html as lxml_html
import yfinance as yf

from app.models import NewsArticle, NewsCategory, NewsResponse, TickerNews

LlmNewsAnalyzer = Callable[[str, NewsArticle, str], dict[str, Any] | None]


@dataclass(frozen=True)
class NewsSettings:
    """Provider settings for news retrieval."""

    finnhub_api_key: str | None = None
    finnhub_base_url: str = "https://finnhub.io/api/v1"
    finnhub_company_news_days: int = 14
    request_timeout: int = 10
    article_request_timeout: int = 4
    background_enrichment_enabled: bool = True
    background_workers: int = 3
    llm_enabled: bool = False
    llm_max_articles_per_refresh: int = 5
    llm_max_articles_per_ticker: int = 1
    llm_cache_ttl_seconds: int = 86_400

    @classmethod
    def from_environment(cls) -> "NewsSettings":
        """Build settings from environment variables."""
        api_key = os.getenv("FINNHUB_API_KEY")
        return cls(
            finnhub_api_key=api_key.strip() if api_key else None,
            background_enrichment_enabled=_env_bool("NEWS_BACKGROUND_ENRICHMENT_ENABLED", True),
            llm_enabled=_env_bool("NEWS_LLM_ENABLED", False),
            llm_max_articles_per_refresh=_env_int("NEWS_LLM_MAX_ARTICLES_PER_REFRESH", 5, minimum=0),
            llm_max_articles_per_ticker=_env_int("NEWS_LLM_MAX_ARTICLES_PER_TICKER", 1, minimum=0),
            llm_cache_ttl_seconds=_env_int("NEWS_LLM_CACHE_TTL_SECONDS", 86_400, minimum=60),
        )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(minimum, parsed)


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

    COMPANY_ALIASES: dict[str, tuple[str, ...]] = {
        "AAPL": ("apple",),
        "AMD": ("advanced micro devices",),
        "AMZN": ("amazon",),
        "GOOGL": ("alphabet", "google"),
        "GOOG": ("alphabet", "google"),
        "META": ("meta", "facebook"),
        "MSFT": ("microsoft",),
        "NFLX": ("netflix",),
        "NVDA": ("nvidia",),
        "TSLA": ("tesla",),
    }
    BROAD_MARKET_TERMS = (
        "stock market",
        "stocks",
        "market today",
        "dow jones",
        "nasdaq",
        "s&p 500",
        "federal reserve",
        "inflation",
        "treasury yields",
        "wall street",
    )
    MIN_RELEVANCE_SCORE = 25.0

    def __init__(self, settings: NewsSettings | None = None, llm_analyzer: LlmNewsAnalyzer | None = None) -> None:
        self.settings = settings or NewsSettings.from_environment()
        self._general_cache: dict[tuple[object, ...], tuple[float, list[NewsArticle]]] = {}
        self._ticker_cache: dict[tuple[object, ...], tuple[float, TickerNews]] = {}
        self._analysis_cache: dict[str, tuple[float, NewsArticle]] = {}
        self._llm_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._pending_analysis: set[str] = set()
        self._analysis_lock = Lock()
        self._llm_analyzer = llm_analyzer
        self._executor = (
            ThreadPoolExecutor(
                max_workers=max(1, self.settings.background_workers),
                thread_name_prefix="news-enrichment",
            )
            if self.settings.background_enrichment_enabled
            else None
        )

    def build_news(self, tickers: list[str], per_ticker: int = 5, general_count: int = 8) -> NewsResponse:
        """Return general market news plus per-ticker watchlist news."""
        normalized_tickers = [ticker.upper().strip() for ticker in tickers]
        warnings: list[str] = []
        llm_budget = {
            "remaining": self.settings.llm_max_articles_per_refresh if self.settings.llm_enabled else 0,
        }
        return NewsResponse(
            generated_at=datetime.now(timezone.utc),
            watchlist=normalized_tickers,
            general_market=self._cached_general_market_news(general_count, warnings),
            ticker_news=[
                self._cached_ticker_news(ticker, per_ticker, llm_budget)
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

    def _cached_ticker_news(self, ticker: str, count: int, llm_budget: dict[str, int] | None = None) -> TickerNews:
        key = (ticker.upper().strip(), count, bool(self.settings.finnhub_api_key))
        cached = self._ticker_cache.get(key)
        if cached is not None and cached[0] > time.monotonic():
            result = self._merge_enrichment(cached[1].model_copy(deep=True))
            self._enqueue_enrichment(result, llm_budget)
            return result
        result = self._ticker_news(ticker, count)
        self._ticker_cache[key] = (time.monotonic() + self.CACHE_TTL_SECONDS, result.model_copy(deep=True))
        self._enqueue_enrichment(result, llm_budget)
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
        fetch_count = self._provider_fetch_count(count)
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
                    limit=fetch_count,
                )
                articles = self._rank_ticker_articles(ticker, articles, count, provider_specific=True)
                if articles:
                    return TickerNews(ticker=ticker, articles=articles)
            except Exception as exc:
                warnings.append(f"Finnhub news was unavailable for {ticker}: {exc}")

        try:
            raw_articles = yf.Ticker(ticker).get_news(count=fetch_count)
        except Exception as exc:
            warnings.append(f"News was unavailable for {ticker}: {exc}")
            raw_articles = []

        articles = self._rank_ticker_articles(
            ticker,
            self._normalize_articles(raw_articles, limit=fetch_count),
            count,
            provider_specific=True,
        )
        if not articles and not warnings:
            warnings.append(f"No high-relevance recent headlines were returned for {ticker}.")
        return TickerNews(ticker=ticker, articles=articles, warnings=warnings)

    @staticmethod
    def _provider_fetch_count(count: int) -> int:
        return min(max(count * 3, count + 10), 50)

    def _fetch_finnhub(self, endpoint: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if not self.settings.finnhub_api_key:
            return []

        query = urlencode({**params, "token": self.settings.finnhub_api_key})
        url = f"{self.settings.finnhub_base_url.rstrip('/')}/{endpoint.lstrip('/')}?{query}"
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=self.settings.request_timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data if isinstance(data, list) else []

    def _rank_ticker_articles(
        self,
        ticker: str,
        articles: list[NewsArticle],
        count: int,
        *,
        provider_specific: bool = False,
    ) -> list[NewsArticle]:
        ranked: list[tuple[float, NewsArticle]] = []
        for article in articles:
            relevance = self._article_relevance_score(ticker, article, provider_specific=provider_specific)
            impact = self._article_impact_score(article)
            freshness = self._freshness_score(article.published_at)
            if relevance < self.MIN_RELEVANCE_SCORE:
                continue
            can_enrich = bool(article.url and self.settings.background_enrichment_enabled)
            scored = article.model_copy(
                update={
                    "relevance_score": round(relevance, 2),
                    "impact_score": round(impact, 2),
                    "analysis_status": "pending" if can_enrich else "skipped",
                    "analysis_reason": "Queued for article body analysis." if can_enrich else "Article body analysis is unavailable for this article.",
                }
            )
            ranked.append((relevance + impact + freshness, scored))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [article for _, article in ranked[:count]]

    def _article_relevance_score(self, ticker: str, article: NewsArticle, *, provider_specific: bool = False) -> float:
        symbol = ticker.upper().strip()
        title = article.title or ""
        summary = article.summary or ""
        haystack = f"{title} {summary}".casefold()
        score = 0.0

        if symbol in {related.upper().strip() for related in article.related_tickers}:
            score += 70.0
        if self._contains_ticker(title, symbol):
            score += 45.0
        if self._contains_ticker(summary, symbol):
            score += 20.0

        for alias in self._company_aliases(symbol):
            if self._contains_phrase(title, alias):
                score += 35.0
            elif self._contains_phrase(summary, alias):
                score += 15.0

        if provider_specific and score > 0:
            score += 10.0
        if any(term in haystack for term in self.BROAD_MARKET_TERMS) and score < 40.0:
            score -= 20.0
        return max(0.0, min(score, 100.0))

    def _article_impact_score(self, article: NewsArticle, body: str | None = None) -> float:
        text = f"{article.title} {article.summary or ''} {body or ''}".casefold()
        impact_terms: tuple[tuple[str, float], ...] = (
            ("earnings", 24.0),
            ("guidance", 24.0),
            ("revenue", 16.0),
            ("eps", 16.0),
            ("upgrade", 18.0),
            ("downgrade", 18.0),
            ("price target", 18.0),
            ("contract", 18.0),
            ("partnership", 16.0),
            ("deal", 12.0),
            ("acquisition", 24.0),
            ("merger", 24.0),
            ("fda", 22.0),
            ("sec", 18.0),
            ("lawsuit", 18.0),
            ("investigation", 18.0),
            ("recall", 18.0),
            ("bankruptcy", 26.0),
            ("dividend", 10.0),
            ("buyback", 16.0),
        )
        score = sum(weight for term, weight in impact_terms if self._keyword_in_text(text, term))
        return min(score, 100.0)

    @staticmethod
    def _freshness_score(published_at: datetime | None) -> float:
        if published_at is None:
            return 5.0
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        age_hours = max(0.0, (datetime.now(timezone.utc) - published_at.astimezone(timezone.utc)).total_seconds() / 3600)
        if age_hours <= 18:
            return 25.0
        if age_hours <= 36:
            return 18.0
        if age_hours <= 72:
            return 10.0
        if age_hours <= 336:
            return 2.0
        return -12.0

    @classmethod
    def _contains_ticker(cls, text: str | None, ticker: str) -> bool:
        if not text:
            return False
        return re.search(rf"(?<![A-Z0-9])\$?{re.escape(ticker)}(?![A-Z0-9])", text.upper()) is not None

    @staticmethod
    def _contains_phrase(text: str | None, phrase: str) -> bool:
        if not text:
            return False
        normalized = phrase.casefold()
        return re.search(rf"\b{re.escape(normalized)}\b", text.casefold()) is not None

    @staticmethod
    def _keyword_in_text(text: str, keyword: str) -> bool:
        if " " in keyword:
            return keyword in text
        return re.search(rf"\b{re.escape(keyword)}\b", text) is not None

    def _company_aliases(self, ticker: str) -> tuple[str, ...]:
        return self.COMPANY_ALIASES.get(ticker.upper(), ())

    def _merge_enrichment(self, ticker_news: TickerNews) -> TickerNews:
        now = time.monotonic()
        merged: list[NewsArticle] = []
        with self._analysis_lock:
            expired = [key for key, (expiry, _) in self._analysis_cache.items() if expiry <= now]
            for key in expired:
                self._analysis_cache.pop(key, None)
            for article in ticker_news.articles:
                key = self._analysis_key(ticker_news.ticker, article)
                cached = self._analysis_cache.get(key)
                merged.append(cached[1].model_copy(deep=True) if cached else article.model_copy(deep=True))
        return ticker_news.model_copy(update={"articles": merged})

    def _enqueue_enrichment(self, ticker_news: TickerNews, llm_budget: dict[str, int] | None = None) -> None:
        if self._executor is None:
            return
        llm_for_ticker = 0
        for article in ticker_news.articles:
            if article.analysis_status == "analyzed" or not article.url:
                continue
            key = self._analysis_key(ticker_news.ticker, article)
            with self._analysis_lock:
                cached = self._analysis_cache.get(key)
                if cached and cached[0] > time.monotonic():
                    continue
                if key in self._pending_analysis:
                    continue
                self._pending_analysis.add(key)

            allow_llm = False
            if (
                self.settings.llm_enabled
                and self._llm_analyzer is not None
                and llm_budget is not None
                and llm_budget.get("remaining", 0) > 0
                and llm_for_ticker < self.settings.llm_max_articles_per_ticker
            ):
                allow_llm = True
                llm_for_ticker += 1
                llm_budget["remaining"] -= 1

            self._executor.submit(
                self._run_enrichment_job,
                ticker_news.ticker,
                article.model_copy(deep=True),
                key,
                allow_llm,
            )

    def _run_enrichment_job(self, ticker: str, article: NewsArticle, key: str, allow_llm: bool) -> None:
        try:
            enriched = self._enrich_article(ticker, article, allow_llm=allow_llm)
            expiry = time.monotonic() + self.CACHE_TTL_SECONDS
            with self._analysis_lock:
                self._analysis_cache[key] = (expiry, enriched)
        finally:
            with self._analysis_lock:
                self._pending_analysis.discard(key)

    def _enrich_article(self, ticker: str, article: NewsArticle, *, allow_llm: bool = False) -> NewsArticle:
        if not article.url:
            return article.model_copy(update={"analysis_status": "skipped", "analysis_reason": "No article URL available for body analysis."})
        try:
            body = self._fetch_article_body(article.url)
        except Exception as exc:
            return article.model_copy(update={"analysis_status": "failed", "analysis_reason": f"Article body unavailable: {exc}"})
        if not body:
            return article.model_copy(update={"analysis_status": "failed", "analysis_reason": "Article body was empty or unreadable."})

        category, category_confidence = self._classify_article_with_confidence(article.title, f"{article.summary or ''} {body}")
        deterministic = article.model_copy(
            update={
                "category": category,
                "category_confidence": category_confidence,
                "relevance_score": round(self._article_relevance_score(ticker, article.model_copy(update={"summary": f"{article.summary or ''} {body[:1000]}"}), provider_specific=True), 2),
                "impact_score": round(self._article_impact_score(article, body), 2),
                "analysis_status": "analyzed",
                "analysis_reason": "Article body analyzed with deterministic scoring.",
            }
        )
        llm_result = self._llm_analysis(ticker, deterministic, body, allow_llm=allow_llm)
        if not llm_result:
            return deterministic
        return self._apply_llm_analysis(deterministic, llm_result)

    def _fetch_article_body(self, url: str) -> str:
        request = Request(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "InvestmentTradingNewsBot/0.1",
            },
        )
        with urlopen(request, timeout=self.settings.article_request_timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            if "html" not in content_type and "text" not in content_type:
                return ""
            raw = response.read(1_000_000)
        return self._extract_article_text(raw.decode("utf-8", errors="ignore"))

    @classmethod
    def _extract_article_text(cls, html_text: str) -> str:
        document = lxml_html.fromstring(html_text)
        pieces: list[str] = []
        title = cls._string(document.findtext(".//title"))
        if title:
            pieces.append(title)
        for meta_name in ("description", "og:description", "twitter:description"):
            meta = document.xpath(f'//meta[translate(@name, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")="{meta_name}"]/@content')
            meta.extend(document.xpath(f'//meta[translate(@property, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")="{meta_name}"]/@content'))
            pieces.extend(cls._string(item) for item in meta if cls._string(item))
        for script_text in document.xpath('//script[@type="application/ld+json"]/text()'):
            pieces.extend(cls._json_ld_article_text(script_text))
        for element in document.xpath("//article//p | //main//p | //p"):
            text = cls._string(element.text_content())
            if text and len(text) >= 40:
                pieces.append(text)
            if sum(len(piece) for piece in pieces) > 8_000:
                break
        cleaned: list[str] = []
        seen: set[str] = set()
        for piece in pieces:
            text = re.sub(r"\s+", " ", piece or "").strip()
            if text and text not in seen:
                seen.add(text)
                cleaned.append(text)
        return " ".join(cleaned)[:10_000]

    @classmethod
    def _json_ld_article_text(cls, script_text: str) -> list[str]:
        try:
            data = json.loads(script_text)
        except json.JSONDecodeError:
            return []
        candidates = data if isinstance(data, list) else [data]
        pieces: list[str] = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            if isinstance(graph, list):
                candidates.extend(graph)
            for key in ("headline", "description", "articleBody"):
                value = cls._string(item.get(key))
                if value:
                    pieces.append(value)
        return pieces

    def _llm_analysis(self, ticker: str, article: NewsArticle, body: str, *, allow_llm: bool) -> dict[str, Any] | None:
        if not allow_llm or self._llm_analyzer is None:
            return None
        key = self._analysis_key(ticker, article)
        now = time.monotonic()
        with self._analysis_lock:
            cached = self._llm_cache.get(key)
            if cached and cached[0] > now:
                return dict(cached[1])
        result = self._llm_analyzer(ticker, article.model_copy(deep=True), body)
        if not result:
            return None
        with self._analysis_lock:
            self._llm_cache[key] = (now + self.settings.llm_cache_ttl_seconds, dict(result))
        return result

    def _apply_llm_analysis(self, article: NewsArticle, result: dict[str, Any]) -> NewsArticle:
        updates: dict[str, Any] = {
            "analysis_status": "analyzed",
            "analysis_reason": "Article body analyzed with deterministic scoring and capped LLM review.",
        }
        category = result.get("category")
        if category in {"rating_changes", "contracts", "earnings", "general"}:
            updates["category"] = category
        for field in ("relevance_score", "impact_score", "category_confidence"):
            value = result.get(field)
            if isinstance(value, (int, float)):
                updates[field] = round(max(0.0, min(float(value), 100.0 if field != "category_confidence" else 1.0)), 2)
        reason = self._string(result.get("analysis_reason"))
        if reason:
            updates["analysis_reason"] = reason
        return article.model_copy(update=updates)

    @staticmethod
    def _analysis_key(ticker: str, article: NewsArticle) -> str:
        identity = article.url or f"{article.publisher or ''}|{article.title}"
        digest = hashlib.sha256(identity.encode("utf-8", errors="ignore")).hexdigest()
        return f"{ticker.upper().strip()}:{digest}"

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
        category, category_confidence = cls._classify_article_with_confidence(title, summary)
        return NewsArticle(
            title=title,
            url=cls._url(content.get("canonicalUrl")) or cls._url(content.get("clickThroughUrl")) or cls._url(raw.get("link")),
            publisher=cls._string(provider.get("displayName") or raw.get("publisher")),
            published_at=cls._published_at(content.get("pubDate") or content.get("displayTime") or raw.get("providerPublishTime")),
            summary=summary,
            thumbnail_url=cls._thumbnail_url(content.get("thumbnail") or raw.get("thumbnail")),
            related_tickers=cls._related_tickers(raw.get("relatedTickers") or content.get("relatedTickers")),
            category=category,
            category_confidence=category_confidence,
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
            category, category_confidence = cls._classify_article_with_confidence(title, summary)
            article = NewsArticle(
                title=title,
                url=cls._url(raw.get("url") or raw.get("link")),
                publisher=cls._string(raw.get("source")),
                published_at=cls._published_at(raw.get("datetime")),
                summary=summary,
                thumbnail_url=cls._url(raw.get("image")),
                related_tickers=cls._related_tickers(raw.get("related")),
                category=category,
                category_confidence=category_confidence,
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
        return cls._classify_article_with_confidence(title, summary)[0]

    @classmethod
    def _classify_article_with_confidence(cls, title: str, summary: str | None = None) -> tuple[NewsCategory, float]:
        """Return the strongest category plus a lightweight confidence score."""
        scores: dict[NewsCategory, float] = {category: 0.0 for category in cls.CATEGORY_KEYWORDS}
        title_text = f" {title} ".casefold()
        summary_text = f" {summary or ''} ".casefold()
        for category, keywords in cls.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                needle = keyword.casefold()
                if cls._keyword_in_text(title_text, needle):
                    scores[category] += 2.0
                if cls._keyword_in_text(summary_text, needle):
                    scores[category] += 1.0

        best_category: NewsCategory = "general"
        best_score = 0.0
        priority: tuple[NewsCategory, ...] = ("earnings", "rating_changes", "contracts")
        for category in priority:
            score = scores.get(category, 0.0)
            if score > best_score:
                best_category = category
                best_score = score
        if best_score <= 0:
            return "general", 0.0
        return best_category, round(min(0.99, best_score / (best_score + 2.0)), 2)

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
