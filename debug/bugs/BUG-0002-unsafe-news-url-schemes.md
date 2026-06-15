# BUG-0002: Unsafe News URL Schemes

Status: Fixed
Severity: P1 High
Surface: Static UI, Streamlit UI, News
Created: 2026-06-15
Last updated: 2026-06-15
Related PR/commit: Reliability bug-fix follow-up

## Summary

News providers can return article or thumbnail URL fields that are empty, malformed, or use unsafe schemes such as `javascript:` or `data:`. Rendering those values directly risks broken links, broken images, or unsafe browser behavior.

## User Impact

The Stock News view must be trustworthy during fast review. Unsafe or malformed URLs can clutter cards, create dead links, or expose users to unexpected navigation when they are trying to inspect headlines quickly.

## Environment

- App surface: static UI and Streamlit UI
- View: Stock News
- Inputs: provider article payloads from Yahoo Finance or Finnhub
- Watchlist: any ticker with provider-returned headlines
- Provider context: more likely when provider data includes optional image/link fields from third-party publishers

## Reproduction Steps

1. Provide a news payload with an article URL or thumbnail URL such as `javascript:alert(1)`, `data:text/html,...`, an empty string, or a relative path.
2. Render the Stock News view in either UI.
3. Inspect whether the unsafe value appears as a clickable link or image.

## Expected Behavior

Only absolute `http` and `https` URLs should render as links or images. Unsafe, empty, relative, or malformed URL values should become `null` and render as plain text/no image.

## Actual Behavior

Before the fix, some provider URL fields were treated as strings and could pass through to renderers without scheme validation.

## Suspected Cause

News normalization sanitized string shape but did not validate URL schemes consistently. Frontend renderers also needed defensive checks because provider payloads are external data.

## Fix Notes

`NewsService` now normalizes article and thumbnail URLs through one helper that accepts only absolute `http` and `https` URLs with a network location. Static and Streamlit renderers also re-check URLs before creating anchors or image tags.

## Acceptance Criteria

- [x] `http` and `https` article URLs remain clickable.
- [x] `http` and `https` thumbnails remain visible.
- [x] `javascript:`, `data:`, empty, malformed, and relative URLs become `None`/no rendered link.
- [x] Static renderer checks URL safety before building anchors/images.
- [x] Streamlit renderer checks URL safety before building anchors/images.
- [ ] Stock News smoke checklist passes with provider data.

## Notes

Automated tests cover Yahoo-style and Finnhub-style article normalization with unsafe article and thumbnail URLs.
