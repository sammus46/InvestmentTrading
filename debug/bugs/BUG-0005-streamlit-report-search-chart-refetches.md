# BUG-0005: Streamlit Report Search Causes Chart-History Refetches

Status: Fixed
Severity: P2 Medium
Surface: Streamlit UI, Charts
Created: 2026-06-15
Last updated: 2026-06-15
Related PR/commit: Reliability bug-fix follow-up

## Summary

Filtering the Streamlit report by ticker could create chart-history loads for the filtered subset instead of reusing already-loaded chart history.

## User Impact

Search is a UI-only narrowing action. If it creates provider calls, the app can feel slow, show unnecessary refresh work, or risk provider rate limits while the user is just trying to focus on a subset of tickers.

## Environment

- App surface: Streamlit UI
- View: Trading Levels
- Controls: report ticker search, chart range/interval controls
- Provider context: yfinance chart history

## Reproduction Steps

1. Load a multi-ticker Streamlit report.
2. Type a single ticker in the report search box.
3. Change or clear the search.
4. Observe whether chart-history provider calls happen for each filtered subset.

## Expected Behavior

Search should filter report cards and visible charts locally. Chart data should load for the active watchlist/range/interval and then be displayed for the currently visible tickers without refetching on every search subset.

## Actual Behavior

Before the fix, chart-history cache keys could follow the filtered report subset and create extra provider work.

## Suspected Cause

The chart renderer received the filtered report as its data source instead of separating loaded chart data from visible ticker selection.

## Fix Notes

Streamlit chart rendering now fetches and caches chart history for the full loaded report/watchlist while accepting a separate `visible_tickers` list for display. Filtering the report changes only which already-loaded chart sections are rendered.

## Acceptance Criteria

- [x] Report search can hide/show chart sections without changing the chart-history request key.
- [x] Visible charts follow the filtered ticker set.
- [x] Clearing search restores visible charts without provider calls caused only by search.
- [ ] Streamlit smoke confirms no refresh banner appears for search-only interactions.

## Notes

Changing chart range or interval still intentionally refreshes chart history.
