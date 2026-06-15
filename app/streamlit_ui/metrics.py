"""Streamlit rendering helpers for generated level metrics."""

from __future__ import annotations

from html import escape

import streamlit as st

from app.models import EquityMetrics
from app.services.display import build_metric_display_sections


def metric_rows(metric: EquityMetrics) -> list[dict[str, str]]:
    """Flatten selected metrics into table rows."""
    rows: list[dict[str, str]] = []
    for section in metric_sections(metric):
        rows.extend({"Metric": row.label, "Value": row.value or "-"} for row in section.rows)
        rows.extend({"Metric": row.label, "Value": ", ".join(row.values) or "-"} for row in section.lists)
    return rows


def metric_sections(metric: EquityMetrics):
    """Group selected metrics into card sections that mirror the static app."""
    return metric.display_sections or build_metric_display_sections(metric)


def metric_card_html(metric: EquityMetrics) -> str:
    """Return one ticker card styled like the static app."""
    section_html = []
    for section in metric_sections(metric):
        cells = "".join(
            (
                '<div class="metric-cell">'
                f'<span class="metric-label">{escape(row.label)}</span>'
                f'<span class="metric-value">{escape(row.value or "-")}</span>'
                "</div>"
            )
            for row in section.rows
        )
        cells += "".join(
            (
                '<div class="metric-cell">'
                f'<span class="metric-label">{escape(row.label)}</span>'
                f'<span class="metric-value">{escape(", ".join(row.values) or "-")}</span>'
                "</div>"
            )
            for row in section.lists
        )
        section_html.append(
            '<section class="metric-section">'
            f'<div class="metric-section-title">{escape(section.title)}</div>'
            f'<div class="metric-grid">{cells}</div>'
            "</section>"
        )

    warning_html = ""
    if metric.warnings:
        items = "".join(f"<li>{escape(warning)}</li>" for warning in metric.warnings)
        warning_html = (
            f'<details class="warning"><summary>{len(metric.warnings)} data warning(s)</summary>'
            f"<ul>{items}</ul></details>"
        )

    return (
        '<article class="metric-card">'
        '<div class="metric-card-header">'
        f'<div><span class="drag-glyph">&vellip;</span> <h3 style="display:inline">{escape(metric.ticker)}</h3></div>'
        "</div>"
        f'<div class="metric-card-body">{"".join(section_html)}{warning_html}</div>'
        "</article>"
    )


def render_metric_card(metric: EquityMetrics) -> None:
    """Render one ticker report card."""
    st.markdown(metric_card_html(metric), unsafe_allow_html=True)


def render_metric_grid(metrics: list[EquityMetrics]) -> None:
    """Render ticker report cards in a responsive grid."""
    cards = "".join(metric_card_html(metric) for metric in metrics)
    st.markdown(f'<div class="streamlit-report-grid">{cards}</div>', unsafe_allow_html=True)


def render_metric(metric: EquityMetrics) -> None:
    """Render one ticker report section."""
    render_metric_card(metric)
    if metric.warnings:
        with st.expander(f"{len(metric.warnings)} data warning(s)"):
            for warning in metric.warnings:
                st.warning(warning)
