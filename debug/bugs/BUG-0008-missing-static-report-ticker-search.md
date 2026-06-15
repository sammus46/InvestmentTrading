# BUG-0008: Missing Static Report Ticker Search

Status: Fixed
Severity: P2 Medium
Surface: Static UI, Trading Levels
Created: 2026-06-15
Last updated: 2026-06-15
Related PR/commit: Reliability bug-fix follow-up

## Summary

The Streamlit Trading Levels report had ticker search, but the static UI report toolbar did not. Users could not quickly narrow a large static report to one or more tickers without changing the watchlist or regenerating levels.

## User Impact

Large watchlists are hard to scan under time pressure. Search should let users focus on a small ticker set without changing saved order, reloading provider data, or affecting PDF output.

## Environment

- App surface: static UI
- View: Trading Levels
- Controls: report toolbar, report layout dropdown, charts

## Reproduction Steps

1. Load the static UI with a multi-ticker watchlist.
2. Generate levels.
3. Try to filter the report to `AAPL MSFT` or `AAPL, MSFT`.

## Expected Behavior

The report toolbar should include ticker search. It should accept one ticker or multiple tickers separated by commas, spaces, or newlines, filter report cards and charts locally, and leave saved watchlist/PDF output unchanged.

## Actual Behavior

Before the fix, no static report ticker search was available.

## Suspected Cause

The report layout switcher added presentation options but did not add a static-side ticker filter matching the Streamlit report search.

## Fix Notes

The static report toolbar now includes a report ticker search input. Filtering uses the same multi-token normalization style as watchlist input, renders only matching report cards and charts, and does not refetch levels.

## Acceptance Criteria

- [x] Static report toolbar includes a ticker search input.
- [x] Search accepts comma, space, and newline-separated tickers.
- [x] Search filters report cards locally.
- [x] Search filters rendered chart sections locally.
- [x] Search does not change saved watchlist order or PDF output.
- [ ] Static trading-decision smoke confirms the browser behavior.

## Notes

Invalid search tokens simply produce no matches in the report filter; invalid watchlist tokens are handled separately by BUG-0003.
