from pathlib import Path


def scanner_mobile_css_block() -> str:
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    start = css.index("@media (max-width: 760px)", css.index(".scanner-data-notes li"))
    end = css.index("@media (max-width: 460px)", start)
    return css[start:end]


def test_static_scanner_auto_mobile_keeps_scrollable_table_visible():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    mobile_block = scanner_mobile_css_block()

    assert ".scanner-view-auto .scanner-table-section" not in mobile_block
    assert ".scanner-view-auto .scanner-card-results" not in mobile_block
    assert ".scanner-view-cards .scanner-table-section { display: none; }" in css
    assert ".scanner-view-cards .scanner-card-results { display: grid; }" in css
    assert ".scanner-table th.scanner-cell-ticker" in css
    assert ".scanner-table td.scanner-cell-ticker" in css
    assert "position: sticky" in css


def test_static_levels_view_uses_one_levels_scanner_run_button():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    js = Path("app/static/app.js").read_text(encoding="utf-8")

    assert html.count('id="generate"') == 1
    assert "Run Levels + Scanner" in html
    assert 'id="run-scanner"' not in html
    assert "Run Scanner" not in html
    assert 'await loadLevelsAndScanner();' in js
    assert "async function loadLevelsAndScanner()" in js
    assert "runScannerButton" not in js
    assert 'querySelector("#run-scanner")' not in js
    assert "withScannerBusyState" not in js


def test_static_text_inputs_use_explicit_enter_handling():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    js = Path("app/static/app.js").read_text(encoding="utf-8")

    assert '<form id="watchlist-form"' not in html
    assert '<div class="watchlist-form" role="group" aria-labelledby="watchlist-heading">' in html
    assert 'id="add-ticker" class="primary icon-button" type="button"' in html
    assert 'const addTickerButton = document.querySelector("#add-ticker");' in js
    assert 'addTickerButton.addEventListener("click", addTickersFromInput);' in js
    assert "watchlistFormEl" not in js
    assert 'document.addEventListener("keydown", handleTextInputEnter, { capture: true });' in js
    assert "function handleTextInputEnter(event)" in js
    assert 'if (event.key !== "Enter"' in js
    assert "target === tickersInput" in js
    assert "target === reportSearchEl" in js
    assert "target === watchlistNewsSearchEl" in js
    assert "applyReportSearch({ normalizeInput: true });" in js
    assert "applyWatchlistNewsSearch({ normalizeInput: true });" in js


def test_static_theme_uses_light_surfaces_for_light_mode_actions():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    dark_start = css.index("@media (prefers-color-scheme: dark)")
    light_css = css[:dark_start]
    dark_css = css[dark_start:]

    assert "--action-primary-bg: #ccfbf1" in light_css
    assert "--action-primary-text: #12312f" in light_css
    assert "--emphasis-bg: #ccfbf1" in light_css
    assert "--emphasis-text: #12312f" in light_css
    assert "--major-market-bg: #f0fdfa" in light_css
    assert ".primary { background: var(--action-primary-bg)" in light_css
    assert ".card-header { align-items: center; background: var(--emphasis-bg)" in light_css
    assert ".levels-table .current td { background: var(--emphasis-bg)" in light_css
    assert ".market-strip { background: var(--major-market-bg)" in light_css
    assert "background: #12312f" not in light_css

    assert "--action-primary-bg: #0b3b37" in dark_css
    assert "--action-primary-text: #ccfbf1" in dark_css
    assert "--emphasis-bg: #0b2f2d" in dark_css
    assert "--major-market-bg: #080d12" in dark_css


def test_static_score_analytics_mounts_below_charts():
    html = Path("app/static/index.html").read_text(encoding="utf-8")

    assert 'id="charts-section"' in html
    assert 'id="score-analytics-section"' in html
    assert html.index('id="charts-section"') < html.index('id="score-analytics-section"')


def test_static_report_search_filters_charts_and_score_analytics():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    js = Path("app/static/app.js").read_text(encoding="utf-8")

    assert 'id="report-search-status"' in html
    assert 'const reportSearchStatusEl = document.querySelector("#report-search-status");' in js
    assert 'reportSearchEl?.addEventListener("input", applyReportSearch);' in js
    assert 'reportSearchEl?.addEventListener("search", applyReportSearch);' in js
    assert "function applyReportSearch(options = {})" in js
    assert "normalizeTickerSearchInput(reportSearchEl);" in js
    assert "if (signature === lastAppliedReportSearchSignature)" in js
    assert "renderCurrentReport({ searchSignature: signature });" in js
    assert "function renderCurrentReport(options = {})" in js
    assert "lastAppliedReportSearchSignature = options.searchSignature ?? reportSearchSignature();" in js
    assert "updateReportSearchStatus(visibleMetrics.length, currentReport.metrics.length);" in js
    assert "renderCharts();\n  renderScoreAnalytics();" in js
    assert "function visibleScoreTickers()" in js
    assert "return filteredReportMetrics().map((metric) => metric.ticker);" in js
    assert "const metrics = filteredReportMetrics();" in js
    assert 'watchlistNewsSearchEl?.addEventListener("input", applyWatchlistNewsSearch);' in js
    assert 'watchlistNewsSearchEl?.addEventListener("search", applyWatchlistNewsSearch);' in js
    assert "function applyWatchlistNewsSearch(options = {})" in js


def test_static_score_level_basis_stays_synced_with_level_filter():
    js = Path("app/static/app.js").read_text(encoding="utf-8")

    assert 'level_basis: levelFilter' in js
    assert 'if (key === "levelBasis") {\n    setLevelFilter(value);' in js
    assert 'renderScoreSelect("Basis", "levelBasis", levelFilter' in js


def test_static_news_filters_and_article_chips_are_wired():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    js = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")

    assert 'id="watchlist-news-category"' in html
    assert 'id="watchlist-news-source"' in html
    assert 'id="watchlist-news-view"' in html
    assert "1-column cards" in html
    assert "2-column cards" in html
    assert "Compact list" in html
    assert 'const watchlistNewsCategoryEl = document.querySelector("#watchlist-news-category");' in js
    assert 'const watchlistNewsSourceEl = document.querySelector("#watchlist-news-source");' in js
    assert 'const watchlistNewsViewEl = document.querySelector("#watchlist-news-view");' in js
    assert 'newsView: "cards_1"' in js
    assert "function normalizeNewsView(value)" in js
    assert "updateSettings({ newsView: watchlistNewsViewEl.value });" in js
    assert "function newsViewClass(view)" in js
    assert "function renderTickerNewsList(tickerGroup)" in js
    assert "function renderCollapsedArticleRow(article)" in js
    assert "news-collapsed-title" in js
    assert "news-collapsed-date" in js
    assert "news-date-separator" in js
    assert 'aria-hidden="true">|</span><time' in js
    assert "function articleKeyMessage(article)" in js
    assert "function formatNewsDate(value)" in js
    assert "renderArticleCard(article, { compact: true, showSummary: true })" in js
    assert "function updateNewsFilterControls(news)" in js
    assert "function renderNewsChips(article)" in js
    assert "articleMatchesNewsFilters(article, category, source)" in js
    assert ".news-filter" in css
    assert ".news-chips" in css
    assert ".news-collapsed-row" in css
    assert ".news-collapsed-headline" in css
    assert ".news-collapsed-date" in css
    assert ".news-date-separator" in css
    assert ".ticker-news-header h4 { background: #ccfbf1" in css
    assert ".news-key-message" in css
    assert ".ticker-news-grid { display: grid; gap: 14px; grid-template-columns: 1fr; }" in css
    assert ".ticker-news-grid.news-view-cards-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }" in css
    assert ".ticker-news-grid { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit" not in css


def test_static_score_analytics_renders_heat_views():
    js = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")

    assert 'const SCORE_ANALYTICS_RANGES = ["1D", "7D", "30D", "90D", "1Y", "All"];' in js
    assert 'range: "1D"' in js
    assert 'const SCORE_ANALYTICS_CHART_METRICS = ["heat", "setup", "level"];' in js
    assert 'renderScoreSelect("Chart", "chartMetric"' in js
    assert "function renderScoreLineChart(rows)" in js
    assert "function scoreAxisItems(rows, metric)" in js
    assert "function scoreDisplayPoints(row)" in js
    assert "function renderScoreMovementBadge(row)" in js
    assert "function renderScoreHeatThermometer(row)" in js
    assert "function renderScoreHeatStrip(row)" in js
    assert "function heatScore(setupScore, levelScoreNormalized)" in js
    assert ".score-line-panel" in css
    assert ".score-line-x-axis" in css
    assert ".score-line-end-label" in css
    assert ".score-thermometer" in css
    assert ".score-heat-strip" in css
    assert ".score-heat-strip i.empty" in css
    assert ".score-sparkline-scale" in css


def test_static_sector_analytics_renders_visual_dashboard():
    js = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")

    assert 'const SECTOR_ANALYTICS_SETTINGS_STORAGE_KEY = "sector-analytics-settings-v1";' in js
    assert 'trend_range: sectorAnalyticsSettings.range' in js
    assert 'trend_interval: sectorAnalyticsSettings.interval' in js
    assert "function renderSectorToolbar(analytics)" in js
    assert "function renderSectorStrengthMatrix(rows)" in js
    assert "function renderSectorRotationPanel(analytics, rows)" in js
    assert "function themeTrendSeries(analytics)" in js
    assert "function trendSourceLabel(item)" in js
    assert "Leading + confirming" in js
    assert "theme_trend_series" in js
    assert "function renderSectorMacroStrip(series)" in js
    assert "function renderSectorDetailTable(rows)" in js
    assert "function renderPatternThemeCards(summary)" in js
    assert "function renderThemeHeatmap(rows, bucketLabels)" in js
    assert "function buildThemeHeatmapRows(rows)" in js
    assert "Theme Trends" in js
    assert "Basket" in js
    assert "Watchlist" in js
    assert "By Theme" in js
    assert "Ticker Intraday Heatmap" in js
    assert "Daily Pattern Evidence" in js
    assert "Morning low is the lowest percent-from-open" in js
    assert ".sector-dashboard-toolbar" in css
    assert ".sector-rotation-chart" in css
    assert ".sector-strength-matrix" in css
    assert ".matrix-quadrant-label" in css
    assert ".trend-source-pill" in css
    assert ".pattern-theme-card" in css
    assert ".sector-macro-strip" in css
    assert ".sector-detail-table" in css
    assert ".pattern-help" in css
