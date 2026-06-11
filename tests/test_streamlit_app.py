import json
from datetime import datetime, timezone

from app.streamlit_app import (
    build_streamlit_watchlist_scope,
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


def test_load_streamlit_watchlist_scoped_falls_back_to_legacy_watchlist(tmp_path):
    path = tmp_path / "streamlit_state.json"
    scope = {
        "key": "user:anonymous|device:one",
        "user_key": "user:anonymous",
        "device_key": "device:one",
        "label": "Anonymous / this device",
    }
    path.write_text(json.dumps({"watchlist": ["spy", "qqq"]}), encoding="utf-8")

    assert load_streamlit_watchlist(path, scope=scope) == ["SPY", "QQQ"]


def test_save_streamlit_watchlist_writes_expected_shape(tmp_path):
    path = tmp_path / "nested" / "streamlit_state.json"

    save_streamlit_watchlist(["aapl", "msft", "AAPL"], path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["watchlist"] == ["AAPL", "MSFT"]
    assert "updated_at" in payload


def test_save_streamlit_watchlist_keeps_user_device_scopes_separate(tmp_path):
    path = tmp_path / "streamlit_state.json"
    laptop_scope = {
        "key": "user:one|device:laptop",
        "user_key": "user:one",
        "device_key": "device:laptop",
        "label": "sam@example.com / Windows",
    }
    phone_scope = {
        "key": "user:one|device:phone",
        "user_key": "user:one",
        "device_key": "device:phone",
        "label": "sam@example.com / iOS",
    }

    save_streamlit_watchlist(["aapl", "msft"], path, scope=laptop_scope)
    save_streamlit_watchlist(["nvda"], path, scope=phone_scope)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 2
    assert load_streamlit_watchlist(path, scope=laptop_scope) == ["AAPL", "MSFT"]
    assert load_streamlit_watchlist(path, scope=phone_scope) == ["NVDA"]


def test_streamlit_watchlist_scope_changes_by_user_and_device():
    laptop_context = {
        "headers": {"user-agent": "Desktop Browser", "sec-ch-ua-platform": '"Windows"'},
        "locale": "en-US",
        "timezone": "America/Chicago",
        "timezone_offset": 300,
    }
    phone_context = {
        "headers": {"user-agent": "Mobile Browser", "sec-ch-ua-platform": '"iOS"'},
        "locale": "en-US",
        "timezone": "America/Chicago",
        "timezone_offset": 300,
    }
    user = {"is_logged_in": True, "email": "sam@example.com"}

    laptop_scope = build_streamlit_watchlist_scope(user, laptop_context)
    phone_scope = build_streamlit_watchlist_scope(user, phone_context)
    other_user_scope = build_streamlit_watchlist_scope({"is_logged_in": True, "email": "other@example.com"}, laptop_context)

    assert laptop_scope["key"] != phone_scope["key"]
    assert laptop_scope["key"] != other_user_scope["key"]
    assert laptop_scope["label"] == "sam@example.com / Windows"


def test_refresh_bucket_changes_on_interval_boundary():
    before = datetime(2026, 6, 11, 12, 4, 59, tzinfo=timezone.utc)
    after = datetime(2026, 6, 11, 12, 5, 0, tzinfo=timezone.utc)

    assert refresh_bucket(before, interval_seconds=300) + 1 == refresh_bucket(after, interval_seconds=300)


def test_normalize_ticker_list_accepts_multiple_delimiters():
    assert normalize_ticker_list("aapl, msft\nnvda AAPL") == ["AAPL", "MSFT", "NVDA"]
