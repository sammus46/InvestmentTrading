# BUG-0003: Loose Ticker Validation And Provider Log Clutter

Status: Fixed
Severity: P1 High
Surface: Backend, Static UI, Streamlit UI, Market Data
Created: 2026-06-15
Last updated: 2026-06-15
Related PR/commit: Reliability bug-fix follow-up

## Summary

Ticker input accepted arbitrary text, which allowed emoji, HTML-like strings, shell punctuation, malformed futures suffixes, and very long tokens to reach provider calls. Bad symbols could produce slow responses, noisy macOS launch logs, and confusing warnings.

## User Impact

A watchlist typo should fail quickly and clearly. Slow invalid-symbol provider calls make refreshes feel hung, and provider stderr/stdout noise makes real launch errors harder to see.

## Environment

- App surface: backend request models, static watchlist controls, Streamlit watchlist controls
- Endpoints: `/api/levels`, `/api/scanner`, `/api/news`, `/api/market-snapshot`, `/api/chart-history`, `/api/reports/pdf`
- Provider context: yfinance calls for invalid symbols
- OS: macOS launch logs are especially visible when running from Terminal

## Reproduction Steps

1. Enter a watchlist token such as `<script>`, `AAPL;rm`, `ABC==F`, an emoji, or a symbol longer than 20 characters.
2. Generate levels, refresh news, run scanner, or request chart history.
3. Observe whether the app saves the token, calls providers, logs provider noise, or returns a slow warning response.

## Expected Behavior

Supported Yahoo-style symbols normalize consistently:

- `$TSLA` becomes `TSLA`
- `BRK.B` and `BRK/B` become `BRK-B`
- `^GSPC`, `GC=F`, and `BTC-USD` remain valid

Unsafe or malformed tokens should be rejected before provider calls, with concise validation messages. Static and Streamlit watchlists should skip invalid tokens rather than persisting them.

## Actual Behavior

Before the fix, request models uppercased and deduplicated tokens but did not validate symbol shape. Invalid symbols could flow into provider calls and clutter logs.

## Suspected Cause

Ticker cleanup lived as a permissive request-model helper and was not shared by all app surfaces.

## Fix Notes

Ticker parsing now uses shared backend helpers for splitting, normalization, validation, and deduplication. All request models share the same validator. The static UI mirrors validation before saving watchlist tokens and shows skipped invalid tokens in a short status message. Streamlit watchlist entry also skips invalid tokens with a visible warning. Expected yfinance stdout/stderr noise is suppressed inside provider calls.

## Acceptance Criteria

- [x] Valid Yahoo-style symbols are accepted and normalized consistently.
- [x] Unsafe, malformed, empty, overlong, and script-like symbols return clear `422` validation errors in backend requests.
- [x] Static watchlist controls do not save invalid tokens.
- [x] Streamlit watchlist controls do not save invalid tokens.
- [x] Provider calls suppress expected yfinance stdout/stderr clutter.
- [ ] Static and Streamlit smoke checks confirm invalid token handling in the running UIs.

## Notes

This intentionally changes invalid ticker behavior from delayed `200` responses with warnings to fast validation failures.
