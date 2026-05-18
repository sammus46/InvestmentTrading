"""FastAPI application entry point for the equity levels web app."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.models import GenerateRequest, GenerateResponse
from app.services.market_data import MarketDataService
from app.services.pdf_report import PdfReportService

app = FastAPI(
    title="Investment Trading Levels API",
    description="Calculates daily equity levels of significance from free market data sources.",
    version="0.1.0",
)
market_data = MarketDataService()
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
