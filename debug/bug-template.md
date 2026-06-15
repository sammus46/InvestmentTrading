# BUG-XXXX: Short Title

Status: Known
Severity: P2 Medium
Surface: Static UI | Streamlit UI | Backend | PDF | Scanner | News
Created: YYYY-MM-DD
Last updated: YYYY-MM-DD
Related PR/commit: TBD

## Summary

One or two sentences describing the bug and why it matters.

## User Impact

Describe how this affects fast trading decisions, refresh confidence, app smoothness, or trust in displayed data.

## Environment

- App surface:
- Browser:
- OS:
- Command used to run app:
- Watchlist:
- Market/provider context:

## Reproduction Steps

1. Start from a clean app state or describe the required saved state.
2. Perform the smallest set of actions that reproduces the issue.
3. Record whether the issue happens every time, intermittently, or only after first load.

## Expected Behavior

Describe the intended behavior in observable terms.

## Actual Behavior

Describe what the app does instead. Include timing, stuck state, grey overlay, disabled controls, clutter, stale data, console output, or warnings.

## Suspected Cause

Current hypothesis. Mark unknowns clearly.

## Diagnostics To Capture

- Timestamp and local timezone.
- Tickers used.
- Whether levels/news/scanner/chart refresh functions reran.
- Browser console or terminal errors.
- Provider warnings or rate-limit messages.
- Screenshots or short screen recording if visual timing matters.

## Acceptance Criteria

- [ ] Bug no longer reproduces with the documented steps.
- [ ] User can refresh again immediately after the interaction.
- [ ] Existing warnings remain visible but do not clutter or block the workflow.
- [ ] Relevant checklist passes.
- [ ] Automated regression added when practical.

## Notes

Add investigation notes, discarded hypotheses, and follow-up ideas here.
