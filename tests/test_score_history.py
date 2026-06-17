from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from app.main import generate_score_history
from app.models import (
    BollingerLevels,
    DisplayRow,
    DisplaySection,
    EarningsGap,
    EquityMetrics,
    FiftyTwoWeekRange,
    Ohlc,
    OpeningRange,
    PremarketRange,
    ScannerSetupRow,
    ScoreHistoryPoint,
    ScoreHistoryRequest,
    ScoreHistoryResponse,
    ScoreHistorySummary,
    ScoreHistoryTicker,
    SwingLevels,
    TechnicalLevels,
)
from app.services.score_history import ScoreHistoryService


def metric_with_levels() -> EquityMetrics:
    return EquityMetrics(
        ticker="AAPL",
        selected_metrics=[],
        previous_day=Ohlc(),
        premarket=PremarketRange(),
        previous_session_vwap_5m=None,
        fifty_two_week=FiftyTwoWeekRange(),
        earnings_gap=EarningsGap(),
        first_five_minutes=OpeningRange(),
        swing_levels=SwingLevels(),
        bollinger_bands=BollingerLevels(),
        technical_levels=TechnicalLevels(current_price=100.0),
        data_timestamp=datetime.now(timezone.utc),
        display_sections=[
            DisplaySection(
                title="Levels",
                rows=[
                    DisplayRow(label="Current Price", kind="price", numeric_value=100.0, emphasis="current"),
                    DisplayRow(label="Prev High", kind="price", numeric_value=102.0),
                    DisplayRow(label="50 SMA", kind="price", numeric_value=95.0),
                    DisplayRow(label="9 EMA 5m", kind="price", numeric_value=101.0),
                    DisplayRow(label="BB Upper", kind="price", numeric_value=120.0),
                ],
                lists=[
                    DisplayRow(
                        label="Swing Highs",
                        kind="price",
                        values=["107.00"],
                        numeric_values=[107.0],
                    )
                ],
            )
        ],
    )


def test_level_score_respects_basis_and_near_current_window():
    metric = metric_with_levels()

    all_score = ScoreHistoryService.level_score(metric, "all")
    scanner_score = ScoreHistoryService.level_score(metric, "scanner")
    weight_score = ScoreHistoryService.level_score(metric, "weight_20")

    assert all_score == {"score": 78, "normalized_score": 39.0, "level_count": 4}
    assert scanner_score == {"score": 64, "normalized_score": 42.7, "level_count": 3}
    assert weight_score == {"score": 50, "normalized_score": 50.0, "level_count": 2}


def test_heat_score_reweights_available_components():
    assert ScoreHistoryService.heat_score(4, 50.0) == 50.0
    assert ScoreHistoryService.heat_score(8, 50.0) == 80.0
    assert ScoreHistoryService.heat_score(6, None) == 75.0
    assert ScoreHistoryService.heat_score(None, 62.5) == 62.5
    assert ScoreHistoryService.heat_score(None, None) is None


def test_heat_score_stays_derived_from_setup_and_level_scores():
    setup_score = 2
    level_score_normalized = 31.1

    assert ScoreHistoryService.heat_score(setup_score, level_score_normalized) == 27.4


def test_score_history_merges_same_day_records(tmp_path):
    service = ScoreHistoryService(
        tmp_path / "score_history.json",
        today=lambda: date(2026, 6, 17),
        now=lambda: datetime(2026, 6, 17, 15, 0, tzinfo=timezone.utc),
    )

    service.record_setup_scores([ScannerSetupRow(ticker="AAPL", score=5)])
    service.record_setup_scores([ScannerSetupRow(ticker="AAPL", score=7)])
    service.record_level_scores([metric_with_levels()])
    response = service.build_response(["AAPL"], score_range="30D", score_metric="both", level_basis="weight_20")

    assert len(response.tickers[0].points) == 1
    assert response.tickers[0].points[0].setup_score == 7
    assert response.tickers[0].points[0].level_score == 50
    assert response.tickers[0].points[0].heat_score == 72.5
    assert response.tickers[0].latest_heat_score == 72.5
    assert response.tickers[0].latest_level_count == 2


def test_score_history_one_day_returns_intraday_axis_and_bucket_points(tmp_path):
    service = ScoreHistoryService(
        tmp_path / "score_history.json",
        today=lambda: date(2026, 6, 17),
        now=lambda: datetime(2026, 6, 17, 15, 45, tzinfo=timezone.utc),
    )

    service.record_setup_scores([ScannerSetupRow(ticker="AAPL", score=5)])
    service.record_level_scores([metric_with_levels()])
    response = service.build_response(["AAPL"], score_range="1D", score_metric="both", level_basis="weight_20")
    ticker = response.tickers[0]

    assert response.axis is not None
    assert response.axis.mode == "intraday"
    assert response.axis.bucket_minutes == 30
    assert response.axis.session_start == "09:30"
    assert response.axis.session_end == "16:00"
    assert len(response.axis.buckets) == 13
    assert response.axis.buckets[0].label == "9:30 AM"
    assert response.axis.buckets[0].status == "past"
    assert response.axis.buckets[4].key == "11:30"
    assert response.axis.buckets[4].status == "current"
    assert response.axis.buckets[-1].status == "future"
    assert len(ticker.points) == 1
    assert ticker.points[0].bucket == "11:30"
    assert ticker.points[0].bucket_label == "11:30 AM"
    assert ticker.points[0].bucket_status == "current"
    assert ticker.points[0].setup_score == 5
    assert ticker.points[0].level_score == 50
    assert ticker.points[0].heat_score == 57.5


def test_score_history_one_day_merges_same_bucket_and_deltas_prior_bucket(tmp_path):
    current_now = {"value": datetime(2026, 6, 17, 14, 5, tzinfo=timezone.utc)}
    service = ScoreHistoryService(
        tmp_path / "score_history.json",
        today=lambda: date(2026, 6, 17),
        now=lambda: current_now["value"],
    )

    service.record_setup_scores([ScannerSetupRow(ticker="AAPL", score=4)])
    current_now["value"] = datetime(2026, 6, 17, 14, 20, tzinfo=timezone.utc)
    service.record_setup_scores([ScannerSetupRow(ticker="AAPL", score=6)])
    current_now["value"] = datetime(2026, 6, 17, 14, 35, tzinfo=timezone.utc)
    service.record_setup_scores([ScannerSetupRow(ticker="AAPL", score=5)])
    response = service.build_response(["AAPL"], score_range="1D", score_metric="setup", level_basis="all")
    ticker = response.tickers[0]

    assert [point.bucket for point in ticker.points] == ["10:00", "10:30"]
    assert [point.setup_score for point in ticker.points] == [6, 5]
    assert ticker.setup_delta_1d == -1
    assert response.summary.declining_count == 1


def test_score_history_prunes_old_records_on_write(tmp_path):
    path = tmp_path / "score_history.json"
    path.write_text(
        """
        {
          "version": 1,
          "records": {
            "AAPL": {
              "2026-06-10": {"setup_score": 1},
              "2026-06-16": {"setup_score": 4}
            }
          }
        }
        """,
        encoding="utf-8",
    )
    service = ScoreHistoryService(path, today=lambda: date(2026, 6, 17), retention_days=3)

    service.record_setup_scores([ScannerSetupRow(ticker="AAPL", score=6)])
    response = service.build_response(["AAPL"], score_range="All", score_metric="setup", level_basis="all")

    assert [point.date for point in response.tickers[0].points] == [date(2026, 6, 16), date(2026, 6, 17)]
    assert response.tickers[0].setup_delta_1d == 2


def test_score_history_handles_missing_and_corrupt_store(tmp_path):
    missing = ScoreHistoryService(tmp_path / "missing.json", today=lambda: date(2026, 6, 17))
    missing_response = missing.build_response(["AAPL"])

    assert missing_response.warnings == []
    assert missing_response.tickers[0].warnings == ["No score history was found for AAPL."]

    corrupt_path = tmp_path / "score_history.json"
    corrupt_path.write_text("{not json", encoding="utf-8")
    corrupt = ScoreHistoryService(corrupt_path, today=lambda: date(2026, 6, 17))
    corrupt_response = corrupt.build_response(["AAPL"])

    assert corrupt_response.warnings
    assert "treated as empty" in corrupt_response.warnings[0]


def test_score_history_response_summarizes_deltas(tmp_path):
    path = tmp_path / "score_history.json"
    path.write_text(
        """
        {
          "version": 1,
          "records": {
            "AAPL": {
              "2026-06-12": {"setup_score": 2, "levels": {"all": {"score": 40, "normalized_score": 40.0, "level_count": 2}}},
              "2026-06-16": {"setup_score": 5, "levels": {"all": {"score": 50, "normalized_score": 50.0, "level_count": 2}}},
              "2026-06-17": {"setup_score": 6, "levels": {"all": {"score": 70, "normalized_score": 70.0, "level_count": 2}}}
            }
          }
        }
        """,
        encoding="utf-8",
    )
    service = ScoreHistoryService(path, today=lambda: date(2026, 6, 17))

    response = service.build_response(["AAPL"], score_range="30D", score_metric="both", level_basis="all")
    ticker = response.tickers[0]

    assert ticker.setup_delta_1d == 1
    assert ticker.level_delta_1d == 20
    assert ticker.heat_delta_1d == 15.5
    assert ticker.setup_delta_5d is None
    assert ticker.latest_heat_score == 73.0
    assert response.summary.average_setup_score == 6.0
    assert response.summary.average_level_score_normalized == 70.0
    assert response.summary.average_heat_score == 73.0
    assert response.summary.improving_count == 1


def test_score_history_request_validation_and_route(monkeypatch):
    class FakeScoreHistory:
        def build_response(self, tickers, *, score_range, score_metric, level_basis):
            return ScoreHistoryResponse(
                generated_at=datetime.now(timezone.utc),
                range=score_range,
                score_metric=score_metric,
                level_basis=level_basis,
                summary=ScoreHistorySummary(ticker_count=len(tickers), average_heat_score=80.0),
                tickers=[
                    ScoreHistoryTicker(
                        ticker=tickers[0],
                        points=[
                            ScoreHistoryPoint(date=date(2026, 6, 17), setup_score=8, level_score_normalized=50.0, heat_score=80.0)
                        ],
                        latest_heat_score=80.0,
                    )
                ],
            )

    monkeypatch.setattr("app.main.score_history_service", FakeScoreHistory())
    request = ScoreHistoryRequest(tickers="aapl msft", range="1D", score_metric="setup", level_basis="scanner")
    response = generate_score_history(request)

    assert request.tickers == ["AAPL", "MSFT"]
    assert response.range == "1D"
    assert response.score_metric == "setup"
    assert response.level_basis == "scanner"
    assert response.summary.ticker_count == 2
    assert response.summary.average_heat_score == 80.0
    assert response.tickers[0].points[0].heat_score == 80.0
    assert response.tickers[0].latest_heat_score == 80.0
    with pytest.raises(ValidationError):
        ScoreHistoryRequest(tickers="AAPL", range="BAD")
