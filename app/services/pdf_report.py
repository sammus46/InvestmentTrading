"""PDF report generation for calculated equity metrics."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any

from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import EquityMetrics, GenerateResponse


LEVEL_STYLES: dict[str, dict[str, Any]] = {
    "previous": {"color": "#2563eb", "width": 1.4, "legend": "Previous session"},
    "premarket": {"color": "#ea580c", "width": 1.4, "legend": "Premarket"},
    "opening": {"color": "#7c3aed", "width": 1.4, "legend": "First 5m"},
    "vwap": {"color": "#0891b2", "width": 1.8, "legend": "VWAP"},
    "fifty_two": {"color": "#b91c1c", "width": 3.0, "legend": "52-week high/low"},
    "swing_high": {"color": "#16a34a", "width": 1.5, "legend": "Swing highs"},
    "swing_low": {"color": "#ca8a04", "width": 1.5, "legend": "Swing lows"},
    "bollinger": {"color": "#64748b", "width": 1.2, "legend": "Bollinger Bands"},
}


class PdfReportService:
    """Render an equity metrics response into a downloadable PDF."""

    def build_pdf(self, report: GenerateResponse) -> bytes:
        buffer = BytesIO()
        document = SimpleDocTemplate(buffer, pagesize=letter, title="Equity Levels Report")
        styles = getSampleStyleSheet()
        story = [
            Paragraph("Equity Levels Report", styles["Title"]),
            Paragraph(f"Generated at: {report.generated_at.isoformat()}", styles["Normal"]),
            Spacer(1, 12),
        ]

        for metric in report.metrics:
            story.append(Paragraph(metric.ticker, styles["Heading2"]))
            selected = set(metric.selected_metrics)
            table_data = [["Metric", "Value"]]
            if "previous_day" in selected:
                table_data.extend(
                    [
                        ["Previous Open", self._fmt(metric.previous_day.open)],
                        ["Previous High", self._fmt(metric.previous_day.high)],
                        ["Previous Low", self._fmt(metric.previous_day.low)],
                        ["Previous Close", self._fmt(metric.previous_day.close)],
                    ]
                )
            if "premarket" in selected:
                table_data.extend(
                    [
                        ["Premarket High", self._fmt(metric.premarket.high)],
                        ["Premarket Low", self._fmt(metric.premarket.low)],
                    ]
                )
            if "first_five_minutes" in selected:
                table_data.extend(
                    [
                        ["First 5-Minute High", self._fmt(metric.first_five_minutes.high)],
                        ["First 5-Minute Low", self._fmt(metric.first_five_minutes.low)],
                    ]
                )
            if "previous_session_vwap_5m" in selected:
                table_data.append(["Previous Session VWAP (5m)", self._fmt(metric.previous_session_vwap_5m)])
            if "fifty_two_week" in selected:
                table_data.extend(
                    [
                        ["52-Week High", self._fmt(metric.fifty_two_week.high)],
                        ["52-Week Low", self._fmt(metric.fifty_two_week.low)],
                    ]
                )
            if "swing_levels" in selected:
                table_data.extend(
                    [
                        ["Swing Highs", self._fmt_levels(sorted(metric.swing_levels.highs))],
                        ["Swing Lows", self._fmt_levels(sorted(metric.swing_levels.lows, reverse=True))],
                    ]
                )
            if "bollinger_bands" in selected:
                table_data.extend(
                    [
                        ["Bollinger Upper", self._fmt(metric.bollinger_bands.upper)],
                        ["Bollinger Middle", self._fmt(metric.bollinger_bands.middle)],
                        ["Bollinger Lower", self._fmt(metric.bollinger_bands.lower)],
                    ]
                )
            if "earnings_gap" in selected:
                table_data.extend(
                    [
                        ["Earnings Date", self._fmt_date(metric.earnings_gap.date)],
                        ["Earnings Gap", self._fmt(metric.earnings_gap.gap)],
                        ["Earnings Gap %", self._fmt(metric.earnings_gap.gap_percent)],
                    ]
                )
            table = Table(table_data, colWidths=[220, 220])
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#172554")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
                    ]
                )
            )
            story.append(table)
            story.append(Spacer(1, 8))
            chart = self._chart(metric)
            if chart is not None:
                story.append(Paragraph("Price Chart (latest completed daily closes)", styles["Heading3"]))
                story.append(chart)
                legend = self._legend_table(metric)
                if legend is not None:
                    story.append(legend)
            if metric.warnings:
                story.append(Spacer(1, 6))
                story.append(Paragraph("Warnings: " + "; ".join(metric.warnings), styles["Italic"]))
            story.append(Spacer(1, 14))

        document.build(story)
        return buffer.getvalue()

    def _chart(self, metric: EquityMetrics) -> Drawing | None:
        history = metric.price_history[-180:]
        if not history:
            return None

        width = 440
        height = 180
        left = 38
        right = 56
        bottom = 26
        top = 12
        plot_width = width - left - right
        plot_height = height - top - bottom
        levels = self._chart_levels(metric)
        closes = [point.close for point in history]
        values = closes + [level["value"] for level in levels]
        min_value = min(values)
        max_value = max(values)
        if min_value == max_value:
            min_value -= 1
            max_value += 1
        padding = (max_value - min_value) * 0.08
        min_value -= padding
        max_value += padding

        def x_for(index: int) -> float:
            return left + (plot_width / 2 if len(history) == 1 else index / (len(history) - 1) * plot_width)

        def y_for(value: float) -> float:
            return bottom + ((value - min_value) / (max_value - min_value)) * plot_height

        drawing = Drawing(width, height)
        drawing.add(Rect(0, 0, width, height, rx=10, ry=10, fillColor=colors.HexColor("#f8fafc"), strokeColor=colors.HexColor("#e2e8f0")))
        for ratio in (0, 0.25, 0.5, 0.75, 1):
            value = min_value + (max_value - min_value) * ratio
            y = y_for(value)
            drawing.add(Line(left, y, width - right, y, strokeColor=colors.HexColor("#dbe3ef"), strokeWidth=0.5))
            drawing.add(String(6, y - 3, self._fmt(value), fontSize=6, fillColor=colors.HexColor("#64748b")))

        for level in levels:
            y = y_for(level["value"])
            color = colors.HexColor(level["color"])
            drawing.add(Line(left, y, width - right, y, strokeColor=color, strokeWidth=level["width"]))
            drawing.add(String(width - right + 4, y - 3, level["label"], fontSize=5.5, fillColor=color))

        close_points: list[float] = []
        for index, point in enumerate(history):
            close_points.extend([x_for(index), y_for(point.close)])
        drawing.add(PolyLine(close_points, strokeColor=colors.HexColor("#0f172a"), strokeWidth=2, fillColor=None))
        for index, point in enumerate(history[:: max(1, len(history) // 36)]):
            original_index = index * max(1, len(history) // 36)
            drawing.add(Circle(x_for(original_index), y_for(point.close), 1.3, fillColor=colors.white, strokeColor=colors.HexColor("#0f172a"), strokeWidth=0.6))
        drawing.add(Line(left, bottom, width - right, bottom, strokeColor=colors.HexColor("#94a3b8"), strokeWidth=0.8))
        drawing.add(String(left, 8, history[0].date.strftime("%b %d"), fontSize=7, fillColor=colors.HexColor("#64748b")))
        drawing.add(String(width - right - 34, 8, history[-1].date.strftime("%b %d"), fontSize=7, fillColor=colors.HexColor("#64748b")))
        return drawing

    def _chart_levels(self, metric: EquityMetrics) -> list[dict[str, Any]]:
        selected = set(metric.selected_metrics)
        levels: list[dict[str, Any]] = []

        def add(label: str, value: float | None, style_key: str) -> None:
            if value is None:
                return
            levels.append({"label": label, "value": float(value), **LEVEL_STYLES[style_key]})

        if "previous_day" in selected:
            add("Prev High", metric.previous_day.high, "previous")
            add("Prev Low", metric.previous_day.low, "previous")
            add("Prev Close", metric.previous_day.close, "previous")
        if "premarket" in selected:
            add("PM High", metric.premarket.high, "premarket")
            add("PM Low", metric.premarket.low, "premarket")
        if "first_five_minutes" in selected:
            add("5m High", metric.first_five_minutes.high, "opening")
            add("5m Low", metric.first_five_minutes.low, "opening")
        if "previous_session_vwap_5m" in selected:
            add("VWAP", metric.previous_session_vwap_5m, "vwap")
        if "fifty_two_week" in selected:
            add("52W High", metric.fifty_two_week.high, "fifty_two")
            add("52W Low", metric.fifty_two_week.low, "fifty_two")
        if "swing_levels" in selected:
            for index, value in enumerate(sorted(metric.swing_levels.highs), start=1):
                add(f"SwH {index}", value, "swing_high")
            for index, value in enumerate(sorted(metric.swing_levels.lows, reverse=True), start=1):
                add(f"SwL {index}", value, "swing_low")
        if "bollinger_bands" in selected:
            add("BB U", metric.bollinger_bands.upper, "bollinger")
            add("BB M", metric.bollinger_bands.middle, "bollinger")
            add("BB L", metric.bollinger_bands.lower, "bollinger")
        return levels

    def _legend_table(self, metric: EquityMetrics) -> Table | None:
        groups = []
        seen = set()
        for level in self._chart_levels(metric):
            if level["legend"] in seen:
                continue
            seen.add(level["legend"])
            groups.append([level["legend"], level["color"], level["width"]])
        if not groups:
            return None
        data = [["Close", "black"]] + [[group[0], group[1]] for group in groups]
        table = Table([data[index : index + 3] for index in range(0, len(data), 3)])
        style_commands = [("FONTSIZE", (0, 0), (-1, -1), 7), ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#334155"))]
        for row_index, row in enumerate(table._cellvalues):
            for col_index, cell in enumerate(row):
                if isinstance(cell, list):
                    color = colors.black if cell[1] == "black" else colors.HexColor(cell[1])
                    table._cellvalues[row_index][col_index] = f"■ {cell[0]}"
                    style_commands.append(("TEXTCOLOR", (col_index, row_index), (col_index, row_index), color))
        table.setStyle(TableStyle(style_commands))
        return table

    @staticmethod
    def _fmt(value: float | int | None) -> str:
        return "—" if value is None else f"{value:,.4f}" if isinstance(value, float) else str(value)

    @staticmethod
    def _fmt_date(value: date | None) -> str:
        return "—" if value is None else value.isoformat()

    @staticmethod
    def _fmt_levels(values: list[float]) -> str:
        return "—" if not values else ", ".join(f"{value:,.4f}" for value in values)
