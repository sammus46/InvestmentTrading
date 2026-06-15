# BUG-0001: Streamlit News Expansion Greys Out Page

Status: Known  
Severity: P1 High  
Surface: Streamlit UI, Watchlist News  
Created: 2026-06-15  
Last updated: 2026-06-15  
Related PR/commit: PR #29 follow-up

## Summary

In the Streamlit app, expanding a Watchlist News ticker card with the down arrow can grey out the whole page and take a long time to update on the first expansion. Later arrow clicks can become responsive, which suggests first-use rerender or initialization cost rather than a permanent failure.

## User Impact

The News view is intended for quick trading context. A long grey overlay makes the app feel hung and can reduce confidence that news and levels are up to date. This is especially risky when a user needs to refresh or inspect headlines quickly before making a decision.

## Environment

- App surface: Streamlit UI
- View: Stock News
- Section: Watchlist News
- Control: ticker-card down arrow expansion
- Watchlist: saved watchlist with at least one ticker returning more than five headlines
- Provider context: can be worse when provider responses, chart iframes, or embedded X.com content are slow

## Reproduction Steps

1. Start Streamlit with `python -m streamlit run app/streamlit_app.py`.
2. Use a saved watchlist or add tickers that return more than five watchlist news headlines.
3. Wait for the app to load levels, scanner, news, market snapshot, and charts.
4. Open the `Stock News` view.
5. In `Watchlist News`, click the down arrow on a ticker news card.
6. Observe the first expansion timing, page overlay, and whether the app feels blocked.
7. Click expansion arrows again after the first update and compare responsiveness.

## Expected Behavior

Expanding or collapsing a ticker news card should feel local and fast. The visible card should update within about one second after data is already loaded, no provider refresh should start, and the user should be able to immediately keep scrolling, filtering, or refreshing news.

## Actual Behavior

The whole Streamlit page can grey out and take a long time to update on the first expansion. The app may look temporarily unavailable even though the interaction is only a local card expansion. Later expansion toggles can be faster.

## Suspected Cause

The expansion control likely triggers a full Streamlit script rerun. Even when data is cached, the first rerun may still rebuild expensive UI sections such as charts, iframes, embedded X.com content, or large news/card markup. The problem should be verified before a fix is selected.

## Diagnostics To Capture

- Whether any cached data builders run during card expansion.
- Time from arrow click to page becoming interactive again.
- Whether `build_news`, `build_report`, `build_scanner`, `build_market_snapshot`, or chart history calls execute.
- Whether X.com iframe or chart iframe rendering dominates the rerun.
- Browser console errors, terminal logs, and provider warnings.
- Whether the problem reproduces with a two-ticker watchlist.

## Acceptance Criteria For Future Fix

- [ ] First expansion and collapse complete in about one second after news has loaded.
- [ ] Expansion does not trigger provider fetches or refresh banners.
- [ ] The page does not show a long grey overlay beyond a normal brief Streamlit rerun.
- [ ] User can immediately refresh news after expanding/collapsing cards.
- [ ] Watchlist News search still works with one or multiple tickers.
- [ ] `debug/checklists/trading-decision-ui-smoke-test.md` passes for the News view.

## Notes

Do not mark this fixed solely because expansion arrows exist. The tracked issue is first-expansion responsiveness and the full-page grey overlay experience.
