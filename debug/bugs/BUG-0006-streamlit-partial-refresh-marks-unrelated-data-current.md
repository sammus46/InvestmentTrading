# BUG-0006: Streamlit Partial Refresh Marks Unrelated Data Current

Status: Fixed
Severity: P1 High
Surface: Streamlit UI, Data Freshness
Created: 2026-06-15
Last updated: 2026-06-15
Related PR/commit: Reliability bug-fix follow-up

## Summary

Partial Streamlit refresh actions could mark unrelated datasets as current. For example, refreshing news could make report, scanner, or chart data appear current even when those datasets were not refreshed.

## User Impact

The app needs high confidence about freshness. Marking unrelated sections current can hide stale data and make a user think levels or scanner output were refreshed when only news was updated.

## Environment

- App surface: Streamlit UI
- Actions: Generate Levels, Refresh News, Run Scanner, auto-refresh/load
- Datasets: report, scanner, news, market snapshot, chart history

## Reproduction Steps

1. Load a saved watchlist in Streamlit.
2. Refresh only News.
3. Observe whether report or scanner loaded-state keys are also updated.
4. Repeat with Run Scanner and confirm news/report state is not incorrectly marked current.

## Expected Behavior

Each dataset should track freshness independently. A partial refresh should mark only the dataset(s) it actually loaded as current.

## Actual Behavior

Before the fix, loaded-state tracking was too broad and could treat the current ticker/metric state as globally current after a partial refresh.

## Suspected Cause

Streamlit session-state freshness used a shared refresh token/key rather than dataset-specific keys and tokens.

## Fix Notes

Streamlit now tracks dataset freshness separately for report, scanner, news, market snapshot, and chart history. Partial refresh buttons bump and mark only the relevant dataset tokens.

## Acceptance Criteria

- [x] News refresh marks news and market snapshot current only.
- [x] Run Scanner marks scanner current only.
- [x] Generate Levels/full load marks loaded datasets current together.
- [x] Unit coverage confirms dataset freshness is independent.
- [ ] Streamlit refresh smoke confirms banners appear only for real data refreshes.

## Notes

This is a state-management fix. It does not change response payloads or persistence schema.
