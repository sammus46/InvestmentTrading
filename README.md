# Investment Trading Levels

A simple web application that pulls free market data with `yfinance`, calculates daily equity price levels, and serves watchlist-based reports. It includes the original FastAPI/static UI plus a Streamlit UI that is easy to run on a remote server or Streamlit hosting.

## Features

- Browser-persisted ticker/watchlist input and metric selections using `localStorage`.
- Two main app views: investment trading levels and stock news.
- Shared watchlist input that drives both generated price-level reports and ticker-specific news.
- `Generate Levels` button that requests only the selected metrics from the Python backend.
- `Refresh News` button that retrieves watchlist headlines and general US stock market news.
- Downloadable PDF report button that honors the same metric selections.
- Drag-and-drop report cards with arrow-button fallbacks for rearranging generated ticker cards.
- Organized metric sections for session levels, ranges, technical indicators, and events.
- Metrics currently include previous-session OHLC, premarket and opening ranges, previous-session VWAP, 52-week range, earnings gap, swing highs/lows, and Bollinger Bands.
- Streamlit app entry point for remote-friendly deployment and browser access.

## Requirements

- Python 3.10 or newer.
- A terminal opened at the repository root, which is the folder containing `pyproject.toml`.
- Optional: a Finnhub API key in `FINNHUB_API_KEY` to use Finnhub for news before falling back to Yahoo Finance.

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

To run the Streamlit app instead:

```bat
python -m streamlit run app/streamlit_app.py
```

Open <http://localhost:8501> in your browser.

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

To run the Streamlit app instead:

```powershell
python -m streamlit run app/streamlit_app.py
```

Open <http://localhost:8501> in your browser.

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

To run the Streamlit app instead:

```bash
python -m streamlit run app/streamlit_app.py
```

Open <http://localhost:8501> in your browser.

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
- `No module named streamlit` means the active virtual environment does not have the project dependencies installed. With `.venv` activated, rerun `python -m pip install -e .`, then start the Streamlit UI with `python -m streamlit run app/streamlit_app.py`.

## Remote access

You now have two web app entry points:

- Streamlit UI: `app/streamlit_app.py`
- FastAPI/static UI and JSON/PDF API: `app.main:app`

For a private server, VM, or home machine where you can open a firewall port, run Streamlit on all network interfaces:

```bash
python -m streamlit run app/streamlit_app.py --server.address 0.0.0.0 --server.port 8501
```

Then browse to `http://YOUR_SERVER_IP:8501`.

You can also expose the existing FastAPI app remotely:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then browse to `http://YOUR_SERVER_IP:8000`.

For public internet access, put the app behind authentication or a private tunnel such as a VPN, Tailscale, Cloudflare Tunnel, or a reverse proxy with login. The app pulls market data and has no built-in user accounts, so avoid exposing it as an unauthenticated public service.

For Streamlit Community Cloud, push this repository to GitHub, choose `app/streamlit_app.py` as the main file, and let the platform install dependencies from `pyproject.toml`.


## Generated metrics

Each JSON and PDF report includes the following levels for every requested ticker when the free data source returns enough data:

- Previous completed session open, high, low, and close.
- Latest available session premarket high and low from 1-minute extended-hours bars.
- Previous completed regular-session VWAP from 5-minute bars.
- Completed-session 52-week high and low.
- Most recent earnings date plus the earnings-day opening gap from the prior close.
- Latest available session first five-minute regular-session high and low.
- Major daily swing highs and lows, with nearby levels merged, prioritized by distance from the latest completed close, and displayed in numerical order.
- Daily Bollinger Bands.
- Per-ticker warnings when individual metrics are unavailable, delayed, rate-limited, or missing from the provider response.
- Web and PDF charts showing up to the latest 365 completed daily closes per ticker, with selected price levels overlaid using a consistent clickable color legend. The web charts include a dual-handle x-axis zoom slider, hover tooltips for close points, preset range buttons, and follow the same ticker order as the draggable metric cards.

## API usage

Generate a JSON report:

```bash
curl -X POST http://127.0.0.1:8000/api/levels \
  -H 'Content-Type: application/json' \
  -d '{"tickers":"AAPL, MSFT, NVDA","metrics":["previous_day","swing_levels","bollinger_bands"]}'
```

Omit `metrics` to calculate every available metric. Supported metric IDs are `previous_day`, `premarket`, `previous_session_vwap_5m`, `fifty_two_week`, `earnings_gap`, `first_five_minutes`, `swing_levels`, and `bollinger_bands`.

Generate watchlist and market news:

```bash
curl -X POST http://127.0.0.1:8000/api/news \
  -H 'Content-Type: application/json' \
  -d '{"tickers":"AAPL, MSFT, NVDA","per_ticker":5,"general_count":8}'
```

The news endpoint works without extra configuration through Yahoo Finance data. If `FINNHUB_API_KEY` is set in the environment, the app tries Finnhub first for general market news and watchlist company news, then falls back to Yahoo Finance when Finnhub is unavailable or returns no articles.

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
| `lxml` | Provides the optional HTML/XML parser used by yfinance earnings-calendar lookups. |
| `reportlab` | Builds the downloadable PDF report. |
| `pydantic` | Provides the request/response schemas and ticker normalization validators. |
| `streamlit` | Serves the remote-friendly interactive web app. |
| `pytest` (`dev` extra only) | Runs the unit tests; it is not required to launch the web app. |

The previous development extra included `httpx`, but the current test suite does not import it, so it was removed to avoid installing an unused package.

## Data source notes

The starter implementation uses `yfinance` because it is free and quick to integrate. News retrieval supports Yahoo Finance by default and can use Finnhub when `FINNHUB_API_KEY` is configured. Free data sources can be delayed, rate-limited, unavailable for some symbols, or limited in extended-hours coverage. One-minute extended-hours data, earnings calendars, current-day opening ranges, and free news endpoints can be especially inconsistent outside active market hours or for thinly traded symbols. Provider-specific code is isolated in `app/services/market_data.py` and `app/services/news.py` so future providers can be added without changing routes or frontend code.

## Architecture

```text
app/
  main.py                  FastAPI routes and static UI mounting
  models.py                Request/response schemas
  services/
    market_data.py         Data retrieval and financial calculations
    news.py                Watchlist and general market news retrieval
    pdf_report.py          PDF rendering
  static/
    index.html             Single-page frontend
    styles.css             UI styling
    app.js                 Local persistence, API calls, and report rendering
tests/                     Unit tests for parsing and calculations
```

The code intentionally separates schemas, data services, report generation, and frontend assets so future iterations can add more metrics, replace the data provider, cache results, add authentication, or expand reporting with minimal coupling.
