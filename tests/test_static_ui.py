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
    js = Path("app/static/app.js").read_text(encoding="utf-8")

    assert 'reportSearchEl?.addEventListener("input", () => {\n  renderCurrentReport();\n});' in js
    assert "function renderCurrentReport()" in js
    assert "renderCharts();\n  renderScoreAnalytics();" in js
    assert "function visibleScoreTickers()" in js
    assert "return filteredReportMetrics().map((metric) => metric.ticker);" in js


def test_static_score_level_basis_stays_synced_with_level_filter():
    js = Path("app/static/app.js").read_text(encoding="utf-8")

    assert 'level_basis: levelFilter' in js
    assert 'if (key === "levelBasis") {\n    setLevelFilter(value);' in js
    assert 'renderScoreSelect("Basis", "levelBasis", levelFilter' in js
