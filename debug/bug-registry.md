# Bug Registry

This registry is the durable index for bugs tracked under `debug/bugs/`. Keep it sorted by bug ID and update it whenever status, severity, or next action changes.

| ID | Status | Severity | Surface | Summary | Next action |
| --- | --- | --- | --- | --- | --- |
| [BUG-0001](bugs/BUG-0001-streamlit-news-expand-grey-screen.md) | Fixed | P1 High | Streamlit UI, Watchlist News | First expansion of a ticker news card can grey out the page and feel slow before later toggles become responsive. | Run News-view smoke checklist before marking verified. |
| [BUG-0002](bugs/BUG-0002-unsafe-news-url-schemes.md) | Fixed | P1 High | Static UI, Streamlit UI, News | Unsafe or malformed provider article/thumbnail URLs could render as links or images. | Run Stock News smoke checklist before marking verified. |
| [BUG-0003](bugs/BUG-0003-loose-ticker-validation-and-provider-log-clutter.md) | Fixed | P1 High | Backend, Static UI, Streamlit UI, Market Data | Loose ticker validation allowed unsafe/malformed symbols to reach provider calls and clutter logs. | Smoke invalid ticker handling in both UIs before marking verified. |
| [BUG-0004](bugs/BUG-0004-static-stale-superseded-request-rendering.md) | Fixed | P1 High | Static UI | Superseded static requests could render stale levels, news, scanner rows, snapshots, or charts. | Smoke rapid refresh/watchlist changes before marking verified. |
| [BUG-0005](bugs/BUG-0005-streamlit-report-search-chart-refetches.md) | Fixed | P2 Medium | Streamlit UI, Charts | Streamlit report search could cause chart-history refetches for filtered subsets. | Smoke search-only chart filtering before marking verified. |
| [BUG-0006](bugs/BUG-0006-streamlit-partial-refresh-marks-unrelated-data-current.md) | Fixed | P1 High | Streamlit UI, Data Freshness | Partial refreshes could mark unrelated Streamlit datasets current. | Smoke partial refresh banners/freshness before marking verified. |
| [BUG-0007](bugs/BUG-0007-static-raw-json-validation-messages.md) | Fixed | P2 Medium | Static UI, Backend Validation | Static UI could show raw Pydantic validation JSON instead of concise messages. | Smoke invalid ticker messaging in browser before marking verified. |
| [BUG-0008](bugs/BUG-0008-missing-static-report-ticker-search.md) | Fixed | P2 Medium | Static UI, Trading Levels | Static Trading Levels report lacked the ticker search available in Streamlit. | Smoke report search with one and multiple tickers before marking verified. |
| [BUG-0009](bugs/BUG-0009-streamlit-scanner-rendered-offscreen.md) | Fixed | P1 High | Streamlit UI, Scanner | Scanner data could load and render offscreen away from the Scanner controls, making the table appear missing. | Keep scanner slot directly under Scanner controls and smoke first viewport after loading. |
| [BUG-0010](bugs/BUG-0010-streamlit-cloud-poetry-package-mode.md) | Fixed | P0 Critical | Streamlit Community Cloud, Deployment | Streamlit Cloud dependency install succeeded, then Poetry failed installing the root project package. | Redeploy clean branch and verify logs reach app startup. |

## Registry Rules

- Add a new row the same day a bug file is created.
- Keep `Status` aligned with the bug file header.
- Keep `Next action` short and actionable.
- Do not mark a bug `Verified` until the acceptance criteria in its bug file pass.
