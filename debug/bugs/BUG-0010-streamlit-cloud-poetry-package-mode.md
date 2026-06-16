# BUG-0010: Streamlit Cloud Poetry Package Mode

Status: Fixed
Severity: P0 Critical
Surface: Streamlit Community Cloud, Deployment
Created: 2026-06-16
Last updated: 2026-06-16
Related PR/commit: TBD

## Summary

Streamlit Community Cloud installed Python dependencies from `pyproject.toml` successfully, then failed before app startup while Poetry tried to install the root project package.

## User Impact

The hosted Streamlit app could not deploy or start. Users could not access the latest app version even though dependency resolution completed.

## Environment

- App surface: Streamlit Community Cloud
- Browser: Streamlit Cloud deploy page
- OS: Streamlit Cloud Linux container
- Command used to run app: Streamlit Cloud deployment for `app/streamlit_app.py`
- Watchlist: Not applicable
- Market/provider context: Not applicable

## Reproduction Steps

1. Deploy branch `codex/streamlit-clean-deploy` to Streamlit Community Cloud.
2. Use `app/streamlit_app.py` as the main file path.
3. Let Streamlit Cloud process dependencies from `pyproject.toml`.
4. Observe the Poetry install step after dependency installation.

## Expected Behavior

Poetry should install project dependencies and Streamlit should continue to app startup.

## Actual Behavior

Poetry attempted to install the current project as `investment-trading` and failed with `No file/folder found for package investment-trading`.

## Suspected Cause

Poetry package mode is enabled by default. This repository is an application with an `app/` module, not a publishable package directory named `investment_trading`, so Poetry could not install the root project package.

## Diagnostics To Capture

- Streamlit Cloud UTC logs.
- Branch and commit SHA.
- Main file path.
- Python version selected in advanced settings.
- Dependency file selected by Streamlit Cloud.
- Whether the log reaches Streamlit app startup after dependency processing.

## Acceptance Criteria

- [x] `pyproject.toml` disables Poetry package mode.
- [x] Regression test asserts Poetry package mode remains disabled.
- [x] README documents Streamlit Cloud deployment metadata requirements.
- [ ] Streamlit Cloud deploy logs pass dependency processing and reach app startup.

## Notes

2026-06-16 fix: add `[tool.poetry] package-mode = false` so Poetry uses dependency-only behavior for Streamlit Cloud deployments. This keeps `pyproject.toml` as the single dependency source without requiring a `requirements.txt` fallback or renaming the app package.
