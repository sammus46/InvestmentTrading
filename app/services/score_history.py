"""Persist and query daily ticker score history."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.models import (
    DisplayRow,
    EquityMetrics,
    LevelScoreBasisName,
    ScoreHistoryPoint,
    ScoreHistoryRange,
    ScoreHistoryResponse,
    ScoreHistorySummary,
    ScoreHistoryTicker,
    ScoreHistoryAxis,
    ScoreHistoryAxisBucket,
    ScoreMetricName,
    ScannerSetupRow,
)
from app.services.display import build_metric_display_sections, level_matches_filter, level_type_weight

EASTERN = ZoneInfo("America/New_York")
DEFAULT_STORE_PATH = Path("data") / "score_history.json"
STORE_VERSION = 1
RETENTION_DAYS = 400
NEAR_LEVEL_MAX_DISTANCE_PERCENT = 8.0
LEVEL_WEIGHT_MAX = 50
SETUP_HEAT_WEIGHT = 0.6
LEVEL_HEAT_WEIGHT = 0.4
INTRADAY_BUCKET_MINUTES = 30
SESSION_START = time(9, 30)
SESSION_END = time(16, 0)


class ScoreHistoryService:
    """File-backed daily score history for levels and scanner analytics."""

    def __init__(
        self,
        store_path: Path | str = DEFAULT_STORE_PATH,
        *,
        today: Callable[[], date] | None = None,
        now: Callable[[], datetime] | None = None,
        retention_days: int = RETENTION_DAYS,
    ) -> None:
        self.store_path = Path(store_path)
        self._today = today or (lambda: datetime.now(EASTERN).date())
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.retention_days = retention_days
        self._runtime_warnings: list[str] = []

    def record_setup_scores(self, rows: list[ScannerSetupRow]) -> list[str]:
        """Persist scanner setup scores for the current Eastern date."""
        if not rows:
            return []
        store, warnings = self._load_store()
        run_date = self._today()
        bucket = self._active_intraday_bucket(run_date)
        for row in rows:
            if not row.ticker or row.score is None:
                continue
            record = self._record_for(store, row.ticker, run_date)
            updated_at = self._now_iso()
            setup_score = int(row.score)
            record["setup_score"] = setup_score
            record["updated_at"] = updated_at
            if bucket is not None:
                bucket_record = self._intraday_record_for(record, bucket["key"])
                bucket_record["setup_score"] = setup_score
                bucket_record["updated_at"] = updated_at
        self._prune_store(store)
        warnings.extend(self._save_store(store))
        self._remember_warnings(warnings)
        return warnings

    def record_level_scores(self, metrics: list[EquityMetrics]) -> list[str]:
        """Persist weighted level scores for the current Eastern date."""
        if not metrics:
            return []
        store, warnings = self._load_store()
        run_date = self._today()
        bucket = self._active_intraday_bucket(run_date)
        for metric in metrics:
            record = self._record_for(store, metric.ticker, run_date)
            levels = dict(record.get("levels") or {})
            bucket_record = self._intraday_record_for(record, bucket["key"]) if bucket is not None else None
            bucket_levels = dict(bucket_record.get("levels") or {}) if bucket_record is not None else {}
            for basis in ("all", "scanner", "weight_20"):
                score = self.level_score(metric, basis)
                level_payload = {
                    "score": score["score"],
                    "normalized_score": score["normalized_score"],
                    "level_count": score["level_count"],
                }
                levels[basis] = level_payload
                if bucket_record is not None:
                    bucket_levels[basis] = level_payload
            record["levels"] = levels
            updated_at = self._now_iso()
            record["updated_at"] = updated_at
            if bucket_record is not None:
                bucket_record["levels"] = bucket_levels
                bucket_record["updated_at"] = updated_at
        self._prune_store(store)
        warnings.extend(self._save_store(store))
        self._remember_warnings(warnings)
        return warnings

    def build_response(
        self,
        tickers: list[str],
        *,
        score_range: ScoreHistoryRange = "30D",
        score_metric: ScoreMetricName = "both",
        level_basis: LevelScoreBasisName = "all",
    ) -> ScoreHistoryResponse:
        """Return score history for the requested tickers and controls."""
        store, warnings = self._load_store()
        warnings.extend(self._pop_runtime_warnings())
        cutoff = self._cutoff_date(score_range)
        axis = self._axis_metadata(score_range)
        ticker_rows: list[ScoreHistoryTicker] = []
        for ticker in tickers:
            ticker_rows.append(self._ticker_response(ticker, store, cutoff, level_basis, score_range, axis))
        summary = self._summary(ticker_rows, score_metric)
        return ScoreHistoryResponse(
            generated_at=self._now(),
            range=score_range,
            score_metric=score_metric,
            level_basis=level_basis,
            axis=axis,
            summary=summary,
            tickers=ticker_rows,
            warnings=warnings,
        )

    @classmethod
    def level_score(cls, metric: EquityMetrics, basis: LevelScoreBasisName = "all") -> dict[str, float | int | None]:
        """Return weighted score metadata for levels near the current price."""
        current_price = cls._current_price(metric)
        if current_price is None or current_price <= 0:
            return {"score": None, "normalized_score": None, "level_count": 0}

        total = 0
        count = 0
        for label, value in cls._level_values(metric):
            if value is None or value <= 0:
                continue
            if not cls._basis_matches(label, basis):
                continue
            distance_pct = abs((value - current_price) / current_price) * 100
            if distance_pct > NEAR_LEVEL_MAX_DISTANCE_PERCENT:
                continue
            total += level_type_weight(label)
            count += 1

        if count == 0:
            return {"score": None, "normalized_score": None, "level_count": 0}
        normalized = round((total / (count * LEVEL_WEIGHT_MAX)) * 100, 1)
        return {"score": int(total), "normalized_score": normalized, "level_count": count}

    @staticmethod
    def _basis_matches(label: str, basis: LevelScoreBasisName) -> bool:
        if basis == "scanner":
            return level_matches_filter(label, "scanner")
        if basis == "weight_20":
            return level_matches_filter(label, "weight_20")
        return True

    @classmethod
    def _current_price(cls, metric: EquityMetrics) -> float | None:
        tech_price = cls._float_or_none(metric.technical_levels.current_price)
        if tech_price is not None:
            return tech_price
        for section in metric.display_sections or build_metric_display_sections(metric):
            for row in section.rows:
                if row.emphasis == "current":
                    return cls._float_or_none(row.numeric_value)
        return None

    @classmethod
    def _level_values(cls, metric: EquityMetrics) -> list[tuple[str, float | None]]:
        rows: list[tuple[str, float | None]] = []
        for section in metric.display_sections or build_metric_display_sections(metric):
            for row in section.rows:
                if row.kind != "price" or row.emphasis == "current":
                    continue
                rows.append((row.label, cls._float_or_none(row.numeric_value)))
            for row in section.lists:
                if row.kind != "price":
                    continue
                rows.extend(cls._list_values(row))
        return rows

    @classmethod
    def _list_values(cls, row: DisplayRow) -> list[tuple[str, float | None]]:
        values: list[tuple[str, float | None]] = []
        for index, raw_value in enumerate(row.numeric_values):
            values.append((f"{row.label} {index + 1}", cls._float_or_none(raw_value)))
        return values

    def _ticker_response(
        self,
        ticker: str,
        store: dict[str, Any],
        cutoff: date | None,
        level_basis: LevelScoreBasisName,
        score_range: ScoreHistoryRange,
        axis: ScoreHistoryAxis,
    ) -> ScoreHistoryTicker:
        if score_range == "1D":
            return self._intraday_ticker_response(ticker, store, level_basis, axis)

        raw_records = (store.get("records") or {}).get(ticker, {})
        points: list[ScoreHistoryPoint] = []
        warnings: list[str] = []
        for date_text, raw_record in sorted(raw_records.items()):
            point_date = self._parse_date(date_text)
            if point_date is None:
                warnings.append(f"Skipped malformed score history date for {ticker}: {date_text}.")
                continue
            if cutoff is not None and point_date < cutoff:
                continue
            point = self._point_from_record(point_date, raw_record, level_basis)
            if point.setup_score is not None or point.level_score is not None:
                points.append(point)

        if not points:
            warnings.append(f"No score history was found for {ticker}.")

        return ScoreHistoryTicker(
            ticker=ticker,
            points=points,
            latest_setup_score=self._latest(points, "setup_score"),
            latest_level_score=self._latest(points, "level_score"),
            latest_level_score_normalized=self._latest(points, "level_score_normalized"),
            latest_heat_score=self._latest(points, "heat_score"),
            latest_level_count=int(self._latest(points, "level_count") or 0),
            setup_delta_1d=self._delta(points, "setup_score", 1),
            setup_delta_5d=self._delta(points, "setup_score", 5),
            level_delta_1d=self._delta(points, "level_score", 1),
            level_delta_5d=self._delta(points, "level_score", 5),
            level_normalized_delta_1d=self._delta(points, "level_score_normalized", 1),
            level_normalized_delta_5d=self._delta(points, "level_score_normalized", 5),
            heat_delta_1d=self._delta(points, "heat_score", 1),
            heat_delta_5d=self._delta(points, "heat_score", 5),
            warnings=warnings,
        )

    def _intraday_ticker_response(
        self,
        ticker: str,
        store: dict[str, Any],
        level_basis: LevelScoreBasisName,
        axis: ScoreHistoryAxis,
    ) -> ScoreHistoryTicker:
        run_date = self._today()
        raw_record = ((store.get("records") or {}).get(ticker, {}) or {}).get(run_date.isoformat(), {})
        record = raw_record if isinstance(raw_record, dict) else {}
        raw_intraday = record.get("intraday") if isinstance(record.get("intraday"), dict) else {}
        points: list[ScoreHistoryPoint] = []
        warnings: list[str] = []
        bucket_lookup = {bucket.key: bucket for bucket in axis.buckets}
        for bucket_key, raw_bucket in sorted(raw_intraday.items()):
            if bucket_key not in bucket_lookup:
                continue
            point = self._point_from_record(run_date, raw_bucket, level_basis)
            if point.setup_score is None and point.level_score is None:
                continue
            bucket = bucket_lookup[bucket_key]
            point.bucket = bucket.key
            point.bucket_label = bucket.label
            point.bucket_status = bucket.status
            point.timestamp = self._bucket_start(run_date, bucket.key)
            points.append(point)

        if not points:
            warnings.append(f"No intraday score history was found for {ticker}.")

        return ScoreHistoryTicker(
            ticker=ticker,
            points=points,
            latest_setup_score=self._latest(points, "setup_score"),
            latest_level_score=self._latest(points, "level_score"),
            latest_level_score_normalized=self._latest(points, "level_score_normalized"),
            latest_heat_score=self._latest(points, "heat_score"),
            latest_level_count=int(self._latest(points, "level_count") or 0),
            setup_delta_1d=self._delta(points, "setup_score", 1),
            setup_delta_5d=self._delta(points, "setup_score", 5),
            level_delta_1d=self._delta(points, "level_score", 1),
            level_delta_5d=self._delta(points, "level_score", 5),
            level_normalized_delta_1d=self._delta(points, "level_score_normalized", 1),
            level_normalized_delta_5d=self._delta(points, "level_score_normalized", 5),
            heat_delta_1d=self._delta(points, "heat_score", 1),
            heat_delta_5d=self._delta(points, "heat_score", 5),
            warnings=warnings,
        )

    @staticmethod
    def _point_from_record(
        point_date: date,
        raw_record: object,
        level_basis: LevelScoreBasisName,
    ) -> ScoreHistoryPoint:
        record = raw_record if isinstance(raw_record, dict) else {}
        levels = record.get("levels") if isinstance(record.get("levels"), dict) else {}
        level_record = levels.get(level_basis) if isinstance(levels.get(level_basis), dict) else {}
        setup_score = ScoreHistoryService._int_or_none(record.get("setup_score"))
        level_score = ScoreHistoryService._int_or_none(level_record.get("score"))
        level_score_normalized = ScoreHistoryService._float_or_none(level_record.get("normalized_score"))
        return ScoreHistoryPoint(
            date=point_date,
            setup_score=setup_score,
            level_score=level_score,
            level_score_normalized=level_score_normalized,
            heat_score=ScoreHistoryService.heat_score(setup_score, level_score_normalized),
            level_count=ScoreHistoryService._int_or_none(level_record.get("level_count")) or 0,
        )

    @staticmethod
    def _latest(points: list[ScoreHistoryPoint], field: str) -> Any:
        for point in reversed(points):
            value = getattr(point, field)
            if value is not None:
                return value
        return None

    @classmethod
    def _delta(cls, points: list[ScoreHistoryPoint], field: str, offset: int) -> Any:
        values = [getattr(point, field) for point in points if getattr(point, field) is not None]
        if len(values) <= offset:
            return None
        latest = values[-1]
        previous = values[-1 - offset]
        if latest is None or previous is None:
            return None
        delta = latest - previous
        if isinstance(latest, float) or isinstance(previous, float):
            return round(float(delta), 1)
        return int(delta)

    @classmethod
    def _summary(cls, rows: list[ScoreHistoryTicker], score_metric: ScoreMetricName) -> ScoreHistorySummary:
        tracked = [row for row in rows if row.points]
        setup_values = [row.latest_setup_score for row in rows if row.latest_setup_score is not None]
        level_values = [row.latest_level_score for row in rows if row.latest_level_score is not None]
        level_normalized_values = [
            row.latest_level_score_normalized for row in rows if row.latest_level_score_normalized is not None
        ]
        heat_values = [row.latest_heat_score for row in rows if row.latest_heat_score is not None]
        improving = declining = flat_or_new = 0
        for row in rows:
            movement = cls._movement_delta(row, score_metric)
            if movement is None or abs(movement) < 0.01:
                flat_or_new += 1
            elif movement > 0:
                improving += 1
            else:
                declining += 1
        return ScoreHistorySummary(
            ticker_count=len(rows),
            tracked_ticker_count=len(tracked),
            average_setup_score=cls._avg(setup_values),
            average_level_score=cls._avg(level_values),
            average_level_score_normalized=cls._avg(level_normalized_values),
            average_heat_score=cls._avg(heat_values),
            improving_count=improving,
            declining_count=declining,
            flat_or_new_count=flat_or_new,
        )

    @staticmethod
    def _movement_delta(row: ScoreHistoryTicker, score_metric: ScoreMetricName) -> float | None:
        if score_metric == "setup":
            return float(row.setup_delta_1d) if row.setup_delta_1d is not None else None
        if score_metric == "level":
            return float(row.level_normalized_delta_1d) if row.level_normalized_delta_1d is not None else None
        return float(row.heat_delta_1d) if row.heat_delta_1d is not None else None

    @classmethod
    def heat_score(cls, setup_score: int | None, level_score_normalized: float | None) -> float | None:
        """Return a 0-100 hot/cold score from setup and normalized level scores."""
        components: list[tuple[float, float]] = []
        setup_normalized = cls._setup_score_normalized(setup_score)
        level_normalized = cls._bounded_percent(level_score_normalized)
        if setup_normalized is not None:
            components.append((setup_normalized, SETUP_HEAT_WEIGHT))
        if level_normalized is not None:
            components.append((level_normalized, LEVEL_HEAT_WEIGHT))
        if not components:
            return None
        total_weight = sum(weight for _, weight in components)
        return round(sum(value * weight for value, weight in components) / total_weight, 1)

    @staticmethod
    def _setup_score_normalized(setup_score: int | None) -> float | None:
        if setup_score is None:
            return None
        return round((max(0, min(8, setup_score)) / 8) * 100, 1)

    @staticmethod
    def _bounded_percent(value: float | None) -> float | None:
        if value is None:
            return None
        return max(0.0, min(100.0, float(value)))

    @staticmethod
    def _avg(values: list[int | float | None]) -> float | None:
        numbers = [float(value) for value in values if value is not None]
        return round(sum(numbers) / len(numbers), 2) if numbers else None

    def _axis_metadata(self, score_range: ScoreHistoryRange) -> ScoreHistoryAxis:
        if score_range != "1D":
            return ScoreHistoryAxis(mode="daily")
        run_date = self._today()
        return ScoreHistoryAxis(
            mode="intraday",
            timezone="America/New_York",
            bucket_minutes=INTRADAY_BUCKET_MINUTES,
            session_start=SESSION_START.strftime("%H:%M"),
            session_end=SESSION_END.strftime("%H:%M"),
            buckets=self._intraday_axis_buckets(run_date),
        )

    def _intraday_axis_buckets(self, run_date: date) -> list[ScoreHistoryAxisBucket]:
        now_et = self._now().astimezone(EASTERN)
        session_start = datetime.combine(run_date, SESSION_START, tzinfo=EASTERN)
        session_end = datetime.combine(run_date, SESSION_END, tzinfo=EASTERN)
        total_minutes = int((session_end - session_start).total_seconds() // 60)
        buckets: list[ScoreHistoryAxisBucket] = []
        for offset in range(0, total_minutes, INTRADAY_BUCKET_MINUTES):
            bucket_start = session_start + timedelta(minutes=offset)
            bucket_end = bucket_start + timedelta(minutes=INTRADAY_BUCKET_MINUTES)
            if now_et < bucket_start:
                status = "future"
            elif now_et >= bucket_end:
                status = "past"
            else:
                status = "current"
            buckets.append(
                ScoreHistoryAxisBucket(
                    key=bucket_start.strftime("%H:%M"),
                    label=self._bucket_label(bucket_start),
                    status=status,
                )
            )
        return buckets

    def _active_intraday_bucket(self, run_date: date) -> dict[str, str] | None:
        now_et = self._now().astimezone(EASTERN)
        if now_et.date() != run_date:
            return None
        session_start = datetime.combine(run_date, SESSION_START, tzinfo=EASTERN)
        session_end = datetime.combine(run_date, SESSION_END, tzinfo=EASTERN)
        if now_et < session_start or now_et >= session_end:
            return None
        minutes_since_open = int((now_et - session_start).total_seconds() // 60)
        bucket_offset = (minutes_since_open // INTRADAY_BUCKET_MINUTES) * INTRADAY_BUCKET_MINUTES
        bucket_start = session_start + timedelta(minutes=bucket_offset)
        return {"key": bucket_start.strftime("%H:%M"), "label": self._bucket_label(bucket_start)}

    @staticmethod
    def _bucket_start(run_date: date, bucket_key: str) -> datetime | None:
        try:
            hour, minute = [int(part) for part in bucket_key.split(":", maxsplit=1)]
        except ValueError:
            return None
        return datetime.combine(run_date, time(hour, minute), tzinfo=EASTERN)

    @staticmethod
    def _bucket_label(bucket_start: datetime) -> str:
        hour = bucket_start.hour % 12 or 12
        suffix = "AM" if bucket_start.hour < 12 else "PM"
        return f"{hour}:{bucket_start.minute:02d} {suffix}"

    def _record_for(self, store: dict[str, Any], ticker: str, run_date: date) -> dict[str, Any]:
        records = store.setdefault("records", {})
        ticker_records = records.setdefault(ticker, {})
        return ticker_records.setdefault(run_date.isoformat(), {})

    @staticmethod
    def _intraday_record_for(record: dict[str, Any], bucket_key: str) -> dict[str, Any]:
        intraday = record.setdefault("intraday", {})
        if not isinstance(intraday, dict):
            intraday = {}
            record["intraday"] = intraday
        bucket_record = intraday.setdefault(bucket_key, {})
        if not isinstance(bucket_record, dict):
            bucket_record = {}
            intraday[bucket_key] = bucket_record
        return bucket_record

    def _remember_warnings(self, warnings: list[str]) -> None:
        if not warnings:
            return
        self._runtime_warnings = list(dict.fromkeys([*self._runtime_warnings, *warnings]))

    def _pop_runtime_warnings(self) -> list[str]:
        warnings = list(self._runtime_warnings)
        self._runtime_warnings = []
        return warnings

    def _load_store(self) -> tuple[dict[str, Any], list[str]]:
        if not self.store_path.exists():
            return self._empty_store(), []
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return self._empty_store(), [f"Score history could not be read and was treated as empty: {exc}"]
        if not isinstance(raw, dict):
            return self._empty_store(), ["Score history file did not contain an object and was treated as empty."]
        raw.setdefault("version", STORE_VERSION)
        raw.setdefault("records", {})
        if not isinstance(raw["records"], dict):
            raw["records"] = {}
        return raw, []

    def _save_store(self, store: dict[str, Any]) -> list[str]:
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.store_path.with_suffix(f"{self.store_path.suffix}.tmp")
            temp_path.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            temp_path.replace(self.store_path)
            return []
        except Exception as exc:
            return [f"Score history could not be saved: {exc}"]

    @staticmethod
    def _empty_store() -> dict[str, Any]:
        return {"version": STORE_VERSION, "records": {}}

    def _prune_store(self, store: dict[str, Any]) -> None:
        cutoff = self._today() - timedelta(days=self.retention_days)
        records = store.get("records")
        if not isinstance(records, dict):
            return
        for ticker in list(records):
            ticker_records = records.get(ticker)
            if not isinstance(ticker_records, dict):
                del records[ticker]
                continue
            for date_text in list(ticker_records):
                point_date = self._parse_date(date_text)
                if point_date is None or point_date < cutoff:
                    del ticker_records[date_text]
            if not ticker_records:
                del records[ticker]

    def _cutoff_date(self, score_range: ScoreHistoryRange) -> date | None:
        days_by_range = {"1D": 1, "7D": 7, "30D": 30, "90D": 90, "1Y": 365}
        days = days_by_range.get(score_range)
        if days is None:
            return None
        return self._today() - timedelta(days=days - 1)

    def _now_iso(self) -> str:
        return self._now().astimezone(timezone.utc).isoformat()

    @staticmethod
    def _parse_date(value: str) -> date | None:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _float_or_none(value: object) -> float | None:
        try:
            if value is None:
                return None
            number = float(value)
            if number != number:
                return None
            return number
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _int_or_none(value: object) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None
