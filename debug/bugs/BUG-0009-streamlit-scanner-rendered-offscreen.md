# BUG-0009: Streamlit Scanner Rendered Offscreen

Status: Fixed
Severity: P1 High
Surface: Streamlit UI, Scanner
Created: 2026-06-16
Last updated: 2026-06-16
Related PR/commit: TBD

## Summary

The scanner table could be loaded and rendered in the Streamlit DOM but not visibly appear near the Scanner header/control. Users saw the loading bar disappear and assumed scanner output was missing even though the table existed offscreen in the page flow.

## User Impact

This breaks refresh confidence during fast trading review: the app looks done loading, but the scanner decision surface is not where the user is looking. The user may rerun scanner unnecessarily or miss setup rows that are already available.

## Environment

- App surface: Streamlit Trading Levels view
- Browser: Codex in-app browser against `http://localhost:8501`
- OS: macOS
- Command used to run app: `python -m streamlit run app/streamlit_app.py`
- Watchlist: Reproduced with saved watchlist including `YSS`, `RKLB`, `SPCX`, `INTC`, `AMD`, `MU`, `NVT`, `FIX`
- Market/provider context: yfinance levels/scanner data had already loaded

## Reproduction Steps

1. Start the Streamlit app with a saved watchlist.
2. Let initial levels and scanner autoload finish.
3. Observe the Scanner header and loading/progress area near the top of the page.
4. Scroll or inspect the DOM after data loads.

## Expected Behavior

The Setup Scanner tabs and dataframe should render directly under the Scanner header/control as soon as scanner data is available.

## Actual Behavior

The scanner response was present in Streamlit state and scanner DOM existed, but the scanner output slot was separated from the Scanner controls by the long Levels/Charts flow. In the browser, the visible viewport showed charts while the scanner table measured above the viewport, making it appear absent to the user.

## Suspected Cause

The Streamlit placeholders were created in an order that did not match the intended visual grouping. `report_slot`, `scanner_slot`, and `chart_slot` were independent placeholders, and rerenders could leave the scanner output detached from the visible Scanner section.

## Diagnostics To Capture

- Browser DOM positions for `Setup Scanner`, `Intraday Pattern Analysis`, and `[data-testid="stDataFrame"]`.
- Main Streamlit scroll position and document height.
- Whether `st.session_state.scanner` is non-null after loading.
- Screenshot of the first viewport after loading completes.
- Any Streamlit rerun or placeholder-order changes near `report_slot`, `scanner_slot`, and `chart_slot`.

## Acceptance Criteria

- [x] Scanner table renders directly below the Scanner controls after initial autoload.
- [x] Scanner remains visible after the loading/progress banner disappears.
- [x] Levels and charts render below scanner, not between Scanner controls and scanner output.
- [x] Automated regression guards scanner placeholder order.
- [x] Full test suite passes.

## Notes

2026-06-16 fix: moved `scanner_slot = st.empty()` immediately after the Scanner controls and before `report_slot = st.empty()`. Added `test_streamlit_scanner_slot_stays_with_scanner_controls` so future layout changes preserve the visual grouping.
