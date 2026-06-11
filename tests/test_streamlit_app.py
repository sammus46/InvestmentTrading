import json
from datetime import datetime, timezone

from app.streamlit_app import (
    load_streamlit_watchlist,
    normalize_ticker_list,
    refresh_bucket,
    save_streamlit_watchlist,
)


def test_load_streamlit_watchlist_missing_file_returns_empty(tmp_path):
    assert load_streamlit_watchlist(tmp_path / "missing.json") == []


def test_load_streamlit_watchlist_invalid_json_returns_empty(tmp_path):
    path = tmp_path / "streamlit_state.json"
    path.write_text("{not-json", encoding="utf-8")

    assert load_streamlit_watchlist(path) == []


def test_load_streamlit_watchlist_normalizes_and_dedupes(tmp_path):
    path = tmp_path / "streamlit_state.json"
    path.write_text(json.dumps({"watchlist": ["aapl", "MSFT", "aapl", " nvda "]}), encoding="utf-8")

    assert load_streamlit_watchlist(path) == ["AAPL", "MSFT", "NVDA"]


def test_save_streamlit_watchlist_writes_expected_shape(tmp_path):
    path = tmp_path / "nested" / "streamlit_state.json"

    save_streamlit_watchlist(["aapl", "msft", "AAPL"], path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["watchlist"] == ["AAPL", "MSFT"]
    assert "updated_at" in payload


def test_refresh_bucket_changes_on_interval_boundary():
    before = datetime(2026, 6, 11, 12, 4, 59, tzinfo=timezone.utc)
    after = datetime(2026, 6, 11, 12, 5, 0, tzinfo=timezone.utc)

    assert refresh_bucket(before, interval_seconds=300) + 1 == refresh_bucket(after, interval_seconds=300)


def test_normalize_ticker_list_accepts_multiple_delimiters():
    assert normalize_ticker_list("aapl, msft\nnvda AAPL") == ["AAPL", "MSFT", "NVDA"]
