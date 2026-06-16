# Streamlit Speed Comparison

Generated: 2026-06-16T05:19:55.269428+00:00
Tickers: PWR, NVT, BKSY, RKLB, STRL, NVDA, MU, GEV, MYRG, ASTS, FIX, PLTR

## Summary

| Metric | This app | Adam app | Delta |
| --- | ---: | ---: | ---: |
| First Levels visible | 0.854s | 26.856s | 31.4x faster |
| First Scanner visible | 2.583s | 26.856s | 10.4x faster |
| Final Levels + Scanner | 12.571s | 26.856s | 2.1x faster |
| Earnings completion pass | 6.019s | n/a | final-only in this app |
| yfinance query wall time | 11.916s | 8.781s | 1.4x higher in this app |
| yfinance call count | 37 | 120 | +83 calls |

Adam's UI loop intentionally sleeps 1.5s after each ticker load. The Adam UX time above includes that 18.0s wait for 12 tickers; raw Adam data load time is 8.856s.

## Rendered View Elements

| Element | This app | Adam app |
| --- | ---: | ---: |
| chart_cards | 12 | 0 |
| level_cards | 12 | 12 |
| level_rows | 422 | 326 |
| pattern_detail_rows | 360 | 0 |
| pattern_heatmap_rows | 12 | 0 |
| pattern_summary_rows | 12 | 0 |
| scanner_rows | 12 | 12 |

## Per-Ticker Data Load

| Ticker | This app level rows | This app warnings | Adam load seconds | Adam level rows |
| --- | ---: | ---: | ---: | ---: |
| PWR | 35 | 6 | 1.145 | 27 |
| NVT | 35 | 6 | 0.516 | 27 |
| BKSY | 35 | 6 | 0.754 | 27 |
| RKLB | 35 | 6 | 0.678 | 27 |
| STRL | 35 | 6 | 0.638 | 27 |
| NVDA | 37 | 5 | 0.633 | 29 |
| MU | 35 | 6 | 0.836 | 27 |
| GEV | 35 | 6 | 0.716 | 27 |
| MYRG | 35 | 6 | 0.679 | 27 |
| ASTS | 35 | 6 | 0.952 | 27 |
| FIX | 35 | 6 | 0.712 | 27 |
| PLTR | 35 | 6 | 0.595 | 27 |

## This App Batches

| Batch | Tickers | Levels seconds | Scanner seconds | Batch seconds | Scanner rows | Pattern detail rows |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | PWR, NVT, BKSY | 0.854 | 1.728 | 2.583 | 3 | 90 |
| 2 | RKLB, STRL, NVDA | 0.623 | 0.578 | 1.203 | 3 | 90 |
| 3 | MU, GEV, MYRG | 0.781 | 0.619 | 1.401 | 3 | 90 |
| 4 | ASTS, FIX, PLTR | 0.529 | 0.836 | 1.366 | 3 | 90 |

## yfinance Query Summary

This app batches provider downloads through `yf.download` and reuses the provider cache across levels/scanner batches. Adam loads each ticker with repeated `yf.Ticker(...).history(...)` calls.

### This App

```json
{
  "count": 37,
  "total_seconds": 11.916,
  "avg_seconds": 0.322,
  "max_seconds": 0.589,
  "by_operation": {
    "Ticker.earnings_dates": {
      "count": 12,
      "seconds": 5.919
    },
    "yf.download": {
      "count": 25,
      "seconds": 5.998
    }
  },
  "errors": []
}
```

### Adam App

```json
{
  "count": 120,
  "total_seconds": 8.781,
  "avg_seconds": 0.073,
  "max_seconds": 0.242,
  "by_operation": {
    "Ticker.earnings_dates": {
      "count": 12,
      "seconds": 0.633
    },
    "Ticker.history": {
      "count": 108,
      "seconds": 8.148
    }
  },
  "errors": []
}
```

### This App Earnings Cache

```json
{
  "memory_hits": 12,
  "disk_hits": 0,
  "misses": 12,
  "stale": 0,
  "errors": 0,
  "writes": 12
}
```

## Notes

- This is a direct service/function benchmark, not a networked browser benchmark. It avoids mutating the live Streamlit watchlists and cleanly separates provider query time from rendered element counts.
- This app's Streamlit UI now progressively renders Levels and Scanner by 3-ticker batch; Adam's app renders after the full sequential ticker loop completes.
- Free yfinance responses vary by time, cache state, and rate limits. Treat this as a reproducible local snapshot rather than a permanent SLA.
