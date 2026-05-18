"""PDF report generation for calculated equity metrics."""

from __future__ import annotations

from datetime import date
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import GenerateResponse


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
            table_data = [
                ["Metric", "Value"],
                ["Previous Open", self._fmt(metric.previous_day.open)],
                ["Previous High", self._fmt(metric.previous_day.high)],
                ["Previous Low", self._fmt(metric.previous_day.low)],
                ["Previous Close", self._fmt(metric.previous_day.close)],
                ["Premarket High", self._fmt(metric.premarket.high)],
                ["Premarket Low", self._fmt(metric.premarket.low)],
                ["Previous Session VWAP (5m)", self._fmt(metric.previous_session_vwap_5m)],
                ["52-Week High", self._fmt(metric.fifty_two_week.high)],
                ["52-Week Low", self._fmt(metric.fifty_two_week.low)],
                ["Earnings Date", self._fmt_date(metric.earnings_gap.date)],
                ["Earnings Gap", self._fmt(metric.earnings_gap.gap)],
                ["Earnings Gap %", self._fmt(metric.earnings_gap.gap_percent)],
                ["First 5-Minute High", self._fmt(metric.first_five_minutes.high)],
                ["First 5-Minute Low", self._fmt(metric.first_five_minutes.low)],
                ["Swing Highs", self._fmt_levels(metric.swing_levels.highs)],
                ["Swing Lows", self._fmt_levels(metric.swing_levels.lows)],
                ["Bollinger Upper", self._fmt(metric.bollinger_bands.upper)],
                ["Bollinger Middle", self._fmt(metric.bollinger_bands.middle)],
                ["Bollinger Lower", self._fmt(metric.bollinger_bands.lower)],
            ]
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
            if metric.warnings:
                story.append(Spacer(1, 6))
                story.append(Paragraph("Warnings: " + "; ".join(metric.warnings), styles["Italic"]))
            story.append(Spacer(1, 14))

        document.build(story)
        return buffer.getvalue()

    @staticmethod
    def _fmt(value: float | int | None) -> str:
        return "—" if value is None else f"{value:,.4f}" if isinstance(value, float) else str(value)

    @staticmethod
    def _fmt_date(value: date | None) -> str:
        return "—" if value is None else value.isoformat()

    @staticmethod
    def _fmt_levels(values: list[float]) -> str:
        return "—" if not values else ", ".join(f"{value:,.4f}" for value in values)
