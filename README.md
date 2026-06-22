# Investment Trading Levels

A simple web application that pulls free market data with `yfinance`, calculates daily equity price levels, and serves watchlist-based reports. It includes the original FastAPI/static UI plus a Streamlit UI that is easy to run on a remote server or Streamlit hosting.

## Features

- Browser-persisted ticker/watchlist input, advanced level-weight controls, and durable UI settings using `localStorage`.
- Two main app views: investment trading levels and stock news.
- Shared watchlist input that drives both generated price-level reports and ticker-specific news.
- Shared ticker validation across API requests, static watchlists, and Streamlit watchlists.
- Saved watchlists automatically load levels, scanner output, news, and market performance when the app opens.
- Collapsible Settings panels in both the browser and Streamlit UIs persist the default view, report layout, level filter, chart defaults, auto-load/auto-refresh behavior, and watchlist news headline count.
- `Run Levels + Scanner` button that refreshes generated price-level reports and setup scanner output together.
- Shared backend display sections keep the FastAPI static UI, Streamlit UI, and PDF report aligned.
- `GET /api/config` exposes the metric catalog, chart range/interval defaults, report layouts, and default level weights used by the static UI.
- `Refresh News` button that retrieves watchlist headlines, categorized expanded ticker news cards, and general US stock market news.
- Yahoo-style market and watchlist day-to-date performance snapshots on the Stock News view.
- X.com section embedding public `@unusual_whales` posts below the watchlist news.
- Daily Score Analytics on the Trading Levels page stores setup-score and weighted level-score history in a local backend JSON file, then shows summary tiles and per-ticker trend sparklines below the broker-style charts.
- Downloadable PDF report button that honors the same metric selections.
- Drag-and-drop report cards with arrow-button fallbacks for rearranging generated ticker cards.
- Advanced Controls in the static watchlist drawer and Streamlit sidebar let users test custom level weights against the `Weight 20+` report filter in real time, with reset back to backend defaults.
- Organized metric sections for session levels, ranges, technical indicators, and events.
- Metrics currently include previous-session OHLC, premarket and opening ranges, previous-session VWAP, 52-week range, earnings gap, swing highs/lows, Adam-aligned technical levels, and Bollinger Bands.
- Streamlit app entry point for remote-friendly deployment and browser access.
- Streamlit watchlists persist to `~/.investment_trading/streamlit_state.json` by default and auto-refresh loaded data every 1 minute.

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

For Streamlit Community Cloud, push this repository to GitHub, choose `app/streamlit_app.py` as the main file, and let the platform install dependencies from `pyproject.toml`. Use Python 3.12 or 3.13 in the Streamlit Cloud advanced settings for the most stable dependency resolution. If an existing deployed app is using a different Python version, Streamlit Cloud requires deleting and redeploying the app to change Python versions.

Streamlit Cloud deployment metadata is intentionally guarded:

- Keep `requires-python` bounded with `<4` so Poetry does not solve dependencies against future Python major versions that packages such as `reportlab` do not support.
- Keep `[tool.poetry] package-mode = false` because this repository is deployed as an app, not installed as a publishable Python package named `investment-trading`.
- Do not add a `requirements.txt` unless deliberately replacing `pyproject.toml`; Streamlit Community Cloud uses the first dependency file it finds.
- If Streamlit Cloud logs show `ModuleNotFoundError: No module named 'app'`, confirm `app/streamlit_app.py` still inserts the repository root into `sys.path` before importing `app.models`.
- For future deployment bugs, save the UTC Streamlit logs, record the branch, main file path, Python version, and dependency file used, then add or update a bug note under `debug/bugs/`.

## Ticker input

Ticker input accepts a comma, space, or newline-separated watchlist. Symbols are normalized before use:

- `AAPL`, `MSFT`, and `NVDA` stay unchanged.
- `$TSLA` becomes `TSLA`.
- `BRK.B` and `BRK/B` become `BRK-B`.
- Yahoo-style symbols such as `^GSPC`, `GC=F`, and `BTC-USD` are supported.

Invalid tokens are rejected before provider calls. This includes empty tokens, emoji, HTML/script-like text, shell punctuation, malformed `=` suffixes, and normalized symbols over 20 characters. Backend API requests return `422` validation errors for invalid tickers; the static and Streamlit watchlist controls skip invalid tokens and show a short warning instead of saving them.

## Generated metrics

Each JSON and PDF report includes the following levels for every requested ticker when the free data source returns enough data:

- Previous completed session open, high, low, and close.
- Today's premarket high and low from 1-minute extended-hours bars.
- Previous completed regular-session VWAP from 5-minute bars.
- Completed-session 52-week high and low.
- Most recent earnings date plus the earnings-day opening gap from the prior close when earnings are no more than 30 days old.
- Today's first five-minute regular-session high and low.
- Major daily swing highs and lows, with nearby levels merged, swing highs ordered high-to-low, and swing lows ordered low-to-high.
- Adam-aligned technical levels: latest price, today VWAP, 1-month high/low, 50/200 SMA, 20 EMA daily, 9/20 EMA on 5-minute bars, classic pivots, Fibonacci retracements, earnings open, and pre-earnings close.
- Daily Bollinger Bands. These remain an app-specific display metric and do not feed scanner support/resistance scoring.
- Scanner calculations include VWAP extension, relative strength versus SPY/sector ETF, support/resistance confidence zones, reclaim/rejection signals, setup scoring, and intraday pattern summaries.
- Sector Analytics adds configurable trend ranges and intervals, normalized watchlist-sector and sector-ETF trend series, SPY-relative trend strength, leader/laggard participation counts, macro context using the existing major market instruments, and theme-level intraday heatmaps for watchlist groupings such as Space and Semiconductors.
- Per-ticker warnings when individual metrics are unavailable, delayed, rate-limited, or missing from the provider response.
- Browser-style web charts using app-owned OHLC data, with global and per-ticker controls for line versus candlestick view, supported range, and interval. Charts are compact, follow the same ticker order as the draggable metric cards, and no longer overlay trading levels. PDF charts continue to use completed daily closes.

## Backend calculation comparison

Comparison source: `/Users/sam/Library/CloudStorage/Dropbox/Mac (3)/Documents/Coding projects/adam/trading-levels`, primarily `trading_app.py` plus `pattern_analysis.py`.

The backend level calculations have been aligned to Adam's implementation for the formulas and scanner behavior that drive trading levels: adjusted yfinance history, 400-day daily lookback, strict today-only intraday calculations for day-trading levels, 30-day earnings-gap freshness, Adam swing-level ordering, and Adam support/resistance scoring. Bollinger Bands remain an app-specific display-only level.

Verified differences:

| Area | This app | Adam implementation | Alignment change |
| --- | --- | --- | --- |
| yfinance adjustment mode | Uses `yf.download(..., auto_adjust=True)`. | Uses `yf.Ticker(...).history(..., auto_adjust=True)`. | Aligned on adjusted prices; provider call style remains app-specific. |
| Daily lookback | JSON/PDF metrics and scanner daily levels use 400 calendar days. | Level loader uses 400 days for daily bars. | Aligned. |
| Latest session vs today | Premarket, first-five-minute range, today's VWAP, scanner setup, scanner signals, and intraday EMA require bars whose Eastern date is today. | Same. | Aligned. |
| Previous-session VWAP window | Filters regular-session 5-minute bars from 9:30 ET inclusive to 16:00 ET exclusive. | Filters 9:30 ET to 16:00 ET with pandas default endpoint handling. | Effectively equivalent for normal 5-minute bars ending at 15:55; minor endpoint-style difference remains. |
| Earnings gap recency | Returns the latest earnings date, suppresses gap/open/previous-close levels when older than 30 days, and marks the gap stale. | Suppresses gap levels older than 30 days and keeps earnings open plus pre-earnings close as levels. | Aligned, with an explicit API `is_stale` flag. Earnings levels are display-only in this app's scanner support/resistance candidate set. |
| Swing levels | Merges swing highs/lows within 0.3%, keeps up to five swing highs descending and swing lows ascending. | Same. | Aligned. |
| Scanner swing levels | Adds the first three daily swing highs/lows as support/resistance candidates. | Same. | Aligned. |
| Support/resistance candidate set | Uses Adam's scanner-quality set: today/previous VWAP, PM high/low, previous high/low/close, first-five high/low, 50/200 SMA, 1-month high/low, pivot/R1/S1, and daily swing highs/lows. | Same. | Aligned. EMAs, Fibonacci levels, R2/S2, earnings levels, and Bollinger Bands remain display-only. |
| Support/resistance scoring | Uses Adam's 0.50%-1.50% zone tolerance, previous-VWAP demotion after 11:00 ET, state-machine reaction counting, distance/reaction/recency weights, 5-point confluence bonus, 92 score cap, and 8% max distance filter. | Same. | Aligned. |
| Reclaim/rejection signals | Uses VWAP, PM high, previous high/low, R1, S1, and pivot; no 9 EMA signal. | Same. | Aligned. |
| Sector ETF fallback | Uses the hardcoded ticker map first, then yfinance sector lookup. | Same. | Aligned. |
| Adam-only displayed levels | Exposed through the `technical_levels` API model and rendered in static UI, Streamlit UI, and PDFs. | Displays these in the main levels table. | Aligned for report visibility. |
| Bollinger Bands | Included as a report metric and PDF chart overlay. | Not calculated or displayed in Adam's level table. | Deliberate app-specific extra; it does not feed scanner scoring or nearest scanner support/resistance. |

## API usage

Generate a JSON report:

```bash
curl -X POST http://127.0.0.1:8000/api/levels \
  -H 'Content-Type: application/json' \
  -d '{"tickers":"AAPL, MSFT, NVDA","metrics":["previous_day","swing_levels","technical_levels","bollinger_bands"]}'
```

Omit `metrics` to calculate every available metric. Supported metric IDs are `previous_day`, `premarket`, `previous_session_vwap_5m`, `fifty_two_week`, `earnings_gap`, `first_five_minutes`, `swing_levels`, `technical_levels`, and `bollinger_bands`.

Fetch frontend configuration:

```bash
curl http://127.0.0.1:8000/api/config
```

The config response includes the ordered metric catalog plus supported chart ranges, intervals, and default intervals. The static UI uses this endpoint instead of hardcoding those backend constants.

Generate watchlist and market news:

```bash
curl -X POST http://127.0.0.1:8000/api/news \
  -H 'Content-Type: application/json' \
  -d '{"tickers":"AAPL, MSFT, NVDA","per_ticker":10,"general_count":8}'
```

The news endpoint works without extra configuration through Yahoo Finance data. If `FINNHUB_API_KEY` is set in the environment, the app tries Finnhub first for general market news and watchlist company news, then falls back to Yahoo Finance when Finnhub is unavailable or returns no articles.
Use `per_ticker` from 1 to 20; the static and Streamlit UIs request 10 headlines per ticker, show the top 5 by default, and group the expanded ticker view into price rating changes, company contract announcements, earnings reports, and general news.
Article and thumbnail URLs are normalized before rendering; only absolute `http` and `https` URLs are shown as links or images.

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

The scanner uses the same saved watchlist as the levels and news views. In the browser and Streamlit UIs, the `Run Levels + Scanner` button refreshes both the price-level report and scanner output together. Expected missing optional inputs, such as young tickers without 200 completed daily closes, are shown as quiet data notes instead of warning rows. Setup score, relative strength, VWAP state, lows-held, range, and momentum cells use compact color/symbol coding for faster scanning. The browser and Streamlit UIs default to a horizontally scrollable ticker-row table on mobile, with the stacked cards view still available as an explicit setting.

Generate sector analytics:

```bash
curl -X POST http://127.0.0.1:8000/api/sector-analytics \
  -H 'Content-Type: application/json' \
  -d '{"tickers":"AAPL, MSFT, NVDA","trend_range":"3M","trend_interval":"1d"}'
```

The response keeps the existing sector rows, recommendations, pattern summary, ticker heatmap, and detail records, and adds normalized trend series for covered watchlist sectors, sector ETFs, `SPY`, the existing macro snapshot instruments, and `theme_heatmap` rows aggregated from ticker-level intraday patterns. Official `sector` and `etf` fields remain available for ETF-relative strength, while user-facing `theme` fields group names such as `RKLB`, `BKSY`, and `ASTS` under `Space` for clearer watchlist analytics. Daily pattern details are supporting evidence: morning low is the lowest percent-from-open in the 9:00-10:55 AM MT window, and recovery is close percent minus that morning low. The browser UI persists its Sector Analytics controls in `sector-analytics-settings-v1`; Streamlit stores equivalent settings in the app state file.

Fetch score history:

```bash
curl -X POST http://127.0.0.1:8000/api/score-history \
  -H 'Content-Type: application/json' \
  -d '{"tickers":"AAPL, MSFT, NVDA","range":"1D","score_metric":"both","level_basis":"weight_20"}'
```

Score history starts when levels or scanner data is refreshed after this feature is installed. Supported ranges are `1D`, `7D`, `30D`, `90D`, `1Y`, and `All`. The `1D` range is a regular-session trading-day view using 30-minute Eastern-time buckets from 9:30 AM to 4:00 PM; future buckets are returned as axis metadata so the UIs can draw empty bars for parts of the session that have not happened yet. Longer ranges use one stored daily point per Eastern date.

`/api/scanner` records the existing 0-8 setup score, and `/api/levels` records weighted level scores for `all`, `scanner`, and `weight_20` bases using backend-owned canonical level weights. The derived heat score is a 0-100 blend of setup and normalized level score. Movement labels compare the selected metric with the prior observed bucket for `1D`, or the prior daily point for longer ranges; `Both` uses heat movement. History is persisted at `data/score_history.json`, which is intentionally ignored by git.

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

For bug triage, known issue records, and manual refresh/UI reliability checks, see [`debug/README.md`](debug/README.md).

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

The starter implementation uses `yfinance` because it is free and quick to integrate. News retrieval supports Yahoo Finance by default and can use Finnhub when `FINNHUB_API_KEY` is configured. Free data sources can be delayed, rate-limited, unavailable for some symbols, or limited in extended-hours coverage. One-minute extended-hours data, earnings calendars, current-day opening ranges, and free news endpoints can be especially inconsistent outside active market hours or for thinly traded symbols. Provider-specific market data code is isolated behind `app/services/providers.py`, while pure level formulas live in `app/services/calculations.py`. Future providers should plug into the provider interface rather than route handlers, frontend code, or scanner analysis.

## Architecture

```text
app/
  main.py                  FastAPI routes and static UI mounting
  models.py                Request/response schemas
  services/
    calculations.py        Pure level formulas and session-window helpers
    display.py             Metric catalog, /api/config payloads, and formatted display sections
    market_data.py         Data orchestration and response assembly
    news.py                Watchlist and general market news retrieval
    providers.py           yfinance/Finnhub provider adapter and provider protocol
    pdf_report.py          PDF rendering
    scanner.py             Setup scanner and intraday pattern analysis
  streamlit_ui/
    metrics.py             Streamlit metric-card rendering
  static/
    index.html             Single-page frontend
    styles.css             UI styling
    app.js                 Local persistence and page orchestration
    modules/
      api.js               Browser API client
      formatters.js        Browser escaping/formatting helpers
      levels.js            Browser metric-card rendering
tests/                     Unit tests for parsing and calculations
```

The code intentionally separates schemas, data services, report generation, and frontend assets so future iterations can add more metrics, replace the data provider, cache results, add authentication, or expand reporting with minimal coupling.

Shared presentation is now backend-owned. Each `EquityMetrics` item still includes the raw level fields, and also includes additive `display_sections` with already formatted rows/lists. Static browser cards, Streamlit metric cards, and PDF tables render those sections first, so new report rows can be added once in `app/services/display.py`.

Scanner calculations use public `MarketDataService` methods and typed intermediate scanner data instead of calling market-data private methods. Its support/resistance candidate set remains intentionally narrower than the full display catalog: today/previous VWAP, premarket levels, previous-session levels, opening range, 50/200 SMA, 1-month range, pivot/R1/S1, and daily swing highs/lows can affect nearest support/resistance. EMAs, Fibonacci, R2/S2, earnings levels, and Bollinger Bands remain display-only unless the scanner rules are deliberately expanded later.
