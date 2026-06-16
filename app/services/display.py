"""Shared report display metadata and formatting helpers."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Literal, Mapping

from app.models import (
    DEFAULT_METRICS,
    CHART_DEFAULT_INTERVAL_BY_RANGE,
    CHART_INTERVALS_BY_RANGE,
    AppConfigResponse,
    ChartRangeConfig,
    DisplayRowEmphasis,
    DisplayRowKind,
    DisplayRow,
    DisplaySection,
    EquityMetrics,
    MetricDefinition,
    MetricName,
    ReportLayoutDefinition,
    ReportLayoutName,
)

METRIC_CATALOG: tuple[MetricDefinition, ...] = (
    MetricDefinition(id="previous_day", label="Previous day OHLC", group="Session", order=0),
    MetricDefinition(id="premarket", label="Premarket range", group="Session", order=1),
    MetricDefinition(id="first_five_minutes", label="Opening range", group="Session", order=2),
    MetricDefinition(id="previous_session_vwap_5m", label="Previous session VWAP", group="Trend", order=3),
    MetricDefinition(id="fifty_two_week", label="52-week range", group="Levels", order=4),
    MetricDefinition(id="swing_levels", label="Swing highs/lows", group="Levels", order=5),
    MetricDefinition(id="bollinger_bands", label="Bollinger Bands", group="Indicators", order=6),
    MetricDefinition(id="technical_levels", label="Technical levels", group="Indicators", order=7),
    MetricDefinition(id="earnings_gap", label="Earnings gap", group="Events", order=8),
)

REPORT_LAYOUT_CATALOG: tuple[ReportLayoutDefinition, ...] = (
    ReportLayoutDefinition(
        id="grid",
        label="Grid",
        description="Grouped cards with sectioned metrics.",
        order=0,
    ),
    ReportLayoutDefinition(
        id="price_ladder",
        label="Price Ladder",
        description="Adam-style price-sorted levels around current price.",
        order=1,
        default=True,
    ),
    ReportLayoutDefinition(
        id="compact",
        label="Compact",
        description="Dense ticker cards for quick scanning.",
        order=2,
    ),
    ReportLayoutDefinition(
        id="compare",
        label="Compare",
        description="Cross-ticker table using the same report rows.",
        order=3,
    ),
)

DEFAULT_REPORT_LAYOUT: ReportLayoutName = "price_ladder"
LevelFilterName = Literal["all", "scanner", "weight_20"]
DEFAULT_LEVEL_FILTER: LevelFilterName = "all"
LEVEL_FILTER_LABELS: dict[LevelFilterName, str] = {
    "all": "All Levels",
    "scanner": "Scanner Levels Only",
    "weight_20": "Weight 20+ Only",
}
LEVEL_FILTER_OPTIONS: tuple[LevelFilterName, ...] = tuple(LEVEL_FILTER_LABELS.keys())

LEVEL_TYPE_WEIGHTS_PATH = Path(__file__).with_name("level_type_weights.json")
LEVEL_TYPE_WEIGHT_ALIASES = {
    "VWAP Today": "VWAP (Today)",
    "Today VWAP": "VWAP (Today)",
    "Premarket High": "PM High",
    "Premarket Low": "PM Low",
    "First 5m High": "5-Min High",
    "First 5m Low": "5-Min Low",
    "1M High": "1-Month High",
    "1M Low": "1-Month Low",
    "VWAP 5m": "VWAP (Prev Session)",
    "200 SMA": "200 SMA (Daily)",
    "50 SMA": "50 SMA (Daily)",
    "9 EMA 5m": "9 EMA (5-Min)",
    "20 EMA Daily": "20 EMA (Daily)",
    "20 EMA 5m": "20 EMA (5-Min)",
    "R1": "R1 (Pivot)",
    "S1": "S1 (Pivot)",
    "R2": "R2 (Pivot)",
    "S2": "S2 (Pivot)",
    "Earnings Open": "Earnings Gap Open",
}

SCANNER_LEVEL_LABELS = {
    "VWAP (Today)",
    "VWAP Today",
    "Today VWAP",
    "VWAP (Prev Session)",
    "VWAP 5m",
    "PM High",
    "Premarket High",
    "PM Low",
    "Premarket Low",
    "Prev High",
    "Prev Low",
    "Prev Close",
    "5-Min High",
    "First 5m High",
    "5-Min Low",
    "First 5m Low",
    "1-Month High",
    "1M High",
    "1-Month Low",
    "1M Low",
    "200 SMA (Daily)",
    "200 SMA",
    "50 SMA (Daily)",
    "50 SMA",
    "Pivot",
    "R1 (Pivot)",
    "R1",
    "S1 (Pivot)",
    "S1",
}

PRIORITY_PRICE_LABELS = {
    "Prev High",
    "Prev Low",
    "Premarket High",
    "Premarket Low",
    "VWAP Today",
    "9 EMA 5m",
    "Pivot",
    "R1",
    "S1",
}


def normalize_level_filter(level_filter: object) -> LevelFilterName:
    """Return a supported Levels card filter."""
    candidate = str(level_filter or "")
    if candidate in LEVEL_FILTER_LABELS:
        return candidate  # type: ignore[return-value]
    return DEFAULT_LEVEL_FILTER


def level_filter_label(level_filter: object) -> str:
    """Return the visible label for a Levels card filter."""
    return LEVEL_FILTER_LABELS[normalize_level_filter(level_filter)]


def load_level_type_weights() -> dict[str, int]:
    """Load canonical Adam level type weights from the checked-in JSON file."""
    raw = json.loads(LEVEL_TYPE_WEIGHTS_PATH.read_text(encoding="utf-8"))
    return {str(label): int(weight) for label, weight in raw.items()}


LEVEL_TYPE_WEIGHTS = load_level_type_weights()
SWING_LEVEL_WEIGHT = 24


def level_type_weight(label: str, level_type_weights: Mapping[str, int] | None = None) -> int:
    """Return Adam-compatible trust weight for a display level label."""
    weights = {**LEVEL_TYPE_WEIGHTS, **(level_type_weights or {})}
    if label.startswith(("Daily Swing High", "Swing Highs")):
        return int(weights.get("Daily Swing High", SWING_LEVEL_WEIGHT))
    if label.startswith(("Daily Swing Low", "Swing Lows")):
        return int(weights.get("Daily Swing Low", SWING_LEVEL_WEIGHT))
    canonical_label = LEVEL_TYPE_WEIGHT_ALIASES.get(label, label)
    return int(weights.get(canonical_label, 5))


def is_scanner_level_label(label: str) -> bool:
    """Return whether a display level is part of scanner support/resistance inputs."""
    return label in SCANNER_LEVEL_LABELS or label.startswith(
        ("Daily Swing High", "Daily Swing Low", "Swing Highs", "Swing Lows")
    )


def level_matches_filter(
    label: str,
    level_filter: object,
    level_type_weights: Mapping[str, int] | None = None,
) -> bool:
    """Return whether a level label should be shown for the selected filter."""
    normalized = normalize_level_filter(level_filter)
    if normalized == "scanner":
        return is_scanner_level_label(label)
    if normalized == "weight_20":
        return level_type_weight(label, level_type_weights) >= 20
    return True


def metric_catalog() -> list[MetricDefinition]:
    """Return metric metadata in display order."""
    return [metric.model_copy() for metric in METRIC_CATALOG]


def report_layout_catalog() -> list[ReportLayoutDefinition]:
    """Return report layout metadata in display order."""
    return [layout.model_copy() for layout in REPORT_LAYOUT_CATALOG]


def level_type_weight_defaults() -> dict[str, int]:
    """Return browser-facing level type weight defaults, including implied swing levels."""
    return {
        **LEVEL_TYPE_WEIGHTS,
        "Daily Swing High": SWING_LEVEL_WEIGHT,
        "Daily Swing Low": SWING_LEVEL_WEIGHT,
    }


def app_config() -> AppConfigResponse:
    """Return browser-facing configuration from backend constants."""
    return AppConfigResponse(
        metrics=metric_catalog(),
        chart_ranges={
            chart_range: ChartRangeConfig(
                intervals=list(intervals),
                default_interval=CHART_DEFAULT_INTERVAL_BY_RANGE[chart_range],
            )
            for chart_range, intervals in CHART_INTERVALS_BY_RANGE.items()
        },
        report_layouts=report_layout_catalog(),
        default_report_layout=DEFAULT_REPORT_LAYOUT,
        level_type_weights=level_type_weight_defaults(),
    )


def build_metric_display_sections(metric: EquityMetrics) -> list[DisplaySection]:
    """Build formatted report sections from raw metric fields."""
    selected = set(metric.selected_metrics)
    sections: list[DisplaySection] = []

    session_rows: list[DisplayRow] = []
    if "previous_day" in selected:
        session_rows.extend(
            [
                _price_row("Prev Open", metric.previous_day.open),
                _price_row("Prev High", metric.previous_day.high),
                _price_row("Prev Low", metric.previous_day.low),
                _price_row("Prev Close", metric.previous_day.close),
            ]
        )
    if "premarket" in selected:
        session_rows.extend(
            [
                _price_row("Premarket High", metric.premarket.high),
                _price_row("Premarket Low", metric.premarket.low),
            ]
        )
    if "first_five_minutes" in selected:
        session_rows.extend(
            [
                _price_row("First 5m High", metric.first_five_minutes.high),
                _price_row("First 5m Low", metric.first_five_minutes.low),
            ]
        )
    if session_rows:
        sections.append(DisplaySection(title="Session Levels", rows=session_rows))

    level_rows: list[DisplayRow] = []
    level_lists: list[DisplayRow] = []
    if "previous_session_vwap_5m" in selected:
        level_rows.append(_price_row("VWAP 5m", metric.previous_session_vwap_5m))
    if "fifty_two_week" in selected:
        level_rows.extend(
            [
                _price_row("52W High", metric.fifty_two_week.high),
                _price_row("52W Low", metric.fifty_two_week.low),
            ]
        )
    if "swing_levels" in selected:
        level_lists.extend(
            [
                _price_list("Swing Highs", metric.swing_levels.highs),
                _price_list("Swing Lows", metric.swing_levels.lows),
            ]
        )
    if level_rows or level_lists:
        sections.append(DisplaySection(title="Range & Levels", rows=level_rows, lists=level_lists))

    technical_rows: list[DisplayRow] = []
    if "technical_levels" in selected:
        tech = metric.technical_levels
        technical_rows.extend(
            [
                _price_row("Current Price", tech.current_price, emphasis="current"),
                _price_row("VWAP Today", tech.today_vwap),
                _price_row("1M High", tech.one_month_high),
                _price_row("1M Low", tech.one_month_low),
                _price_row("50 SMA", tech.sma_50),
                _price_row("200 SMA", tech.sma_200),
                _price_row("20 EMA Daily", tech.ema_20_daily),
                _price_row("9 EMA 5m", tech.ema_9_5m),
                _price_row("20 EMA 5m", tech.ema_20_5m),
                _price_row("Pivot", tech.pivot),
                _price_row("R1", tech.r1),
                _price_row("S1", tech.s1),
                _price_row("R2", tech.r2),
                _price_row("S2", tech.s2),
                _price_row("Fib 61.8%", tech.fib_618),
                _price_row("Fib 50.0%", tech.fib_500),
                _price_row("Fib 38.2%", tech.fib_382),
                _price_row("Earnings Open", tech.earnings_open),
                _price_row("Pre-Earnings Close", tech.pre_earnings_close),
            ]
        )
    if technical_rows:
        sections.append(DisplaySection(title="Technical Levels", rows=technical_rows))

    indicator_rows: list[DisplayRow] = []
    if "bollinger_bands" in selected:
        indicator_rows.extend(
            [
                _price_row("BB Upper", metric.bollinger_bands.upper),
                _price_row("BB Middle", metric.bollinger_bands.middle),
                _price_row("BB Lower", metric.bollinger_bands.lower),
            ]
        )
    if "earnings_gap" in selected:
        indicator_rows.extend(
            [
                _row("Earnings Date", metric.earnings_gap.date, kind="date"),
                _row("Earnings Gap", metric.earnings_gap.gap),
                _row("Earnings Gap %", metric.earnings_gap.gap_percent, kind="percent"),
            ]
        )
    if indicator_rows:
        sections.append(DisplaySection(title="Indicators & Events", rows=indicator_rows))

    return sections


def metric_definitions_match_defaults() -> bool:
    """Return whether catalog defaults cover the request default metrics."""
    catalog_defaults = tuple(metric.id for metric in METRIC_CATALOG if metric.default)
    return set(catalog_defaults) == set(DEFAULT_METRICS)


def _price_row(
    label: str,
    value: float | None,
    *,
    emphasis: DisplayRowEmphasis | None = None,
) -> DisplayRow:
    row_emphasis = emphasis or ("priority" if label in PRIORITY_PRICE_LABELS else "normal")
    return _row(label, value, kind="price", numeric_value=_float_or_none(value), emphasis=row_emphasis)


def _row(
    label: str,
    value: Any,
    *,
    kind: DisplayRowKind = "text",
    numeric_value: float | None = None,
    emphasis: DisplayRowEmphasis = "normal",
) -> DisplayRow:
    if numeric_value is None and kind == "percent":
        numeric_value = _float_or_none(value)
    return DisplayRow(
        label=label,
        value=_fmt(value),
        kind=kind,
        numeric_value=numeric_value,
        emphasis=emphasis,
    )


def _price_list(label: str, values: list[float]) -> DisplayRow:
    return DisplayRow(
        label=label,
        values=[_fmt(value) for value in values],
        kind="price",
        numeric_values=[float(value) for value in values],
    )


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)
