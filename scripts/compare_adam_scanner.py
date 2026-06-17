"""Compare this app's scanner setup scoring with Adam's app.

This is a live audit helper. It fetches current market data from both code paths
and prints any raw-input or scanner-output differences without writing score
history or importing this app's Streamlit module.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import types
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.market_data import MarketDataService
from app.services.providers import YFinanceProvider
from app.services.scanner import ScannerService


DEFAULT_ADAM_PATH = Path("/Users/sam/Library/CloudStorage/Dropbox/Mac (3)/Documents/Coding projects/adam/trading-levels")

RAW_INPUT_FIELDS = (
    "price",
    "prev_h",
    "prev_l",
    "prev_c",
    "pm_high",
    "pm_low",
    "f5_high",
    "f5_low",
    "monthly_h",
    "monthly_l",
    "today_vwap",
    "vwap",
    "sma_50",
    "sma_200",
    "ema_20_daily",
    "ema_9_5m",
    "ema_20_5m",
    "pivot",
    "r1",
    "s1",
    "r2",
    "s2",
    "fib_382",
    "fib_500",
    "fib_618",
    "earn_open",
    "earn_prev_close",
    "stock_pct",
    "rs_vs_spy",
    "rs_vs_sector",
    "vwap_ext",
)

SETUP_FIELDS = (
    "nearest_name",
    "nearest_val",
    "nearest_pct",
    "consec",
    "hold_count",
    "level_held",
    "is_tight",
    "off_high_pct",
    "good_pullback",
    "momentum",
    "score",
)

SUPPORT_RESISTANCE_FIELDS = (
    "support_zone",
    "support_score",
    "support_reason",
    "resistance_zone",
    "resistance_score",
    "resistance_reason",
    "rr",
)


class FakeSessionState(dict):
    """Enough session_state behavior for loading Adam's function definitions."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


class FakeStreamlit(types.ModuleType):
    """Tiny Streamlit shim used only while executing Adam's pre-UI code."""

    def __init__(self) -> None:
        super().__init__("streamlit")
        self.secrets: dict[str, str] = {}
        self.session_state = FakeSessionState()
        self.query_params: dict[str, str] = {}

    def cache_data(self, func: Callable[..., Any] | None = None, *args: Any, **kwargs: Any) -> Callable[..., Any]:
        del args, kwargs
        if callable(func):
            return func

        def decorate(wrapped: Callable[..., Any]) -> Callable[..., Any]:
            return wrapped

        return decorate

    def set_page_config(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    def markdown(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs


def load_adam_namespace(adam_path: Path) -> dict[str, Any]:
    """Execute Adam's definitions up to the UI loop and return the namespace."""
    source_path = adam_path / "trading_app.py"
    source = source_path.read_text(encoding="utf-8")
    marker = "# Auto-refresh every 60 seconds when data is loaded"
    pre_ui_source = source.split(marker, 1)[0]
    fake_st = FakeStreamlit()
    original_streamlit = sys.modules.get("streamlit")
    sys.modules["streamlit"] = fake_st
    namespace: dict[str, Any] = {"__file__": str(source_path), "__name__": "adam_scanner_compare"}
    try:
        exec(compile(pre_ui_source, str(source_path), "exec"), namespace)
    finally:
        if original_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = original_streamlit
    return namespace


def number_or_none(value: object) -> float | None:
    """Return a finite float for numeric-ish values."""
    try:
        if value is None or isinstance(value, bool) or type(value).__name__ in {"bool", "bool_"}:
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalized_text(value: object) -> str | None:
    """Normalize cosmetic UI text so semantic scanner values compare cleanly."""
    if value is None:
        return None
    text = str(value).replace("\u2013", "-").replace("\u2014", "-")
    text = text.encode("ascii", "ignore").decode("ascii").strip()
    text = " ".join(text.split())
    if text in {"", "-", "None"}:
        return None
    return text


def normalized_value(field: str, value: object) -> object:
    """Normalize field values before comparison and JSON output."""
    number = number_or_none(value)
    if number is not None:
        return round(number, 4)
    text = normalized_text(value)
    if field == "momentum" and text:
        return text.replace("Turning Up", "Turning Up").replace("Ticking Up", "Ticking Up")
    return text


def values_match(field: str, adam_value: object, mine_value: object, tolerance: float) -> bool:
    """Return whether two values are equivalent for audit purposes."""
    adam_number = number_or_none(adam_value)
    mine_number = number_or_none(mine_value)
    if adam_number is not None or mine_number is not None:
        return adam_number is not None and mine_number is not None and abs(adam_number - mine_number) <= tolerance
    return normalized_value(field, adam_value) == normalized_value(field, mine_value)


def differences(
    fields: tuple[str, ...],
    adam_values: dict[str, Any],
    mine_values: dict[str, Any],
    *,
    tolerance: float,
) -> list[dict[str, Any]]:
    """Return normalized differences for the requested fields."""
    found: list[dict[str, Any]] = []
    for field in fields:
        adam_value = adam_values.get(field)
        mine_value = mine_values.get(field)
        if values_match(field, adam_value, mine_value, tolerance):
            continue
        found.append(
            {
                "field": field,
                "adam": normalized_value(field, adam_value),
                "mine": normalized_value(field, mine_value),
            }
        )
    return found


def signal_values(adam_data: dict[str, Any], mine_data: dict[str, Any]) -> tuple[object, object]:
    """Return normalized signal values from the two app shapes."""
    return adam_data.get("signal_text"), mine_data.get("signal")


def compare_ticker(symbol: str, adam_data: dict[str, Any], mine_data: dict[str, Any]) -> dict[str, Any]:
    """Compare one ticker's raw inputs and scanner outputs."""
    adam_setup = adam_data.get("setup") if isinstance(adam_data.get("setup"), dict) else {}
    mine_setup = mine_data.get("setup") if isinstance(mine_data.get("setup"), dict) else {}
    adam_sr = adam_data.get("sr") if isinstance(adam_data.get("sr"), dict) else {}
    mine_sr = mine_data.get("sr") if isinstance(mine_data.get("sr"), dict) else {}
    adam_signal, mine_signal = signal_values(adam_data, mine_data)
    signal_diff = []
    if not values_match("signal", adam_signal, mine_signal, 0.01):
        signal_diff.append(
            {
                "field": "signal",
                "adam": normalized_value("signal", adam_signal),
                "mine": normalized_value("signal", mine_signal),
            }
        )

    return {
        "ticker": symbol,
        "setup_score_match": values_match("score", adam_setup.get("score"), mine_setup.get("score"), 0.01),
        "adam_setup_score": normalized_value("score", adam_setup.get("score")),
        "mine_setup_score": normalized_value("score", mine_setup.get("score")),
        "raw_input_differences": differences(RAW_INPUT_FIELDS, adam_data, mine_data, tolerance=0.02),
        "setup_differences": differences(SETUP_FIELDS, adam_setup, mine_setup, tolerance=0.02),
        "signal_differences": signal_diff,
        "support_resistance_differences": differences(
            SUPPORT_RESISTANCE_FIELDS,
            adam_sr,
            mine_sr,
            tolerance=0.02,
        ),
    }


def compare_tickers(tickers: list[str], adam_path: Path) -> list[dict[str, Any]]:
    """Load both app paths and compare scanner outputs for tickers."""
    namespace = load_adam_namespace(adam_path)
    load_ticker_data: Callable[[str], dict[str, Any]] = namespace["load_ticker_data"]
    market_data = MarketDataService(provider=YFinanceProvider())
    scanner = ScannerService(market_data)
    market_data.prefetch_scanner_downloads(tickers, include_setup=True, include_patterns=False)
    benchmark_cache: dict[str, float | None] = {}
    results: list[dict[str, Any]] = []
    for symbol in tickers:
        adam_data = load_ticker_data(symbol)
        mine_scan = scanner._load_ticker_data(symbol, benchmark_cache, include_earnings=True)
        results.append(compare_ticker(symbol, adam_data, mine_scan.data))
    return results


def print_report(results: list[dict[str, Any]], *, verbose: bool) -> None:
    """Print a compact human-readable comparison report."""
    for result in results:
        status = "MATCH" if result["setup_score_match"] and not result["setup_differences"] else "DIFF"
        print(
            f"{result['ticker']}: {status} setup "
            f"adam={result['adam_setup_score']} mine={result['mine_setup_score']}"
        )
        groups = (
            ("setup", result["setup_differences"]),
            ("signal", result["signal_differences"]),
            ("support/resistance", result["support_resistance_differences"]),
            ("raw inputs", result["raw_input_differences"]),
        )
        for label, items in groups:
            if not items:
                continue
            print(f"  {label}: {len(items)} difference(s)")
            if verbose or label == "setup":
                for item in items:
                    print(f"    {item['field']}: Adam={item['adam']!r} Mine={item['mine']!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", nargs="*", default=["YSS"], help="Ticker symbols to compare.")
    parser.add_argument("--adam-path", type=Path, default=DEFAULT_ADAM_PATH, help="Path to Adam's trading-levels repo.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of a text report.")
    parser.add_argument("--verbose", action="store_true", help="Print every non-setup difference field.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tickers = [ticker.upper().strip() for ticker in args.tickers if ticker.strip()]
    results = compare_tickers(tickers, args.adam_path)
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_report(results, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
