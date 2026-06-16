# Streamlit Speed Comparison

Generated: 2026-06-16T05:21:26.349594+00:00
Tickers: PWR, NVT, BKSY, RKLB, STRL, NVDA, MU, GEV, MYRG, ASTS, FIX, PLTR

## Summary

| Metric | This app | Adam app | Delta |
| --- | ---: | ---: | ---: |
| First Levels visible | 0.848s | 31.817s | 37.5x faster |
| First Scanner visible | 2.528s | 31.817s | 12.6x faster |
| Final Levels + Scanner | 16.502s | 31.817s | 1.9x faster |
| Earnings completion pass | 0.079s | n/a | final-only in this app |
| yfinance query wall time | 15.826s | 13.749s | 1.2x higher in this app |
| yfinance call count | 28 | 120 | +92 calls |

Adam's UI loop intentionally sleeps 1.5s after each ticker load. The Adam UX time above includes that 18.0s wait for 12 tickers; raw Adam data load time is 13.817s.

## Rendered View Elements

| Element | This app | Adam app |
| --- | ---: | ---: |
| chart_cards | 12 | 0 |
| level_cards | 12 | 12 |
| level_rows | 421 | 326 |
| pattern_detail_rows | 360 | 0 |
| pattern_heatmap_rows | 12 | 0 |
| pattern_summary_rows | 12 | 0 |
| scanner_rows | 12 | 12 |

## Per-Ticker Data Load

| Ticker | This app level rows | This app warnings | Adam load seconds | Adam level rows |
| --- | ---: | ---: | ---: | ---: |
| PWR | 35 | 6 | 1.439 | 27 |
| NVT | 35 | 6 | 1.029 | 27 |
| BKSY | 35 | 6 | 1.123 | 27 |
| RKLB | 35 | 6 | 1.016 | 27 |
| STRL | 35 | 6 | 1.038 | 27 |
| NVDA | 37 | 5 | 1.076 | 29 |
| MU | 35 | 6 | 1.103 | 27 |
| GEV | 35 | 6 | 1.019 | 27 |
| MYRG | 35 | 6 | 0.960 | 27 |
| ASTS | 35 | 6 | 1.196 | 27 |
| FIX | 34 | 6 | 1.572 | 27 |
| PLTR | 35 | 6 | 1.246 | 27 |

## This App Batches

| Batch | Tickers | Levels seconds | Scanner seconds | Batch seconds | Scanner rows | Pattern detail rows |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | PWR, NVT, BKSY | 0.848 | 1.678 | 2.528 | 3 | 90 |
| 2 | RKLB, STRL, NVDA | 0.716 | 0.528 | 1.246 | 3 | 90 |
| 3 | MU, GEV, MYRG | 0.636 | 0.480 | 1.117 | 3 | 90 |
| 4 | ASTS, FIX, PLTR | 10.484 | 1.044 | 11.531 | 3 | 90 |

## yfinance Query Summary

This app batches provider downloads through `yf.download` and reuses the provider cache across levels/scanner batches. Adam loads each ticker with repeated `yf.Ticker(...).history(...)` calls.

### This App

```json
{
  "count": 28,
  "total_seconds": 15.826,
  "avg_seconds": 0.565,
  "max_seconds": 10.018,
  "by_operation": {
    "Ticker.fast_info": {
      "count": 3,
      "seconds": 0.0
    },
    "yf.download": {
      "count": 25,
      "seconds": 15.826
    }
  },
  "errors": []
}
```

### Adam App

```json
{
  "count": 120,
  "total_seconds": 13.749,
  "avg_seconds": 0.115,
  "max_seconds": 0.67,
  "by_operation": {
    "Ticker.earnings_dates": {
      "count": 12,
      "seconds": 6.818
    },
    "Ticker.history": {
      "count": 108,
      "seconds": 6.931
    }
  },
  "errors": []
}
```

### This App Earnings Cache

```json
{
  "memory_hits": 12,
  "disk_hits": 12,
  "misses": 0,
  "stale": 0,
  "errors": 0,
  "writes": 0
}
```

## Notes

- This is a direct service/function benchmark, not a networked browser benchmark. It avoids mutating the live Streamlit watchlists and cleanly separates provider query time from rendered element counts.
- This app's Streamlit UI now progressively renders Levels and Scanner by 3-ticker batch; Adam's app renders after the full sequential ticker loop completes.
- Free yfinance responses vary by time, cache state, and rate limits. Treat this as a reproducible local snapshot rather than a permanent SLA.
