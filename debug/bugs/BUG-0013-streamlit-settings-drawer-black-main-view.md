# BUG-0013: Streamlit Settings Drawer Blacks Out Main View

Status: Fixed
Severity: P1 High
Surface: Streamlit UI, Settings
Created: 2026-06-16
Last updated: 2026-06-16
Related PR/commit: TBD

## Summary

On desktop, clicking the top-right Streamlit settings button could render the settings panel while the main app area behind it became a blank black surface instead of staying visible behind a right-side drawer.

## User Impact

Settings are meant to be a quick overlay for changing defaults, chart options, and refresh behavior. A blacked-out main view makes the app look broken and prevents users from keeping context while adjusting preferences.

## Environment

- App surface: Streamlit UI
- View: any main Streamlit view
- Control: top-right settings gear
- Command used to run app: `python -m streamlit run app/streamlit_app.py`
- Provider context: not provider-dependent

## Reproduction Steps

1. Start the Streamlit app with `python -m streamlit run app/streamlit_app.py`.
2. Open the app on a desktop-width viewport.
3. Click the top-right settings gear.
4. Observe whether the settings drawer opens from the right while the main app remains visible.

## Expected Behavior

The settings panel should behave as a right-side drawer below the sticky brand bar. The main app should remain visible and normally laid out behind it. The drawer should scroll independently and close when the `<<` button is clicked.

## Actual Behavior

The settings panel appears, but the main content area behind it can become a blank black surface.

## Cause

The CSS selector `div[data-testid="stVerticalBlock"]:has(.streamlit-settings-panel-marker)` could match Streamlit ancestor layout blocks that contain the settings marker, not only the innermost settings panel block. When those ancestors received the fixed-position drawer styling, the main page layout could be displaced or covered.

## Fix Notes

The settings drawer CSS now scopes the panel surface and related button styling to the innermost matching `stVerticalBlock` by excluding blocks that contain another vertical block with the settings marker. The theme-token surface selector uses the same scoped selector, so dark/light styling still applies only to the actual drawer.

## Diagnostics To Capture

- Browser viewport size and Streamlit theme mode.
- Whether the main content remains visible immediately after the gear click.
- Whether the drawer scrolls independently when its contents exceed the viewport.
- Whether the `<<` close button restores the prior view.

## Acceptance Criteria

- [x] Base drawer CSS targets the innermost settings panel block.
- [x] Theme surface CSS targets the same scoped settings panel selector.
- [x] Settings panel remains fixed to the right below the sticky brand bar.
- [x] Automated regression coverage prevents the broad selector from returning.
- [ ] Desktop smoke confirms the main view remains visible while opening and closing settings.
