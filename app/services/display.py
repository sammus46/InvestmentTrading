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
    DisplayRow,
    DisplaySection,
    EquityMetrics,
    MetricDefinition,
    MetricName,
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


def metric_catalog() -> list[MetricDefinition]:
    """Return metric metadata in display order."""
    return [metric.model_copy() for metric in METRIC_CATALOG]


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
    )


def build_metric_display_sections(metric: EquityMetrics) -> list[DisplaySection]:
    """Build formatted report sections from raw metric fields."""
    selected = set(metric.selected_metrics)
    sections: list[DisplaySection] = []

    session_rows: list[DisplayRow] = []
    if "previous_day" in selected:
        session_rows.extend(
            [
                _row("Prev Open", metric.previous_day.open),
                _row("Prev High", metric.previous_day.high),
                _row("Prev Low", metric.previous_day.low),
                _row("Prev Close", metric.previous_day.close),
            ]
        )
    if "premarket" in selected:
        session_rows.extend(
            [
                _row("Premarket High", metric.premarket.high),
                _row("Premarket Low", metric.premarket.low),
            ]
        )
    if "first_five_minutes" in selected:
        session_rows.extend(
            [
                _row("First 5m High", metric.first_five_minutes.high),
                _row("First 5m Low", metric.first_five_minutes.low),
            ]
        )
    if session_rows:
        sections.append(DisplaySection(title="Session Levels", rows=session_rows))

    level_rows: list[DisplayRow] = []
    level_lists: list[DisplayRow] = []
    if "previous_session_vwap_5m" in selected:
        level_rows.append(_row("VWAP 5m", metric.previous_session_vwap_5m))
    if "fifty_two_week" in selected:
        level_rows.extend(
            [
                _row("52W High", metric.fifty_two_week.high),
                _row("52W Low", metric.fifty_two_week.low),
            ]
        )
    if "swing_levels" in selected:
        level_lists.extend(
            [
                _list("Swing Highs", metric.swing_levels.highs),
                _list("Swing Lows", metric.swing_levels.lows),
            ]
        )
    if level_rows or level_lists:
        sections.append(DisplaySection(title="Range & Levels", rows=level_rows, lists=level_lists))

    technical_rows: list[DisplayRow] = []
    if "technical_levels" in selected:
        tech = metric.technical_levels
        technical_rows.extend(
            [
                _row("Current Price", tech.current_price),
                _row("VWAP Today", tech.today_vwap),
                _row("1M High", tech.one_month_high),
                _row("1M Low", tech.one_month_low),
                _row("50 SMA", tech.sma_50),
                _row("200 SMA", tech.sma_200),
                _row("20 EMA Daily", tech.ema_20_daily),
                _row("9 EMA 5m", tech.ema_9_5m),
                _row("20 EMA 5m", tech.ema_20_5m),
                _row("Pivot", tech.pivot),
                _row("R1", tech.r1),
                _row("S1", tech.s1),
                _row("R2", tech.r2),
                _row("S2", tech.s2),
                _row("Fib 61.8%", tech.fib_618),
                _row("Fib 50.0%", tech.fib_500),
                _row("Fib 38.2%", tech.fib_382),
                _row("Earnings Open", tech.earnings_open),
                _row("Pre-Earnings Close", tech.pre_earnings_close),
            ]
        )
    if technical_rows:
        sections.append(DisplaySection(title="Technical Levels", rows=technical_rows))

    indicator_rows: list[DisplayRow] = []
    if "bollinger_bands" in selected:
        indicator_rows.extend(
            [
                _row("BB Upper", metric.bollinger_bands.upper),
                _row("BB Middle", metric.bollinger_bands.middle),
                _row("BB Lower", metric.bollinger_bands.lower),
            ]
        )
    if "earnings_gap" in selected:
        indicator_rows.extend(
            [
                _row("Earnings Date", metric.earnings_gap.date),
                _row("Earnings Gap", metric.earnings_gap.gap),
                _row("Earnings Gap %", metric.earnings_gap.gap_percent),
            ]
        )
    if indicator_rows:
        sections.append(DisplaySection(title="Indicators & Events", rows=indicator_rows))

    return sections


def metric_definitions_match_defaults() -> bool:
    """Return whether catalog defaults cover the request default metrics."""
    catalog_defaults = tuple(metric.id for metric in METRIC_CATALOG if metric.default)
    return set(catalog_defaults) == set(DEFAULT_METRICS)


def _row(label: str, value: Any) -> DisplayRow:
    return DisplayRow(label=label, value=_fmt(value))


def _list(label: str, values: list[float]) -> DisplayRow:
    return DisplayRow(label=label, values=[_fmt(value) for value in values])


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)
