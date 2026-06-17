# Trading Decision UI Smoke Test

Use this checklist when changing layout, filters, expand/collapse controls, news cards, report cards, chart controls, or warning presentation. The app should help a user make fast decisions without visual clutter or stale state.

## Levels View

- [ ] Report cards are visible after load and use the saved watchlist order.
- [ ] `Grid`, `Price Ladder`, `Compact`, and `Compare` layouts switch without refetching data.
- [ ] The report search box supports one ticker and multiple tickers separated by commas, spaces, or newlines.
- [ ] Static and Streamlit report search behave the same for the same ticker tokens.
- [ ] Search filtering does not change PDF output or saved watchlist order.
- [ ] Charts follow the filtered report tickers and hide cleanly when there are no matches.
- [ ] Score Analytics appears below all charts, follows the same report search ticker filter, and does not change PDF output or saved watchlist order.
- [ ] Changing the `Levels` filter also changes the Score Analytics level basis while charts remain visible for the searched tickers.
- [ ] Warning/details areas are collapsed or compact enough that they do not dominate the decision view.

## News View

- [ ] General Market News is readable and does not mix with watchlist-specific filters.
- [ ] Watchlist News search supports one ticker and multiple tickers separated by commas, spaces, or newlines.
- [ ] Watchlist News search preserves the existing watchlist/news order.
- [ ] Ticker news cards show a compact top-headlines state by default.
- [ ] Expansion arrows reveal additional categorized headlines without losing scroll position or triggering a long grey overlay.
- [ ] Collapsing an expanded card returns to the compact state quickly.
- [ ] Article links and thumbnails render only for normal `http` or `https` provider URLs.
- [ ] Empty results show a clear message and do not leave stale cards on screen.

## Refresh Confidence

- [ ] A user can refresh levels/news/scanner data after using filters and expansion controls.
- [ ] No control remains disabled after a completed refresh.
- [ ] The latest generated/refreshed timestamp or status is visible where applicable.
- [ ] Provider warnings are specific to the affected ticker or section and do not look like full-app failures.

## Fast Decision Acceptance

The screen passes when a user can identify current levels, nearby support/resistance, relevant watchlist news, market context, and scanner notes in under a minute without needing to reload the browser or restart the app.
