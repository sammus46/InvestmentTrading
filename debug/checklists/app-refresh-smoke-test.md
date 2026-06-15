# App Refresh Smoke Test

Use this checklist when touching watchlist state, data loading, refresh buttons, Streamlit session state, news rendering, scanner rendering, or chart rendering.

## Setup

- Use a small watchlist first, such as `AAPL, MSFT`, then repeat with the saved production-style watchlist.
- Run the static UI with `python -m uvicorn app.main:app --reload`.
- Run the Streamlit UI with `python -m streamlit run app/streamlit_app.py`.
- Keep the terminal visible for provider warnings, tracebacks, and repeated refresh activity.

## Static UI

- [ ] Open the static app and confirm the saved watchlist renders.
- [ ] Generate levels and confirm report cards, charts, and warnings render without a page crash.
- [ ] Enter invalid ticker tokens such as `<script>`, `AAPL;MSFT`, and an overlong symbol; confirm they are rejected before saving or shown as concise validation errors.
- [ ] Click `Refresh News` and confirm market news, watchlist news, market snapshot, and watchlist performance update.
- [ ] Click `Run Scanner` and confirm setup rows or quiet data notes render.
- [ ] Trigger `Refresh News` again immediately and confirm the button re-enables and status does not get stuck.
- [ ] Trigger a levels/news/scanner refresh, then quickly change the watchlist; confirm older responses do not overwrite the current UI.
- [ ] Remove, add, and reorder a ticker; confirm levels/news/scanner views keep the same order and do not duplicate stale cards.
- [ ] Confirm provider failures show warnings or data notes instead of blanking the entire view.

## Streamlit UI

- [ ] Open the Streamlit app and confirm saved watchlist autoload begins.
- [ ] Confirm the top refresh banner appears only during active loading and clears after completion.
- [ ] Enter invalid ticker tokens such as `<script>`, `AAPL;MSFT`, and an overlong symbol; confirm they are skipped and not saved.
- [ ] Click `Generate Levels`; confirm report cards, charts, and warnings render without a long stuck overlay.
- [ ] Click `Run Scanner`; confirm scanner output updates and the app remains responsive.
- [ ] Switch to `Stock News`, click `Refresh News`, and confirm all news sections return or show clear empty states.
- [ ] Trigger a second refresh immediately after completion; confirm the app accepts it and does not remain greyed out.
- [ ] Add/remove/reorder tickers from the sidebar; confirm the saved watchlist reloads and controls remain responsive.
- [ ] Confirm provider warnings do not prevent future refreshes.

## Failure Capture

When a check fails, capture the exact action, ticker list, local time, terminal output, visible app state, whether controls are disabled, and whether refreshing the browser recovers the app. Open or update a bug file in `debug/bugs/`.
