# Investment Trading Levels

A simple web application that pulls free market data with `yfinance`, calculates daily equity price levels, and serves watchlist-based reports. It includes the original FastAPI/static UI plus a Streamlit UI that is easy to run on a remote server or Streamlit hosting.

## Features

- Browser-persisted ticker/watchlist input and metric selections using `localStorage`.
- Two main app views: investment trading levels and stock news.
- Shared watchlist input that drives both generated price-level reports and ticker-specific news.
- Saved watchlists automatically load levels, scanner output, news, and market performance when the app opens.
- `Generate Levels` button that requests only the selected metrics from the Python backend.
- `Refresh News` button that retrieves watchlist headlines, categorized expanded ticker news cards, and general US stock market news.
- Yahoo-style market and watchlist day-to-date performance snapshots on the Stock News view.
- X.com section embedding public `@unusual_whales` posts below the watchlist news.
- `Run Scanner` button that manually scans the shared watchlist for setup scores, support/resistance zones, risk/reward, and recurring intraday dip patterns.
- Downloadable PDF report button that honors the same metric selections.
- Drag-and-drop report cards with arrow-button fallbacks for rearranging generated ticker cards.
- Organized metric sections for session levels, ranges, technical indicators, and events.
- Metrics currently include previous-session OHLC, premarket and opening ranges, previous-session VWAP, 52-week range, earnings gap, swing highs/lows, and Bollinger Bands.
- Streamlit app entry point for remote-friendly deployment and browser access.
- Streamlit watchlists persist to `~/.investment_trading/streamlit_state.json` by default and auto-refresh loaded data every 5 minutes.

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
- Scanner-only calculations include latest price, today VWAP, 1-month high/low, SMA/EMA levels, classic pivots, Fibonacci retracements, VWAP extension, relative strength versus SPY/sector ETF, support/resistance confidence zones, reclaim/rejection signals, and intraday pattern summaries.
- Per-ticker warnings when individual metrics are unavailable, delayed, rate-limited, or missing from the provider response.
- Browser-style web charts using app-owned OHLC data, with global and per-ticker controls for line versus candlestick view, supported range, and interval. Charts are compact, follow the same ticker order as the draggable metric cards, and no longer overlay trading levels. PDF charts continue to use completed daily closes.

## Backend calculation comparison

Comparison source: `/Users/sam/Library/CloudStorage/Dropbox/Mac (3)/Documents/Coding projects/adam/trading-levels`, primarily `trading_app.py` plus `pattern_analysis.py`.

Most core formulas already match Adam's implementation: previous-day OHLC, 52-week high/low, 1-month high/low, previous-session VWAP typical-price math, premarket range, first-five-minute range, SMA/EMA, classic pivots, Fibonacci retracements, VWAP extension, relative strength labels, setup scoring, reclaim/rejection scanning, and intraday pattern-analysis thresholds are conceptually the same. The remaining differences are mostly data-source settings, session-date behavior, stale earnings filtering, swing-level selection, and support/resistance scoring details.

Verified differences:

| Area | This app | Adam implementation | Alignment change |
| --- | --- | --- | --- |
| yfinance adjustment mode | Uses `yf.download(..., auto_adjust=False)` for backend history. | Uses `yf.Ticker(...).history(..., auto_adjust=True)` for price history. | Decide whether backend levels should become adjusted. If yes, change downloads or add an adjustment setting and update expected test values. |
| Daily lookback | JSON/PDF metrics use 365 calendar days; scanner uses 400 days. | Level loader uses 400 days for daily bars. | Use 400 days anywhere Adam-matched daily levels need a full scanner-compatible history. |
| Latest session vs today | Premarket, first-five-minute range, today's VWAP, and intraday EMA use the latest available session when today's bars are missing. | These calculations require bars whose Eastern date is exactly today. | Change scanner/day-trading calculations to strict today-only behavior if the goal is exact Adam parity; keep latest-session fallback only where weekend/holiday display is preferred. |
| Previous-session VWAP window | Filters 9:30 ET inclusive to 16:00 ET exclusive. | Filters 9:30 ET to 16:00 ET with pandas default endpoint inclusivity. | Usually equivalent for 5-minute bars ending at 15:55. If exact parity is required, use Adam's endpoint handling. |
| Earnings gap recency | Returns the most recent completed earnings gap regardless of age and only returns date/gap/% in the API model. | Suppresses gap levels older than 30 days and keeps earnings open plus pre-earnings close as levels. | Add the 30-day staleness cutoff and expose/store earnings open and pre-earnings close if they should participate in scanner support/resistance. |
| Swing levels | Merges swing highs/lows within 0.3%, then keeps the five levels nearest the latest completed close. | Merges within 0.3%, then keeps the first five sorted swing highs descending and swing lows ascending. | Change swing-level selection ordering if Adam parity matters. |
| Scanner swing levels | Scanner support/resistance does not include daily swing highs/lows. | Scanner adds the first three daily swing highs/lows as structural support/resistance candidates. | Add `swing_highs` and `swing_lows` to scanner data and include the first three of each in the support/resistance candidate map. |
| Support/resistance candidate set | Includes EMAs, Fibonacci levels, R2/S2, and earnings placeholders in the scored candidate map. | Excludes EMAs, Fibonacci levels, R2/S2, and stale earnings from scanner-quality support/resistance; includes swing highs/lows. | Trim the scanner candidate map to Adam's signal-focused set. |
| Support/resistance zone tolerance | Minimum zone tolerance is 0.25%; max is 1.5%. | Minimum zone tolerance is 0.50%; max is 1.5%. | Raise minimum zone tolerance to 0.50%. |
| Previous VWAP scoring | Previous-session VWAP always keeps its normal weight. | Previous-session VWAP is demoted after 11:00 ET because today's VWAP is established. | Add time-of-day demotion for previous-session VWAP. |
| Level reaction counting | Counts each nearby bar that closes on the expected side of the level, so adjacent bars can inflate reaction count. | Uses a state machine: approach, interact, then depart meaningfully before one reaction is counted. | Replace reaction counting with Adam's distinct-test state machine. |
| Confidence scoring | Distance contributes 20/15/10/5/-10; reactions add 25/18/8; recency can add up to 25; scores cap at 100. | Distance contributes 15/12/8/4/-5; reactions add 30/20/10; recency is capped at 15; scores cap at 92. | Adopt Adam's scoring weights and score cap. |
| Zone confluence bonus | Adds 8 points per extra level in a zone and caps at 100. | Adds 5 points per extra level and caps at 92. | Adopt Adam's lower confluence bonus and cap. |
| Zone distance filter | Any support below price or resistance above price can win. | Zones must be within 8% of current price to be day-trading relevant. | Add Adam's 8% max-distance filter. |
| Reclaim/rejection signals | Includes 9 EMA as a signal level and priority item. | Uses VWAP, PM high, previous high/low, R1, S1, and pivot; no 9 EMA. | Remove 9 EMA from reclaim/rejection parity mode. |
| Sector ETF fallback | Uses a hardcoded ticker-to-ETF map only; unknown tickers become `Other`. | Uses the hardcoded map first, then falls back to yfinance sector lookup. | Add yfinance sector fallback for unknown tickers if sector-relative strength should match Adam. |
| Bollinger Bands | Included as a report metric. | Not calculated or displayed in Adam's level table. | Keep as an app-specific extra, or remove/hide from Adam-parity output. |
| Adam-only displayed levels | Some are scanner-only or absent from JSON/PDF report output: today VWAP, 1-month high/low, SMA/EMA, pivots, Fibonacci, earnings open, and pre-earnings close. | Displays these in the main levels table. | Promote selected scanner-only levels into shared models/UI/PDF if the primary report should match Adam's table. |

Planned alignment path:

1. Add tests that lock Adam parity for stale earnings, swing-level ordering, strict today-only intraday calculations, and support/resistance scoring.
2. Update `app/services/market_data.py` for data adjustment mode, daily lookback, earnings cutoff/details, swing selection, and intraday session-date behavior.
3. Update `app/services/scanner.py` for Adam's scanner candidate set, swing levels, zone tolerance, previous-VWAP demotion, reaction state machine, confidence weights, confluence cap, distance filter, and sector fallback.
4. Extend `app/models.py`, `app/static/app.js`, `app/streamlit_app.py`, and `app/services/pdf_report.py` only if Adam-only levels should become first-class report outputs.
5. Keep Bollinger Bands as an app-specific optional metric unless the product goal is exact Adam table parity.

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
  -d '{"tickers":"AAPL, MSFT, NVDA","per_ticker":10,"general_count":8}'
```

The news endpoint works without extra configuration through Yahoo Finance data. If `FINNHUB_API_KEY` is set in the environment, the app tries Finnhub first for general market news and watchlist company news, then falls back to Yahoo Finance when Finnhub is unavailable or returns no articles.
Use `per_ticker` from 1 to 20; the static and Streamlit UIs request 10 headlines per ticker, show the top 5 by default, and group the expanded ticker view into price rating changes, company contract announcements, earnings reports, and general news.

Generate major market and watchlist performance snapshots:

```bash
curl -X POST http://127.0.0.1:8000/api/market-snapshot \
  -H 'Content-Type: application/json' \
  -d '{"tickers":"AAPL, MSFT, NVDA"}'
```

The snapshot endpoint returns S&P 500, Dow 30, Nasdaq, Russell 2000, VIX, Gold, Bitcoin USD, Brent Crude Oil, and the requested watchlist with latest price, previous completed close, day-to-date change, percent change, and intraday sparkline points when available.

Generate OHLC chart history:

```bash
curl -X POST http://127.0.0.1:8000/api/chart-history \
  -H 'Content-Type: application/json' \
  -d '{"tickers":["AAPL","MSFT"],"range":"1D","interval":"5m"}'
```

Supported chart ranges are `1D`, `WTD`, `5D`, `MTD`, `1M`, `QTD`, `3M`, `6M`, `YTD`, `1Y`, `2Y`, and `5Y`. The browser and Streamlit UIs label `1Y` as `1YR`. Supported intervals are `1m`, `2m`, `5m`, `15m`, `30m`, `1h`, `1d`, `1wk`, and `1mo`, with range-specific validation. The browser UI defaults to `Line`, `1D`, and `5m`; WTD/MTD/QTD use calendar-aware start dates, intraday chart history uses regular-session bars only, and daily, weekly, and monthly chart bars use provider date bars.

Run the scanner:

```bash
curl -X POST http://127.0.0.1:8000/api/scanner \
  -H 'Content-Type: application/json' \
  -d '{"tickers":"AAPL, MSFT, NVDA","include_setup":true,"include_patterns":true}'
```

The scanner uses the same saved watchlist as the levels and news views. In the browser UI it autoloads for a saved watchlist and can still be rerun manually. Expected missing optional inputs, such as young tickers without 200 completed daily closes, are shown as quiet data notes instead of warning rows. Setup score, lows-held, and momentum cells are color-coded for faster scanning.

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
