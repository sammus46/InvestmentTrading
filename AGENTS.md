# InvestmentTrading Agent Guide

## Codebase overview

This repository contains a small Python/FastAPI backend plus a static frontend for generating equity price-level reports.

- `app/main.py` defines the FastAPI application, JSON report endpoint, PDF endpoint, health check, and static file mount.
- `app/models.py` contains Pydantic schemas shared by route handlers and services.
- `app/services/market_data.py` owns market data retrieval and financial metric calculations. Keep provider-specific code here so replacing `yfinance` later does not affect routes or frontend code.
- `app/services/pdf_report.py` converts generated metrics into a PDF download.
- `app/static/` contains the browser UI. It persists ticker input in `localStorage`, calls API endpoints, renders metric cards, and downloads PDFs.
- `tests/` contains unit tests for parsing and calculation behavior.

## Development principles

- Keep route handlers thin; put business logic in service modules.
- Keep each financial metric calculation small and independently testable.
- Prefer typed Pydantic models for new API payloads and responses.
- Do not place provider-specific API assumptions in frontend code.
- When adding a new metric, update `EquityMetrics`, `MarketDataService`, the UI rendering in `app/static/app.js`, PDF output, README feature docs, and tests where practical.
- Free market data can be rate-limited or incomplete. Return warnings in API responses instead of failing an entire multi-ticker report when one metric is unavailable.

## Common commands

```bash
pip install -e '.[dev]'
pytest
uvicorn app.main:app --reload
```
