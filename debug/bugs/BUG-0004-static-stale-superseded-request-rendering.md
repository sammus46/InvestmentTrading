# BUG-0004: Static Stale Superseded Request Rendering

Status: Fixed
Severity: P1 High
Surface: Static UI
Created: 2026-06-15
Last updated: 2026-06-15
Related PR/commit: Reliability bug-fix follow-up

## Summary

Rapid watchlist edits, refresh clicks, chart changes, layout changes, or search changes could allow an older static UI request to finish after a newer one and render stale levels, news, scanner rows, snapshots, or chart history.

## User Impact

Stale trading levels or news can mislead quick decisions. The app should not show outdated cards after the user has already changed the watchlist or requested fresher data.

## Environment

- App surface: static FastAPI UI
- Views: Trading Levels and Stock News
- Triggers: saved watchlist autoload, Generate Levels, Refresh News, Run Scanner, chart range/interval controls, watchlist reorder/remove/add
- Provider context: easiest to reproduce when provider calls are slow or rate-limited

## Reproduction Steps

1. Start the static UI with a saved watchlist.
2. Trigger levels/news/scanner loading.
3. Before the request completes, change the watchlist or trigger another refresh.
4. Observe whether the older response renders after the newer state is visible.

## Expected Behavior

Superseded requests should be aborted when possible. Any response that still arrives after it was superseded should be ignored and must not update the current UI.

## Actual Behavior

Before the fix, requests did not carry per-surface abort signals or sequence tokens, so late responses could still update the page.

## Suspected Cause

The static API client had no `AbortController` support, and individual surfaces did not track request ownership.

## Fix Notes

The static API client now accepts abort signals. Levels, news, scanner, market snapshot, global chart history, and per-ticker chart history each track their own controller and sequence token. Superseded requests are aborted, and stale responses are ignored before rendering.

## Acceptance Criteria

- [x] Static API helpers accept abort signals.
- [x] Levels, news, scanner, snapshot, and chart loads use request tokens.
- [x] Per-ticker chart history requests are independently abortable.
- [x] Abort errors do not show user-facing failure messages.
- [ ] Manual static smoke confirms rapid refresh/watchlist changes do not render stale cards.

## Notes

This is a presentation/orchestration fix only. It does not change trading calculations, scanner scoring, or response shapes.
