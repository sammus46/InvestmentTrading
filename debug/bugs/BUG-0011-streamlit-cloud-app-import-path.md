# BUG-0011: Streamlit Cloud App Import Path

Status: Fixed
Severity: P0 Critical
Surface: Streamlit Community Cloud, Deployment
Created: 2026-06-16
Last updated: 2026-06-16
Related PR/commit: TBD

## Summary

Streamlit Community Cloud reached app startup, then failed to import the local `app` package from `app/streamlit_app.py`.

## User Impact

The hosted Streamlit app still could not start after dependency installation succeeded. Users saw a deployment that got further than previous attempts but ended in a runtime import crash.

## Environment

- App surface: Streamlit Community Cloud
- Browser: Streamlit Cloud deploy logs
- OS: Streamlit Cloud Linux container
- Command used to run app: Streamlit Cloud deployment for `app/streamlit_app.py`
- Watchlist: Not applicable
- Market/provider context: Not applicable

## Reproduction Steps

1. Deploy branch `codex/streamlit-poetry-deploy-fix` to Streamlit Community Cloud.
2. Use `app/streamlit_app.py` as the main file path.
3. Let Streamlit Cloud install dependencies from `pyproject.toml`.
4. Observe Streamlit app startup after dependency processing.

## Expected Behavior

`app/streamlit_app.py` should import local modules such as `app.models` and continue to render the Streamlit UI.

## Actual Behavior

Streamlit started, then raised `ModuleNotFoundError: No module named 'app'` at `from app.models import ...`.

## Suspected Cause

Streamlit executed the entrypoint from inside the `app/` directory while Poetry non-package mode left the repository root uninstalled. The repo root was not on `sys.path`, so absolute imports from the local `app` package failed.

## Diagnostics To Capture

- Streamlit Cloud UTC logs.
- Branch and commit SHA.
- Main file path.
- Python version selected in advanced settings.
- Whether logs show dependency success before runtime import failure.
- The first import traceback line from `app/streamlit_app.py`.

## Acceptance Criteria

- [x] Streamlit entrypoint inserts the repository root into `sys.path` before importing local `app` modules.
- [x] Regression test asserts bootstrap order before `from app.models import`.
- [x] README documents the import-path deployment failure.
- [ ] Streamlit Cloud deploy logs reach app startup without `ModuleNotFoundError`.

## Notes

2026-06-16 fix: add a startup bootstrap in `app/streamlit_app.py` so the repository root is available for absolute `app.*` imports even when Streamlit runs the file from inside the `app/` directory.
