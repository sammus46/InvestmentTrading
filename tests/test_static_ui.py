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
