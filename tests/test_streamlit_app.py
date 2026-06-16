import json
from datetime import datetime, timezone

from app.models import (
    BollingerLevels,
    DisplayRow,
    DisplaySection,
    EarningsGap,
    EquityMetrics,
    FiftyTwoWeekRange,
    NewsArticle,
    OpeningRange,
    Ohlc,
    PremarketRange,
    SwingLevels,
    TechnicalLevels,
    TickerNews,
)
from app.streamlit_app import (
    dataset_refresh_token,
    filter_report_metrics,
    filter_ticker_news_groups,
    load_streamlit_watchlist,
    mark_streamlit_data_current,
    metric_card_html,
    metric_rows,
    normalize_level_search,
    normalize_report_layout,
    normalize_ticker_list,
    report_layout_label,
    refresh_bucket,
    save_streamlit_watchlist,
    streamlit_autoload_datasets,
    streamlit_dataset_current,
    ticker_news_body_html,
    ticker_news_card_html,
)
from app.streamlit_ui.metrics import compare_table_html, insert_current_price, ladder_rows


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
    assert normalize_ticker_list("aapl, msft\nnvda AAPL $tsla brk.b brk/b") == [
        "AAPL",
        "MSFT",
        "NVDA",
        "TSLA",
        "BRK-B",
    ]


def test_normalize_ticker_list_skips_invalid_tokens():
    assert normalize_ticker_list("aapl <script> 💥 msft") == ["AAPL", "MSFT"]


def test_streamlit_metric_rendering_uses_display_sections():
    metric = EquityMetrics(
        ticker="AAPL",
        selected_metrics=["previous_day"],
        previous_day=Ohlc(open=10.0, high=12.0, low=9.0, close=11.0),
        premarket=PremarketRange(),
        previous_session_vwap_5m=None,
        fifty_two_week=FiftyTwoWeekRange(),
        earnings_gap=EarningsGap(),
        first_five_minutes=OpeningRange(),
        swing_levels=SwingLevels(),
        bollinger_bands=BollingerLevels(),
        technical_levels=TechnicalLevels(),
        data_timestamp=datetime(2026, 6, 15, tzinfo=timezone.utc),
        display_sections=[
            DisplaySection(title="Shared Section", rows=[DisplayRow(label="Shared Level", value="123.45")])
        ],
    )

    assert metric_rows(metric) == [{"Metric": "Shared Level", "Value": "123.45"}]
    assert "Shared Section" in metric_card_html(metric)
    assert "Shared Level" in metric_card_html(metric)


def test_streamlit_report_layout_helpers_use_catalog():
    assert normalize_report_layout("price_ladder") == "price_ladder"
    assert normalize_report_layout("bad-layout") == "grid"
    assert report_layout_label("compare") == "Compare"


def test_streamlit_level_search_filters_report_metrics():
    metrics = [
        EquityMetrics(
            ticker="AAPL",
            selected_metrics=["previous_day"],
            previous_day=Ohlc(),
            premarket=PremarketRange(),
            previous_session_vwap_5m=None,
            fifty_two_week=FiftyTwoWeekRange(),
            earnings_gap=EarningsGap(),
            first_five_minutes=OpeningRange(),
            swing_levels=SwingLevels(),
            bollinger_bands=BollingerLevels(),
            technical_levels=TechnicalLevels(),
            data_timestamp=datetime(2026, 6, 15, tzinfo=timezone.utc),
        ),
        EquityMetrics(
            ticker="MSFT",
            selected_metrics=["previous_day"],
            previous_day=Ohlc(),
            premarket=PremarketRange(),
            previous_session_vwap_5m=None,
            fifty_two_week=FiftyTwoWeekRange(),
            earnings_gap=EarningsGap(),
            first_five_minutes=OpeningRange(),
            swing_levels=SwingLevels(),
            bollinger_bands=BollingerLevels(),
            technical_levels=TechnicalLevels(),
            data_timestamp=datetime(2026, 6, 15, tzinfo=timezone.utc),
        ),
    ]

    assert normalize_level_search(" aap ") == "AAP"
    assert [metric.ticker for metric in filter_report_metrics(metrics, "aap")] == ["AAPL"]
    assert [metric.ticker for metric in filter_report_metrics(metrics, "aap, ms")] == ["AAPL", "MSFT"]
    assert [metric.ticker for metric in filter_report_metrics(metrics, "ms aap")] == ["AAPL", "MSFT"]
    assert [metric.ticker for metric in filter_report_metrics(metrics, "$aap")] == ["AAPL"]
    assert [metric.ticker for metric in filter_report_metrics(metrics, "ms\nzz")] == ["MSFT"]
    assert filter_report_metrics(metrics, "") == metrics
    assert filter_report_metrics(metrics, "zz") == []
    assert filter_report_metrics(metrics, "<script>") == []


def test_streamlit_watchlist_news_search_filters_ticker_groups():
    groups = [
        TickerNews(ticker="AAPL", articles=[NewsArticle(title="AAPL headline")]),
        TickerNews(ticker="MSFT", articles=[NewsArticle(title="MSFT headline")]),
        TickerNews(ticker="NVDA", articles=[NewsArticle(title="NVDA headline")]),
    ]

    assert [group.ticker for group in filter_ticker_news_groups(groups, "aap, nv")] == ["AAPL", "NVDA"]
    assert [group.ticker for group in filter_ticker_news_groups(groups, "ms nv")] == ["MSFT", "NVDA"]
    assert [group.ticker for group in filter_ticker_news_groups(groups, "$aap")] == ["AAPL"]
    assert filter_ticker_news_groups(groups, "") == groups
    assert filter_ticker_news_groups(groups, "zz") == []
    assert filter_ticker_news_groups(groups, "<script>") == []


def test_streamlit_watchlist_news_card_supports_collapsed_and_expanded_body():
    group = TickerNews(
        ticker="AAPL",
        articles=[
            NewsArticle(title=f"Headline {index}", category="general" if index % 2 else "earnings")
            for index in range(8)
        ],
    )

    collapsed = ticker_news_body_html(group, expanded=False)
    expanded = ticker_news_body_html(group, expanded=True)
    card = ticker_news_card_html(group, expanded=True)

    assert "Headline 0" in collapsed
    assert "Headline 5" not in collapsed
    assert "Headline 5" in expanded
    assert "streamlit-news-category-details" in expanded
    assert "streamlit-news-toggle-details" in card
    assert "streamlit-news-toggle-arrow" in card
    assert "open" in ticker_news_card_html(group, expanded=True)
    assert "st.button" not in card


def test_streamlit_loaded_state_tracks_datasets_independently():
    tickers = ("AAPL",)
    metrics = ("previous_day",)

    mark_streamlit_data_current(tickers, metrics, datasets=("report",))

    assert streamlit_dataset_current("report", tickers, metrics)
    assert not streamlit_dataset_current("scanner", tickers, metrics)
    assert dataset_refresh_token("report") == 0


def test_streamlit_autoload_datasets_prioritize_levels_before_news():
    assert streamlit_autoload_datasets("Investment Trading Levels") == ("report", "scanner")
    assert streamlit_autoload_datasets("Stock News") == ("report", "scanner", "market_snapshot", "news")
    assert streamlit_autoload_datasets("Investment Trading Levels", include_news=True) == (
        "report",
        "scanner",
        "market_snapshot",
        "news",
    )


def test_price_ladder_rows_sort_and_insert_current_price():
    metric = EquityMetrics(
        ticker="AAPL",
        selected_metrics=["previous_day", "technical_levels"],
        previous_day=Ohlc(open=10.0, high=12.0, low=9.0, close=11.0),
        premarket=PremarketRange(),
        previous_session_vwap_5m=None,
        fifty_two_week=FiftyTwoWeekRange(),
        earnings_gap=EarningsGap(),
        first_five_minutes=OpeningRange(),
        swing_levels=SwingLevels(),
        bollinger_bands=BollingerLevels(),
        technical_levels=TechnicalLevels(current_price=11.5),
        data_timestamp=datetime(2026, 6, 15, tzinfo=timezone.utc),
    )

    price_rows, current_price, non_price_rows = ladder_rows(metric)
    rows_with_current = insert_current_price(price_rows, current_price)

    assert current_price == 11.5
    assert non_price_rows == []
    assert [row["label"] for row in price_rows[:4]] == ["Prev High", "Prev Close", "Prev Open", "Prev Low"]
    assert [row["label"] for row in rows_with_current[:3]] == ["Prev High", "Current Price", "Prev Close"]


def test_streamlit_metric_rendering_supports_all_report_layouts():
    metric = EquityMetrics(
        ticker="AAPL",
        selected_metrics=["previous_day", "technical_levels"],
        previous_day=Ohlc(open=10.0, high=12.0, low=9.0, close=11.0),
        premarket=PremarketRange(),
        previous_session_vwap_5m=None,
        fifty_two_week=FiftyTwoWeekRange(),
        earnings_gap=EarningsGap(),
        first_five_minutes=OpeningRange(),
        swing_levels=SwingLevels(),
        bollinger_bands=BollingerLevels(),
        technical_levels=TechnicalLevels(current_price=11.5),
        data_timestamp=datetime(2026, 6, 15, tzinfo=timezone.utc),
    )

    assert "metric-section" in metric_card_html(metric, "grid")
    assert "levels-table" in metric_card_html(metric, "price_ladder")
    assert "compact-metric" in metric_card_html(metric, "compact")
    assert "compare-table" in compare_table_html([metric])
