# Debug and Bug Testing

This folder tracks reliability bugs, reproduction notes, and manual smoke tests for the static FastAPI UI and Streamlit UI. The goal is simple: the apps should stay smooth, refreshable, and dependable while showing trading levels, scanner context, news, and charts for quick trading decisions.

## Folder Map

- `bug-registry.md`: index of known, fixed, and verified bugs.
- `bug-template.md`: copy this file when opening a new bug record.
- `bugs/`: one Markdown file per bug.
- `checklists/`: repeatable manual checks for refresh reliability and fast-decision UI behavior.

## Bug Workflow

1. Capture the symptom with the app surface, exact action, ticker/watchlist, time, and whether market data providers were slow or rate-limited.
2. Reproduce with the smallest watchlist that still shows the issue.
3. Add or update a bug file under `debug/bugs/`.
4. Update `debug/bug-registry.md` with status, severity, and next action.
5. Fix in code only after the bug has a clear expected behavior and verification checklist.
6. After fixing, mark the bug `Fixed`, run the relevant checklist, then mark it `Verified` only when the issue is no longer reproducible.

## Status Values

- `Known`: recorded and reproducible enough to track, but no fix has landed.
- `Investigating`: actively being reproduced or root-caused.
- `Fixed`: code or docs changed to address the issue, but verification is not complete.
- `Verified`: fix passed the documented acceptance checks.
- `Won't fix`: deliberately not changing, with rationale in the bug file.

## Severity

- `P0 Critical`: app crashes, cannot start, loses saved watchlist data, or blocks all report/news refreshes.
- `P1 High`: blocks fast decision-making, causes long hangs, stale display, or severe UI unresponsiveness.
- `P2 Medium`: confusing or cluttered behavior with a practical workaround.
- `P3 Low`: cosmetic issue or minor polish item.

## When To Add Automated Regression Tests

Promote a bug into an automated test when the fix changes backend calculations, API response shape, scanner/news logic, parsing, cache invalidation, or a pure helper function. For UI-only Streamlit/browser behavior that is difficult to automate locally, keep the manual checklist current and add unit tests around any extracted helper logic.

## Manual Smoke Cadence

Run the refresh smoke test before merging changes that touch data loading, refresh buttons, watchlist state, Streamlit session state, news rendering, report rendering, or chart rendering. Run the trading-decision UI smoke test before merging changes that affect on-screen layout, filters, expand/collapse controls, or warnings.

## Reliability Definition

A bug is not considered resolved until the user can refresh levels/news/scanner data repeatedly, search/filter without losing data, expand/collapse dense UI sections, and recover from provider warnings without getting stuck behind disabled controls, long grey overlays, stale content, or a broken page.
