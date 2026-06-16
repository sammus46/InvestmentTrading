"""Compare Streamlit data/render speed against Adam's Streamlit app.

The benchmark intentionally separates data/query time from app-imposed UX waits.
Adam's app sleeps between ticker loads in the UI loop, so the report includes
both raw load time and estimated as-app UX time.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import types
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import yfinance as yf

from app.models import DEFAULT_METRICS, ChartInterval, ChartRange, EquityMetrics, GenerateResponse, ScannerResponse
from app.services.market_data import MarketDataService
from app.services.providers import YFinanceProvider
from app.services.scanner import ScannerService
from app.streamlit_app import STREAMLIT_REPORT_BATCH_SIZE, ticker_batches
from app.streamlit_ui.metrics import metric_card_html


DEFAULT_TICKERS = ("PWR", "NVT", "BKSY", "RKLB", "STRL", "NVDA", "MU", "GEV", "MYRG", "ASTS", "FIX", "PLTR")
DEFAULT_ADAM_PATH = Path("/Users/sam/Library/CloudStorage/Dropbox/Mac (3)/Documents/Coding projects/adam/trading-levels")
ADAM_UI_SLEEP_PER_TICKER_SECONDS = 1.5
ADAM_UI_MAX_RETRIES = 3
MINE_CHART_RANGE: ChartRange = "1D"
MINE_CHART_INTERVAL: ChartInterval = "5m"


class TagCounter(HTMLParser):
    """Small HTML tag counter used for rendered view element estimates."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: dict[str, int] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        self.tags[tag] = self.tags.get(tag, 0) + 1


@dataclass
class QueryRecord:
    app: str
    operation: str
    symbol: str
    period: str | None
    interval: str | None
    prepost: bool | None
    elapsed_seconds: float
    rows: int | None = None
    error: str | None = None


@dataclass
class QueryRecorder:
    records: list[QueryRecord] = field(default_factory=list)

    def add(
        self,
        *,
        app: str,
        operation: str,
        symbol: str,
        period: str | None = None,
        interval: str | None = None,
        prepost: bool | None = None,
        elapsed_seconds: float,
        rows: int | None = None,
        error: str | None = None,
    ) -> None:
        self.records.append(
            QueryRecord(
                app=app,
                operation=operation,
                symbol=symbol,
                period=period,
                interval=interval,
                prepost=prepost,
                elapsed_seconds=elapsed_seconds,
                rows=rows,
                error=error,
            )
        )

    def summarize(self, app: str) -> dict[str, Any]:
        records = [record for record in self.records if record.app == app]
        elapsed = [record.elapsed_seconds for record in records]
        by_operation: dict[str, dict[str, Any]] = {}
        for record in records:
            item = by_operation.setdefault(record.operation, {"count": 0, "seconds": 0.0})
            item["count"] += 1
            item["seconds"] += record.elapsed_seconds
        return {
            "count": len(records),
            "total_seconds": round(sum(elapsed), 3),
            "avg_seconds": round(statistics.mean(elapsed), 3) if elapsed else 0.0,
            "max_seconds": round(max(elapsed), 3) if elapsed else 0.0,
            "by_operation": {
                operation: {"count": data["count"], "seconds": round(data["seconds"], 3)}
                for operation, data in sorted(by_operation.items())
            },
            "errors": [record.__dict__ for record in records if record.error],
        }


@contextmanager
def timed_yfinance(app_name: str, recorder: QueryRecorder):
    """Record yfinance download/history/metadata calls made inside the context."""
    original_download = yf.download
    original_ticker = yf.Ticker

    def timed_download(*args: Any, **kwargs: Any) -> pd.DataFrame:
        symbol = str(args[0]) if args else str(kwargs.get("tickers", ""))
        started = time.perf_counter()
        try:
            frame = original_download(*args, **kwargs)
        except Exception as exc:
            recorder.add(
                app=app_name,
                operation="yf.download",
                symbol=symbol,
                period=kwargs.get("period"),
                interval=kwargs.get("interval"),
                prepost=kwargs.get("prepost"),
                elapsed_seconds=time.perf_counter() - started,
                error=type(exc).__name__,
            )
            raise
        recorder.add(
            app=app_name,
            operation="yf.download",
            symbol=symbol,
            period=kwargs.get("period"),
            interval=kwargs.get("interval"),
            prepost=kwargs.get("prepost"),
            elapsed_seconds=time.perf_counter() - started,
            rows=len(frame) if isinstance(frame, pd.DataFrame) else None,
        )
        return frame

    class TimedTicker:
        def __init__(self, symbol: str, *args: Any, **kwargs: Any) -> None:
            self.symbol = symbol
            self._ticker = original_ticker(symbol, *args, **kwargs)

        def history(self, *args: Any, **kwargs: Any) -> pd.DataFrame:
            started = time.perf_counter()
            try:
                frame = self._ticker.history(*args, **kwargs)
            except Exception as exc:
                recorder.add(
                    app=app_name,
                    operation="Ticker.history",
                    symbol=self.symbol,
                    period=kwargs.get("period"),
                    interval=kwargs.get("interval"),
                    prepost=kwargs.get("prepost"),
                    elapsed_seconds=time.perf_counter() - started,
                    error=type(exc).__name__,
                )
                raise
            recorder.add(
                app=app_name,
                operation="Ticker.history",
                symbol=self.symbol,
                period=kwargs.get("period"),
                interval=kwargs.get("interval"),
                prepost=kwargs.get("prepost"),
                elapsed_seconds=time.perf_counter() - started,
                rows=len(frame) if isinstance(frame, pd.DataFrame) else None,
            )
            return frame

        @property
        def fast_info(self) -> Any:
            started = time.perf_counter()
            try:
                value = self._ticker.fast_info
            except Exception as exc:
                recorder.add(
                    app=app_name,
                    operation="Ticker.fast_info",
                    symbol=self.symbol,
                    elapsed_seconds=time.perf_counter() - started,
                    error=type(exc).__name__,
                )
                raise
            recorder.add(
                app=app_name,
                operation="Ticker.fast_info",
                symbol=self.symbol,
                elapsed_seconds=time.perf_counter() - started,
            )
            return value

        @property
        def earnings_dates(self) -> Any:
            started = time.perf_counter()
            try:
                value = self._ticker.earnings_dates
            except Exception as exc:
                recorder.add(
                    app=app_name,
                    operation="Ticker.earnings_dates",
                    symbol=self.symbol,
                    elapsed_seconds=time.perf_counter() - started,
                    error=type(exc).__name__,
                )
                raise
            recorder.add(
                app=app_name,
                operation="Ticker.earnings_dates",
                symbol=self.symbol,
                elapsed_seconds=time.perf_counter() - started,
                rows=len(value) if isinstance(value, pd.DataFrame) else None,
            )
            return value

        @property
        def info(self) -> Any:
            started = time.perf_counter()
            try:
                value = self._ticker.info
            except Exception as exc:
                recorder.add(
                    app=app_name,
                    operation="Ticker.info",
                    symbol=self.symbol,
                    elapsed_seconds=time.perf_counter() - started,
                    error=type(exc).__name__,
                )
                raise
            recorder.add(app=app_name, operation="Ticker.info", symbol=self.symbol, elapsed_seconds=time.perf_counter() - started)
            return value

        def __getattr__(self, name: str) -> Any:
            return getattr(self._ticker, name)

    yf.download = timed_download
    yf.Ticker = TimedTicker
    try:
        yield
    finally:
        yf.download = original_download
        yf.Ticker = original_ticker


class FakeSessionState(dict):
    """Enough Streamlit session_state behavior for loading Adam's functions."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


class FakeStreamlit(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("streamlit")
        self.secrets: dict[str, str] = {}
        self.session_state = FakeSessionState()
        self.query_params: dict[str, str] = {}

    def cache_data(self, *args: Any, **kwargs: Any) -> Callable[..., Any]:
        del args, kwargs

        def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
            return func

        return decorate

    def set_page_config(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    def markdown(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs


def load_adam_namespace(adam_path: Path) -> dict[str, Any]:
    """Execute Adam's function definitions without running the Streamlit UI."""
    source = (adam_path / "trading_app.py").read_text(encoding="utf-8")
    marker = "# Auto-refresh every 60 seconds when data is loaded"
    pre_ui_source = source.split(marker, 1)[0]
    fake_st = FakeStreamlit()
    original_streamlit = sys.modules.get("streamlit")
    sys.modules["streamlit"] = fake_st
    namespace: dict[str, Any] = {"__file__": str(adam_path / "trading_app.py"), "__name__": "adam_trading_app_benchmark"}
    try:
        exec(compile(pre_ui_source, str(adam_path / "trading_app.py"), "exec"), namespace)
    finally:
        if original_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = original_streamlit
    return namespace


def count_tags(html: str) -> dict[str, int]:
    parser = TagCounter()
    parser.feed(html)
    return parser.tags


def count_adam_level_rows(data: dict[str, Any]) -> int:
    """Count rows Adam's levels table would render for one ticker."""
    fields = [
        "monthly_h",
        "monthly_l",
        "sma_200",
        "sma_50",
        "ema_20_daily",
        "r2",
        "r1",
        "pivot",
        "s1",
        "s2",
        "fib_618",
        "fib_500",
        "fib_382",
        "prev_h",
        "prev_l",
        "prev_c",
        "today_vwap",
        "vwap",
        "ema_9_5m",
        "ema_20_5m",
        "pm_high",
        "pm_low",
        "f5_high",
        "f5_low",
        "earn_open",
        "earn_prev_close",
    ]
    total = sum(1 for field in fields if data.get(field))
    total += len(data.get("swing_highs") or [])
    total += len(data.get("swing_lows") or [])
    return total


def summarize_times(values: list[float]) -> dict[str, float]:
    if not values:
        return {"total": 0.0, "avg": 0.0, "min": 0.0, "max": 0.0}
    return {
        "total": round(sum(values), 3),
        "avg": round(statistics.mean(values), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def benchmark_mine(tickers: tuple[str, ...], recorder: QueryRecorder) -> dict[str, Any]:
    provider = YFinanceProvider()
    market_data = MarketDataService(provider=provider)
    scanner = ScannerService(market_data)
    batches = ticker_batches(tickers, batch_size=STREAMLIT_REPORT_BATCH_SIZE)
    report_metrics: list[EquityMetrics] = []
    scanner_responses: list[ScannerResponse] = []
    batch_results: list[dict[str, Any]] = []
    started = time.perf_counter()
    first_levels_seconds: float | None = None
    first_scanner_seconds: float | None = None

    with timed_yfinance("mine", recorder):
        for index, batch in enumerate(batches, start=1):
            batch_started = time.perf_counter()
            levels_started = time.perf_counter()
            metrics = market_data.build_metrics(list(batch), list(DEFAULT_METRICS), include_earnings=False)
            levels_seconds = time.perf_counter() - levels_started
            report_metrics.extend(metrics)
            if first_levels_seconds is None:
                first_levels_seconds = time.perf_counter() - started

            render_started = time.perf_counter()
            level_tags: dict[str, int] = {}
            level_rows = 0
            for metric in metrics:
                html = metric_card_html(metric, "price_ladder")
                tags = count_tags(html)
                for tag, count in tags.items():
                    level_tags[tag] = level_tags.get(tag, 0) + count
                level_rows += tags.get("tr", 0)
            level_render_seconds = time.perf_counter() - render_started

            scanner_started = time.perf_counter()
            scanner_response = scanner.build_scanner(
                list(batch),
                include_setup=True,
                include_patterns=True,
                include_earnings=False,
            )
            scanner_seconds = time.perf_counter() - scanner_started
            scanner_responses.append(scanner_response)
            if first_scanner_seconds is None:
                first_scanner_seconds = time.perf_counter() - started

            batch_results.append(
                {
                    "index": index,
                    "tickers": list(batch),
                    "levels_seconds": round(levels_seconds, 3),
                    "scanner_seconds": round(scanner_seconds, 3),
                    "levels_render_seconds": round(level_render_seconds, 4),
                    "batch_seconds": round(time.perf_counter() - batch_started, 3),
                    "level_rows": level_rows,
                    "level_tags": level_tags,
                    "scanner_rows": len(scanner_response.setup_rows),
                    "pattern_summary_rows": len(scanner_response.pattern_summary),
                    "pattern_detail_rows": len(scanner_response.pattern_details),
                }
            )

        final_scanner = ScannerService.merge_responses(tickers, scanner_responses)
        earnings_started = time.perf_counter()
        metrics_by_ticker = {metric.ticker: metric for metric in report_metrics}
        for batch in batches:
            batch_metrics = [
                metrics_by_ticker[ticker]
                for ticker in batch
                if ticker in metrics_by_ticker
            ]
            completed_metrics = market_data.complete_metrics_earnings(batch_metrics)
            metrics_by_ticker.update({metric.ticker: metric for metric in completed_metrics})
            scanner_update = scanner.build_scanner(
                list(batch),
                include_setup=True,
                include_patterns=False,
                include_earnings=True,
            )
            final_scanner = ScannerService.replace_setup_rows(tickers, final_scanner, [scanner_update])
        report_metrics = [
            metrics_by_ticker[ticker]
            for ticker in tickers
            if ticker in metrics_by_ticker
        ]
        earnings_completion_seconds = time.perf_counter() - earnings_started

        chart_started = time.perf_counter()
        charts = market_data.build_chart_history(list(tickers), MINE_CHART_RANGE, MINE_CHART_INTERVAL)
        chart_seconds = time.perf_counter() - chart_started

    total_seconds = time.perf_counter() - started
    per_ticker = [
        {
            "ticker": metric.ticker,
            "warning_count": len(metric.warnings),
            "level_rows": count_tags(metric_card_html(metric, "price_ladder")).get("tr", 0),
        }
        for metric in report_metrics
    ]
    return {
        "app": "mine",
        "tickers": list(tickers),
        "ticker_count": len(tickers),
        "batch_size": STREAMLIT_REPORT_BATCH_SIZE,
        "batches": batch_results,
        "first_levels_visible_seconds": round(first_levels_seconds or 0.0, 3),
        "first_scanner_visible_seconds": round(first_scanner_seconds or 0.0, 3),
        "final_levels_and_scanner_seconds": round(total_seconds - chart_seconds, 3),
        "earnings_completion_seconds": round(earnings_completion_seconds, 3),
        "chart_query_seconds": round(chart_seconds, 3),
        "end_to_end_with_charts_seconds": round(total_seconds, 3),
        "per_ticker": per_ticker,
        "rendered_view_elements": {
            "level_cards": len(report_metrics),
            "level_rows": sum(row["level_rows"] for row in per_ticker),
            "scanner_rows": len(final_scanner.setup_rows),
            "pattern_summary_rows": len(final_scanner.pattern_summary),
            "pattern_heatmap_rows": len(final_scanner.pattern_heatmap),
            "pattern_detail_rows": len(final_scanner.pattern_details),
            "chart_cards": len(charts.charts),
        },
        "query_summary": recorder.summarize("mine"),
        "earnings_cache_stats": provider.earnings_cache_stats(),
    }


def benchmark_adam(tickers: tuple[str, ...], adam_path: Path, recorder: QueryRecorder) -> dict[str, Any]:
    namespace = load_adam_namespace(adam_path)
    load_ticker_data: Callable[[str], dict[str, Any]] = namespace["load_ticker_data"]
    started = time.perf_counter()
    per_ticker: list[dict[str, Any]] = []
    loaded: dict[str, dict[str, Any]] = {}
    render_seconds: list[float] = []

    with timed_yfinance("adam", recorder):
        for ticker in tickers:
            ticker_started = time.perf_counter()
            data = load_ticker_data(ticker)
            load_seconds = time.perf_counter() - ticker_started
            loaded[ticker] = data
            render_started = time.perf_counter()
            level_rows = count_adam_level_rows(data)
            render_seconds.append(time.perf_counter() - render_started)
            per_ticker.append(
                {
                    "ticker": ticker,
                    "load_seconds": round(load_seconds, 3),
                    "level_rows": level_rows,
                    "has_setup": bool(data.get("setup")),
                    "has_support_resistance": bool(data.get("sr")),
                }
            )

    data_seconds = time.perf_counter() - started
    artificial_sleep_seconds = ADAM_UI_SLEEP_PER_TICKER_SECONDS * len(tickers)
    setup_rows = len(loaded)
    return {
        "app": "adam",
        "tickers": list(tickers),
        "ticker_count": len(tickers),
        "data_load_seconds": round(data_seconds, 3),
        "as_app_ux_sleep_seconds": round(artificial_sleep_seconds, 3),
        "estimated_as_app_levels_and_scanner_seconds": round(data_seconds + artificial_sleep_seconds, 3),
        "first_levels_visible_seconds": round(data_seconds + artificial_sleep_seconds, 3),
        "first_scanner_visible_seconds": round(data_seconds + artificial_sleep_seconds, 3),
        "per_ticker": per_ticker,
        "per_ticker_load_summary": summarize_times([row["load_seconds"] for row in per_ticker]),
        "rendered_view_elements": {
            "level_cards": len(loaded),
            "level_rows": sum(row["level_rows"] for row in per_ticker),
            "scanner_rows": setup_rows,
            "pattern_summary_rows": 0,
            "pattern_heatmap_rows": 0,
            "pattern_detail_rows": 0,
            "chart_cards": 0,
        },
        "logical_render_seconds": round(sum(render_seconds), 6),
        "query_summary": recorder.summarize("adam"),
    }


def build_report(result: dict[str, Any]) -> str:
    mine = result["mine"]
    adam = result["adam"]
    speedup_final = adam["estimated_as_app_levels_and_scanner_seconds"] / mine["final_levels_and_scanner_seconds"]
    speedup_first_levels = adam["first_levels_visible_seconds"] / mine["first_levels_visible_seconds"]
    speedup_first_scanner = adam["first_scanner_visible_seconds"] / mine["first_scanner_visible_seconds"]
    mine_query_seconds = mine["query_summary"]["total_seconds"]
    adam_query_seconds = adam["query_summary"]["total_seconds"]
    query_ratio = max(mine_query_seconds, adam_query_seconds) / max(min(mine_query_seconds, adam_query_seconds), 0.001)
    query_delta = f"{query_ratio:.1f}x lower in this app" if mine_query_seconds <= adam_query_seconds else f"{query_ratio:.1f}x higher in this app"
    lines = [
        "# Streamlit Speed Comparison",
        "",
        f"Generated: {result['generated_at']}",
        f"Tickers: {', '.join(result['tickers'])}",
        "",
        "## Summary",
        "",
        "| Metric | This app | Adam app | Delta |",
        "| --- | ---: | ---: | ---: |",
        f"| First Levels visible | {mine['first_levels_visible_seconds']:.3f}s | {adam['first_levels_visible_seconds']:.3f}s | {speedup_first_levels:.1f}x faster |",
        f"| First Scanner visible | {mine['first_scanner_visible_seconds']:.3f}s | {adam['first_scanner_visible_seconds']:.3f}s | {speedup_first_scanner:.1f}x faster |",
        f"| Final Levels + Scanner | {mine['final_levels_and_scanner_seconds']:.3f}s | {adam['estimated_as_app_levels_and_scanner_seconds']:.3f}s | {speedup_final:.1f}x faster |",
        f"| Earnings completion pass | {mine['earnings_completion_seconds']:.3f}s | n/a | final-only in this app |",
        f"| yfinance query wall time | {mine_query_seconds:.3f}s | {adam_query_seconds:.3f}s | {query_delta} |",
        f"| yfinance call count | {mine['query_summary']['count']} | {adam['query_summary']['count']} | {adam['query_summary']['count'] - mine['query_summary']['count']:+d} calls |",
        "",
        "Adam's UI loop intentionally sleeps 1.5s after each ticker load. The Adam UX time above includes that 18.0s wait for 12 tickers; raw Adam data load time is "
        f"{adam['data_load_seconds']:.3f}s.",
        "",
        "## Rendered View Elements",
        "",
        "| Element | This app | Adam app |",
        "| --- | ---: | ---: |",
    ]
    for key in sorted(mine["rendered_view_elements"]):
        lines.append(f"| {key} | {mine['rendered_view_elements'][key]} | {adam['rendered_view_elements'][key]} |")
    lines.extend(
        [
            "",
            "## Per-Ticker Data Load",
            "",
            "| Ticker | This app level rows | This app warnings | Adam load seconds | Adam level rows |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    mine_by_ticker = {row["ticker"]: row for row in mine["per_ticker"]}
    for row in adam["per_ticker"]:
        mine_row = mine_by_ticker.get(row["ticker"], {})
        lines.append(
            f"| {row['ticker']} | {mine_row.get('level_rows', 0)} | {mine_row.get('warning_count', 0)} | "
            f"{row['load_seconds']:.3f} | {row['level_rows']} |"
        )
    lines.extend(
        [
            "",
            "## This App Batches",
            "",
            "| Batch | Tickers | Levels seconds | Scanner seconds | Batch seconds | Scanner rows | Pattern detail rows |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for batch in mine["batches"]:
        lines.append(
            f"| {batch['index']} | {', '.join(batch['tickers'])} | {batch['levels_seconds']:.3f} | "
            f"{batch['scanner_seconds']:.3f} | {batch['batch_seconds']:.3f} | {batch['scanner_rows']} | "
            f"{batch['pattern_detail_rows']} |"
        )
    lines.extend(
        [
            "",
            "## yfinance Query Summary",
            "",
            "This app batches provider downloads through `yf.download` and reuses the provider cache across levels/scanner batches. Adam loads each ticker with repeated `yf.Ticker(...).history(...)` calls.",
            "",
            "### This App",
            "",
            "```json",
            json.dumps(mine["query_summary"], indent=2),
            "```",
            "",
            "### Adam App",
            "",
            "```json",
            json.dumps(adam["query_summary"], indent=2),
            "```",
            "",
            "### This App Earnings Cache",
            "",
            "```json",
            json.dumps(mine.get("earnings_cache_stats", {}), indent=2),
            "```",
            "",
            "## Notes",
            "",
            "- This is a direct service/function benchmark, not a networked browser benchmark. It avoids mutating the live Streamlit watchlists and cleanly separates provider query time from rendered element counts.",
            "- This app's Streamlit UI now progressively renders Levels and Scanner by 3-ticker batch; Adam's app renders after the full sequential ticker loop completes.",
            "- Free yfinance responses vary by time, cache state, and rate limits. Treat this as a reproducible local snapshot rather than a permanent SLA.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adam-path", type=Path, default=DEFAULT_ADAM_PATH)
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()

    tickers = tuple(ticker.strip().upper() for ticker in args.tickers.replace(",", " ").split() if ticker.strip())
    recorder = QueryRecorder()
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tickers": list(tickers),
        "mine": benchmark_mine(tickers, recorder),
        "adam": benchmark_adam(tickers, args.adam_path, recorder),
    }
    markdown = build_report(result)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
