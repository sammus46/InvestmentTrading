"""FastAPI application entry point for the equity levels web app."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.models import (
    AppConfigResponse,
    ChartHistoryRequest,
    ChartHistoryResponse,
    GenerateRequest,
    GenerateResponse,
    MarketSnapshotRequest,
    MarketSnapshotResponse,
    NewsRequest,
    NewsResponse,
    ScannerRequest,
    ScannerResponse,
    ScoreHistoryRequest,
    ScoreHistoryResponse,
    SectorAnalyticsRequest,
    SectorAnalyticsResponse,
)
from app.services.display import app_config
from app.services.market_data import MarketDataService
from app.services.news import NewsService
from app.services.pdf_report import PdfReportService
from app.services.scanner import ScannerService
from app.services.score_history import ScoreHistoryService

app = FastAPI(
    title="Investment Trading Levels API",
    description="Calculates daily equity levels of significance from free market data sources.",
    version="0.1.0",
)
market_data = MarketDataService()
news_service = NewsService()
pdf_reports = PdfReportService()
scanner_service = ScannerService(market_data)
score_history_service = ScoreHistoryService()


@app.get("/api/health")
def health() -> dict[str, str]:
    """Return a lightweight service health check."""
    return {"status": "ok"}


@app.get("/api/config", response_model=AppConfigResponse)
def get_config() -> AppConfigResponse:
    """Return shared frontend configuration."""
    return app_config()


@app.post("/api/levels", response_model=GenerateResponse)
def generate_levels(request: GenerateRequest) -> GenerateResponse:
    """Generate metrics for each requested ticker."""
    response = GenerateResponse(
        generated_at=datetime.now(timezone.utc),
        metrics=market_data.build_metrics(request.tickers, request.metrics),
    )
    try:
        score_history_service.record_level_scores(response.metrics)
    except Exception:
        pass
    return response


@app.post("/api/news", response_model=NewsResponse)
def generate_news(request: NewsRequest) -> NewsResponse:
    """Generate watchlist and general market news."""
    return news_service.build_news(
        request.tickers,
        per_ticker=request.per_ticker,
        general_count=request.general_count,
    )


@app.post("/api/scanner", response_model=ScannerResponse)
def generate_scanner(request: ScannerRequest) -> ScannerResponse:
    """Generate setup scanner and intraday pattern analysis."""
    response = scanner_service.build_scanner(
        request.tickers,
        include_setup=request.include_setup,
        include_patterns=request.include_patterns,
        pattern_lookback_days=request.pattern_lookback_days,
    )
    try:
        score_history_service.record_setup_scores(response.setup_rows)
    except Exception:
        pass
    return response


@app.post("/api/score-history", response_model=ScoreHistoryResponse)
def generate_score_history(request: ScoreHistoryRequest) -> ScoreHistoryResponse:
    """Return persisted daily score trends for requested tickers."""
    return score_history_service.build_response(
        request.tickers,
        score_range=request.range,
        score_metric=request.score_metric,
        level_basis=request.level_basis,
    )


@app.post("/api/sector-analytics", response_model=SectorAnalyticsResponse)
def generate_sector_analytics(request: SectorAnalyticsRequest) -> SectorAnalyticsResponse:
    """Generate sector trend and intraday pattern analytics."""
    return scanner_service.build_sector_analytics(
        request.tickers,
        pattern_lookback_days=request.pattern_lookback_days,
        trend_range=request.trend_range,
        trend_interval=request.trend_interval,
    )


@app.post("/api/market-snapshot", response_model=MarketSnapshotResponse)
def generate_market_snapshot(request: MarketSnapshotRequest) -> MarketSnapshotResponse:
    """Generate major market and watchlist day-to-date performance."""
    return market_data.build_market_snapshot(request.tickers)


@app.post("/api/chart-history", response_model=ChartHistoryResponse)
def generate_chart_history(request: ChartHistoryRequest) -> ChartHistoryResponse:
    """Generate OHLC chart history for broker-style charts."""
    return market_data.build_chart_history(request.tickers, request.range, request.interval)


@app.post("/api/reports/pdf")
def generate_pdf(request: GenerateRequest) -> Response:
    """Generate a PDF report for each requested ticker."""
    report = GenerateResponse(
        generated_at=datetime.now(timezone.utc),
        metrics=market_data.build_metrics(request.tickers, request.metrics, include_history=True),
    )
    pdf = pdf_reports.build_pdf(report)
    filename = f"equity-levels-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
