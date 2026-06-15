"""Shared report display metadata and formatting helpers."""

from __future__ import annotations

from datetime import date
from typing import Any

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
        default=True,
    ),
    ReportLayoutDefinition(
        id="price_ladder",
        label="Price Ladder",
        description="Adam-style price-sorted levels around current price.",
        order=1,
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

DEFAULT_REPORT_LAYOUT: ReportLayoutName = "grid"

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


def metric_catalog() -> list[MetricDefinition]:
    """Return metric metadata in display order."""
    return [metric.model_copy() for metric in METRIC_CATALOG]


def report_layout_catalog() -> list[ReportLayoutDefinition]:
    """Return report layout metadata in display order."""
    return [layout.model_copy() for layout in REPORT_LAYOUT_CATALOG]


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
