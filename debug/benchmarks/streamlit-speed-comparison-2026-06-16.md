# Streamlit Speed Comparison

Generated: 2026-06-16T04:33:20.893334+00:00
Tickers: PWR, NVT, BKSY, RKLB, STRL, NVDA, MU, GEV, MYRG, ASTS, FIX, PLTR

## Summary

| Metric | This app | Adam app | Delta |
| --- | ---: | ---: | ---: |
| First Levels visible | 2.429s | 26.257s | 10.8x faster |
| First Scanner visible | 4.594s | 26.257s | 5.7x faster |
| Final Levels + Scanner | 14.902s | 26.257s | 1.8x faster |
| yfinance query wall time | 14.318s | 8.186s | 1.7x higher in this app |
| yfinance call count | 41 | 120 | +79 calls |

Adam's UI loop intentionally sleeps 1.5s after each ticker load. The Adam UX time above includes that 18.0s wait for 12 tickers; raw Adam data load time is 8.257s.

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
| PWR | 35 | 6 | 1.139 | 27 |
| NVT | 35 | 6 | 0.579 | 27 |
| BKSY | 35 | 6 | 0.691 | 27 |
| RKLB | 35 | 6 | 0.576 | 27 |
| STRL | 35 | 6 | 0.611 | 27 |
| NVDA | 37 | 5 | 0.725 | 29 |
| MU | 35 | 6 | 0.582 | 27 |
| GEV | 35 | 6 | 0.624 | 27 |
| MYRG | 35 | 6 | 0.698 | 27 |
| ASTS | 35 | 6 | 0.828 | 27 |
| FIX | 35 | 6 | 0.594 | 27 |
| PLTR | 35 | 6 | 0.609 | 27 |

## This App Batches

| Batch | Tickers | Levels seconds | Scanner seconds | Batch seconds | Scanner rows | Pattern detail rows |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | PWR, NVT, BKSY | 2.429 | 2.163 | 4.594 | 3 | 90 |
| 2 | RKLB, STRL, NVDA | 2.237 | 0.734 | 2.973 | 3 | 90 |
| 3 | MU, GEV, MYRG | 2.823 | 0.850 | 3.675 | 3 | 90 |
| 4 | ASTS, FIX, PLTR | 2.449 | 1.210 | 3.661 | 3 | 90 |

## yfinance Query Summary

This app batches provider downloads through `yf.download` and reuses the provider cache across levels/scanner batches. Adam loads each ticker with repeated `yf.Ticker(...).history(...)` calls.

### This App

```json
{
  "count": 41,
  "total_seconds": 14.318,
  "avg_seconds": 0.349,
  "max_seconds": 0.914,
  "by_operation": {
    "Ticker.earnings_dates": {
      "count": 12,
      "seconds": 7.05
    },
    "yf.download": {
      "count": 29,
      "seconds": 7.267
    }
  },
  "errors": []
}
```

### Adam App

```json
{
  "count": 120,
  "total_seconds": 8.186,
  "avg_seconds": 0.068,
  "max_seconds": 0.23,
  "by_operation": {
    "Ticker.earnings_dates": {
      "count": 12,
      "seconds": 0.637
    },
    "Ticker.history": {
      "count": 108,
      "seconds": 7.549
    }
  },
  "errors": []
}
```

## Notes

- This is a direct service/function benchmark, not a networked browser benchmark. It avoids mutating the live Streamlit watchlists and cleanly separates provider query time from rendered element counts.
- This app's Streamlit UI now progressively renders Levels and Scanner by 3-ticker batch; Adam's app renders after the full sequential ticker loop completes.
- Free yfinance responses vary by time, cache state, and rate limits. Treat this as a reproducible local snapshot rather than a permanent SLA.
