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

## Requirements

- Python 3.10 or newer.
- A terminal opened at the repository root, which is the folder containing `pyproject.toml`.

If you already activated a virtual environment, do not run `python -m venv .venv` again inside that active environment. Create the virtual environment once, then activate it whenever you return to the project.

## Quickstart on Windows Command Prompt

Run these commands one line at a time from the repository root:

```bat
py -3.10 -m venv .venv
```

```bat
.venv\Scripts\activate.bat
```

```bat
python -m pip install --upgrade pip
```

```bat
python -m pip install -e .
```

```bat
python -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000> in your browser.

## Quickstart on Windows PowerShell

Run these commands one line at a time from the repository root:

```powershell
py -3.10 -m venv .venv
```

```powershell
.\.venv\Scripts\Activate.ps1
```

```powershell
python -m pip install --upgrade pip
```

```powershell
python -m pip install -e .
```

```powershell
python -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000> in your browser.

## Quickstart on macOS and Linux

Use Python 3.10 or newer, then run these commands one line at a time from the repository root:

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
python -m pip install --upgrade pip
```

```bash
python -m pip install -e .
```

```bash
python -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000> in your browser. The first install can take a while because `pandas`, `yfinance`, and `reportlab` include compiled wheels or sizable transitive dependencies. Subsequent installs should be faster because pip reuses its local download cache.

If pip reports `Package 'investment-trading' requires a different Python`, check the virtual environment's interpreter with `python --version` and recreate it with Python 3.10 or newer before reinstalling.

For test/development tools, install the optional development extra after activating the virtual environment:

```bash
python -m pip install -e '.[dev]'
```

On Windows Command Prompt, use double quotes for the development extra:

```bat
python -m pip install -e ".[dev]"
```

## Troubleshooting startup on Windows

- `Permission denied: '.venv\\Scripts\\python.exe'` usually means the virtual environment is already active, a Python process is still using it, or Windows is locking files while you try to recreate it. Stop the running app if needed, run `deactivate`, close terminals that are using `.venv`, then either reuse the existing `.venv` or delete and recreate it.
- `'source' is not recognized` means you are in Windows Command Prompt. Use `.venv\Scripts\activate.bat` instead. In PowerShell, use `.\.venv\Scripts\Activate.ps1`.
- `requires a different Python` means the Python used to create `.venv` is outside the supported version range. This project supports Python 3.10 or newer. Check with `python --version` after activation.
- `'uvicorn' is not recognized` usually means installation did not finish successfully. Rerun `python -m pip install -e .`, then start the app with `python -m uvicorn app.main:app --reload`.


## Generated metrics

Each JSON and PDF report includes the following levels for every requested ticker when the free data source returns enough data:

- Previous completed session open, high, low, and close.
- Today's premarket high and low from 1-minute extended-hours bars.
- Previous completed regular-session VWAP from 5-minute bars.
- Completed-session 52-week high and low.
- Most recent earnings date plus the earnings-day opening gap from the prior close.
- Today's first five-minute regular-session high and low.
- Major daily swing highs and lows, with nearby levels merged into concise support/resistance lists.
- Daily Bollinger Bands.
- Per-ticker warnings when individual metrics are unavailable, delayed, rate-limited, or missing from the provider response.

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

Run these commands one line at a time from the repository root:

```bash
source .venv/bin/activate
```

```bash
python -m pip install -e '.[dev]'
```

```bash
pytest
```

On Windows Command Prompt, activate with `.venv\Scripts\activate.bat` and install the development extra with `python -m pip install -e ".[dev]"`.

## Dependency audit

The runtime dependency list is intentionally small and maps to imports used by the app:

| Dependency | Why it is needed |
| --- | --- |
| `fastapi` | Defines the API application, route decorators, responses, and static-file serving. |
| `uvicorn` | Runs the ASGI app during local development and deployment. The project uses the base package instead of `uvicorn[standard]` to avoid optional speed/reload extras during the first install. |
| `pandas` | Performs DataFrame cleanup, rolling Bollinger Band calculations, intraday time-window filtering, and VWAP math. |
| `yfinance` | Retrieves the free daily and intraday equity data used by the metrics service. |
| `reportlab` | Builds the downloadable PDF report. |
| `pydantic` | Provides the request/response schemas and ticker normalization validators. |
| `pytest` (`dev` extra only) | Runs the unit tests; it is not required to launch the web app. |

The previous development extra included `httpx`, but the current test suite does not import it, so it was removed to avoid installing an unused package.

## Data source notes

The starter implementation uses `yfinance` because it is free and quick to integrate. Free data sources can be delayed, rate-limited, unavailable for some symbols, or limited in extended-hours coverage. One-minute extended-hours data, earnings calendars, and current-day opening ranges can be especially inconsistent outside active market hours or for thinly traded symbols. The market data implementation is isolated in `app/services/market_data.py` so a future provider can be added without changing the API or frontend.

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
