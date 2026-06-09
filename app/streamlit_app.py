"""Streamlit entry point for the equity levels app."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from app.models import DEFAULT_METRICS, EquityMetrics, GenerateRequest, GenerateResponse, MetricName
from app.services.market_data import MarketDataService
from app.services.pdf_report import PdfReportService


METRIC_OPTIONS: dict[MetricName, str] = {
    "previous_day": "Previous day OHLC",
    "premarket": "Premarket range",
    "first_five_minutes": "Opening range",
    "previous_session_vwap_5m": "Previous session VWAP",
    "fifty_two_week": "52-week range",
    "swing_levels": "Swing highs/lows",
    "bollinger_bands": "Bollinger Bands",
    "earnings_gap": "Earnings gap",
}


st.set_page_config(page_title="Investment Trading Levels", layout="wide")


@st.cache_resource
def market_data_service() -> MarketDataService:
    """Return one service instance per Streamlit worker process."""
    return MarketDataService()


@st.cache_resource
def pdf_report_service() -> PdfReportService:
    """Return one PDF renderer per Streamlit worker process."""
    return PdfReportService()


@st.cache_data(ttl=300, show_spinner=False)
def build_report(tickers: tuple[str, ...], metrics: tuple[MetricName, ...]) -> GenerateResponse:
    """Fetch and calculate metrics, cached briefly to avoid repeated provider calls."""
    return GenerateResponse(
        generated_at=datetime.now(timezone.utc),
        metrics=market_data_service().build_metrics(list(tickers), list(metrics)),
    )


def fmt(value: Any) -> str:
    """Format display values for Streamlit tables."""
    if value is None or value == "":
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def metric_rows(metric: EquityMetrics) -> list[dict[str, str]]:
    """Flatten selected metrics into table rows."""
    selected = set(metric.selected_metrics)
    rows: list[tuple[str, Any]] = []

    if "previous_day" in selected:
        rows.extend(
            [
                ("Previous Open", metric.previous_day.open),
                ("Previous High", metric.previous_day.high),
                ("Previous Low", metric.previous_day.low),
                ("Previous Close", metric.previous_day.close),
            ]
        )
    if "premarket" in selected:
        rows.extend(
            [
                ("Premarket High", metric.premarket.high),
                ("Premarket Low", metric.premarket.low),
                ("Premarket Bars", metric.premarket.bars),
            ]
        )
    if "first_five_minutes" in selected:
        rows.extend(
            [
                ("First 5m High", metric.first_five_minutes.high),
                ("First 5m Low", metric.first_five_minutes.low),
                ("First 5m Bars", metric.first_five_minutes.bars),
            ]
        )
    if "previous_session_vwap_5m" in selected:
        rows.append(("Previous Session VWAP (5m)", metric.previous_session_vwap_5m))
    if "fifty_two_week" in selected:
        rows.extend(
            [
                ("52-Week High", metric.fifty_two_week.high),
                ("52-Week Low", metric.fifty_two_week.low),
            ]
        )
    if "swing_levels" in selected:
        rows.extend(
            [
                ("Swing Highs", ", ".join(fmt(level) for level in sorted(metric.swing_levels.highs))),
                ("Swing Lows", ", ".join(fmt(level) for level in sorted(metric.swing_levels.lows, reverse=True))),
            ]
        )
    if "bollinger_bands" in selected:
        rows.extend(
            [
                ("Bollinger Upper", metric.bollinger_bands.upper),
                ("Bollinger Middle", metric.bollinger_bands.middle),
                ("Bollinger Lower", metric.bollinger_bands.lower),
            ]
        )
    if "earnings_gap" in selected:
        rows.extend(
            [
                ("Earnings Date", metric.earnings_gap.date.isoformat() if metric.earnings_gap.date else None),
                ("Earnings Gap", metric.earnings_gap.gap),
                ("Earnings Gap %", metric.earnings_gap.gap_percent),
            ]
        )

    return [{"Metric": label, "Value": fmt(value)} for label, value in rows]


def chart_frame(metric: EquityMetrics) -> pd.DataFrame:
    """Build a daily close chart frame for Streamlit."""
    return pd.DataFrame(
        [{"date": point.date, "close": point.close} for point in metric.price_history]
    )


def render_metric(metric: EquityMetrics) -> None:
    """Render one ticker report section."""
    st.subheader(metric.ticker)
    rows = metric_rows(metric)
    table_col, chart_col = st.columns([0.95, 1.25], gap="large")

    with table_col:
        if rows:
            st.dataframe(rows, hide_index=True, use_container_width=True)
        else:
            st.info("No metric rows were calculated for this ticker.")

    with chart_col:
        history = chart_frame(metric)
        if history.empty:
            st.info("No daily close history was returned for this ticker.")
        else:
            st.line_chart(history, x="date", y="close", use_container_width=True)

    if metric.warnings:
        with st.expander(f"{len(metric.warnings)} data warning(s)"):
            for warning in metric.warnings:
                st.warning(warning)


def selected_metric_ids(labels: list[str]) -> list[MetricName]:
    """Translate selected labels back to metric ids."""
    label_to_id = {label: metric_id for metric_id, label in METRIC_OPTIONS.items()}
    return [label_to_id[label] for label in labels]


def main() -> None:
    """Run the Streamlit application."""
    st.title("Investment Trading Levels")

    with st.sidebar:
        ticker_text = st.text_area("Tickers", value="AAPL, MSFT, NVDA", height=110)
        selected_labels = st.multiselect(
            "Metrics",
            options=list(METRIC_OPTIONS.values()),
            default=[METRIC_OPTIONS[metric_id] for metric_id in DEFAULT_METRICS],
        )
        generate = st.button("Generate Levels", type="primary", use_container_width=True)

    if "report" not in st.session_state:
        st.session_state.report = None

    if generate:
        try:
            request = GenerateRequest(tickers=ticker_text, metrics=selected_metric_ids(selected_labels))
        except ValidationError as exc:
            st.error(exc.errors()[0]["msg"])
            return

        with st.spinner("Generating levels..."):
            st.session_state.report = build_report(tuple(request.tickers), tuple(request.metrics))

    report: GenerateResponse | None = st.session_state.report
    if report is None:
        st.info("Enter tickers and generate levels to view a report.")
        return

    st.caption(f"Generated at {report.generated_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")

    pdf = pdf_report_service().build_pdf(report)
    st.download_button(
        "Download PDF Report",
        data=pdf,
        file_name=f"equity-levels-{report.generated_at.strftime('%Y%m%d-%H%M%S')}.pdf",
        mime="application/pdf",
    )

    for metric in report.metrics:
        render_metric(metric)


if __name__ == "__main__":
    main()
