# BUG-0007: Static Raw JSON Validation Messages

Status: Fixed
Severity: P2 Medium
Surface: Static UI, Backend Validation
Created: 2026-06-15
Last updated: 2026-06-15
Related PR/commit: Reliability bug-fix follow-up

## Summary

When the backend returned Pydantic validation errors, the static UI could surface raw JSON details instead of a short readable message.

## User Impact

Raw validation JSON is noisy and slows down correction. A user entering a bad ticker should see exactly what to fix without parsing API internals.

## Environment

- App surface: static UI
- Endpoints: any JSON API call with request validation
- Example input: invalid ticker text or malformed chart request

## Reproduction Steps

1. Send an invalid ticker or malformed request through the static UI.
2. Observe the status/error message.

## Expected Behavior

The static UI should show concise messages such as `unsupported ticker symbol: <token>` or `ticker symbol is too long: <token>`.

## Actual Behavior

Before the fix, nested validation details could appear as raw JSON or overly technical text.

## Suspected Cause

The static error formatter did not flatten FastAPI/Pydantic `detail` arrays.

## Fix Notes

The static `readableError` helper now extracts and joins validation `msg` values from `detail` arrays before falling back to generic response text.

## Acceptance Criteria

- [x] Pydantic validation arrays become concise status text.
- [x] Non-validation errors still fall back to the existing message behavior.
- [ ] Static smoke confirms invalid ticker entry shows a readable message in the browser.

## Notes

This is frontend presentation only; backend status codes remain unchanged.
