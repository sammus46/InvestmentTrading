# Investment Trading Levels

A simple FastAPI application that pulls free market data with `yfinance`, calculates daily equity price levels, and serves a lightweight browser UI for watchlist-based reports.

## Features

- Browser-persisted ticker/watchlist input using `localStorage`.
- `Generate Levels` button that requests metrics from the Python backend.
- Downloadable PDF report button.
- Metrics currently include:
  - previous daily open, high, low, and close;
  - latest premarket high and low from extended-hours intraday bars;
  - previous regular-session VWAP from 5 minute bars;
  - 20 period, 2 standard deviation Bollinger Bands from daily closes.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000> in your browser.

## API usage

Generate a JSON report:

```bash
curl -X POST http://127.0.0.1:8000/api/levels \
  -H 'Content-Type: application/json' \
  -d '{"tickers":"AAPL, MSFT, NVDA"}'
```

Download a PDF report:

```bash
curl -X POST http://127.0.0.1:8000/api/reports/pdf \
  -H 'Content-Type: application/json' \
  -d '{"tickers":["AAPL","MSFT"]}' \
  --output equity-levels.pdf
```

## Testing

```bash
pytest
```

## Data source notes

The starter implementation uses `yfinance` because it is free and quick to integrate. Free data sources can be delayed, rate-limited, unavailable for some symbols, or limited in extended-hours coverage. The market data implementation is isolated in `app/services/market_data.py` so a future provider can be added without changing the API or frontend.

## Architecture

```text
app/
  main.py                  FastAPI routes and static UI mounting
  models.py                Request/response schemas
  services/
    market_data.py         Data retrieval and financial calculations
    pdf_report.py          PDF rendering
  static/
    index.html             Single-page frontend
    styles.css             UI styling
    app.js                 Local persistence, API calls, and report rendering
tests/                     Unit tests for parsing and calculations
```

The code intentionally separates schemas, data services, report generation, and frontend assets so future iterations can add more metrics, replace the data provider, cache results, add authentication, or expand reporting with minimal coupling.
