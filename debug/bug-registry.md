# Bug Registry

This registry is the durable index for bugs tracked under `debug/bugs/`. Keep it sorted by bug ID and update it whenever status, severity, or next action changes.

| ID | Status | Severity | Surface | Summary | Next action |
| --- | --- | --- | --- | --- | --- |
| [BUG-0001](bugs/BUG-0001-streamlit-news-expand-grey-screen.md) | Known | P1 High | Streamlit UI, Watchlist News | First expansion of a ticker news card can grey out the page and feel slow before later toggles become responsive. | Reproduce with timing, confirm whether a full Streamlit rerun or expensive iframe/chart render is responsible, then fix expansion to avoid user-visible hangs. |

## Registry Rules

- Add a new row the same day a bug file is created.
- Keep `Status` aligned with the bug file header.
- Keep `Next action` short and actionable.
- Do not mark a bug `Verified` until the acceptance criteria in its bug file pass.
