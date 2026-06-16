import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

import app.streamlit_app as streamlit_app_module
from streamlit.testing.v1 import AppTest

from app.models import (
    BollingerLevels,
    DisplayRow,
    DisplaySection,
    EarningsGap,
    EquityMetrics,
    FiftyTwoWeekRange,
    GenerateResponse,
    NewsArticle,
    OpeningRange,
    Ohlc,
    PremarketRange,
    ScannerResponse,
    ScannerSetupRow,
    SwingLevels,
    TechnicalLevels,
    TickerNews,
)
from app.streamlit_app import (
    ANALYTICS_VIEW,
    dataset_refresh_token,
    filter_report_metrics,
    filter_ticker_news_groups,
    load_streamlit_watchlist,
    load_streamlit_settings,
    mark_streamlit_data_current,
    merge_streamlit_datasets,
    metric_card_html,
    metric_rows,
    normalize_level_search,
    normalize_level_weights,
    normalize_report_layout,
    normalize_streamlit_settings,
    normalize_ticker_list,
    progressive_report_responses,
    report_layout_label,
    refresh_bucket,
    replace_report_metrics,
    save_streamlit_settings,
    save_streamlit_watchlist,
    split_scanner_global_messages,
    start_pipelined_levels_scanner_loader,
    streamlit_autoload_datasets,
    streamlit_dataset_current,
    STREAMLIT_VIEWS,
    ticker_news_body_html,
    ticker_news_card_html,
)
from app.streamlit_ui.metrics import compare_table_html, insert_current_price, ladder_rows


def streamlit_metric_fixture(ticker: str, selected_metrics=None) -> EquityMetrics:
    return EquityMetrics(
        ticker=ticker,
        selected_metrics=list(selected_metrics or ["previous_day"]),
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
    )


def streamlit_app_smoke_script(state_path: str) -> None:
    import json
    import os
    from datetime import datetime, timezone
    from pathlib import Path

    import app.streamlit_app as app
    from app.models import (
        BollingerLevels,
        ChartHistoryResponse,
        EarningsGap,
        EquityMetrics,
        FiftyTwoWeekRange,
        OpeningRange,
        Ohlc,
        PremarketRange,
        ScannerResponse,
        ScannerSetupRow,
        SwingLevels,
        TechnicalLevels,
    )

    Path(state_path).write_text(json.dumps({"watchlist": ["AAPL", "MSFT", "NVDA"]}), encoding="utf-8")
    os.environ[app.STREAMLIT_STATE_ENV] = state_path

    class FakeMarketData:
        def build_metrics(self, tickers, metrics, include_earnings=True):
            del include_earnings
            return [
                EquityMetrics(
                    ticker=ticker,
                    selected_metrics=list(metrics),
                    previous_day=Ohlc(open=10.0, high=12.0, low=9.0, close=11.0),
                    premarket=PremarketRange(),
                    previous_session_vwap_5m=None,
                    fifty_two_week=FiftyTwoWeekRange(),
                    earnings_gap=EarningsGap(),
                    first_five_minutes=OpeningRange(),
                    swing_levels=SwingLevels(),
                    bollinger_bands=BollingerLevels(),
                    technical_levels=TechnicalLevels(current_price=11.0),
                    data_timestamp=datetime(2026, 6, 15, tzinfo=timezone.utc),
                )
                for ticker in tickers
            ]

        def complete_metrics_earnings(self, metrics):
            return metrics

    class FakeScanner:
        def build_scanner(self, tickers, include_setup=True, include_patterns=True, include_earnings=True):
            del include_setup, include_patterns, include_earnings
            return ScannerResponse(
                generated_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
                watchlist=list(tickers),
                setup_rows=[ScannerSetupRow(ticker=ticker, score=5) for ticker in tickers],
            )

    class FakePdf:
        def build_pdf(self, report):
            del report
            return b"%PDF-1.4\n%%EOF"

    def fake_build_chart_history(tickers, chart_range, interval, refresh_token=0):
        del tickers, refresh_token
        return ChartHistoryResponse(
            generated_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            range=chart_range,
            interval=interval,
            charts=[],
        )

    original_market_data_service = app.market_data_service
    original_scanner_service = app.scanner_service
    original_pdf_report_service = app.pdf_report_service
    original_build_chart_history = app.build_chart_history
    original_render_auto_refresh_fragment = app.render_auto_refresh_fragment
    original_render_streamlit_theme_bridge = app.render_streamlit_theme_bridge
    try:
        app.market_data_service = lambda: FakeMarketData()
        app.scanner_service = lambda: FakeScanner()
        app.pdf_report_service = lambda: FakePdf()
        app.build_chart_history = fake_build_chart_history
        app.render_auto_refresh_fragment = lambda enabled, view: None
        app.render_streamlit_theme_bridge = lambda: None
        app.main()
    finally:
        app.market_data_service = original_market_data_service
        app.scanner_service = original_scanner_service
        app.pdf_report_service = original_pdf_report_service
        app.build_chart_history = original_build_chart_history
        app.render_auto_refresh_fragment = original_render_auto_refresh_fragment
        app.render_streamlit_theme_bridge = original_render_streamlit_theme_bridge


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
    assert payload["settings"]["report_layout"] == "price_ladder"
    assert "updated_at" in payload


def test_streamlit_settings_load_from_watchlist_only_state(tmp_path):
    path = tmp_path / "streamlit_state.json"
    path.write_text(json.dumps({"watchlist": ["AAPL"]}), encoding="utf-8")

    settings = load_streamlit_settings(path)

    assert settings["report_layout"] == "price_ladder"
    assert settings["level_filter"] == "all"
    assert settings["chart_range"] == "1D"
    assert settings["chart_interval"] == "5m"
    assert settings["auto_load"] is True
    assert settings["auto_refresh"] is True
    assert settings["scanner_view"] == "auto"
    assert settings["news_per_ticker"] == 10
    assert settings["level_weights"] == {}


def test_streamlit_settings_normalize_invalid_values():
    settings = normalize_streamlit_settings(
        {
            "default_view": "bad",
            "report_layout": "bad",
            "level_filter": "bad",
            "chart_type": "Bars",
            "chart_range": "5Y",
            "chart_interval": "1m",
            "scanner_view": "bad",
            "auto_load": False,
            "auto_refresh": False,
            "news_per_ticker": 999,
            "level_weights": {"PM High": "19", "Bad Level": 40, "PM Low": 28, "Prev Close": 51},
        }
    )

    assert settings["default_view"] == "Investment Trading Levels"
    assert settings["report_layout"] == "price_ladder"
    assert settings["level_filter"] == "all"
    assert settings["chart_type"] == "Line"
    assert settings["chart_range"] == "5Y"
    assert settings["chart_interval"] == "1mo"
    assert settings["scanner_view"] == "auto"
    assert settings["auto_load"] is False
    assert settings["auto_refresh"] is False
    assert settings["news_per_ticker"] == 20
    assert settings["level_weights"] == {"PM High": 19, "Prev Close": 50}


def test_streamlit_level_weight_normalization_drops_defaults_and_unknowns():
    assert normalize_level_weights({"PM High": 19, "PM Low": 28, "Bad": 50, "Prev Close": -2}) == {
        "PM High": 19,
        "Prev Close": 0,
    }


def test_streamlit_settings_accept_sector_analytics_view():
    settings = normalize_streamlit_settings({"default_view": ANALYTICS_VIEW})

    assert settings["default_view"] == ANALYTICS_VIEW
    assert ANALYTICS_VIEW in STREAMLIT_VIEWS


def test_save_streamlit_settings_preserves_watchlist(tmp_path):
    path = tmp_path / "streamlit_state.json"
    save_streamlit_watchlist(["aapl", "msft"], path)

    save_streamlit_settings(
        {
            "default_view": "Stock News",
            "report_layout": "compact",
            "level_filter": "scanner",
            "scanner_view": "cards",
            "chart_type": "Candles",
            "chart_range": "1Y",
            "chart_interval": "1d",
            "auto_load": False,
            "auto_refresh": False,
            "news_per_ticker": 6,
            "level_weights": {"PM High": 19},
        },
        path,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["watchlist"] == ["AAPL", "MSFT"]
    assert payload["settings"]["default_view"] == "Stock News"
    assert payload["settings"]["report_layout"] == "compact"
    assert payload["settings"]["level_filter"] == "scanner"
    assert payload["settings"]["scanner_view"] == "cards"
    assert payload["settings"]["chart_type"] == "Candles"
    assert payload["settings"]["news_per_ticker"] == 6
    assert payload["settings"]["level_weights"] == {"PM High": 19}


def test_refresh_bucket_changes_on_interval_boundary():
    before = datetime(2026, 6, 11, 12, 0, 59, tzinfo=timezone.utc)
    after = datetime(2026, 6, 11, 12, 1, 0, tzinfo=timezone.utc)

    assert refresh_bucket(before) + 1 == refresh_bucket(after)


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
    assert "Shared Section" in metric_card_html(metric, "grid")
    assert "Shared Level" in metric_card_html(metric, "grid")


def test_streamlit_report_layout_helpers_use_catalog():
    assert normalize_report_layout("price_ladder") == "price_ladder"
    assert normalize_report_layout("bad-layout") == "price_ladder"
    assert report_layout_label("compare") == "Compare"


def test_streamlit_levels_copy_replaces_report_label():
    source = Path("app/streamlit_app.py").read_text(encoding="utf-8")

    assert 'st.header("Levels")' in source
    assert "Download PDF Levels" in source
    assert 'st.header("Report")' not in source
    assert "Download PDF Report" not in source


def test_streamlit_scanner_slot_stays_with_scanner_controls():
    source = Path("app/streamlit_app.py").read_text(encoding="utf-8")

    scanner_controls = source.index('st.subheader("Scanner")')
    scanner_slot = source.index("scanner_slot = st.empty()", scanner_controls)
    report_slot = source.index("report_slot = st.empty()", scanner_controls)

    assert scanner_controls < scanner_slot < report_slot


def test_streamlit_entrypoint_bootstraps_repo_root_before_app_imports():
    source = Path("app/streamlit_app.py").read_text(encoding="utf-8")

    project_root = source.index("PROJECT_ROOT = Path(__file__).resolve().parents[1]")
    sys_path_insert = source.index("sys.path.insert(0, str(PROJECT_ROOT))", project_root)
    app_import = source.index("from app.models import")

    assert project_root < sys_path_insert < app_import


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
    assert not streamlit_dataset_current("news", tickers, metrics)
    assert not streamlit_dataset_current("market_snapshot", tickers, metrics)
    assert dataset_refresh_token("report") == 0


def test_progressive_report_responses_batch_and_preserve_ticker_order():
    calls = []

    def loader(batch, metrics, refresh_token):
        calls.append((batch, metrics, refresh_token))
        return GenerateResponse(
            generated_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            metrics=[
                EquityMetrics(
                    ticker=ticker,
                    selected_metrics=list(metrics),
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
                )
                for ticker in batch
            ],
        )

    responses = progressive_report_responses(
        ("MSFT", "AAPL", "NVDA", "TSLA"),
        ("previous_day",),
        42,
        batch_size=3,
        loader=loader,
    )

    assert [call[0] for call in calls] == [("MSFT", "AAPL", "NVDA"), ("TSLA",)]
    assert [len(response.metrics) for response in responses] == [3, 4]
    assert [metric.ticker for metric in responses[-1].metrics] == ["MSFT", "AAPL", "NVDA", "TSLA"]
    assert all(call[2] == 42 for call in calls)


def test_replace_report_metrics_preserves_watchlist_order_for_earnings_updates():
    report = GenerateResponse(
        generated_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
        metrics=[
            streamlit_metric_fixture("MSFT", ["previous_day"]),
            streamlit_metric_fixture("AAPL", ["previous_day"]),
            streamlit_metric_fixture("NVDA", ["previous_day"]),
        ],
    )
    updated_aapl = streamlit_metric_fixture("AAPL", ["earnings_gap"])
    updated_aapl.earnings_gap = EarningsGap(date=datetime(2026, 6, 10, tzinfo=timezone.utc).date(), gap=1.25)

    updated = replace_report_metrics(("MSFT", "AAPL", "NVDA"), report, [updated_aapl])

    assert [metric.ticker for metric in updated.metrics] == ["MSFT", "AAPL", "NVDA"]
    assert updated.metrics[1].selected_metrics == ["earnings_gap"]
    assert updated.metrics[1].earnings_gap.gap == 1.25


def test_pipelined_levels_scanner_events_batch_and_preserve_order():
    calls = []

    def report_loader(batch, metrics, refresh_token):
        calls.append(("levels", batch, metrics, refresh_token))
        return GenerateResponse(
            generated_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            metrics=[streamlit_metric_fixture(ticker, metrics) for ticker in batch],
        )

    def scanner_loader(batch, refresh_token):
        calls.append(("scanner", batch, refresh_token))
        return ScannerResponse(
            generated_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            watchlist=list(batch),
            setup_rows=[ScannerSetupRow(ticker=ticker, score=index) for index, ticker in enumerate(batch)],
        )

    events, worker = start_pipelined_levels_scanner_loader(
        ("MSFT", "AAPL", "NVDA", "TSLA"),
        ("previous_day",),
        11,
        22,
        report_loader,
        scanner_loader,
        batch_size=3,
    )
    received = []
    while True:
        event = events.get(timeout=2)
        received.append(event)
        if event.kind == "done":
            break

    worker.join(timeout=2)

    assert not worker.is_alive()
    assert [(event.kind, event.batch) for event in received] == [
        ("levels", ("MSFT", "AAPL", "NVDA")),
        ("scanner", ("MSFT", "AAPL", "NVDA")),
        ("levels", ("TSLA",)),
        ("scanner", ("TSLA",)),
        ("done", ()),
    ]
    assert calls == [
        ("levels", ("MSFT", "AAPL", "NVDA"), ("previous_day",), 11),
        ("scanner", ("MSFT", "AAPL", "NVDA"), 22),
        ("levels", ("TSLA",), ("previous_day",), 11),
        ("scanner", ("TSLA",), 22),
    ]


def test_pipelined_loader_starts_next_batch_after_scanner_event_is_queued():
    second_levels_started = Event()
    release_second_levels = Event()

    def report_loader(batch, metrics, refresh_token):
        del refresh_token
        if batch == ("MSFT",):
            second_levels_started.set()
            assert release_second_levels.wait(timeout=2)
        return GenerateResponse(
            generated_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            metrics=[streamlit_metric_fixture(ticker, metrics) for ticker in batch],
        )

    def scanner_loader(batch, refresh_token):
        del refresh_token
        return ScannerResponse(
            generated_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            watchlist=list(batch),
            setup_rows=[ScannerSetupRow(ticker=batch[0], score=5)],
        )

    events, worker = start_pipelined_levels_scanner_loader(
        ("AAPL", "MSFT"),
        ("previous_day",),
        0,
        0,
        report_loader,
        scanner_loader,
        batch_size=1,
    )

    while True:
        event = events.get(timeout=2)
        if event.kind == "scanner" and event.batch == ("AAPL",):
            break

    assert second_levels_started.wait(timeout=2)
    release_second_levels.set()
    while event.kind != "done":
        event = events.get(timeout=2)
    worker.join(timeout=2)

    assert not worker.is_alive()


def test_streamlit_app_initial_load_renders_levels_and_scanner(tmp_path):
    app = AppTest.from_function(
        streamlit_app_smoke_script,
        kwargs={"state_path": str(tmp_path / "streamlit_state.json")},
        default_timeout=8,
    )

    app.run(timeout=8)

    assert not app.exception
    assert "Levels" in [header.value for header in app.header]
    assert "Report" not in [header.value for header in app.header]
    assert any("AAPL" in markdown.value for markdown in app.markdown)
    assert not any("Loading levels and scanner" in markdown.value for markdown in app.markdown)


def test_merge_streamlit_datasets_keeps_load_order_and_dedupes():
    assert merge_streamlit_datasets(("scanner", "report"), ("report", "news", "chart"), ("bad",)) == (
        "scanner",
        "report",
        "news",
        "chart",
    )


def test_streamlit_autoload_datasets_prioritize_levels_before_news():
    assert streamlit_autoload_datasets("Investment Trading Levels") == ("report", "scanner")
    assert streamlit_autoload_datasets("Stock News") == ("report", "scanner", "market_snapshot", "news")
    assert streamlit_autoload_datasets("Sector Analytics") == ("sector_analytics",)
    assert streamlit_autoload_datasets("Investment Trading Levels", include_news=True) == (
        "report",
        "scanner",
        "market_snapshot",
        "news",
    )


def test_streamlit_scanner_no_longer_owns_pattern_tabs():
    source = Path("app/streamlit_app.py").read_text(encoding="utf-8")
    scanner_start = source.index("def render_scanner(")
    scanner_end = source.index("def render_pattern_analysis(", scanner_start)
    scanner_source = source[scanner_start:scanner_end]

    assert "st.tabs" not in scanner_source
    assert "Intraday Pattern Analysis" not in scanner_source


def test_render_scanner_outputs_setup_html_table(monkeypatch):
    markdown_calls = []
    info_calls = []

    monkeypatch.setitem(streamlit_app_module.st.session_state, "scanner_view", "table")
    monkeypatch.setattr(
        streamlit_app_module.st,
        "markdown",
        lambda body, **kwargs: markdown_calls.append((body, kwargs)),
    )
    monkeypatch.setattr(
        streamlit_app_module.st,
        "dataframe",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("scanner should render HTML, not dataframe")),
    )
    monkeypatch.setattr(streamlit_app_module.st, "info", lambda message: info_calls.append(message))

    streamlit_app_module.render_scanner(
        ScannerResponse(
            generated_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            watchlist=["AAPL"],
            setup_rows=[
                ScannerSetupRow(ticker="AAPL", score=5),
                ScannerSetupRow(ticker="MSFT", score=0),
                ScannerSetupRow(ticker="TSLA", score=None),
            ],
        )
    )

    assert markdown_calls
    rendered_html, markdown_kwargs = markdown_calls[0]
    assert "streamlit-scanner-table" in rendered_html
    assert "5/8" in rendered_html
    assert "0/8" in rendered_html
    assert markdown_kwargs["unsafe_allow_html"] is True
    assert not info_calls


def test_scanner_setup_table_html_formats_scores_and_tones():
    html = streamlit_app_module.scanner_setup_table_html(
        ScannerResponse(
            generated_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            watchlist=["AAPL", "MSFT", "TSLA", "NVDA"],
            setup_rows=[
                ScannerSetupRow(
                    ticker="AAPL",
                    price=100,
                    score=8,
                    signal="Reclaimed VWAP",
                    vwap_extension_label="+0.4%  Healthy",
                    vwap_extension_percent=0.4,
                    rs_vs_spy_label="+2.5%  Strong ↑↑",
                    rs_vs_spy_percent=2.5,
                    support_confidence=85,
                    resistance_confidence=65,
                    risk_reward=3.2,
                    setup_distance_percent=0.2,
                    lows_held=3,
                    range_compression="Tight",
                    off_high_percent=0.4,
                    momentum="Turning Up",
                ),
                ScannerSetupRow(
                    ticker="MSFT",
                    score=5,
                    signal="Rejecting R1",
                    vwap_extension_label="+1.1%  Extended",
                    vwap_extension_percent=1.1,
                    rs_vs_spy_label="+0.1%  Inline →",
                    rs_vs_spy_percent=0.1,
                    support_confidence=55,
                    resistance_confidence=40,
                    risk_reward=2.1,
                    setup_distance_percent=0.7,
                    lows_held=2,
                    range_compression="Wide",
                    off_high_percent=-4.2,
                    momentum="Ticking Up",
                ),
                ScannerSetupRow(
                    ticker="TSLA",
                    score=0,
                    vwap_extension_label="-1.2%  Below",
                    vwap_extension_percent=-1.2,
                    rs_vs_spy_label="-2.5%  Very Weak ↓↓",
                    rs_vs_spy_percent=-2.5,
                    risk_reward=0.4,
                    lows_held=1,
                    momentum="Still Falling",
                ),
                ScannerSetupRow(
                    ticker="NVDA",
                    score=None,
                    vwap_extension_label="-0.4%  Near",
                    vwap_extension_percent=-0.4,
                    momentum="Flat",
                ),
            ],
        )
    )

    assert "8/8" in html
    assert "5/8" in html
    assert "0/8" in html
    assert "--score-width:100.0%" in html
    assert "streamlit-scanner-score-bar" not in html
    assert 'title="Turning Up"' in html
    assert 'title="+2.5%  Strong ↑↑"' in html
    assert ">++</span>" in html
    assert ">!</span>" in html
    assert ">T</span>" in html
    assert ">W</span>" in html
    assert "+2.50%" in html
    for tone in ("tone-strong", "tone-good", "tone-watch", "tone-danger", "tone-neutral", "tone-info"):
        assert tone in html


def test_scanner_setup_html_renders_table_and_card_views():
    report = ScannerResponse(
        generated_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
        watchlist=["AAPL"],
        setup_rows=[
            ScannerSetupRow(
                ticker="AAPL",
                price=100,
                score=8,
                signal="Reclaimed VWAP",
                risk_reward=3.2,
                setup_level="VWAP",
                setup_distance_percent=0.2,
                vwap_extension_percent=0.4,
                rs_vs_spy_percent=2.5,
                momentum="Turning Up",
            )
        ],
    )

    auto_html = streamlit_app_module.scanner_setup_html(report)
    card_html = streamlit_app_module.scanner_setup_html(report, "cards")
    table_html = streamlit_app_module.scanner_setup_html(report, "table")

    assert 'class="streamlit-scanner-render view-auto"' in auto_html
    assert 'class="streamlit-scanner-render view-cards"' in card_html
    assert 'class="streamlit-scanner-render view-table"' in table_html
    assert "streamlit-scanner-card-list" in card_html
    assert "streamlit-scanner-card-primary" in card_html
    assert "streamlit-scanner-table-panel" in auto_html
    assert 'class="streamlit-scanner-cell-score align-center"' in auto_html
    assert 'class="streamlit-scanner-cell-ticker"' in auto_html


def test_streamlit_scanner_auto_mobile_keeps_scrollable_table_visible():
    source = Path("app/streamlit_app.py").read_text(encoding="utf-8")
    scanner_css_start = source.index(".streamlit-scanner-render")
    mobile_start = source.index("@media (max-width: 760px)", scanner_css_start)
    mobile_end = source.index("@media (max-width: 460px)", mobile_start)
    mobile_block = source[mobile_start:mobile_end]

    assert ".streamlit-scanner-render.view-auto .streamlit-scanner-table-panel" not in mobile_block
    assert ".streamlit-scanner-render.view-auto .streamlit-scanner-card-panel" not in mobile_block
    assert ".streamlit-scanner-render.view-cards .streamlit-scanner-table-panel" in source
    assert ".streamlit-scanner-render.view-cards .streamlit-scanner-card-panel" in source
    assert ".streamlit-scanner-table th.streamlit-scanner-cell-ticker" in source
    assert ".streamlit-scanner-table td.streamlit-scanner-cell-ticker" in source


def test_scanner_setup_table_html_escapes_values_and_renders_reasons():
    html = streamlit_app_module.scanner_setup_table_html(
        ScannerResponse(
            generated_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            watchlist=["<BAD>"],
            setup_rows=[
                ScannerSetupRow(
                    ticker="<BAD>",
                    score=7,
                    signal="<script>alert('x')</script>",
                    best_support="<support>",
                    support_reason="held <twice>",
                    best_resistance="<resistance>",
                    resistance_reason="rejected <once>",
                    warnings=["warning <x>"],
                    data_notes=["note <y>"],
                )
            ],
        )
    )

    assert "<BAD>" not in html
    assert "&lt;BAD&gt;" in html
    assert "<script>" not in html
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in html
    assert "streamlit-scanner-reason" in html
    assert "held &lt;twice&gt;" in html
    assert "rejected &lt;once&gt;" in html
    assert "warning &lt;x&gt;" in html
    assert "note &lt;y&gt;" in html


def test_scanner_setup_frame_formats_zero_and_missing_scores():
    frame = streamlit_app_module.scanner_setup_frame(
        ScannerResponse(
            generated_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            watchlist=["AAPL", "MSFT", "TSLA"],
            setup_rows=[
                ScannerSetupRow(ticker="AAPL", score=8),
                ScannerSetupRow(ticker="MSFT", score=0),
                ScannerSetupRow(ticker="TSLA", score=None),
            ],
        )
    )

    assert frame["Score"].tolist() == ["8/8", "0/8", "-"]


def test_scanner_global_pattern_absences_render_as_notes():
    visible, notes = split_scanner_global_messages(
        [
            "No pattern data was returned for SPCX.",
            "Pattern analysis failed for AAPL: bad frame",
        ]
    )

    assert visible == ["Pattern analysis failed for AAPL: bad frame"]
    assert notes == ["No pattern data was returned for SPCX."]


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


def test_price_ladder_level_filters_match_scanner_and_weight_buckets():
    metric = EquityMetrics(
        ticker="AAPL",
        selected_metrics=[
            "previous_day",
            "premarket",
            "first_five_minutes",
            "previous_session_vwap_5m",
            "fifty_two_week",
            "swing_levels",
            "technical_levels",
        ],
        previous_day=Ohlc(open=10.0, high=12.0, low=9.0, close=11.0),
        premarket=PremarketRange(high=11.8, low=10.4, bars=10),
        previous_session_vwap_5m=10.75,
        fifty_two_week=FiftyTwoWeekRange(high=25.0, low=5.0),
        earnings_gap=EarningsGap(),
        first_five_minutes=OpeningRange(high=11.7, low=10.25, bars=5),
        swing_levels=SwingLevels(highs=[15.0], lows=[8.0]),
        bollinger_bands=BollingerLevels(),
        technical_levels=TechnicalLevels(
            current_price=11.5,
            today_vwap=11.25,
            one_month_high=20.0,
            one_month_low=6.0,
            sma_50=10.2,
            sma_200=9.7,
            pivot=10.6,
            r1=12.4,
            s1=8.9,
            r2=13.0,
            s2=7.5,
        ),
        data_timestamp=datetime(2026, 6, 15, tzinfo=timezone.utc),
    )

    scanner_rows, _, scanner_notes = ladder_rows(metric, "scanner")
    weight_rows, _, weight_notes = ladder_rows(metric, "weight_20")
    custom_weight_rows, _, _ = ladder_rows(
        metric,
        "weight_20",
        {"PM High": 19, "Daily Swing High": 24, "Daily Swing Low": 24, "Prev Close": 20},
    )
    scanner_labels = [row["label"] for row in scanner_rows]
    weight_labels = [row["label"] for row in weight_rows]
    custom_weight_labels = [row["label"] for row in custom_weight_rows]

    assert "Prev Close" in scanner_labels
    assert "R1" in scanner_labels
    assert "R2" not in scanner_labels
    assert "Prev Open" not in scanner_labels
    assert "Premarket High" in weight_labels
    assert "Swing Highs 1" in weight_labels
    assert "1M High" in weight_labels
    assert "Prev Close" not in weight_labels
    assert "Pivot" not in weight_labels
    assert "Premarket High" not in custom_weight_labels
    assert "Prev Close" in custom_weight_labels
    assert scanner_notes == []
    assert weight_notes == []
    assert 'class="ladder-row above priority"' in metric_card_html(metric, "price_ladder", level_filter="weight_20")
    assert "Premarket High" not in metric_card_html(
        metric,
        "grid",
        level_filter="weight_20",
        level_type_weights={"PM High": 19, "Daily Swing High": 24, "Daily Swing Low": 24, "Prev Close": 20},
    )
    assert "Prev Close" in metric_card_html(
        metric,
        "compact",
        level_filter="weight_20",
        level_type_weights={"PM High": 19, "Daily Swing High": 24, "Daily Swing Low": 24, "Prev Close": 20},
    )
    assert "Prev Close" in compare_table_html(
        [metric],
        level_filter="weight_20",
        level_type_weights={"PM High": 19, "Daily Swing High": 24, "Daily Swing Low": 24, "Prev Close": 20},
    )


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
