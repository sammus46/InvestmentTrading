const STORAGE_KEY = "equity-levels-watchlist";
const METRICS_STORAGE_KEY = "equity-levels-selected-metrics";
const CARD_ORDER_STORAGE_KEY = "equity-levels-card-order";
const ACTIVE_VIEW_STORAGE_KEY = "equity-levels-active-view";
const DEFAULT_CHART_WINDOW_DAYS = 365;
const NEWS_COLLAPSED_HEADLINE_COUNT = 5;
const NEWS_EXPANDED_HEADLINE_COUNT = 10;
const NEWS_MAX_HEADLINE_COUNT = 20;

const NEWS_CATEGORY_LABELS = {
  rating_changes: "Price Rating Changes",
  contracts: "Company Contract Announcements",
  earnings: "Earnings Reports",
  general: "General News",
};

const LEVEL_STYLES = {
  previous: { color: "#2563eb", width: 1.35, dash: "6 5", legend: "Previous session" },
  premarket: { color: "#ea580c", width: 1.35, dash: "4 4", legend: "Premarket" },
  opening: { color: "#7c3aed", width: 1.35, dash: "3 5", legend: "First 5m" },
  vwap: { color: "#0891b2", width: 1.75, dash: "", legend: "VWAP" },
  fiftyTwo: { color: "#b91c1c", width: 2, dash: "", legend: "52-week high/low" },
  swingHigh: { color: "#16a34a", width: 1.35, dash: "8 4", legend: "Swing highs" },
  swingLow: { color: "#ca8a04", width: 1.35, dash: "8 4", legend: "Swing lows" },
  bollinger: { color: "#64748b", width: 1.2, dash: "2 4", legend: "Bollinger Bands" },
};

const METRIC_DEFINITIONS = [
  { id: "previous_day", label: "Previous day OHLC", group: "Session" },
  { id: "premarket", label: "Premarket range", group: "Session" },
  { id: "first_five_minutes", label: "Opening range", group: "Session" },
  { id: "previous_session_vwap_5m", label: "Previous session VWAP", group: "Trend" },
  { id: "fifty_two_week", label: "52-week range", group: "Levels" },
  { id: "swing_levels", label: "Swing highs/lows", group: "Levels" },
  { id: "bollinger_bands", label: "Bollinger Bands", group: "Indicators" },
  { id: "earnings_gap", label: "Earnings gap", group: "Events" },
];

const tickersInput = document.querySelector("#tickers");
const metricSelectorEl = document.querySelector("#metric-selector");
const generateButton = document.querySelector("#generate");
const pdfButton = document.querySelector("#download-pdf");
const statusEl = document.querySelector("#status");
const resultsEl = document.querySelector("#results");
const generatedAtEl = document.querySelector("#generated-at");
const runScannerButton = document.querySelector("#run-scanner");
const scannerStatusEl = document.querySelector("#scanner-status");
const scannerGeneratedAtEl = document.querySelector("#scanner-generated-at");
const scannerSetupEl = document.querySelector("#scanner-setup-results");
const scannerPatternEl = document.querySelector("#scanner-pattern-results");
const scannerTabButtons = [...document.querySelectorAll("[data-scanner-tab]")];
const saveStateEl = document.querySelector("#save-state");
const chartsSectionEl = document.querySelector("#charts-section");
const viewNavButtons = [...document.querySelectorAll("[data-view]")];
const viewPanels = {
  levels: document.querySelector("#view-levels"),
  news: document.querySelector("#view-news"),
};
const refreshNewsButton = document.querySelector("#refresh-news");
const newsStatusEl = document.querySelector("#news-status");
const newsGeneratedAtEl = document.querySelector("#news-generated-at");
const marketNewsEl = document.querySelector("#market-news");
const watchlistNewsEl = document.querySelector("#watchlist-news");
const xNewsEl = document.querySelector("#x-news");
const newsInfoButtons = [...document.querySelectorAll("[data-news-info]")];
const menuToggleButton = document.querySelector("#menu-toggle");
const controlsDrawerEl = document.querySelector("#controls-drawer");
const drawerBackdropEl = document.querySelector("#drawer-backdrop");
const drawerCloseButton = document.querySelector("#drawer-close");
const metricsControlsEl = document.querySelector("#metrics-controls");

let currentReport = null;
let currentNews = null;
let currentScanner = null;
let scannerSort = { key: "score", direction: "desc" };
let draggedTicker = null;
let expandedNewsTickers = new Set();
const chartWindows = {};
const hiddenChartGroups = {};

tickersInput.value = localStorage.getItem(STORAGE_KEY) || "";
renderMetricSelector();
switchView(localStorage.getItem(ACTIVE_VIEW_STORAGE_KEY) || "levels", { loadNews: false });
updateNewsInfoTooltips();

viewNavButtons.forEach((button) => {
  button.addEventListener("click", () => switchView(button.dataset.view));
});

menuToggleButton.addEventListener("click", () => {
  if (document.body.classList.contains("drawer-open")) {
    closeControlsDrawer();
  } else {
    openControlsDrawer();
  }
});

drawerCloseButton.addEventListener("click", closeControlsDrawer);
drawerBackdropEl.addEventListener("click", closeControlsDrawer);
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeControlsDrawer();
  }
});

metricSelectorEl.addEventListener("change", () => {
  persistSelectedMetrics();
  saveStateEl.textContent = "Saved locally";
});

tickersInput.addEventListener("input", () => {
  localStorage.setItem(STORAGE_KEY, tickersInput.value);
  saveStateEl.textContent = "Saved locally";
  currentNews = null;
  currentScanner = null;
  expandedNewsTickers.clear();
  renderNewsEmptyState();
  renderScannerEmptyState();
});

generateButton.addEventListener("click", async () => {
  await withBusyState("Generating levels...", async () => {
    const report = await postJson("/api/levels", buildPayload());
    renderReport(report);
    setStatus("Report generated successfully. Drag cards or use the arrow buttons to reorder them.", "success");
  });
});

pdfButton.addEventListener("click", async () => {
  await withBusyState("Preparing PDF...", async () => {
    const response = await fetch("/api/reports/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload({ useCurrentReportOrder: true })),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filenameFromDisposition(response.headers.get("Content-Disposition"));
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setStatus("PDF report downloaded.", "success");
  });
});

refreshNewsButton.addEventListener("click", async () => {
  await loadNews();
});

watchlistNewsEl.addEventListener("click", (event) => {
  const button = event.target.closest("[data-news-toggle]");
  if (!button || !currentNews) return;
  const ticker = button.dataset.newsToggle;
  if (expandedNewsTickers.has(ticker)) {
    expandedNewsTickers.delete(ticker);
  } else {
    expandedNewsTickers.add(ticker);
  }
  renderWatchlistNews(currentNews.ticker_news || []);
});

runScannerButton.addEventListener("click", async () => {
  await loadScanner();
});

scannerTabButtons.forEach((button) => {
  button.addEventListener("click", () => switchScannerTab(button.dataset.scannerTab));
});

scannerSetupEl.addEventListener("click", (event) => {
  const sortButton = event.target.closest("[data-scanner-sort]");
  if (!sortButton || !currentScanner) return;
  const key = sortButton.dataset.scannerSort;
  scannerSort = {
    key,
    direction: scannerSort.key === key && scannerSort.direction === "desc" ? "asc" : "desc",
  };
  renderScannerSetup(currentScanner.setup_rows || []);
});

chartsSectionEl.addEventListener("input", (event) => {
  const slider = event.target.closest("[data-window-bound]");
  if (!slider) return;
  updateChartWindowBound(slider.dataset.ticker, slider.dataset.windowBound, Number(slider.value));
  syncChartZoomControl(slider.dataset.ticker);
});

chartsSectionEl.addEventListener("change", (event) => {
  const slider = event.target.closest("[data-window-bound]");
  if (!slider) return;
  renderTickerChartByTicker(slider.dataset.ticker);
});

chartsSectionEl.addEventListener("pointerdown", (event) => {
  const rangeSlider = event.target.closest(".range-slider");
  if (!rangeSlider || event.target.closest("input")) return;
  event.preventDefault();
  startChartWindowTrackDrag(rangeSlider, event);
});

chartsSectionEl.addEventListener("click", (event) => {
  const legendButton = event.target.closest("[data-chart-group]");
  if (legendButton) {
    toggleChartGroup(legendButton.dataset.ticker, legendButton.dataset.chartGroup);
    return;
  }

  const presetButton = event.target.closest("[data-window-preset]");
  if (presetButton) {
    applyChartWindowPreset(presetButton.dataset.ticker, presetButton.dataset.windowPreset);
  }
});

resultsEl.addEventListener("click", (event) => {
  const button = event.target.closest("[data-move]");
  if (!button || !currentReport) return;
  moveMetric(button.dataset.ticker, button.dataset.move === "up" ? -1 : 1);
});

resultsEl.addEventListener("dragstart", (event) => {
  const card = event.target.closest(".card");
  if (!card) return;
  draggedTicker = card.dataset.ticker;
  card.classList.add("dragging");
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", draggedTicker);
});

resultsEl.addEventListener("dragover", (event) => {
  if (!draggedTicker) return;
  const target = event.target.closest(".card");
  if (!target || target.dataset.ticker === draggedTicker) return;
  event.preventDefault();
  target.classList.add("drag-over");
});

resultsEl.addEventListener("dragleave", (event) => {
  event.target.closest(".card")?.classList.remove("drag-over");
});

resultsEl.addEventListener("drop", (event) => {
  const target = event.target.closest(".card");
  if (!target || !draggedTicker || !currentReport) return;
  event.preventDefault();
  reorderMetrics(draggedTicker, target.dataset.ticker);
});

resultsEl.addEventListener("dragend", () => {
  draggedTicker = null;
  document.querySelectorAll(".dragging, .drag-over").forEach((el) => el.classList.remove("dragging", "drag-over"));
});

function renderMetricSelector() {
  const selected = getSelectedMetrics();
  const grouped = METRIC_DEFINITIONS.reduce((groups, metric) => {
    groups[metric.group] = groups[metric.group] || [];
    groups[metric.group].push(metric);
    return groups;
  }, {});

  metricSelectorEl.innerHTML = Object.entries(grouped).map(([group, metrics]) => `
    <fieldset class="metric-picker-group">
      <legend>${escapeHtml(group)}</legend>
      ${metrics.map((metric) => `
        <label class="checkbox-card">
          <input type="checkbox" value="${escapeHtml(metric.id)}" ${selected.includes(metric.id) ? "checked" : ""} />
          <span>${escapeHtml(metric.label)}</span>
        </label>
      `).join("")}
    </fieldset>
  `).join("");
}

function switchView(view, options = {}) {
  const nextView = viewPanels[view] ? view : "levels";
  localStorage.setItem(ACTIVE_VIEW_STORAGE_KEY, nextView);
  viewNavButtons.forEach((button) => {
    const active = button.dataset.view === nextView;
    button.classList.toggle("active", active);
    if (active) {
      button.setAttribute("aria-current", "page");
    } else {
      button.removeAttribute("aria-current");
    }
  });
  Object.entries(viewPanels).forEach(([panelView, panel]) => {
    const active = panelView === nextView;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
  metricsControlsEl.hidden = nextView !== "levels";

  if (nextView === "news") {
    loadXTimeline();
    if (options.loadNews !== false && !currentNews) {
      loadNews();
    }
  }
}

function openControlsDrawer() {
  document.body.classList.add("drawer-open");
  controlsDrawerEl.setAttribute("aria-hidden", "false");
  menuToggleButton.setAttribute("aria-expanded", "true");
  drawerBackdropEl.hidden = false;
}

function closeControlsDrawer() {
  document.body.classList.remove("drawer-open");
  controlsDrawerEl.setAttribute("aria-hidden", "true");
  menuToggleButton.setAttribute("aria-expanded", "false");
  drawerBackdropEl.hidden = true;
}

function getSelectedMetrics() {
  try {
    const stored = JSON.parse(localStorage.getItem(METRICS_STORAGE_KEY));
    const allowed = METRIC_DEFINITIONS.map((metric) => metric.id);
    const valid = Array.isArray(stored) ? stored.filter((metric) => allowed.includes(metric)) : [];
    if (valid.length) return [...new Set(valid)];
  } catch (_) {
    // Fall back to all metrics if localStorage was edited manually.
  }
  return METRIC_DEFINITIONS.map((metric) => metric.id);
}

function readSelectedMetrics() {
  const selected = [...metricSelectorEl.querySelectorAll("input:checked")].map((input) => input.value);
  return selected.length ? selected : METRIC_DEFINITIONS.map((metric) => metric.id);
}

function persistSelectedMetrics() {
  localStorage.setItem(METRICS_STORAGE_KEY, JSON.stringify(readSelectedMetrics()));
}

function buildPayload(options = {}) {
  persistSelectedMetrics();
  return {
    tickers: options.useCurrentReportOrder && currentReport?.metrics?.length
      ? currentReport.metrics.map((metric) => metric.ticker)
      : tickersInput.value,
    metrics: readSelectedMetrics(),
  };
}

function buildNewsPayload() {
  return {
    tickers: tickersInput.value,
    per_ticker: Math.min(NEWS_EXPANDED_HEADLINE_COUNT, NEWS_MAX_HEADLINE_COUNT),
    general_count: 8,
  };
}

function buildScannerPayload() {
  return {
    tickers: tickersInput.value,
    include_setup: true,
    include_patterns: true,
    pattern_lookback_days: 30,
  };
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function withBusyState(message, callback) {
  const tickers = tickersInput.value.trim();
  if (!tickers) {
    setStatus("Enter at least one ticker symbol.", "error");
    return;
  }
  if (!readSelectedMetrics().length) {
    setStatus("Select at least one metric to calculate.", "error");
    return;
  }
  setStatus(message, "");
  generateButton.disabled = true;
  pdfButton.disabled = true;
  try {
    await callback();
  } catch (error) {
    setStatus(readableError(error), "error");
  } finally {
    generateButton.disabled = false;
    pdfButton.disabled = false;
  }
}

async function withNewsBusyState(message, callback) {
  const tickers = tickersInput.value.trim();
  if (!tickers) {
    setNewsStatus("Enter at least one ticker symbol.", "error");
    return;
  }
  setNewsStatus(message, "");
  refreshNewsButton.disabled = true;
  try {
    await callback();
  } catch (error) {
    setNewsStatus(readableError(error), "error");
  } finally {
    refreshNewsButton.disabled = false;
  }
}

async function withScannerBusyState(message, callback) {
  const tickers = tickersInput.value.trim();
  if (!tickers) {
    setScannerStatus("Enter at least one ticker symbol.", "error");
    return;
  }
  setScannerStatus(message, "");
  runScannerButton.disabled = true;
  try {
    await callback();
  } catch (error) {
    setScannerStatus(readableError(error), "error");
  } finally {
    runScannerButton.disabled = false;
  }
}

async function loadNews() {
  await withNewsBusyState("Loading market and watchlist news...", async () => {
    const news = await postJson("/api/news", buildNewsPayload());
    renderNews(news);
    if (!news.warnings?.length) {
      setNewsStatus("News refreshed.", "success");
    }
  });
}

async function loadScanner() {
  await withScannerBusyState("Running scanner for the shared watchlist...", async () => {
    const scanner = await postJson("/api/scanner", buildScannerPayload());
    renderScanner(scanner);
    setScannerStatus(scanner.warnings?.length ? scanner.warnings.join(" ") : "Scanner completed.", scanner.warnings?.length ? "error" : "success");
  });
}

function renderReport(report) {
  currentReport = {
    ...report,
    metrics: applyStoredCardOrder(report.metrics),
  };
  generatedAtEl.textContent = `Generated ${new Date(report.generated_at).toLocaleString()}`;
  renderCurrentReport();
}

function renderCurrentReport() {
  if (!currentReport?.metrics?.length) {
    resultsEl.className = "results empty";
    resultsEl.textContent = "No metrics were returned.";
    return;
  }
  resultsEl.className = "results";
  resultsEl.innerHTML = currentReport.metrics.map((metric, index) => renderMetricCard(metric, index)).join("");
  persistCardOrder(currentReport.metrics.map((metric) => metric.ticker));
  renderCharts();
}

function renderNews(news) {
  currentNews = news;
  expandedNewsTickers.clear();
  newsGeneratedAtEl.textContent = `News refreshed ${new Date(news.generated_at).toLocaleString()}`;
  updateNewsInfoTooltips(news.generated_at);
  renderWarningStatus(news.warnings || []);
  renderMarketNews(news.general_market || []);
  renderWatchlistNews(news.ticker_news || []);
}

function renderNewsEmptyState() {
  if (currentNews) return;
  newsGeneratedAtEl.textContent = "Use the shared watchlist to pull ticker-specific headlines plus broad US market news.";
  updateNewsInfoTooltips();
  marketNewsEl.className = "news-list empty";
  marketNewsEl.textContent = "Open the News view or refresh to load market headlines.";
  watchlistNewsEl.className = "ticker-news-grid empty";
  watchlistNewsEl.textContent = "Enter tickers and refresh news.";
  setNewsStatus("", "");
}

function renderScannerEmptyState() {
  if (currentScanner) return;
  scannerGeneratedAtEl.textContent = "Run the setup scanner and intraday pattern analysis for the shared watchlist.";
  scannerSetupEl.className = "scanner-empty";
  scannerSetupEl.textContent = "Run the scanner to view setup scores, support/resistance zones, and risk/reward.";
  scannerPatternEl.className = "scanner-empty";
  scannerPatternEl.textContent = "Run the scanner to view recurring intraday dip patterns.";
  setScannerStatus("", "");
}

function renderScanner(scanner) {
  currentScanner = scanner;
  scannerGeneratedAtEl.textContent = `Scanner generated ${new Date(scanner.generated_at).toLocaleString()}`;
  renderScannerSetup(scanner.setup_rows || []);
  renderScannerPatterns(scanner);
}

function switchScannerTab(tab) {
  const nextTab = tab === "patterns" ? "patterns" : "setup";
  scannerTabButtons.forEach((button) => {
    const active = button.dataset.scannerTab === nextTab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".scanner-section").forEach((section) => {
    const active = section.id === `scanner-${nextTab}`;
    section.classList.toggle("active", active);
    section.hidden = !active;
  });
}

function renderScannerSetup(rows) {
  if (!rows.length) {
    scannerSetupEl.className = "scanner-empty";
    scannerSetupEl.textContent = "Run the scanner to view setup scores, support/resistance zones, and risk/reward.";
    return;
  }
  const sorted = [...rows].sort((left, right) => compareScannerRows(left, right, scannerSort.key, scannerSort.direction));
  const columns = [
    ["score", "Score"],
    ["ticker", "Ticker"],
    ["price", "Price"],
    ["signal", "Signal"],
    ["vwap_extension_percent", "VWAP Ext"],
    ["rs_vs_spy_percent", "RS vs SPY"],
    ["rs_vs_sector_percent", "RS vs Sec"],
    ["best_support", "Best Support"],
    ["support_confidence", "Sup Conf"],
    ["best_resistance", "Best Resistance"],
    ["resistance_confidence", "Res Conf"],
    ["risk_reward", "R/R"],
    ["setup_level", "Setup At"],
    ["setup_distance_percent", "% Away"],
    ["lows_held", "Lows Held"],
    ["range_compression", "Range"],
    ["off_high_percent", "Off High"],
    ["momentum", "Momentum"],
  ];
  scannerSetupEl.className = "scanner-table-wrap";
  scannerSetupEl.innerHTML = `
    <table class="scanner-table">
      <thead>
        <tr>${columns.map(([key, label]) => `<th><button type="button" data-scanner-sort="${key}">${label}${scannerSort.key === key ? `<span>${scannerSort.direction === "desc" ? " desc" : " asc"}</span>` : ""}</button></th>`).join("")}</tr>
      </thead>
      <tbody>
        ${sorted.map((row) => `
          <tr>
            <td>${renderScore(row.score)}</td>
            <td><strong>${escapeHtml(row.ticker)}</strong></td>
            <td>${formatValue(row.price)}</td>
            <td>${formatScannerText(row.signal)}</td>
            <td>${formatScannerText(row.vwap_extension_label)}</td>
            <td>${formatScannerText(row.rs_vs_spy_label)}</td>
            <td>${formatScannerText(row.rs_vs_sector_label)}</td>
            <td>${formatScannerText(row.best_support)}</td>
            <td>${formatValue(row.support_confidence)}</td>
            <td>${formatScannerText(row.best_resistance)}</td>
            <td>${formatValue(row.resistance_confidence)}</td>
            <td>${row.risk_reward ? `${formatValue(row.risk_reward)}R` : "&mdash;"}</td>
            <td>${formatScannerText(row.setup_level)}</td>
            <td>${formatPercent(row.setup_distance_percent)}</td>
            <td>${row.lows_held ? `${row.lows_held}x` : "&mdash;"}</td>
            <td>${formatScannerText(row.range_compression)}</td>
            <td>${formatPercent(row.off_high_percent)}</td>
            <td>${formatScannerText(row.momentum)}</td>
          </tr>
          ${row.warnings?.length ? `<tr class="scanner-warning-row"><td colspan="${columns.length}">${row.warnings.map(escapeHtml).join(" ")}</td></tr>` : ""}
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderScannerPatterns(scanner) {
  const summary = scanner.pattern_summary || [];
  if (!summary.length) {
    scannerPatternEl.className = "scanner-empty";
    scannerPatternEl.textContent = "No pattern analysis was returned.";
    return;
  }
  scannerPatternEl.className = "scanner-patterns";
  const buckets = scanner.pattern_bucket_labels || scanner.pattern_buckets || [];
  scannerPatternEl.innerHTML = `
    <section class="scanner-subsection">
      <h3>Pattern Summary</h3>
      <div class="scanner-table-wrap">
        <table class="scanner-table compact">
          <thead><tr><th>Sector</th><th>Ticker</th><th>Days</th><th>Dip Days</th><th>Consistency</th><th>Avg Dip</th><th>Avg Recovery</th><th>Common Low Times</th></tr></thead>
          <tbody>
            ${summary.map((row) => `
              <tr>
                <td>${escapeHtml(row.sector || "Other")}</td>
                <td><strong>${escapeHtml(row.ticker)}</strong></td>
                <td>${row.total_days}</td>
                <td>${row.dip_days}</td>
                <td>${row.consistency_percent}%</td>
                <td>${formatPercent(row.average_dip_percent)}</td>
                <td>${formatSignedPercent(row.average_recovery_percent)}</td>
                <td>${(row.top_low_times || []).map(escapeHtml).join(", ") || "&mdash;"}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </section>
    <section class="scanner-subsection">
      <h3>5-Min Heatmap</h3>
      ${renderPatternHeatmap(scanner.pattern_heatmap || [], buckets)}
    </section>
    <section class="scanner-subsection">
      <h3>Per-Ticker Detail</h3>
      ${renderPatternDetails(scanner.pattern_details || [])}
    </section>
    <section class="scanner-subsection">
      <h3>Key Takeaways</h3>
      <ul class="scanner-takeaways">${(scanner.takeaways || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </section>
  `;
}

function renderPatternHeatmap(rows, bucketLabels) {
  if (!rows.length) return '<div class="scanner-empty">No heatmap data returned.</div>';
  return `
    <div class="heatmap-wrap">
      <table class="heatmap-table">
        <thead><tr><th>Ticker</th>${bucketLabels.map((label, index) => `<th title="${escapeHtml(label)}">${index % 6 === 0 ? escapeHtml(label.replace(" ET", "")) : ""}</th>`).join("")}</tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <th>${escapeHtml(row.ticker)}</th>
              ${(row.values || []).map((value) => `<td style="background:${heatmapColor(value)}" title="${value === null || value === undefined ? "No data" : `${value.toFixed(2)}%`}">${value === null || value === undefined ? "" : value.toFixed(1)}</td>`).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderPatternDetails(details) {
  if (!details.length) return '<div class="scanner-empty">No day-by-day details returned.</div>';
  const byTicker = details.reduce((groups, detail) => {
    groups[detail.ticker] = groups[detail.ticker] || [];
    groups[detail.ticker].push(detail);
    return groups;
  }, {});
  return Object.entries(byTicker).map(([ticker, rows]) => `
    <details class="pattern-detail">
      <summary>${escapeHtml(ticker)} - ${rows.length} days</summary>
      <div class="scanner-table-wrap">
        <table class="scanner-table compact">
          <thead><tr><th>Date</th><th>Morning Low</th><th>Low Time</th><th>Recovery</th><th>Dip?</th><th>Day Low</th><th>Day Low Time</th><th>Close From Open</th></tr></thead>
          <tbody>
            ${rows.map((row) => `
              <tr>
                <td>${formatDate(row.date) || escapeHtml(row.date)}</td>
                <td>${formatPercent(row.morning_low_percent)}</td>
                <td>${escapeHtml(row.morning_low_time)}</td>
                <td>${formatSignedPercent(row.recovery_to_close_percent)}</td>
                <td>${row.dip_in_window ? "Yes" : "No"}</td>
                <td>${formatPercent(row.day_low_percent)}</td>
                <td>${escapeHtml(row.day_low_time)}</td>
                <td>${formatSignedPercent(row.close_from_open_percent)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </details>
  `).join("");
}

function renderWarningStatus(warnings) {
  if (!warnings.length) return;
  setNewsStatus(warnings.join(" "), "error");
}

function renderMarketNews(articles) {
  if (!articles.length) {
    marketNewsEl.className = "news-list empty";
    marketNewsEl.textContent = "No general market headlines were returned.";
    return;
  }
  marketNewsEl.className = "news-list";
  marketNewsEl.innerHTML = articles.map((article) => renderArticleCard(article, { compact: false })).join("");
}

function renderWatchlistNews(tickerNews) {
  if (!tickerNews.length) {
    watchlistNewsEl.className = "ticker-news-grid empty";
    watchlistNewsEl.textContent = "No watchlist news was returned.";
    return;
  }
  watchlistNewsEl.className = "ticker-news-grid";
  watchlistNewsEl.innerHTML = tickerNews.map(renderTickerNews).join("");
}

function renderTickerNews(tickerGroup) {
  const articles = tickerGroup.articles || [];
  const warnings = tickerGroup.warnings || [];
  const ticker = tickerGroup.ticker || "";
  const isExpanded = expandedNewsTickers.has(ticker);
  const visibleArticles = isExpanded
    ? articles.slice(0, NEWS_EXPANDED_HEADLINE_COUNT)
    : articles.slice(0, NEWS_COLLAPSED_HEADLINE_COUNT);
  const articleMarkup = isExpanded
    ? renderCategorizedTickerArticles(visibleArticles)
    : `<div class="ticker-articles">${visibleArticles.map((article) => renderArticleCard(article, { compact: true })).join("")}</div>`;
  return `
    <article class="ticker-news-card ${isExpanded ? "expanded" : ""}">
      <div class="ticker-news-header">
        <h4>${escapeHtml(ticker)}</h4>
        ${articles.length > NEWS_COLLAPSED_HEADLINE_COUNT ? renderNewsToggleButton(ticker, isExpanded, articles.length) : ""}
      </div>
      ${warnings.length ? `<div class="inline-warning">${warnings.map(escapeHtml).join(" ")}</div>` : ""}
      ${articles.length ? articleMarkup : `<p class="news-empty">No recent headlines returned.</p>`}
    </article>
  `;
}

function renderNewsToggleButton(ticker, isExpanded, articleCount) {
  const expandedCount = Math.min(articleCount, NEWS_EXPANDED_HEADLINE_COUNT);
  const label = isExpanded
    ? `Show top ${NEWS_COLLAPSED_HEADLINE_COUNT} headlines for ${ticker}`
    : `Show ${expandedCount} headlines for ${ticker}`;
  return `
    <button
      class="news-toggle-button"
      type="button"
      data-news-toggle="${escapeHtml(ticker)}"
      aria-expanded="${isExpanded}"
      aria-label="${escapeHtml(label)}"
      title="${escapeHtml(label)}"
    >
      <span aria-hidden="true">${isExpanded ? "&#9652;" : "&#9662;"}</span>
    </button>
  `;
}

function renderCategorizedTickerArticles(articles) {
  const grouped = groupArticlesByCategory(articles);
  const groups = Object.keys(NEWS_CATEGORY_LABELS).map((category) => {
    const categoryArticles = grouped[category] || [];
    if (!categoryArticles.length) return "";
    return `
      <section class="ticker-article-group category-${escapeHtml(category)}" aria-label="${escapeHtml(NEWS_CATEGORY_LABELS[category])}">
        <div class="ticker-article-group-heading">
          <h5>${escapeHtml(NEWS_CATEGORY_LABELS[category])}</h5>
          <span>${categoryArticles.length}</span>
        </div>
        <div class="ticker-articles">
          ${categoryArticles.map((article) => renderArticleCard(article, { compact: true })).join("")}
        </div>
      </section>
    `;
  }).join("");
  return groups ? `<div class="ticker-article-groups">${groups}</div>` : `<p class="news-empty">No categorized headlines returned.</p>`;
}

function groupArticlesByCategory(articles) {
  return articles.reduce((groups, article) => {
    const category = NEWS_CATEGORY_LABELS[article.category] ? article.category : "general";
    groups[category] = groups[category] || [];
    groups[category].push(article);
    return groups;
  }, {});
}

function updateNewsInfoTooltips(generatedAt = null) {
  const refreshed = generatedAt
    ? `News refreshed ${new Date(generatedAt).toLocaleString()}.`
    : "News has not been refreshed yet.";
  const descriptions = {
    market: `${refreshed} Major headlines related to the US stock market.`,
    watchlist: `${refreshed} Headlines grouped by ticker from the same list used for levels.`,
    x: `${refreshed} Public @unusual_whales posts embedded from X.com.`,
  };
  newsInfoButtons.forEach((button) => {
    const text = descriptions[button.dataset.newsInfo] || refreshed;
    button.setAttribute("aria-label", text);
    button.title = text;
    const tooltip = button.querySelector(".info-tooltip");
    if (tooltip) {
      tooltip.textContent = text;
    }
  });
}

function loadXTimeline() {
  if (!xNewsEl || xNewsEl.dataset.loaded === "true") return;
  xNewsEl.dataset.loaded = "true";
  xNewsEl.innerHTML = `
    <a
      class="twitter-timeline"
      data-height="520"
      data-theme="light"
      data-dnt="true"
      href="https://twitter.com/unusual_whales?ref_src=twsrc%5Etfw"
    >
      Posts by @unusual_whales
    </a>
    <p class="x-news-fallback">
      If the timeline does not load, open <a href="https://x.com/unusual_whales" target="_blank" rel="noopener noreferrer">@unusual_whales on X.com</a>.
    </p>
  `;

  if (window.twttr?.widgets?.load) {
    window.twttr.widgets.load(xNewsEl);
    showXTimelineFallbackIfNeeded();
    return;
  }

  const existingScript = document.querySelector('script[src="https://platform.twitter.com/widgets.js"]');
  if (existingScript) {
    existingScript.addEventListener("load", () => {
      window.twttr?.widgets?.load(xNewsEl);
      showXTimelineFallbackIfNeeded();
    }, { once: true });
    showXTimelineFallbackIfNeeded();
    return;
  }

  const script = document.createElement("script");
  script.src = "https://platform.twitter.com/widgets.js";
  script.async = true;
  script.charset = "utf-8";
  script.addEventListener("load", () => {
    window.twttr?.widgets?.load(xNewsEl);
    showXTimelineFallbackIfNeeded();
  }, { once: true });
  script.addEventListener("error", () => xNewsEl.classList.add("timeline-fallback-visible"), { once: true });
  document.body.appendChild(script);
}

function showXTimelineFallbackIfNeeded() {
  window.setTimeout(() => {
    if (xNewsEl && !xNewsEl.querySelector("iframe")) {
      xNewsEl.classList.add("timeline-fallback-visible");
    }
  }, 6500);
}

function renderArticleCard(article, options = {}) {
  const published = article.published_at ? new Date(article.published_at).toLocaleString() : "";
  const related = article.related_tickers?.length
    ? `<div class="related-tickers">${article.related_tickers.slice(0, 6).map((ticker) => `<span>${escapeHtml(ticker)}</span>`).join("")}</div>`
    : "";
  const image = article.thumbnail_url && !options.compact
    ? `<img src="${escapeHtml(article.thumbnail_url)}" alt="" loading="lazy" />`
    : "";
  const title = article.url
    ? `<a href="${escapeHtml(article.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(article.title)}</a>`
    : `<span>${escapeHtml(article.title)}</span>`;

  return `
    <article class="news-card ${options.compact ? "compact" : ""}">
      ${image}
      <div class="news-card-body">
        <h4>${title}</h4>
        <div class="news-meta">
          ${article.publisher ? `<span>${escapeHtml(article.publisher)}</span>` : ""}
          ${published ? `<time datetime="${escapeHtml(article.published_at)}">${escapeHtml(published)}</time>` : ""}
        </div>
        ${article.summary && !options.compact ? `<p>${escapeHtml(article.summary)}</p>` : ""}
        ${related}
      </div>
    </article>
  `;
}

function renderMetricCard(metric, index) {
  const selected = metric.selected_metrics || readSelectedMetrics();
  const sections = [
    {
      title: "Session Levels",
      rows: [
        selected.includes("previous_day") && ["Prev Open", metric.previous_day.open],
        selected.includes("previous_day") && ["Prev High", metric.previous_day.high],
        selected.includes("previous_day") && ["Prev Low", metric.previous_day.low],
        selected.includes("previous_day") && ["Prev Close", metric.previous_day.close],
        selected.includes("premarket") && ["Premarket High", metric.premarket.high],
        selected.includes("premarket") && ["Premarket Low", metric.premarket.low],
        selected.includes("first_five_minutes") && ["First 5m High", metric.first_five_minutes.high],
        selected.includes("first_five_minutes") && ["First 5m Low", metric.first_five_minutes.low],
      ].filter(Boolean),
    },
    {
      title: "Range & Levels",
      rows: [
        selected.includes("previous_session_vwap_5m") && ["VWAP 5m", metric.previous_session_vwap_5m],
        selected.includes("fifty_two_week") && ["52W High", metric.fifty_two_week.high],
        selected.includes("fifty_two_week") && ["52W Low", metric.fifty_two_week.low],
      ].filter(Boolean),
      lists: selected.includes("swing_levels") ? [
        ["Swing Highs", sortLevels(metric.swing_levels.highs, "asc")],
        ["Swing Lows", sortLevels(metric.swing_levels.lows, "desc")],
      ] : [],
    },
    {
      title: "Indicators & Events",
      rows: [
        selected.includes("bollinger_bands") && ["BB Upper", metric.bollinger_bands.upper],
        selected.includes("bollinger_bands") && ["BB Middle", metric.bollinger_bands.middle],
        selected.includes("bollinger_bands") && ["BB Lower", metric.bollinger_bands.lower],
        selected.includes("earnings_gap") && ["Earnings Date", formatDate(metric.earnings_gap.date)],
        selected.includes("earnings_gap") && ["Earnings Gap", metric.earnings_gap.gap],
        selected.includes("earnings_gap") && ["Earnings Gap %", metric.earnings_gap.gap_percent],
      ].filter(Boolean),
    },
  ].filter((section) => section.rows.length || section.lists?.length);

  const warningHtml = metric.warnings.length
    ? `<details class="warning"><summary>${metric.warnings.length} data warning${metric.warnings.length === 1 ? "" : "s"}</summary><ul>${metric.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul></details>`
    : "";

  return `
    <article class="card" draggable="true" data-ticker="${escapeHtml(metric.ticker)}">
      <div class="card-header">
        <div>
          <span class="drag-handle" aria-hidden="true">&vellip;&vellip;</span>
          <h3>${escapeHtml(metric.ticker)}</h3>
        </div>
        <div class="card-actions" aria-label="Reorder ${escapeHtml(metric.ticker)} card">
          <button type="button" data-move="up" data-ticker="${escapeHtml(metric.ticker)}" ${index === 0 ? "disabled" : ""} aria-label="Move ${escapeHtml(metric.ticker)} up">&uarr;</button>
          <button type="button" data-move="down" data-ticker="${escapeHtml(metric.ticker)}" ${index === currentReport.metrics.length - 1 ? "disabled" : ""} aria-label="Move ${escapeHtml(metric.ticker)} down">&darr;</button>
        </div>
      </div>
      <div class="card-body">
        ${sections.map(renderMetricSection).join("")}
        ${warningHtml}
      </div>
    </article>
  `;
}

function renderMetricSection(section) {
  return `
    <section class="metric-section">
      <h4>${escapeHtml(section.title)}</h4>
      ${section.rows.length ? `<div class="metric-grid">${section.rows.map(([label, value]) => `<div class="metric"><span>${label}</span><strong>${formatValue(value)}</strong></div>`).join("")}</div>` : ""}
      ${section.lists?.length ? `<div class="level-lists">${section.lists.map(([label, levels]) => renderLevelList(label, levels)).join("")}</div>` : ""}
    </section>
  `;
}

function renderLevelList(label, levels) {
  if (!levels?.length) return "";
  return `
    <section class="level-list">
      <h5>${escapeHtml(label)}</h5>
      <div class="chips">
        ${levels.map((level) => `<span>${formatValue(level)}</span>`).join("")}
      </div>
    </section>
  `;
}


function renderCharts() {
  if (!currentReport?.metrics?.length) {
    chartsSectionEl.className = "charts-section empty";
    chartsSectionEl.innerHTML = `
      <div class="charts-header">
        <div>
          <h3>Charts</h3>
          <p>Generate a report to view 365-day close charts with selected price levels.</p>
        </div>
      </div>
    `;
    return;
  }

  chartsSectionEl.className = "charts-section";
  chartsSectionEl.innerHTML = `
    <div class="charts-header">
      <div>
        <h3>Charts</h3>
        <p>Charts stay in the same order as the report cards. Drag either end of a chart range slider to zoom the x-axis.</p>
      </div>
    </div>
    <div class="charts-grid">
      ${currentReport.metrics.map(renderTickerChart).join("")}
    </div>
  `;
}

function renderTickerChart(metric) {
  const history = metric.price_history || [];
  if (!history.length) {
    return `
      <article class="chart-card" data-chart-ticker="${escapeHtml(metric.ticker)}">
        <div class="chart-card-header"><h4>${escapeHtml(metric.ticker)}</h4></div>
        <p class="chart-empty">No daily close history was returned for this ticker.</p>
      </article>
    `;
  }

  const maxWindow = Math.min(DEFAULT_CHART_WINDOW_DAYS, history.length);
  const range = normalizeChartWindow(metric.ticker, maxWindow);
  const selectedWindow = chartWindowLength(range);
  const visibleHistory = history.slice(range.start - 1, range.end);
  const levels = getChartLevels(metric);
  const hiddenGroups = getHiddenChartGroups(metric.ticker);
  const visibleLevels = levels.filter((level) => !hiddenGroups.has(level.group));
  const showClose = !hiddenGroups.has("close");

  return `
    <article class="chart-card" data-chart-ticker="${escapeHtml(metric.ticker)}">
      <div class="chart-card-header">
        <div>
          <h4>${escapeHtml(metric.ticker)}</h4>
        </div>
      </div>
      ${renderChartLegend(metric.ticker, levels, hiddenGroups)}
      ${buildChartSvg(visibleHistory, visibleLevels, showClose)}
      ${renderChartZoomControls(metric.ticker, range, selectedWindow, maxWindow)}
    </article>
  `;
}

function getChartLevels(metric) {
  const selected = metric.selected_metrics || readSelectedMetrics();
  const levels = [];
  const add = (label, value, group) => {
    if (Number.isFinite(Number(value))) levels.push({ label, value: Number(value), group, ...LEVEL_STYLES[group] });
  };

  if (selected.includes("previous_day")) {
    add("Prev High", metric.previous_day.high, "previous");
    add("Prev Low", metric.previous_day.low, "previous");
    add("Prev Close", metric.previous_day.close, "previous");
  }
  if (selected.includes("premarket")) {
    add("Premarket High", metric.premarket.high, "premarket");
    add("Premarket Low", metric.premarket.low, "premarket");
  }
  if (selected.includes("first_five_minutes")) {
    add("First 5m High", metric.first_five_minutes.high, "opening");
    add("First 5m Low", metric.first_five_minutes.low, "opening");
  }
  if (selected.includes("previous_session_vwap_5m")) add("VWAP 5m", metric.previous_session_vwap_5m, "vwap");
  if (selected.includes("fifty_two_week")) {
    add("52W High", metric.fifty_two_week.high, "fiftyTwo");
    add("52W Low", metric.fifty_two_week.low, "fiftyTwo");
  }
  if (selected.includes("swing_levels")) {
    sortLevels(metric.swing_levels.highs, "asc").forEach((value, index) => add(`Swing High ${index + 1}`, value, "swingHigh"));
    sortLevels(metric.swing_levels.lows, "desc").forEach((value, index) => add(`Swing Low ${index + 1}`, value, "swingLow"));
  }
  if (selected.includes("bollinger_bands")) {
    add("BB Upper", metric.bollinger_bands.upper, "bollinger");
    add("BB Middle", metric.bollinger_bands.middle, "bollinger");
    add("BB Lower", metric.bollinger_bands.lower, "bollinger");
  }
  return levels;
}

function buildChartSvg(history, levels, showClose = true) {
  const width = 860;
  const height = 430;
  const margin = { top: 24, right: 88, bottom: 50, left: 58 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const closes = showClose ? history.map((point) => Number(point.close)) : [];
  const levelValues = levels.map((level) => level.value);
  const chartValues = closes.length || levelValues.length ? [...closes, ...levelValues] : history.map((point) => Number(point.close));
  let minValue = Math.min(...chartValues);
  let maxValue = Math.max(...chartValues);
  if (minValue === maxValue) {
    minValue -= 1;
    maxValue += 1;
  }
  const padding = (maxValue - minValue) * 0.08;
  minValue -= padding;
  maxValue += padding;

  const xFor = (index) => margin.left + (history.length === 1 ? plotWidth / 2 : (index / (history.length - 1)) * plotWidth);
  const yFor = (value) => margin.top + ((maxValue - value) / (maxValue - minValue)) * plotHeight;
  const closePoints = history.map((point, index) => `${xFor(index).toFixed(2)},${yFor(Number(point.close)).toFixed(2)}`).join(" ");
  const first = history[0];
  const last = history[history.length - 1];
  const gridValues = [0, 0.25, 0.5, 0.75, 1].map((ratio) => maxValue - (maxValue - minValue) * ratio);

  return `
    <svg class="price-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Daily close chart with marked price levels">
      <rect class="chart-bg" x="0" y="0" width="${width}" height="${height}" rx="8"></rect>
      ${gridValues.map((value) => {
        const y = yFor(value).toFixed(2);
        return `<line class="chart-grid-line" x1="${margin.left}" x2="${width - margin.right}" y1="${y}" y2="${y}"></line><text class="chart-axis-label" x="12" y="${Number(y) + 4}">${formatValue(value)}</text>`;
      }).join("")}
      ${levels.map((level) => {
        const y = yFor(level.value).toFixed(2);
        return `<line class="chart-level-line" x1="${margin.left}" x2="${width - margin.right}" y1="${y}" y2="${y}" stroke="${level.color}" stroke-width="${level.width}" stroke-dasharray="${level.dash}"></line><text class="chart-level-label" x="${width - margin.right + 8}" y="${Number(y) + 4}" fill="${level.color}">${escapeHtml(level.label)}</text>`;
      }).join("")}
      ${showClose ? `<polyline class="chart-close-line" points="${closePoints}"></polyline>` : ""}
      ${showClose ? history.map((point, index) => `<circle class="chart-close-point" cx="${xFor(index).toFixed(2)}" cy="${yFor(Number(point.close)).toFixed(2)}" r="${history.length > 80 ? 2 : 3}"><title>${escapeHtml(buildPointTooltip(point, levels))}</title></circle>`).join("") : ""}
      <line class="chart-axis" x1="${margin.left}" x2="${width - margin.right}" y1="${height - margin.bottom}" y2="${height - margin.bottom}"></line>
      <text class="chart-axis-label" x="${margin.left}" y="${height - 14}">${formatChartDate(first.date)}</text>
      <text class="chart-axis-label" x="${width - margin.right - 80}" y="${height - 14}">${formatChartDate(last.date)}</text>
    </svg>
  `;
}

function renderChartLegend(ticker, levels, hiddenGroups) {
  const groups = [...new Map(levels.map((level) => [level.group, level])).values()];
  const button = (group, label, swatchHtml) => `
    <button class="chart-legend-toggle ${hiddenGroups.has(group) ? "is-hidden" : ""}" type="button" data-ticker="${escapeHtml(ticker)}" data-chart-group="${escapeHtml(group)}" aria-pressed="${hiddenGroups.has(group) ? "false" : "true"}">
      ${swatchHtml}${escapeHtml(label)}
    </button>`;

  return `
    <div class="chart-legend" aria-label="Chart line visibility controls">
      ${button("close", "Daily close", `<i class="legend-close"></i>`)}
      ${groups.map((level) => button(level.group, level.legend, `<i style="background:${level.color}; height:${Math.max(3, level.width)}px"></i>`)).join("")}
    </div>
  `;
}

function renderChartZoomControls(ticker, range, selectedWindow, maxWindow) {
  const presets = [
    ["1d", "Last 1 day"],
    ["3d", "Last 3 days"],
    ["wtd", "Week to date"],
    ["mtd", "Month to date"],
    ["3mtd", "3 months to date"],
    ["ytd", "Year to date"],
    ["1y", "Last 1 year"],
  ];

  return `
    <div class="chart-zoom-panel">
      <div class="zoom-control" aria-label="X-axis zoom">
        <span>X-axis zoom</span>
        <div class="zoom-row range-zoom-row">
          <div class="range-slider" data-ticker="${escapeHtml(ticker)}" data-max-window="${maxWindow}" style="--range-start:${chartWindowPercent(range.start, maxWindow)}%; --range-end:${chartWindowPercent(range.end, maxWindow)}%">
            <input class="chart-window chart-window-start" data-ticker="${escapeHtml(ticker)}" data-window-bound="start" type="range" min="1" max="${maxWindow}" value="${range.start}" aria-label="First visible session" />
            <input class="chart-window chart-window-end" data-ticker="${escapeHtml(ticker)}" data-window-bound="end" type="range" min="1" max="${maxWindow}" value="${range.end}" aria-label="Last visible session" />
          </div>
          <output>${formatChartWindowLength(selectedWindow)}</output>
        </div>
      </div>
      <div class="chart-range-buttons" aria-label="Quick x-axis ranges">
        ${presets.map(([preset, label]) => `<button type="button" data-ticker="${escapeHtml(ticker)}" data-window-preset="${preset}">${escapeHtml(label)}</button>`).join("")}
      </div>
    </div>
  `;
}

function formatChartDate(value) {
  return parseChartDate(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function getHiddenChartGroups(ticker) {
  hiddenChartGroups[ticker] = hiddenChartGroups[ticker] || new Set();
  return hiddenChartGroups[ticker];
}

function normalizeChartWindow(ticker, maxWindow) {
  const saved = chartWindows[ticker];
  let range = typeof saved === "object" && saved !== null
    ? { start: Number(saved.start), end: Number(saved.end) }
    : { start: Math.max(1, maxWindow - Number(saved || maxWindow) + 1), end: maxWindow };

  range.start = Math.min(Math.max(Number.isFinite(range.start) ? Math.round(range.start) : 1, 1), maxWindow);
  range.end = Math.min(Math.max(Number.isFinite(range.end) ? Math.round(range.end) : maxWindow, 1), maxWindow);
  if (range.start > range.end) {
    [range.start, range.end] = [range.end, range.start];
  }
  chartWindows[ticker] = range;
  return range;
}

function updateChartWindowBound(ticker, bound, value) {
  const metric = findMetric(ticker);
  const maxWindow = Math.min(DEFAULT_CHART_WINDOW_DAYS, metric?.price_history?.length || 1);
  const range = normalizeChartWindow(ticker, maxWindow);
  if (bound === "start") {
    range.start = Math.min(Math.max(Math.round(value), 1), range.end);
  } else {
    range.end = Math.max(Math.min(Math.round(value), maxWindow), range.start);
  }
  chartWindows[ticker] = range;
  return range;
}

function renderTickerChartByTicker(ticker) {
  const metric = findMetric(ticker);
  const chartCard = findTickerChartCard(ticker);
  if (!metric || !chartCard) return;
  chartCard.outerHTML = renderTickerChart(metric);
}

function syncChartZoomControl(ticker) {
  const metric = findMetric(ticker);
  const chartCard = findTickerChartCard(ticker);
  if (!metric || !chartCard) return;

  const maxWindow = Math.min(DEFAULT_CHART_WINDOW_DAYS, metric.price_history?.length || 1);
  const range = normalizeChartWindow(ticker, maxWindow);
  const rangeSlider = chartCard.querySelector(".range-slider");
  const startInput = chartCard.querySelector("[data-window-bound='start']");
  const endInput = chartCard.querySelector("[data-window-bound='end']");
  const output = chartCard.querySelector(".range-zoom-row output");

  if (rangeSlider) {
    rangeSlider.style.setProperty("--range-start", `${chartWindowPercent(range.start, maxWindow)}%`);
    rangeSlider.style.setProperty("--range-end", `${chartWindowPercent(range.end, maxWindow)}%`);
  }
  if (startInput) startInput.value = range.start;
  if (endInput) endInput.value = range.end;
  if (output) output.textContent = formatChartWindowLength(chartWindowLength(range));
}

function startChartWindowTrackDrag(rangeSlider, event) {
  const ticker = rangeSlider.dataset.ticker;
  const maxWindow = Number(rangeSlider.dataset.maxWindow) || 1;
  if (!ticker) return;

  const initialValue = chartWindowValueFromPointer(rangeSlider, event.clientX, maxWindow);
  const initialRange = normalizeChartWindow(ticker, maxWindow);
  const startDistance = Math.abs(initialValue - initialRange.start);
  const endDistance = Math.abs(initialValue - initialRange.end);
  const activeBound = startDistance <= endDistance ? "start" : "end";

  const updateFromPointer = (pointerEvent) => {
    const value = chartWindowValueFromPointer(rangeSlider, pointerEvent.clientX, maxWindow);
    updateChartWindowBound(ticker, activeBound, value);
    syncChartZoomControl(ticker);
  };

  const stopDrag = (pointerEvent) => {
    updateFromPointer(pointerEvent);
    window.removeEventListener("pointermove", updateFromPointer);
    window.removeEventListener("pointerup", stopDrag);
    renderTickerChartByTicker(ticker);
  };

  updateFromPointer(event);
  window.addEventListener("pointermove", updateFromPointer);
  window.addEventListener("pointerup", stopDrag, { once: true });
}

function chartWindowValueFromPointer(rangeSlider, clientX, maxWindow) {
  const rect = rangeSlider.getBoundingClientRect();
  const ratio = rect.width ? (clientX - rect.left) / rect.width : 0;
  const clampedRatio = Math.min(Math.max(ratio, 0), 1);
  return Math.round(1 + clampedRatio * (maxWindow - 1));
}

function chartWindowLength(range) {
  return range.end - range.start + 1;
}

function formatChartWindowLength(selectedWindow) {
  return `${selectedWindow} session${selectedWindow === 1 ? "" : "s"}`;
}

function chartWindowPercent(value, maxWindow) {
  return ((value - 1) / Math.max(1, maxWindow - 1)) * 100;
}

function findMetric(ticker) {
  return currentReport?.metrics?.find((item) => item.ticker === ticker);
}

function findTickerChartCard(ticker) {
  return [...chartsSectionEl.querySelectorAll("[data-chart-ticker]")].find((card) => card.dataset.chartTicker === ticker);
}

function buildPointTooltip(point, levels) {
  const levelLines = levels.length
    ? levels.map((level) => `${level.label}: ${formatValue(level.value)}`).join("\n")
    : "No visible price levels";
  return `${formatChartDate(point.date)} close: ${formatValue(point.close)}\n${levelLines}`;
}

function toggleChartGroup(ticker, group) {
  const groups = getHiddenChartGroups(ticker);
  if (groups.has(group)) {
    groups.delete(group);
  } else {
    groups.add(group);
  }
  renderTickerChartByTicker(ticker);
}

function applyChartWindowPreset(ticker, preset) {
  const metric = findMetric(ticker);
  if (!metric?.price_history?.length) return;
  const maxWindow = Math.min(DEFAULT_CHART_WINDOW_DAYS, metric.price_history.length);
  const windowSize = getPresetWindow(metric.price_history, preset);
  chartWindows[ticker] = { start: maxWindow - windowSize + 1, end: maxWindow };
  renderTickerChartByTicker(ticker);
}

function getPresetWindow(history, preset) {
  const maxWindow = Math.min(DEFAULT_CHART_WINDOW_DAYS, history.length);
  if (preset === "1d") return Math.min(1, maxWindow);
  if (preset === "3d") return Math.min(3, maxWindow);
  if (preset === "1y") return maxWindow;

  const latest = parseChartDate(history[history.length - 1].date);
  let start = new Date(latest);
  if (preset === "wtd") {
    const day = latest.getDay();
    const daysFromMonday = day === 0 ? 6 : day - 1;
    start.setDate(latest.getDate() - daysFromMonday);
  } else if (preset === "mtd") {
    start = new Date(latest.getFullYear(), latest.getMonth(), 1);
  } else if (preset === "3mtd") {
    start = new Date(latest.getFullYear(), latest.getMonth() - 3, latest.getDate());
  } else if (preset === "ytd") {
    start = new Date(latest.getFullYear(), 0, 1);
  }

  const count = history.filter((point) => parseChartDate(point.date) >= start).length;
  return Math.min(Math.max(count || 1, 1), maxWindow);
}

function parseChartDate(value) {
  return new Date(`${value}T12:00:00`);
}

function moveMetric(ticker, direction) {
  const currentIndex = currentReport.metrics.findIndex((metric) => metric.ticker === ticker);
  const nextIndex = currentIndex + direction;
  if (currentIndex < 0 || nextIndex < 0 || nextIndex >= currentReport.metrics.length) return;
  const [metric] = currentReport.metrics.splice(currentIndex, 1);
  currentReport.metrics.splice(nextIndex, 0, metric);
  renderCurrentReport();
}

function reorderMetrics(sourceTicker, targetTicker) {
  const sourceIndex = currentReport.metrics.findIndex((metric) => metric.ticker === sourceTicker);
  const targetIndex = currentReport.metrics.findIndex((metric) => metric.ticker === targetTicker);
  if (sourceIndex < 0 || targetIndex < 0 || sourceIndex === targetIndex) return;
  const [metric] = currentReport.metrics.splice(sourceIndex, 1);
  currentReport.metrics.splice(targetIndex, 0, metric);
  renderCurrentReport();
}

function applyStoredCardOrder(metrics) {
  const order = getStoredCardOrder();
  if (!order.length) return metrics;
  return [...metrics].sort((left, right) => {
    const leftIndex = order.indexOf(left.ticker);
    const rightIndex = order.indexOf(right.ticker);
    if (leftIndex === -1 && rightIndex === -1) return 0;
    if (leftIndex === -1) return 1;
    if (rightIndex === -1) return -1;
    return leftIndex - rightIndex;
  });
}

function getStoredCardOrder() {
  try {
    const stored = JSON.parse(localStorage.getItem(CARD_ORDER_STORAGE_KEY));
    return Array.isArray(stored) ? stored : [];
  } catch (_) {
    return [];
  }
}

function persistCardOrder(order) {
  localStorage.setItem(CARD_ORDER_STORAGE_KEY, JSON.stringify(order));
}

function compareScannerRows(left, right, key, direction) {
  const leftValue = left[key];
  const rightValue = right[key];
  const emptyLeft = leftValue === null || leftValue === undefined || leftValue === "";
  const emptyRight = rightValue === null || rightValue === undefined || rightValue === "";
  if (emptyLeft && emptyRight) return 0;
  if (emptyLeft) return 1;
  if (emptyRight) return -1;
  const factor = direction === "desc" ? -1 : 1;
  if (typeof leftValue === "number" && typeof rightValue === "number") {
    return (leftValue - rightValue) * factor;
  }
  return String(leftValue).localeCompare(String(rightValue)) * factor;
}

function renderScore(score) {
  if (score === null || score === undefined) return "&mdash;";
  return `<span class="scanner-score">${Number(score)}/8</span>`;
}

function formatScannerText(value) {
  if (value === null || value === undefined || value === "") return "&mdash;";
  return escapeHtml(value);
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") return "&mdash;";
  return `${Number(value).toFixed(2)}%`;
}

function formatSignedPercent(value) {
  if (value === null || value === undefined || value === "") return "&mdash;";
  const number = Number(value);
  return `${number >= 0 ? "+" : ""}${number.toFixed(2)}%`;
}

function heatmapColor(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "#f8fafc";
  const bounded = Math.max(-3, Math.min(3, Number(value)));
  const intensity = Math.abs(bounded) / 3;
  if (bounded < 0) {
    return `rgba(185, 28, 28, ${0.12 + intensity * 0.62})`;
  }
  return `rgba(15, 118, 110, ${0.12 + intensity * 0.62})`;
}

function sortLevels(levels, direction) {
  const sorted = [...(levels || [])].sort((left, right) => left - right);
  return direction === "desc" ? sorted.reverse() : sorted;
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "&mdash;";
  if (typeof value === "string") return escapeHtml(value);
  return Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatDate(value) {
  if (!value) return null;
  return new Date(`${value}T12:00:00`).toLocaleDateString();
}

function setStatus(message, type) {
  statusEl.textContent = message;
  statusEl.className = `status ${type}`.trim();
}

function setNewsStatus(message, type) {
  newsStatusEl.textContent = message;
  newsStatusEl.className = `status ${type}`.trim();
}

function setScannerStatus(message, type) {
  scannerStatusEl.textContent = message;
  scannerStatusEl.className = `status ${type}`.trim();
}

function filenameFromDisposition(header) {
  const match = header?.match(/filename="?([^";]+)"?/);
  return match?.[1] || "equity-levels.pdf";
}

function readableError(error) {
  try {
    const parsed = JSON.parse(error.message);
    if (parsed.detail) return typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
  } catch (_) {
    // Keep the original message below when the server did not return JSON.
  }
  return error.message || "Request failed.";
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[char]);
}
