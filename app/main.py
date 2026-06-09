"""FastAPI application entry point for the equity levels web app."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.models import GenerateRequest, GenerateResponse, NewsRequest, NewsResponse
from app.services.market_data import MarketDataService
from app.services.news import NewsService
from app.services.pdf_report import PdfReportService

app = FastAPI(
    title="Investment Trading Levels API",
    description="Calculates daily equity levels of significance from free market data sources.",
    version="0.1.0",
)
market_data = MarketDataService()
news_service = NewsService()
pdf_reports = PdfReportService()


@app.get("/api/health")
def health() -> dict[str, str]:
    """Return a lightweight service health check."""
    return {"status": "ok"}


@app.post("/api/levels", response_model=GenerateResponse)
def generate_levels(request: GenerateRequest) -> GenerateResponse:
    """Generate metrics for each requested ticker."""
    return GenerateResponse(
        generated_at=datetime.now(timezone.utc),
        metrics=market_data.build_metrics(request.tickers, request.metrics),
    )


@app.post("/api/news", response_model=NewsResponse)
def generate_news(request: NewsRequest) -> NewsResponse:
    """Generate watchlist and general market news."""
    return news_service.build_news(
        request.tickers,
        per_ticker=request.per_ticker,
        general_count=request.general_count,
    )


@app.post("/api/reports/pdf")
def generate_pdf(request: GenerateRequest) -> Response:
    """Generate a PDF report for each requested ticker."""
    report = generate_levels(request)
    pdf = pdf_reports.build_pdf(report)
    filename = f"equity-levels-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
