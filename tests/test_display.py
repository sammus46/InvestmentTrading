from datetime import datetime, timezone

from app.main import get_config
from app.models import (
    BollingerLevels,
    DisplayRow,
    DisplaySection,
    EarningsGap,
    EquityMetrics,
    FiftyTwoWeekRange,
    OpeningRange,
    Ohlc,
    PremarketRange,
    SwingLevels,
    TechnicalLevels,
)
from app.services.display import (
    build_metric_display_sections,
    metric_catalog,
    metric_definitions_match_defaults,
    report_layout_catalog,
)
from app.services.pdf_report import PdfReportService


def metric_fixture(selected_metrics=None) -> EquityMetrics:
    return EquityMetrics(
        ticker="AAPL",
        selected_metrics=selected_metrics
        or [
            "previous_day",
            "premarket",
            "first_five_minutes",
            "previous_session_vwap_5m",
            "fifty_two_week",
            "swing_levels",
            "bollinger_bands",
            "technical_levels",
            "earnings_gap",
        ],
        previous_day=Ohlc(open=10.0, high=12.0, low=9.0, close=11.0),
        premarket=PremarketRange(high=11.5, low=10.5, bars=10),
        previous_session_vwap_5m=10.75,
        fifty_two_week=FiftyTwoWeekRange(high=20.0, low=5.0),
        earnings_gap=EarningsGap(gap=1.25, gap_percent=5.0),
        first_five_minutes=OpeningRange(high=11.25, low=10.25, bars=5),
        swing_levels=SwingLevels(highs=[15.0, 14.0], lows=[8.0, 7.5]),
        bollinger_bands=BollingerLevels(upper=13.0, middle=11.0, lower=9.0),
        technical_levels=TechnicalLevels(current_price=11.5, today_vwap=11.25, pivot=10.67),
        data_timestamp=datetime(2026, 6, 15, tzinfo=timezone.utc),
    )


def test_metric_catalog_matches_default_set_and_display_order():
    catalog = metric_catalog()

    assert metric_definitions_match_defaults()
    assert [metric.id for metric in catalog] == [
        "previous_day",
        "premarket",
        "first_five_minutes",
        "previous_session_vwap_5m",
        "fifty_two_week",
        "swing_levels",
        "bollinger_bands",
        "technical_levels",
        "earnings_gap",
    ]
    assert [metric.order for metric in catalog] == list(range(len(catalog)))


def test_display_sections_respect_partial_metric_selection():
    metric = metric_fixture(["previous_day", "swing_levels"])

    sections = build_metric_display_sections(metric)

    assert [section.title for section in sections] == ["Session Levels", "Range & Levels"]
    assert [row.label for row in sections[0].rows] == ["Prev Open", "Prev High", "Prev Low", "Prev Close"]
    assert sections[1].lists[0].values == ["15.00", "14.00"]


def test_config_endpoint_returns_catalog_and_chart_ranges():
    config = get_config()

    assert config.metrics[0].id == "previous_day"
    assert config.chart_ranges["1D"].default_interval == "5m"
    assert "1m" in config.chart_ranges["1D"].intervals
    assert config.default_report_layout == "grid"
    assert [layout.id for layout in config.report_layouts] == ["grid", "price_ladder", "compact", "compare"]


def test_report_layout_catalog_defaults_to_grid():
    layouts = report_layout_catalog()

    assert [layout.id for layout in layouts] == ["grid", "price_ladder", "compact", "compare"]
    assert [layout.id for layout in layouts if layout.default] == ["grid"]


def test_display_rows_include_numeric_and_emphasis_metadata():
    metric = metric_fixture()

    sections = build_metric_display_sections(metric)
    session_rows = sections[0].rows
    technical_rows = next(section.rows for section in sections if section.title == "Technical Levels")
    indicator_rows = next(section.rows for section in sections if section.title == "Indicators & Events")

    prev_high = next(row for row in session_rows if row.label == "Prev High")
    current_price = next(row for row in technical_rows if row.label == "Current Price")
    pivot = next(row for row in technical_rows if row.label == "Pivot")
    earnings_gap_pct = next(row for row in indicator_rows if row.label == "Earnings Gap %")

    assert prev_high.kind == "price"
    assert prev_high.numeric_value == 12.0
    assert prev_high.emphasis == "priority"
    assert current_price.emphasis == "current"
    assert pivot.emphasis == "priority"
    assert earnings_gap_pct.kind == "percent"
    assert earnings_gap_pct.numeric_value == 5.0


def test_pdf_uses_existing_display_sections(monkeypatch):
    metric = metric_fixture(["previous_day"])
    metric.display_sections = [
        DisplaySection(title="Shared Section", rows=[DisplayRow(label="Shared Level", value="123.45")])
    ]

    def fail_if_rebuilt(_metric):
        raise AssertionError("PDF should prefer precomputed display sections")

    monkeypatch.setattr("app.services.pdf_report.build_metric_display_sections", fail_if_rebuilt)
    pdf = PdfReportService().build_pdf(
        type("Report", (), {"generated_at": datetime(2026, 6, 15, tzinfo=timezone.utc), "metrics": [metric]})()
    )

    assert pdf.startswith(b"%PDF")
