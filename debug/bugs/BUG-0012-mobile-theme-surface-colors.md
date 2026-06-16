# BUG-0012: Mobile Theme Surface Colors

Status: Fixed
Severity: P2 Medium
Surface: Static UI, Streamlit UI, Mobile
Created: 2026-06-16
Last updated: 2026-06-16
Related PR/commit: TBD

## Summary

Mobile light mode used dark teal or near-black fills with white text for large app surfaces such as primary action buttons, metric headers, table identity rows, and market strips. Dark mode also risked inheriting light-mode treatments when selectors were not tied to semantic theme tokens.

## User Impact

The UI looked visually inverted in light mode and made common actions feel heavier than the surrounding app chrome. On small screens this was especially distracting because large CTA buttons and card headers occupied much of the viewport.

## Environment

- App surface: Streamlit mobile UI, static mobile UI
- Browser: Mobile browser or Streamlit Cloud webview
- OS: iOS/mobile; system theme can affect Streamlit `system` mode
- Command used to run app: `python -m streamlit run app/streamlit_app.py` or FastAPI static frontend
- Watchlist: Any saved watchlist
- Market/provider context: Not provider-dependent

## Reproduction Steps

1. Open the mobile Streamlit app in light mode or system mode while the OS is light.
2. View the Trading Levels tab before and after generating levels.
3. Scroll to Levels, Scanner, Stock News, or Sector Analytics sections.
4. Compare large buttons, metric card headers, current table rows, major market strips, and active tab/radio treatments against the app's light background.

## Expected Behavior

Light mode should use light teal or neutral light surfaces with dark readable text. Dark mode should use dark surfaces with light readable text. System mode should follow the resolved OS theme without mixing the opposite theme's surface/text pairings.

## Actual Behavior

Light mode used hard dark fills, including `#12312f`, `#111827`, or `--brand-deep`, with forced white text on large controls and headers. The combination looked like a dark-mode component dropped into a light-mode page.

## Cause

A previous mobile readability fix solved low-contrast dark headers by forcing broad selectors to `--brand-deep` plus white text. That treated the brand color as a universal surface color rather than separating semantic roles such as primary action, emphasis header, active navigation, sidebar toggle, and market strip. Because those selectors applied after the theme marker bridge, they overrode the intended light-mode palette and also made future system-mode behavior fragile.

## Diagnostics To Capture

- App theme selection: Light, Dark, or System.
- OS/browser resolved color scheme when app theme is System.
- Screenshot of first viewport and a generated levels card.
- Screenshot of Stock News and Sector Analytics after refresh.
- Whether the static FastAPI UI shows the same light/dark surface pairing.

## Acceptance Criteria

- [x] Light mode primary actions use light teal backgrounds with dark teal text.
- [x] Light mode metric/card headers and current table rows use light emphasis surfaces with dark text.
- [x] Dark mode keeps dark emphasis surfaces with light text.
- [x] System mode inherits the resolved light/dark token set instead of hardcoded opposite-theme colors.
- [x] Static and Streamlit CSS use semantic tokens for the affected surfaces.
- [x] Automated regression checks cover the affected CSS tokens.
- [ ] Mobile smoke check confirms light, dark, and system modes on the hosted app.

## Notes

2026-06-16 fix: introduce semantic theme tokens for primary actions, emphasis headers, active controls, sidebar toggles, and major market strips. Use light teal fills in light mode and dark teal fills in dark mode, with text colors paired by token rather than forced globally.

During local mobile verification, the Streamlit theme bridge failed on Streamlit 1.45 because `st.iframe` was not available. The fix also routes iframe-backed HTML through `streamlit.components.v1.html`, which keeps the bridge, chart embeds, and X timeline embeds compatible with the supported Streamlit API.
