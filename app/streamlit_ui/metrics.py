"""Streamlit rendering helpers for generated level metrics."""

from __future__ import annotations

from collections.abc import Mapping
from html import escape

import streamlit as st

from app.models import DisplayRow, EquityMetrics, ReportLayoutName
from app.services.display import (
    DEFAULT_LEVEL_FILTER,
    DEFAULT_REPORT_LAYOUT,
    LevelFilterName,
    build_metric_display_sections,
    level_matches_filter,
    level_type_weight,
    normalize_level_filter,
)


def metric_rows(metric: EquityMetrics) -> list[dict[str, str]]:
    """Flatten selected metrics into table rows."""
    return [{"Metric": str(row["label"]), "Value": str(row["value"])} for row in flatten_display_rows(metric)]


def metric_sections(metric: EquityMetrics):
    """Group selected metrics into card sections that mirror the static app."""
    return metric.display_sections or build_metric_display_sections(metric)


def metric_card_html(
    metric: EquityMetrics,
    layout: ReportLayoutName = DEFAULT_REPORT_LAYOUT,
    index: int = 0,
    total_count: int = 1,
    level_filter: LevelFilterName = DEFAULT_LEVEL_FILTER,
    level_type_weights: Mapping[str, int] | None = None,
) -> str:
    """Return one ticker card for the selected report layout."""
    if layout == "price_ladder":
        return price_ladder_card_html(metric, index, total_count, level_filter, level_type_weights)
    if layout == "compact":
        return compact_card_html(metric, index, total_count, level_filter, level_type_weights)
    return grid_card_html(metric, index, total_count, level_filter, level_type_weights)


def render_metric_card(
    metric: EquityMetrics,
    layout: ReportLayoutName = DEFAULT_REPORT_LAYOUT,
    level_filter: LevelFilterName = DEFAULT_LEVEL_FILTER,
    level_type_weights: Mapping[str, int] | None = None,
) -> None:
    """Render one ticker report card."""
    st.markdown(
        metric_card_html(metric, layout, level_filter=level_filter, level_type_weights=level_type_weights),
        unsafe_allow_html=True,
    )


def render_metric_grid(
    metrics: list[EquityMetrics],
    layout: ReportLayoutName = DEFAULT_REPORT_LAYOUT,
    level_filter: LevelFilterName = DEFAULT_LEVEL_FILTER,
    level_type_weights: Mapping[str, int] | None = None,
) -> None:
    """Render ticker report metrics in the selected layout."""
    if layout == "compare":
        st.markdown(compare_table_html(metrics, level_filter, level_type_weights), unsafe_allow_html=True)
        return
    cards = "".join(
        metric_card_html(metric, layout, index, len(metrics), level_filter, level_type_weights)
        for index, metric in enumerate(metrics)
    )
    class_name = layout.replace("_", "-")
    st.markdown(f'<div class="streamlit-report-grid streamlit-report-layout-{class_name}">{cards}</div>', unsafe_allow_html=True)


def render_metric(
    metric: EquityMetrics,
    layout: ReportLayoutName = DEFAULT_REPORT_LAYOUT,
    level_filter: LevelFilterName = DEFAULT_LEVEL_FILTER,
    level_type_weights: Mapping[str, int] | None = None,
) -> None:
    """Render one ticker report section."""
    render_metric_card(metric, layout, level_filter, level_type_weights)
    if metric.warnings:
        with st.expander(f"{len(metric.warnings)} data warning(s)"):
            for warning in metric.warnings:
                st.warning(warning)


def grid_card_html(
    metric: EquityMetrics,
    index: int = 0,
    total_count: int = 1,
    level_filter: LevelFilterName = DEFAULT_LEVEL_FILTER,
    level_type_weights: Mapping[str, int] | None = None,
) -> str:
    """Return the current grouped-card report view."""
    normalized_filter = normalize_level_filter(level_filter)
    section_html = []
    for section in metric_sections(metric):
        rows = [
            row for row in section.rows
            if row.emphasis == "current" or level_matches_filter(row.label, normalized_filter, level_type_weights)
        ]
        lists = [filter_display_list(row, normalized_filter, level_type_weights) for row in section.lists]
        lists = [row for row in lists if row.values]
        if not rows and not lists:
            continue
        cells = "".join(
            (
                '<div class="metric-cell">'
                f'<span class="metric-label">{escape(row.label)}</span>'
                f'<span class="metric-value">{escape(row.value or "-")}</span>'
                "</div>"
            )
            for row in rows
        )
        cells += "".join(
            (
                '<div class="metric-cell">'
                f'<span class="metric-label">{escape(row.label)}</span>'
                f'<span class="metric-value">{escape(", ".join(row.values) or "-")}</span>'
                "</div>"
            )
            for row in lists
        )
        section_html.append(
            '<section class="metric-section">'
            f'<div class="metric-section-title">{escape(section.title)}</div>'
            f'<div class="metric-grid">{cells}</div>'
            "</section>"
        )

    return (
        '<article class="metric-card">'
        f"{card_header_html(metric, index, total_count)}"
        f'<div class="metric-card-body">{"".join(section_html)}{warning_html(metric)}</div>'
        "</article>"
    )


def price_ladder_card_html(
    metric: EquityMetrics,
    index: int = 0,
    total_count: int = 1,
    level_filter: LevelFilterName = DEFAULT_LEVEL_FILTER,
    level_type_weights: Mapping[str, int] | None = None,
) -> str:
    """Return an Adam-style price ladder for one ticker."""
    price_rows, current_price, non_price_rows = ladder_rows(metric, level_filter, level_type_weights)
    return (
        '<article class="metric-card ladder-card">'
        f"{card_header_html(metric, index, total_count)}"
        '<div class="ladder-body">'
        f"{ladder_table_html(price_rows, current_price, level_type_weights)}"
        f"{non_price_rows_html(non_price_rows)}"
        f"{warning_html(metric)}"
        "</div>"
        "</article>"
    )


def compact_card_html(
    metric: EquityMetrics,
    index: int = 0,
    total_count: int = 1,
    level_filter: LevelFilterName = DEFAULT_LEVEL_FILTER,
    level_type_weights: Mapping[str, int] | None = None,
) -> str:
    """Return a dense card for quick scanning."""
    cells = "".join(
        (
            f'<div class="compact-metric {row["emphasis"]}">'
            f'<span>{escape(str(row["label"]))}</span>'
            f'<strong>{escape(str(row["value"]))}</strong>'
            "</div>"
        )
        for row in flatten_display_rows(metric, level_filter, level_type_weights)
    )
    return (
        '<article class="metric-card compact-card">'
        f"{card_header_html(metric, index, total_count)}"
        f'<div class="compact-body">{cells}{warning_html(metric)}</div>'
        "</article>"
    )


def compare_table_html(
    metrics: list[EquityMetrics],
    level_filter: LevelFilterName = DEFAULT_LEVEL_FILTER,
    level_type_weights: Mapping[str, int] | None = None,
) -> str:
    """Return a cross-ticker comparison table."""
    rows_by_ticker = [(metric, flatten_display_rows(metric, level_filter, level_type_weights)) for metric in metrics]
    labels: list[str] = []
    for _, rows in rows_by_ticker:
        for row in rows:
            if row["label"] not in labels:
                labels.append(row["label"])
    if not labels:
        return '<div class="metric-empty">No report rows returned.</div>'

    header = "".join(f"<th>{escape(label)}</th>" for label in labels)
    body = "".join(
        (
            "<tr>"
            f"<th>{escape(metric.ticker)}</th>"
            + "".join(
                f"<td>{escape(row_by_label[label]['value']) if label in row_by_label else '-'}</td>"
                for label in labels
            )
            + "</tr>"
        )
        for metric, rows in rows_by_ticker
        for row_by_label in [{row["label"]: row for row in rows}]
    )
    return (
        '<div class="compare-wrap streamlit-report-layout-compare">'
        '<table class="compare-table">'
        f"<thead><tr><th>Ticker</th>{header}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
        "</div>"
    )


def card_header_html(metric: EquityMetrics, index: int, total_count: int) -> str:
    del index, total_count
    return (
        '<div class="metric-card-header">'
        f'<div><span class="drag-glyph">&vellip;</span> <h3 style="display:inline">{escape(metric.ticker)}</h3></div>'
        "</div>"
    )


def warning_html(metric: EquityMetrics) -> str:
    if not metric.warnings:
        return ""
    items = "".join(f"<li>{escape(warning)}</li>" for warning in metric.warnings)
    return (
        f'<details class="warning"><summary>{len(metric.warnings)} data warning(s)</summary>'
        f"<ul>{items}</ul></details>"
    )


def ladder_table_html(
    price_rows: list[dict[str, object]],
    current_price: float | None,
    level_type_weights: Mapping[str, int] | None = None,
) -> str:
    rows = insert_current_price(price_rows, current_price)
    if not rows:
        return '<div class="metric-empty">No price levels returned.</div>'
    table_rows = []
    for row in rows:
        numeric_value = float(row["numeric_value"])
        is_current = row["kind"] == "current"
        side = "current" if is_current else "neutral" if current_price is None else "above" if numeric_value > current_price else "below"
        priority = " priority" if row["emphasis"] == "priority" or level_type_weight(str(row["label"]), level_type_weights) >= 20 else ""
        table_rows.append(
            f'<tr class="ladder-row {side}{priority}">'
            f'<td>{escape(str(row["label"]))}</td>'
            f"<td>{format_money(numeric_value)}</td>"
            f"<td>{'-' if is_current else format_distance_percent(current_price, numeric_value)}</td>"
            "</tr>"
        )
    return (
        '<table class="levels-table">'
        "<thead><tr><th>Level</th><th>Price</th><th>% From Now</th></tr></thead>"
        f"<tbody>{''.join(table_rows)}</tbody>"
        "</table>"
    )


def non_price_rows_html(rows: list[dict[str, object]]) -> str:
    if not rows:
        return ""
    return (
        '<div class="ladder-notes">'
        + "".join(
            f'<div><span>{escape(str(row["label"]))}</span><strong>{escape(str(row["value"]))}</strong></div>'
            for row in rows
        )
        + "</div>"
    )


def flatten_display_rows(
    metric: EquityMetrics,
    level_filter: LevelFilterName = DEFAULT_LEVEL_FILTER,
    level_type_weights: Mapping[str, int] | None = None,
) -> list[dict[str, object]]:
    """Return scalar display rows plus joined list rows."""
    normalized_filter = normalize_level_filter(level_filter)
    rows: list[dict[str, object]] = []
    for section in metric_sections(metric):
        rows.extend(normalize_row(row) for row in section.rows)
        rows.extend(
            normalize_row(row, value=", ".join(row.values))
            for row in section.lists
        )
    return [
        row for row in rows
        if row["value"] not in ("", "-")
        and (row["emphasis"] == "current" or level_matches_filter(str(row["label"]), normalized_filter, level_type_weights))
    ]


def ladder_rows(
    metric: EquityMetrics,
    level_filter: LevelFilterName = DEFAULT_LEVEL_FILTER,
    level_type_weights: Mapping[str, int] | None = None,
) -> tuple[list[dict[str, object]], float | None, list[dict[str, object]]]:
    """Return price rows, current price, and non-price rows for price ladder rendering."""
    normalized_filter = normalize_level_filter(level_filter)
    price_rows: list[dict[str, object]] = []
    non_price_rows: list[dict[str, object]] = []
    current_price: float | None = None

    for section in metric_sections(metric):
        for raw_row in section.rows:
            row = normalize_row(raw_row)
            if row["kind"] == "price" and row["numeric_value"] is not None:
                if row["emphasis"] == "current":
                    current_price = float(row["numeric_value"])
                else:
                    price_rows.append(row)
            elif row["value"] not in ("", "-"):
                non_price_rows.append(row)
        for raw_row in section.lists:
            for index, value in enumerate(raw_row.numeric_values):
                price_rows.append(
                    normalize_row(
                        raw_row,
                        label=f"{raw_row.label} {index + 1}",
                        value=raw_row.values[index] if index < len(raw_row.values) else "",
                        numeric_value=value,
                    )
                )

    price_rows = [
        row for row in price_rows
        if level_matches_filter(str(row["label"]), normalized_filter, level_type_weights)
    ]
    if normalized_filter != "all":
        non_price_rows = []

    price_rows.sort(key=lambda row: float(row["numeric_value"]), reverse=True)
    return price_rows, current_price, non_price_rows


def filter_display_list(
    row: DisplayRow,
    level_filter: LevelFilterName,
    level_type_weights: Mapping[str, int] | None = None,
) -> DisplayRow:
    """Return list row values that match the active level filter."""
    next_values: list[str] = []
    next_numeric_values: list[float] = []
    for index, value in enumerate(row.values):
        label = f"{row.label} {index + 1}"
        if not level_matches_filter(label, level_filter, level_type_weights):
            continue
        next_values.append(value)
        if index < len(row.numeric_values):
            next_numeric_values.append(row.numeric_values[index])
    return row.model_copy(update={"values": next_values, "numeric_values": next_numeric_values})


def normalize_row(
    row: DisplayRow,
    *,
    label: str | None = None,
    value: str | None = None,
    numeric_value: float | None = None,
) -> dict[str, object]:
    return {
        "label": label or row.label,
        "value": value if value is not None else row.value or "",
        "kind": row.kind,
        "numeric_value": numeric_value if numeric_value is not None else row.numeric_value,
        "emphasis": row.emphasis,
    }


def insert_current_price(
    price_rows: list[dict[str, object]],
    current_price: float | None,
) -> list[dict[str, object]]:
    """Insert the current price row into a descending price ladder."""
    if current_price is None:
        return price_rows
    rows: list[dict[str, object]] = []
    inserted = False
    for row in price_rows:
        if not inserted and current_price >= float(row["numeric_value"]):
            rows.append(current_row(current_price))
            inserted = True
        rows.append(row)
    if not inserted:
        rows.append(current_row(current_price))
    return rows


def current_row(price: float) -> dict[str, object]:
    return {
        "label": "Current Price",
        "value": f"{price:,.2f}",
        "kind": "current",
        "numeric_value": price,
        "emphasis": "current",
    }


def format_money(value: float) -> str:
    return f"${value:,.2f}"


def format_distance_percent(current_price: float | None, value: float) -> str:
    if current_price in (None, 0):
        return "-"
    percent = ((value - current_price) / current_price) * 100
    return f"{percent:+.2f}%"
