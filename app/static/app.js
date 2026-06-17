import { getJson, postJson } from "./modules/api.js";
import { escapeHtml } from "./modules/formatters.js";
import { renderMetrics } from "./modules/levels.js";

const STORAGE_KEY = "equity-levels-watchlist";
const CARD_ORDER_STORAGE_KEY = "equity-levels-card-order";
const ACTIVE_VIEW_STORAGE_KEY = "equity-levels-active-view";
const CHART_SETTINGS_STORAGE_KEY = "equity-levels-chart-settings";
const REPORT_LAYOUT_STORAGE_KEY = "equity-levels-report-layout";
const SETTINGS_STORAGE_KEY = "investment-trading-settings-v1";
const NEWS_COLLAPSED_HEADLINE_COUNT = 5;
const NEWS_EXPANDED_HEADLINE_COUNT = 10;
const NEWS_MAX_HEADLINE_COUNT = 20;
const NEWS_ENRICHMENT_POLL_INTERVAL_MS = 2500;
const NEWS_ENRICHMENT_MAX_POLLS = 4;
const AUTO_REFRESH_SECONDS = 60;
const TICKER_MAX_LENGTH = 20;
const TICKER_PATTERN = /^(?:\^[A-Z0-9][A-Z0-9-]*|[A-Z0-9][A-Z0-9-]*(?:=[A-Z0-9]+)?)$/;

const NEWS_CATEGORY_LABELS = {
  rating_changes: "Price Rating Changes",
  contracts: "Company Contract Announcements",
  earnings: "Earnings Reports",
  general: "General News",
};

const CHART_TYPES = ["line", "candles"];
const DEFAULT_CHART_SETTINGS = { type: "line", range: "1D", interval: "5m" };
const SCORE_ANALYTICS_RANGES = ["7D", "30D", "90D", "1Y", "All"];
const SCORE_ANALYTICS_METRICS = ["setup", "level", "both"];
const SCORE_ANALYTICS_CHART_METRICS = ["heat", "setup", "level"];
const SCORE_ANALYTICS_MOVEMENTS = ["all", "improving", "declining", "flat"];
const SCORE_ANALYTICS_SORTS = ["watchlist", "setup", "level", "gain", "drop"];
const SCORE_SERIES_COLORS = ["#0f766e", "#2563eb", "#dc2626", "#ca8a04", "#7c3aed", "#0891b2", "#be185d", "#4d7c0f"];
const DEFAULT_SCORE_ANALYTICS_SETTINGS = {
  range: "30D",
  scoreMetric: "both",
  chartMetric: "heat",
  movement: "all",
  sort: "watchlist",
};
const LEVEL_WEIGHT_MIN = 0;
const LEVEL_WEIGHT_MAX = 50;
let LEVEL_TYPE_WEIGHT_DEFAULTS = {
  "VWAP (Today)": 30,
  "PM High": 28,
  "PM Low": 28,
  "Prev High": 26,
  "Prev Low": 26,
  "Daily Swing High": 24,
  "Daily Swing Low": 24,
  "5-Min High": 22,
  "5-Min Low": 22,
  "1-Month High": 20,
  "1-Month Low": 20,
  "VWAP (Prev Session)": 18,
  "Prev Close": 16,
  "200 SMA (Daily)": 16,
  "50 SMA (Daily)": 14,
  "9 EMA (5-Min)": 14,
  "20 EMA (5-Min)": 12,
  "20 EMA (Daily)": 12,
  "Pivot": 10,
  "R1 (Pivot)": 10,
  "S1 (Pivot)": 10,
  "R2 (Pivot)": 8,
  "S2 (Pivot)": 8,
  "Earnings Gap Open": 8,
  "Pre-Earnings Close": 8,
  "Fib 61.8%": 8,
  "Fib 50.0%": 7,
  "Fib 38.2%": 6,
};
const DEFAULT_SETTINGS = {
  version: 1,
  watchlist: [],
  defaultView: "levels",
  reportLayout: "grid",
  levelFilter: "all",
  levelWeights: {},
  chartSettings: DEFAULT_CHART_SETTINGS,
  autoLoad: true,
  autoRefresh: true,
  scannerView: "auto",
  newsPerTicker: NEWS_EXPANDED_HEADLINE_COUNT,
  scoreAnalytics: DEFAULT_SCORE_ANALYTICS_SETTINGS,
};
const LEVEL_FILTERS = [
  { id: "all", label: "All Levels", shortLabel: "All" },
  { id: "scanner", label: "Scanner Levels Only", shortLabel: "Scanner" },
  { id: "weight_20", label: "Weight 20+ Only", shortLabel: "Weight 20+" },
];
const SCANNER_VIEW_OPTIONS = [
  { id: "auto", label: "Auto" },
  { id: "table", label: "Table" },
  { id: "cards", label: "Cards" },
];
const SCANNER_COLUMNS = [
  { key: "score", label: "Score", title: "Setup score", cell: "score", align: "center" },
  { key: "ticker", label: "Ticker", title: "Ticker", cell: "ticker" },
  { key: "price", label: "Price", title: "Current price", cell: "price", align: "right" },
  { key: "signal", label: "Sig", title: "Signal", cell: "signal" },
  { key: "vwap_extension_percent", label: "VWAP", title: "VWAP extension", cell: "vwap", align: "center" },
  { key: "rs_vs_spy_percent", label: "RS SPY", title: "Relative strength versus SPY", cell: "rsSpy", align: "center" },
  { key: "rs_vs_sector_percent", label: "RS Sec", title: "Relative strength versus sector ETF", cell: "rsSector", align: "center" },
  { key: "best_support", label: "Support", title: "Best support", cell: "support", wrap: true },
  { key: "support_confidence", label: "S Conf", title: "Support confidence", cell: "supportConfidence", align: "center" },
  { key: "best_resistance", label: "Resist", title: "Best resistance", cell: "resistance", wrap: true },
  { key: "resistance_confidence", label: "R Conf", title: "Resistance confidence", cell: "resistanceConfidence", align: "center" },
  { key: "risk_reward", label: "R/R", title: "Risk/reward", cell: "riskReward", align: "center" },
  { key: "setup_level", label: "Setup", title: "Setup level", cell: "setupLevel" },
  { key: "setup_distance_percent", label: "Away", title: "Distance from setup level", cell: "setupDistance", align: "right" },
  { key: "lows_held", label: "Lows", title: "Lows held", cell: "lowsHeld", align: "center" },
  { key: "range_compression", label: "Range", title: "Range compression", cell: "range", align: "center" },
  { key: "off_high_percent", label: "High", title: "Distance from high", cell: "offHigh", align: "right" },
  { key: "momentum", label: "Mom", title: "Momentum", cell: "momentum", align: "center" },
];
let RANGE_INTERVALS = {
  "1D": ["1m", "2m", "5m", "15m", "30m", "1h"],
  "WTD": ["1m", "2m", "5m", "15m", "30m", "1h"],
  "5D": ["1m", "2m", "5m", "15m", "30m", "1h"],
  "MTD": ["5m", "15m", "30m", "1h", "1d"],
  "1M": ["5m", "15m", "30m", "1h", "1d"],
  "QTD": ["1h", "1d", "1wk"],
  "3M": ["1h", "1d", "1wk"],
  "6M": ["1h", "1d", "1wk"],
  "YTD": ["1d", "1wk", "1mo"],
  "1Y": ["1d", "1wk", "1mo"],
  "2Y": ["1d", "1wk", "1mo"],
  "5Y": ["1d", "1wk", "1mo"],
};
let RANGE_DEFAULT_INTERVAL = {
  "1D": "5m",
  "WTD": "5m",
  "5D": "5m",
  "MTD": "15m",
  "1M": "15m",
  "QTD": "1h",
  "3M": "1h",
  "6M": "1d",
  "YTD": "1d",
  "1Y": "1d",
  "2Y": "1wk",
  "5Y": "1mo",
};
const EASTERN_CHART_TIME_FORMATTER = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

let METRIC_DEFINITIONS = [
  { id: "previous_day", label: "Previous day OHLC", group: "Session" },
  { id: "premarket", label: "Premarket range", group: "Session" },
  { id: "first_five_minutes", label: "Opening range", group: "Session" },
  { id: "previous_session_vwap_5m", label: "Previous session VWAP", group: "Trend" },
  { id: "fifty_two_week", label: "52-week range", group: "Levels" },
  { id: "swing_levels", label: "Swing highs/lows", group: "Levels" },
  { id: "bollinger_bands", label: "Bollinger Bands", group: "Indicators" },
  { id: "technical_levels", label: "Technical levels", group: "Indicators" },
  { id: "earnings_gap", label: "Earnings gap", group: "Events" },
];
let REPORT_LAYOUTS = [
  { id: "grid", label: "Grid", description: "Grouped cards with sectioned metrics.", order: 0, default: true },
  { id: "price_ladder", label: "Price Ladder", description: "Price-sorted levels around current price.", order: 1 },
  { id: "compact", label: "Compact", description: "Dense ticker cards for quick scanning.", order: 2 },
  { id: "compare", label: "Compare", description: "Cross-ticker table using report rows.", order: 3 },
];
let DEFAULT_REPORT_LAYOUT = "grid";

const tickersInput = document.querySelector("#tickers");
const watchlistFormEl = document.querySelector("#watchlist-form");
const watchlistListEl = document.querySelector("#watchlist-list");
const generateButton = document.querySelector("#generate");
const pdfButton = document.querySelector("#download-pdf");
const reportLayoutSelectEl = document.querySelector("#report-layout");
const reportSearchEl = document.querySelector("#report-search");
const reportSearchStatusEl = document.querySelector("#report-search-status");
const statusEl = document.querySelector("#status");
const resultsEl = document.querySelector("#results");
const generatedAtEl = document.querySelector("#generated-at");
const scannerStatusEl = document.querySelector("#scanner-status");
const scannerGeneratedAtEl = document.querySelector("#scanner-generated-at");
const scannerSetupEl = document.querySelector("#scanner-setup-results");
const saveStateEl = document.querySelector("#save-state");
const chartsSectionEl = document.querySelector("#charts-section");
const scoreAnalyticsSectionEl = document.querySelector("#score-analytics-section");
const viewNavButtons = [...document.querySelectorAll("[data-view]")];
const viewPanels = {
  levels: document.querySelector("#view-levels"),
  news: document.querySelector("#view-news"),
  analytics: document.querySelector("#view-analytics"),
};
const refreshAnalyticsButton = document.querySelector("#refresh-analytics");
const analyticsStatusEl = document.querySelector("#analytics-status");
const analyticsGeneratedAtEl = document.querySelector("#analytics-generated-at");
const sectorCoverageEl = document.querySelector("#sector-coverage");
const sectorRecommendationsEl = document.querySelector("#sector-recommendations");
const sectorTrendsEl = document.querySelector("#sector-trends");
const analyticsPatternEl = document.querySelector("#analytics-pattern-results");
const refreshNewsButton = document.querySelector("#refresh-news");
const newsStatusEl = document.querySelector("#news-status");
const newsGeneratedAtEl = document.querySelector("#news-generated-at");
const marketNewsEl = document.querySelector("#market-news");
const watchlistNewsEl = document.querySelector("#watchlist-news");
const watchlistNewsSearchEl = document.querySelector("#watchlist-news-search");
const marketSnapshotEl = document.querySelector("#market-snapshot");
const watchlistPerformanceEl = document.querySelector("#watchlist-performance");
const xNewsEl = document.querySelector("#x-news");
const newsInfoButtons = [...document.querySelectorAll("[data-news-info]")];
const menuToggleButton = document.querySelector("#menu-toggle");
const settingsToggleButton = document.querySelector("#settings-toggle");
const controlsDrawerEl = document.querySelector("#controls-drawer");
const settingsDrawerEl = document.querySelector("#settings-drawer");
const drawerBackdropEl = document.querySelector("#drawer-backdrop");
const drawerCloseButton = document.querySelector("#drawer-close");
const settingsCloseButton = document.querySelector("#settings-close");
const levelWeightsListEl = document.querySelector("#level-weights-list");
const resetLevelWeightsButton = document.querySelector("#reset-level-weights");
const settingsDefaultViewEl = document.querySelector("#setting-default-view");
const settingsAutoLoadEl = document.querySelector("#setting-auto-load");
const settingsAutoRefreshEl = document.querySelector("#setting-auto-refresh");
const settingsReportLayoutEl = document.querySelector("#setting-report-layout");
const settingsLevelFilterEl = document.querySelector("#setting-level-filter");
const settingsScannerViewEl = document.querySelector("#setting-scanner-view");
const levelFilterSelectEl = document.querySelector("#level-filter");
const settingsChartTypeEl = document.querySelector("#setting-chart-type");
const settingsChartRangeEl = document.querySelector("#setting-chart-range");
const settingsChartIntervalEl = document.querySelector("#setting-chart-interval");
const settingsNewsCountEl = document.querySelector("#setting-news-count");

let currentReport = null;
let currentNews = null;
let currentScanner = null;
let currentAnalytics = null;
let currentMarketSnapshot = null;
let currentChartHistory = null;
let currentScoreHistory = null;
let scoreAnalyticsError = "";
let appSettings = loadStoredSettings();
let watchlistTickers = loadStoredWatchlist();
let scannerSort = { key: "score", direction: "desc" };
let draggedTicker = null;
let expandedNewsTickers = new Set();
let chartSettings = loadStoredChartSettings();
let reportLayout = loadStoredReportLayout();
let levelFilter = appSettings.levelFilter;
let scoreAnalyticsSettings = appSettings.scoreAnalytics;
let watchlistRefreshTimer = null;
let autoRefreshTimer = null;
let newsEnrichmentPollTimer = null;
let newsEnrichmentPollAttempts = 0;
let newsEnrichmentPollKey = "";
let runControlsDisableDepth = 0;
const chartOverrides = {};
const chartDataCache = new Map();
const chartInstances = new Map();
const chartResizeObservers = new Map();
const statusTimers = new WeakMap();
const requestState = {
  levels: { controller: null, seq: 0 },
  news: { controller: null, seq: 0 },
  scanner: { controller: null, seq: 0 },
  analytics: { controller: null, seq: 0 },
  snapshot: { controller: null, seq: 0 },
  chart: { controller: null, seq: 0 },
  score: { controller: null, seq: 0 },
};
const tickerChartRequests = new Map();

initializeApp();

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

settingsToggleButton.addEventListener("click", () => {
  if (document.body.classList.contains("settings-open")) {
    closeSettingsDrawer();
  } else {
    openSettingsDrawer();
  }
});

drawerCloseButton.addEventListener("click", closeControlsDrawer);
settingsCloseButton.addEventListener("click", closeSettingsDrawer);
drawerBackdropEl.addEventListener("click", closeAllDrawers);
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeAllDrawers();
  }
});

watchlistFormEl.addEventListener("submit", (event) => {
  event.preventDefault();
  addTickersFromInput();
});

watchlistListEl.addEventListener("click", (event) => {
  const button = event.target.closest("[data-watchlist-action]");
  if (!button) return;
  const ticker = button.dataset.ticker;
  if (button.dataset.watchlistAction === "remove") {
    removeWatchlistTicker(ticker);
  } else if (button.dataset.watchlistAction === "up") {
    moveWatchlistTicker(ticker, -1);
  } else if (button.dataset.watchlistAction === "down") {
    moveWatchlistTicker(ticker, 1);
  }
});

levelWeightsListEl?.addEventListener("input", handleLevelWeightControlInput);
levelWeightsListEl?.addEventListener("change", handleLevelWeightControlInput);
resetLevelWeightsButton?.addEventListener("click", resetLevelWeights);

generateButton.addEventListener("click", async () => {
  await loadLevelsAndScanner();
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

reportLayoutSelectEl?.addEventListener("change", () => {
  setReportLayout(reportLayoutSelectEl.value);
});

levelFilterSelectEl?.addEventListener("change", () => {
  setLevelFilter(levelFilterSelectEl.value);
});

reportSearchEl?.addEventListener("input", applyReportSearch);
reportSearchEl?.addEventListener("search", applyReportSearch);
reportSearchEl?.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  applyReportSearch({ normalizeInput: true });
});

settingsDefaultViewEl?.addEventListener("change", () => {
  updateSettings({ defaultView: settingsDefaultViewEl.value });
  switchView(appSettings.defaultView);
});

settingsAutoLoadEl?.addEventListener("change", () => {
  updateSettings({ autoLoad: settingsAutoLoadEl.checked });
});

settingsAutoRefreshEl?.addEventListener("change", () => {
  updateSettings({ autoRefresh: settingsAutoRefreshEl.checked });
  startAutoRefreshTimer();
});

settingsReportLayoutEl?.addEventListener("change", () => {
  setReportLayout(settingsReportLayoutEl.value);
});

settingsLevelFilterEl?.addEventListener("change", () => {
  setLevelFilter(settingsLevelFilterEl.value);
});

settingsScannerViewEl?.addEventListener("change", () => {
  updateSettings({ scannerView: settingsScannerViewEl.value });
  renderSettingsControls();
  if (currentScanner) {
    renderScannerSetup(currentScanner.setup_rows || []);
  }
});

settingsChartTypeEl?.addEventListener("change", () => {
  updateGlobalChartSetting("type", settingsChartTypeEl.value);
});

settingsChartRangeEl?.addEventListener("change", () => {
  updateGlobalChartSetting("range", settingsChartRangeEl.value);
});

settingsChartIntervalEl?.addEventListener("change", () => {
  updateGlobalChartSetting("interval", settingsChartIntervalEl.value);
});

settingsNewsCountEl?.addEventListener("change", () => {
  updateSettings({ newsPerTicker: Number(settingsNewsCountEl.value) });
  renderSettingsControls();
  if (currentNews && watchlistTickers.length) {
    loadNews();
  }
});

refreshNewsButton.addEventListener("click", async () => {
  await Promise.all([loadMarketSnapshot(), loadNews()]);
});

refreshAnalyticsButton.addEventListener("click", async () => {
  await loadSectorAnalytics();
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

watchlistNewsSearchEl?.addEventListener("input", () => {
  renderWatchlistNews(currentNews?.ticker_news || []);
});

scannerSetupEl.addEventListener("click", (event) => {
  const sortButton = event.target.closest("[data-scanner-sort]");
  if (sortButton && currentScanner) {
    const key = sortButton.dataset.scannerSort;
    scannerSort = {
      key,
      direction: scannerSort.key === key && scannerSort.direction === "desc" ? "asc" : "desc",
    };
    renderScannerSetup(currentScanner.setup_rows || []);
    return;
  }
  const directionButton = event.target.closest("[data-scanner-sort-direction]");
  if (directionButton && currentScanner) {
    scannerSort = {
      ...scannerSort,
      direction: scannerSort.direction === "desc" ? "asc" : "desc",
    };
    renderScannerSetup(currentScanner.setup_rows || []);
  }
});

scannerSetupEl.addEventListener("change", (event) => {
  const sortSelect = event.target.closest("[data-scanner-sort-select]");
  if (!sortSelect || !currentScanner) return;
  scannerSort = {
    ...scannerSort,
    key: sortSelect.value,
  };
  renderScannerSetup(currentScanner.setup_rows || []);
});

chartsSectionEl.addEventListener("change", (event) => {
  const globalControl = event.target.closest("[data-chart-global]");
  if (globalControl) {
    updateGlobalChartSetting(globalControl.dataset.chartGlobal, globalControl.value);
    return;
  }

  const overrideControl = event.target.closest("[data-chart-override]");
  if (overrideControl) {
    updateChartOverride(
      overrideControl.dataset.ticker,
      overrideControl.dataset.chartOverride,
      overrideControl.value,
    );
  }
});

chartsSectionEl.addEventListener("click", (event) => {
  const resetButton = event.target.closest("[data-chart-reset]");
  if (resetButton) {
    resetChartOverride(resetButton.dataset.chartReset);
  }
});

scoreAnalyticsSectionEl?.addEventListener("change", (event) => {
  const control = event.target.closest("[data-score-setting]");
  if (!control) return;
  updateScoreAnalyticsSetting(control.dataset.scoreSetting, control.value);
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

async function initializeApp() {
  await loadAppConfig();
  appSettings = normalizeSettings(appSettings);
  chartSettings = appSettings.chartSettings;
  scoreAnalyticsSettings = appSettings.scoreAnalytics;
  reportLayout = appSettings.reportLayout;
  levelFilter = appSettings.levelFilter;
  persistSettings();
  renderReportLayoutControl();
  renderLevelFilterControl();
  renderLevelWeightControls();
  renderSettingsControls();
  renderWatchlistControls();
  switchView(appSettings.defaultView, { loadNews: false, loadSnapshot: false, persist: false });
  updateNewsInfoTooltips();
  if (appSettings.autoLoad) {
    autoloadSavedWatchlist();
  }
  startAutoRefreshTimer();
}

async function loadAppConfig() {
  try {
    const config = await getJson("/api/config");
    if (Array.isArray(config.metrics) && config.metrics.length) {
      METRIC_DEFINITIONS = [...config.metrics].sort((left, right) => left.order - right.order);
    }
    if (config.chart_ranges) {
      RANGE_INTERVALS = Object.fromEntries(
        Object.entries(config.chart_ranges).map(([range, value]) => [range, value.intervals || []]),
      );
      RANGE_DEFAULT_INTERVAL = Object.fromEntries(
        Object.entries(config.chart_ranges).map(([range, value]) => [range, value.default_interval]),
      );
    }
    if (Array.isArray(config.report_layouts) && config.report_layouts.length) {
      REPORT_LAYOUTS = [...config.report_layouts].sort((left, right) => left.order - right.order);
    }
    if (config.default_report_layout) {
      DEFAULT_REPORT_LAYOUT = config.default_report_layout;
    }
    if (config.level_type_weights && typeof config.level_type_weights === "object") {
      LEVEL_TYPE_WEIGHT_DEFAULTS = normalizeWeightDefaults(config.level_type_weights);
    }
    DEFAULT_SETTINGS.reportLayout = DEFAULT_REPORT_LAYOUT;
    reportLayout = normalizeReportLayout(reportLayout);
    appSettings = normalizeSettings(appSettings);
  } catch (error) {
    console.warn("Using bundled UI config because /api/config failed.", error);
  }
}

function renderReportLayoutControl() {
  if (!reportLayoutSelectEl) return;
  reportLayout = normalizeReportLayout(reportLayout);
  const options = REPORT_LAYOUTS
    .map((layout) => `<option value="${escapeHtml(layout.id)}">${escapeHtml(layout.label)}</option>`)
    .join("");
  reportLayoutSelectEl.innerHTML = options;
  if (settingsReportLayoutEl) {
    settingsReportLayoutEl.innerHTML = options;
  }
  reportLayoutSelectEl.value = reportLayout;
  if (settingsReportLayoutEl) {
    settingsReportLayoutEl.value = reportLayout;
  }
  const selected = REPORT_LAYOUTS.find((layout) => layout.id === reportLayout);
  if (selected?.description) {
    reportLayoutSelectEl.title = selected.description;
    if (settingsReportLayoutEl) settingsReportLayoutEl.title = selected.description;
  }
}

function setReportLayout(layout) {
  reportLayout = normalizeReportLayout(layout);
  updateSettings({ reportLayout });
  renderReportLayoutControl();
  renderCurrentReport();
}

function loadStoredReportLayout() {
  return normalizeReportLayout(appSettings.reportLayout);
}

function normalizeReportLayout(layout) {
  const fallback = REPORT_LAYOUTS.some((item) => item.id === DEFAULT_REPORT_LAYOUT) ? DEFAULT_REPORT_LAYOUT : "grid";
  return REPORT_LAYOUTS.some((item) => item.id === layout) ? layout : fallback;
}

function switchView(view, options = {}) {
  const nextView = viewPanels[view] ? view : "levels";
  if (options.persist !== false) {
    updateSettings({ defaultView: nextView });
  }
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

  if (nextView === "news") {
    loadXTimeline();
    if (options.loadSnapshot !== false && !currentMarketSnapshot) {
      loadMarketSnapshot();
    }
    if (options.loadNews !== false && !currentNews) {
      loadNews();
    }
  } else if (nextView === "analytics" && options.loadAnalytics !== false && !currentAnalytics) {
    loadSectorAnalytics();
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
  if (!document.body.classList.contains("settings-open")) {
    drawerBackdropEl.hidden = true;
  }
}

function openSettingsDrawer() {
  document.body.classList.add("settings-open");
  settingsDrawerEl.setAttribute("aria-hidden", "false");
  settingsToggleButton.setAttribute("aria-expanded", "true");
  drawerBackdropEl.hidden = false;
}

function closeSettingsDrawer() {
  document.body.classList.remove("settings-open");
  settingsDrawerEl.setAttribute("aria-hidden", "true");
  settingsToggleButton.setAttribute("aria-expanded", "false");
  if (!document.body.classList.contains("drawer-open")) {
    drawerBackdropEl.hidden = true;
  }
}

function closeAllDrawers() {
  closeControlsDrawer();
  closeSettingsDrawer();
}

function loadStoredSettings() {
  let stored = {};
  try {
    stored = JSON.parse(localStorage.getItem(SETTINGS_STORAGE_KEY)) || {};
  } catch (_) {
    stored = {};
  }
  return normalizeSettings({
    ...migratedLegacySettings(),
    ...stored,
  });
}

function migratedLegacySettings() {
  const legacyChartSettings = (() => {
    try {
      return JSON.parse(localStorage.getItem(CHART_SETTINGS_STORAGE_KEY));
    } catch (_) {
      return null;
    }
  })();
  return {
    watchlist: loadLegacyWatchlist(),
    defaultView: localStorage.getItem(ACTIVE_VIEW_STORAGE_KEY) || DEFAULT_SETTINGS.defaultView,
    reportLayout: localStorage.getItem(REPORT_LAYOUT_STORAGE_KEY) || DEFAULT_SETTINGS.reportLayout,
    chartSettings: legacyChartSettings || DEFAULT_SETTINGS.chartSettings,
  };
}

function loadLegacyWatchlist() {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (!stored) return [];
  try {
    const parsed = JSON.parse(stored);
    if (Array.isArray(parsed)) return normalizeTickers(parsed);
  } catch (_) {
    // Older versions stored a delimited textarea string.
  }
  return normalizeTickers(stored);
}

function normalizeSettings(candidate = {}) {
  const chart = normalizeChartSettings(candidate.chartSettings || candidate.chart || {});
  return {
    version: 1,
    watchlist: normalizeTickers(candidate.watchlist || []),
    defaultView: viewPanels[candidate.defaultView] ? candidate.defaultView : DEFAULT_SETTINGS.defaultView,
    reportLayout: normalizeReportLayout(candidate.reportLayout),
    levelFilter: normalizeLevelFilter(candidate.levelFilter),
    levelWeights: normalizeLevelWeights(candidate.levelWeights),
    chartSettings: chart,
    autoLoad: typeof candidate.autoLoad === "boolean" ? candidate.autoLoad : DEFAULT_SETTINGS.autoLoad,
    autoRefresh: typeof candidate.autoRefresh === "boolean" ? candidate.autoRefresh : DEFAULT_SETTINGS.autoRefresh,
    scannerView: normalizeScannerView(candidate.scannerView),
    newsPerTicker: normalizeNewsCount(candidate.newsPerTicker),
    scoreAnalytics: normalizeScoreAnalyticsSettings(candidate.scoreAnalytics),
  };
}

function updateSettings(patch) {
  appSettings = normalizeSettings({
    ...appSettings,
    ...patch,
  });
  persistSettings();
}

function persistSettings() {
  localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(appSettings));
}

function normalizeLevelFilter(value) {
  return LEVEL_FILTERS.some((item) => item.id === value) ? value : DEFAULT_SETTINGS.levelFilter;
}

function normalizeScannerView(value) {
  return SCANNER_VIEW_OPTIONS.some((item) => item.id === value) ? value : DEFAULT_SETTINGS.scannerView;
}

function normalizeNewsCount(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return DEFAULT_SETTINGS.newsPerTicker;
  return Math.max(1, Math.min(NEWS_MAX_HEADLINE_COUNT, Math.round(number)));
}

function normalizeScoreAnalyticsSettings(candidate = {}) {
  const source = candidate && typeof candidate === "object" ? candidate : {};
  return {
    range: SCORE_ANALYTICS_RANGES.includes(source.range) ? source.range : DEFAULT_SCORE_ANALYTICS_SETTINGS.range,
    scoreMetric: SCORE_ANALYTICS_METRICS.includes(source.scoreMetric)
      ? source.scoreMetric
      : DEFAULT_SCORE_ANALYTICS_SETTINGS.scoreMetric,
    chartMetric: SCORE_ANALYTICS_CHART_METRICS.includes(source.chartMetric)
      ? source.chartMetric
      : DEFAULT_SCORE_ANALYTICS_SETTINGS.chartMetric,
    movement: SCORE_ANALYTICS_MOVEMENTS.includes(source.movement)
      ? source.movement
      : DEFAULT_SCORE_ANALYTICS_SETTINGS.movement,
    sort: SCORE_ANALYTICS_SORTS.includes(source.sort) ? source.sort : DEFAULT_SCORE_ANALYTICS_SETTINGS.sort,
  };
}

function normalizeWeightDefaults(candidate = {}) {
  const normalized = {};
  Object.entries(candidate || {}).forEach(([label, value]) => {
    const weight = clampLevelWeight(value);
    if (weight !== null) normalized[label] = weight;
  });
  return Object.keys(normalized).length ? normalized : LEVEL_TYPE_WEIGHT_DEFAULTS;
}

function normalizeLevelWeights(candidate = {}) {
  if (!candidate || typeof candidate !== "object") return {};
  const normalized = {};
  Object.entries(candidate).forEach(([label, value]) => {
    if (!Object.prototype.hasOwnProperty.call(LEVEL_TYPE_WEIGHT_DEFAULTS, label)) return;
    const weight = clampLevelWeight(value);
    if (weight === null || weight === LEVEL_TYPE_WEIGHT_DEFAULTS[label]) return;
    normalized[label] = weight;
  });
  return normalized;
}

function clampLevelWeight(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  return Math.max(LEVEL_WEIGHT_MIN, Math.min(LEVEL_WEIGHT_MAX, Math.round(number)));
}

function activeLevelTypeWeights() {
  return {
    ...LEVEL_TYPE_WEIGHT_DEFAULTS,
    ...appSettings.levelWeights,
  };
}

function renderLevelFilterControl() {
  const options = LEVEL_FILTERS
    .map((filter) => `<option value="${escapeHtml(filter.id)}">${escapeHtml(filter.shortLabel)}</option>`)
    .join("");
  if (levelFilterSelectEl) {
    levelFilterSelectEl.innerHTML = options;
    levelFilterSelectEl.value = levelFilter;
  }
  if (settingsLevelFilterEl) {
    settingsLevelFilterEl.innerHTML = LEVEL_FILTERS
      .map((filter) => `<option value="${escapeHtml(filter.id)}">${escapeHtml(filter.label)}</option>`)
      .join("");
    settingsLevelFilterEl.value = levelFilter;
  }
}

function setLevelFilter(value) {
  levelFilter = normalizeLevelFilter(value);
  updateSettings({ levelFilter });
  renderLevelFilterControl();
  renderCurrentReport();
  if (currentScoreHistory || currentReport || currentScanner) {
    loadScoreHistory();
  }
}

function renderSettingsControls() {
  if (settingsDefaultViewEl) settingsDefaultViewEl.value = appSettings.defaultView;
  if (settingsAutoLoadEl) settingsAutoLoadEl.checked = appSettings.autoLoad;
  if (settingsAutoRefreshEl) settingsAutoRefreshEl.checked = appSettings.autoRefresh;
  renderReportLayoutControl();
  renderLevelFilterControl();
  renderChartSettingsControls();
  if (settingsScannerViewEl) {
    settingsScannerViewEl.value = appSettings.scannerView;
  }
  if (settingsNewsCountEl) settingsNewsCountEl.value = String(appSettings.newsPerTicker);
}

function renderChartSettingsControls() {
  if (settingsChartTypeEl) {
    settingsChartTypeEl.value = chartSettings.type;
  }
  if (settingsChartRangeEl) {
    settingsChartRangeEl.innerHTML = Object.keys(RANGE_INTERVALS)
      .map((range) => `<option value="${escapeHtml(range)}">${escapeHtml(formatChartOption(range))}</option>`)
      .join("");
    settingsChartRangeEl.value = chartSettings.range;
  }
  if (settingsChartIntervalEl) {
    settingsChartIntervalEl.innerHTML = (RANGE_INTERVALS[chartSettings.range] || [])
      .map((interval) => `<option value="${escapeHtml(interval)}">${escapeHtml(formatChartOption(interval))}</option>`)
      .join("");
    settingsChartIntervalEl.value = chartSettings.interval;
  }
}

function loadStoredWatchlist() {
  return normalizeTickers(appSettings.watchlist);
}

function normalizeTickers(value) {
  return parseTickers(value).valid;
}

function parseTickers(value) {
  const candidates = Array.isArray(value) ? value : String(value || "").replace(/,/g, " ").split(/\s+/);
  const valid = [];
  const invalid = [];
  candidates.forEach((candidate) => {
    const raw = String(candidate).trim();
    if (!raw) return;
    const ticker = normalizeTickerToken(raw);
    if (ticker && !valid.includes(ticker)) {
      valid.push(ticker);
    } else if (!ticker && !invalid.includes(raw)) {
      invalid.push(raw);
    }
  });
  return { valid, invalid };
}

function normalizeTickerToken(value) {
  let ticker = String(value || "").trim().toUpperCase();
  if (!ticker) return null;
  if (ticker.startsWith("$")) ticker = ticker.slice(1);
  ticker = ticker.replace(/[./]/g, "-");
  if (!ticker || ticker.length > TICKER_MAX_LENGTH) return null;
  if (/[<>"'`;&|\\]/.test(ticker)) return null;
  if ((ticker.match(/=/g) || []).length > 1 || ticker.startsWith("=") || ticker.endsWith("=")) return null;
  return TICKER_PATTERN.test(ticker) ? ticker : null;
}

function searchTickerTerms(value) {
  const candidates = String(value || "").replace(/,/g, " ").split(/\s+/);
  const terms = [];
  candidates.forEach((candidate) => {
    const raw = String(candidate).trim().toUpperCase();
    if (!raw) return;
    const term = normalizeTickerToken(raw) || raw;
    if (!terms.includes(term)) terms.push(term);
  });
  return terms;
}

function persistWatchlist() {
  updateSettings({ watchlist: watchlistTickers });
  localStorage.setItem(STORAGE_KEY, JSON.stringify(watchlistTickers));
  saveStateEl.textContent = "Saved locally";
}

function renderWatchlistControls() {
  watchlistListEl.innerHTML = watchlistTickers.length
    ? watchlistTickers.map((ticker, index) => `
      <li class="watchlist-item">
        <strong>${escapeHtml(ticker)}</strong>
        <div class="watchlist-actions" aria-label="Manage ${escapeHtml(ticker)}">
          <button type="button" data-watchlist-action="up" data-ticker="${escapeHtml(ticker)}" ${index === 0 ? "disabled" : ""} aria-label="Move ${escapeHtml(ticker)} up">&uarr;</button>
          <button type="button" data-watchlist-action="down" data-ticker="${escapeHtml(ticker)}" ${index === watchlistTickers.length - 1 ? "disabled" : ""} aria-label="Move ${escapeHtml(ticker)} down">&darr;</button>
          <button type="button" data-watchlist-action="remove" data-ticker="${escapeHtml(ticker)}" aria-label="Remove ${escapeHtml(ticker)}">&times;</button>
        </div>
      </li>
    `).join("")
    : '<li class="watchlist-empty">No tickers saved.</li>';
}

function renderLevelWeightControls() {
  if (!levelWeightsListEl) return;
  const weights = activeLevelTypeWeights();
  levelWeightsListEl.innerHTML = Object.entries(LEVEL_TYPE_WEIGHT_DEFAULTS)
    .map(([label, defaultWeight]) => renderLevelWeightRow(label, weights[label], defaultWeight))
    .join("");
  renderLevelWeightResetState();
}

function renderLevelWeightRow(label, weight, defaultWeight) {
  const inputId = `level-weight-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`;
  const changed = weight !== defaultWeight;
  const meta = changed ? `Custom, default ${defaultWeight}` : `Default ${defaultWeight}`;
  return `
    <div class="level-weight-row${changed ? " changed" : ""}">
      <label class="level-weight-label" for="${escapeHtml(inputId)}">${escapeHtml(label)}</label>
      <div class="level-weight-controls">
        <input id="${escapeHtml(inputId)}" type="range" min="${LEVEL_WEIGHT_MIN}" max="${LEVEL_WEIGHT_MAX}" step="1" value="${weight}" data-level-weight-label="${escapeHtml(label)}" aria-label="${escapeHtml(label)} weight" />
        <input type="number" min="${LEVEL_WEIGHT_MIN}" max="${LEVEL_WEIGHT_MAX}" step="1" value="${weight}" data-level-weight-label="${escapeHtml(label)}" aria-label="${escapeHtml(label)} weight value" />
      </div>
      <span class="level-weight-meta">${escapeHtml(meta)}</span>
    </div>
  `;
}

function handleLevelWeightControlInput(event) {
  const control = event.target.closest("[data-level-weight-label]");
  if (!control) return;
  const label = control.dataset.levelWeightLabel;
  if (!Object.prototype.hasOwnProperty.call(LEVEL_TYPE_WEIGHT_DEFAULTS, label)) return;
  const weight = clampLevelWeight(control.value);
  if (weight === null) return;
  setLevelWeight(label, weight);
  syncLevelWeightRow(control.closest(".level-weight-row"), label, weight);
  renderCurrentReport();
}

function setLevelWeight(label, weight) {
  const nextWeights = { ...appSettings.levelWeights };
  if (weight === LEVEL_TYPE_WEIGHT_DEFAULTS[label]) {
    delete nextWeights[label];
  } else {
    nextWeights[label] = weight;
  }
  updateSettings({ levelWeights: nextWeights });
  renderLevelWeightResetState();
}

function syncLevelWeightRow(row, label, weight) {
  if (!row) return;
  const defaultWeight = LEVEL_TYPE_WEIGHT_DEFAULTS[label];
  const changed = weight !== defaultWeight;
  row.classList.toggle("changed", changed);
  row.querySelectorAll("[data-level-weight-label]").forEach((control) => {
    control.value = String(weight);
  });
  const meta = row.querySelector(".level-weight-meta");
  if (meta) {
    meta.textContent = changed ? `Custom, default ${defaultWeight}` : `Default ${defaultWeight}`;
  }
}

function resetLevelWeights() {
  updateSettings({ levelWeights: {} });
  renderLevelWeightControls();
  renderCurrentReport();
}

function renderLevelWeightResetState() {
  if (resetLevelWeightsButton) {
    resetLevelWeightsButton.disabled = !Object.keys(appSettings.levelWeights || {}).length;
  }
}

function addTickersFromInput() {
  const { valid: nextTickers, invalid } = parseTickers(tickersInput.value);
  const invalidMessage = invalid.length
    ? `Skipped invalid ticker${invalid.length === 1 ? "" : "s"}: ${invalid.slice(0, 4).join(", ")}.`
    : "";
  if (invalid.length) {
    setStatus(invalidMessage, "error");
  }
  if (!nextTickers.length) return;
  const beforeLength = watchlistTickers.length;
  nextTickers.forEach((ticker) => {
    if (!watchlistTickers.includes(ticker)) watchlistTickers.push(ticker);
  });
  tickersInput.value = "";
  if (watchlistTickers.length !== beforeLength) {
    persistWatchlist();
    renderWatchlistControls();
    scheduleWatchlistRefresh();
    if (invalidMessage) setStatus(invalidMessage, "error");
  }
}

function removeWatchlistTicker(ticker) {
  const nextTickers = watchlistTickers.filter((item) => item !== ticker);
  if (nextTickers.length === watchlistTickers.length) return;
  watchlistTickers = nextTickers;
  delete chartOverrides[ticker];
  removeCachedTickerCharts(ticker);
  persistWatchlist();
  renderWatchlistControls();
  filterCurrentDataToWatchlist();
  scheduleWatchlistRefresh();
}

function moveWatchlistTicker(ticker, direction) {
  const currentIndex = watchlistTickers.indexOf(ticker);
  const nextIndex = currentIndex + direction;
  if (currentIndex < 0 || nextIndex < 0 || nextIndex >= watchlistTickers.length) return;
  const [item] = watchlistTickers.splice(currentIndex, 1);
  watchlistTickers.splice(nextIndex, 0, item);
  persistWatchlist();
  renderWatchlistControls();
  reorderCurrentDataToWatchlist();
}

function scheduleWatchlistRefresh() {
  clearTimeout(watchlistRefreshTimer);
  if (!watchlistTickers.length) {
    clearLoadedData();
    return;
  }
  if (!appSettings.autoLoad) {
    setStatus("", "");
    return;
  }
  setStatus("Updating...", "");
  watchlistRefreshTimer = setTimeout(() => {
    autoloadSavedWatchlist();
  }, 450);
}

function clearLoadedData() {
  abortAllRequests();
  currentReport = null;
  currentNews = null;
  currentScanner = null;
  currentAnalytics = null;
  currentMarketSnapshot = null;
  currentChartHistory = null;
  currentScoreHistory = null;
  scoreAnalyticsError = "";
  chartDataCache.clear();
  Object.keys(chartOverrides).forEach((ticker) => delete chartOverrides[ticker]);
  disposeCharts();
  expandedNewsTickers.clear();
  generatedAtEl.textContent = "";
  resultsEl.className = "results empty";
  resultsEl.textContent = "";
  renderCharts();
  renderScoreAnalytics();
  renderNewsEmptyState();
  renderMarketSnapshotEmptyState();
  renderScannerEmptyState();
  renderAnalyticsEmptyState();
  setStatus("", "");
}

function filterCurrentDataToWatchlist() {
  if (currentReport?.metrics) {
    currentReport.metrics = currentReport.metrics.filter((metric) => watchlistTickers.includes(metric.ticker));
    renderCurrentReport();
  }
  if (currentScanner?.setup_rows) {
    currentScanner.setup_rows = currentScanner.setup_rows.filter((row) => watchlistTickers.includes(row.ticker));
    renderScanner(currentScanner);
  }
  if (currentAnalytics) {
    currentAnalytics.sector_rows = (currentAnalytics.sector_rows || [])
      .map((row) => ({
        ...row,
        tickers: (row.tickers || []).filter((ticker) => watchlistTickers.includes(ticker)),
      }))
      .filter((row) => row.tickers.length);
    currentAnalytics.pattern_summary = (currentAnalytics.pattern_summary || []).filter((row) => watchlistTickers.includes(row.ticker));
    currentAnalytics.pattern_heatmap = (currentAnalytics.pattern_heatmap || []).filter((row) => watchlistTickers.includes(row.ticker));
    currentAnalytics.pattern_details = (currentAnalytics.pattern_details || []).filter((row) => watchlistTickers.includes(row.ticker));
    currentAnalytics.recommendations = (currentAnalytics.recommendations || [])
      .map((item) => ({ ...item, tickers: (item.tickers || []).filter((ticker) => watchlistTickers.includes(ticker)) }))
      .filter((item) => item.tickers.length || item.tone === "note");
    renderSectorAnalytics(currentAnalytics);
  }
  if (currentNews?.ticker_news) {
    currentNews.ticker_news = currentNews.ticker_news.filter((group) => watchlistTickers.includes(group.ticker));
    renderWatchlistNews(currentNews.ticker_news);
  }
  if (currentMarketSnapshot?.watchlist) {
    currentMarketSnapshot.watchlist = currentMarketSnapshot.watchlist.filter((row) => watchlistTickers.includes(row.symbol));
    renderWatchlistPerformance(currentMarketSnapshot.watchlist);
  }
  if (currentScoreHistory?.tickers) {
    currentScoreHistory.tickers = currentScoreHistory.tickers.filter((row) => watchlistTickers.includes(row.ticker));
    renderScoreAnalytics();
  }
}

function reorderCurrentDataToWatchlist() {
  const byTickerOrder = (left, right) => watchlistTickers.indexOf(left.ticker || left.symbol) - watchlistTickers.indexOf(right.ticker || right.symbol);
  if (currentReport?.metrics) {
    currentReport.metrics.sort(byTickerOrder);
    renderCurrentReport();
  }
  if (currentNews?.ticker_news) {
    currentNews.ticker_news.sort(byTickerOrder);
    renderWatchlistNews(currentNews.ticker_news);
  }
  if (currentAnalytics) {
    currentAnalytics.pattern_summary?.sort(byTickerOrder);
    currentAnalytics.pattern_heatmap?.sort(byTickerOrder);
    currentAnalytics.pattern_details?.sort(byTickerOrder);
    currentAnalytics.sector_rows?.forEach((row) => row.tickers?.sort((left, right) => watchlistTickers.indexOf(left) - watchlistTickers.indexOf(right)));
    renderSectorAnalytics(currentAnalytics);
  }
  if (currentMarketSnapshot?.watchlist) {
    currentMarketSnapshot.watchlist.sort(byTickerOrder);
    renderWatchlistPerformance(currentMarketSnapshot.watchlist);
  }
  if (currentScoreHistory?.tickers) {
    currentScoreHistory.tickers.sort(byTickerOrder);
    renderScoreAnalytics();
  }
}

function removeCachedTickerCharts(ticker) {
  [...chartDataCache.keys()].forEach((key) => {
    if (key.startsWith(`${ticker}|`)) chartDataCache.delete(key);
  });
  const instance = chartInstances.get(ticker);
  if (instance) {
    instance.remove();
    chartInstances.delete(ticker);
  }
  const observer = chartResizeObservers.get(ticker);
  if (observer) {
    observer.disconnect();
    chartResizeObservers.delete(ticker);
  }
}

function orderedPayloadTickers(options = {}) {
  if (options.useCurrentReportOrder && currentReport?.metrics?.length) {
    return currentReport.metrics.map((metric) => metric.ticker);
  }
  return [...watchlistTickers];
}

function readSelectedMetrics() {
  return METRIC_DEFINITIONS.map((metric) => metric.id);
}

function buildPayload(options = {}) {
  return {
    tickers: orderedPayloadTickers(options),
    metrics: readSelectedMetrics(),
  };
}

function buildNewsPayload() {
  return {
    tickers: [...watchlistTickers],
    per_ticker: appSettings.newsPerTicker,
    general_count: 8,
  };
}

function buildScannerPayload() {
  return {
    tickers: [...watchlistTickers],
    include_setup: true,
    include_patterns: false,
    pattern_lookback_days: 30,
  };
}

function buildSectorAnalyticsPayload() {
  return {
    tickers: [...watchlistTickers],
    pattern_lookback_days: 30,
  };
}

function buildMarketSnapshotPayload() {
  return {
    tickers: [...watchlistTickers],
  };
}

function buildChartHistoryPayload(settings = chartSettings, tickers = orderedPayloadTickers({ useCurrentReportOrder: true })) {
  return {
    tickers,
    range: settings.range,
    interval: settings.interval,
  };
}

function buildScoreHistoryPayload() {
  return {
    tickers: orderedPayloadTickers({ useCurrentReportOrder: true }),
    range: scoreAnalyticsSettings.range,
    score_metric: scoreAnalyticsSettings.scoreMetric,
    level_basis: levelFilter,
  };
}

function startRequest(key) {
  const state = requestState[key];
  state.controller?.abort();
  const controller = new AbortController();
  state.controller = controller;
  state.seq += 1;
  const seq = state.seq;
  return {
    signal: controller.signal,
    isCurrent: () => requestState[key]?.seq === seq && requestState[key]?.controller === controller,
    complete: () => {
      if (requestState[key]?.seq === seq && requestState[key]?.controller === controller) {
        requestState[key].controller = null;
      }
    },
  };
}

function startTickerChartRequest(ticker) {
  const existing = tickerChartRequests.get(ticker);
  existing?.controller.abort();
  const controller = new AbortController();
  const seq = (existing?.seq || 0) + 1;
  const request = {
    signal: controller.signal,
    isCurrent: () => tickerChartRequests.get(ticker)?.seq === seq && tickerChartRequests.get(ticker)?.controller === controller,
    complete: () => {
      if (tickerChartRequests.get(ticker)?.seq === seq && tickerChartRequests.get(ticker)?.controller === controller) {
        tickerChartRequests.delete(ticker);
      }
    },
  };
  tickerChartRequests.set(ticker, { controller, seq });
  return request;
}

function abortAllRequests() {
  Object.values(requestState).forEach((state) => state.controller?.abort());
  tickerChartRequests.forEach((request) => request.controller.abort());
  tickerChartRequests.clear();
}

function isAbortError(error) {
  return error?.name === "AbortError";
}

async function withBusyState(message, callback, request = null) {
  if (!watchlistTickers.length) {
    setStatus("Enter at least one ticker symbol.", "error");
    return;
  }
  setStatus(message, "");
  setRunControlsDisabled(true);
  try {
    await callback();
  } catch (error) {
    if (isAbortError(error)) return;
    setStatus(readableError(error), "error");
  } finally {
    setRunControlsDisabled(false);
    if (!request || request.isCurrent()) {
      request?.complete();
    }
  }
}

async function withNewsBusyState(message, callback, request = null) {
  if (!watchlistTickers.length) {
    setNewsStatus("Enter at least one ticker symbol.", "error");
    return;
  }
  setNewsStatus(message, "");
  refreshNewsButton.disabled = true;
  try {
    await callback();
  } catch (error) {
    if (isAbortError(error)) return;
    setNewsStatus(readableError(error), "error");
  } finally {
    if (!request || request.isCurrent()) {
      refreshNewsButton.disabled = false;
      request?.complete();
    }
  }
}

async function withAnalyticsBusyState(message, callback, request = null) {
  if (!watchlistTickers.length) {
    setAnalyticsStatus("Enter at least one ticker symbol.", "error");
    return;
  }
  setAnalyticsStatus(message, "");
  refreshAnalyticsButton.disabled = true;
  try {
    await callback();
  } catch (error) {
    if (isAbortError(error)) return;
    setAnalyticsStatus(readableError(error), "error");
  } finally {
    if (!request || request.isCurrent()) {
      refreshAnalyticsButton.disabled = false;
      request?.complete();
    }
  }
}

async function loadNews() {
  stopNewsEnrichmentPolling();
  const request = startRequest("news");
  await withNewsBusyState("Loading market and watchlist news...", async () => {
    const news = await postJson("/api/news", buildNewsPayload(), { signal: request.signal });
    if (!request.isCurrent()) return;
    renderNews(news);
    startNewsEnrichmentPolling(news);
    if (!news.warnings?.length) {
      setNewsStatus("", "");
    }
  }, request);
}

function startNewsEnrichmentPolling(news) {
  stopNewsEnrichmentPolling();
  if (!newsHasPendingAnalysis(news)) return;
  newsEnrichmentPollAttempts = 0;
  newsEnrichmentPollKey = JSON.stringify(buildNewsPayload());
  scheduleNewsEnrichmentPoll();
}

function scheduleNewsEnrichmentPoll() {
  if (newsEnrichmentPollAttempts >= NEWS_ENRICHMENT_MAX_POLLS) return;
  newsEnrichmentPollTimer = window.setTimeout(pollNewsEnrichment, NEWS_ENRICHMENT_POLL_INTERVAL_MS);
}

async function pollNewsEnrichment() {
  newsEnrichmentPollTimer = null;
  newsEnrichmentPollAttempts += 1;
  const payload = buildNewsPayload();
  if (JSON.stringify(payload) !== newsEnrichmentPollKey) return;
  try {
    const news = await postJson("/api/news", payload);
    if (JSON.stringify(buildNewsPayload()) !== newsEnrichmentPollKey) return;
    renderNews(news, { preserveExpanded: true });
    if (newsHasPendingAnalysis(news)) {
      scheduleNewsEnrichmentPoll();
    }
  } catch (error) {
    if (!isAbortError(error)) {
      scheduleNewsEnrichmentPoll();
    }
  }
}

function stopNewsEnrichmentPolling() {
  if (newsEnrichmentPollTimer) {
    window.clearTimeout(newsEnrichmentPollTimer);
    newsEnrichmentPollTimer = null;
  }
  newsEnrichmentPollAttempts = 0;
  newsEnrichmentPollKey = "";
}

function newsHasPendingAnalysis(news) {
  return Boolean(news?.ticker_news?.some((group) => (
    group.articles || []
  ).some((article) => article.analysis_status === "pending")));
}

async function loadLevels() {
  if (!watchlistTickers.length) {
    setStatus("Enter at least one ticker symbol.", "error");
    return;
  }
  const request = startRequest("levels");
  await withBusyState("Generating levels...", () => fetchLevels(request), request);
}

async function loadScanner() {
  if (!watchlistTickers.length) {
    setScannerStatus("Enter at least one ticker symbol.", "error");
    return;
  }
  const request = startRequest("scanner");
  setScannerStatus("Running scanner for the shared watchlist...", "");
  try {
    await fetchScanner(request);
  } catch (error) {
    if (isAbortError(error)) return;
    setScannerStatus(readableError(error), "error");
  } finally {
    if (request.isCurrent()) {
      request.complete();
    }
  }
}

async function loadLevelsAndScanner() {
  if (!watchlistTickers.length) {
    setStatus("Enter at least one ticker symbol.", "error");
    setScannerStatus("Enter at least one ticker symbol.", "error");
    return;
  }
  const levelsRequest = startRequest("levels");
  const scannerRequest = startRequest("scanner");
  setRunControlsDisabled(true);
  setStatus("Generating levels...", "");
  setScannerStatus("Running scanner for the shared watchlist...", "");

  const levelsLoad = fetchLevels(levelsRequest)
    .catch((error) => {
      if (!isAbortError(error) && levelsRequest.isCurrent()) {
        setStatus(readableError(error), "error");
      }
    })
    .finally(() => {
      if (levelsRequest.isCurrent()) {
        levelsRequest.complete();
      }
    });

  const scannerLoad = fetchScanner(scannerRequest)
    .catch((error) => {
      if (!isAbortError(error) && scannerRequest.isCurrent()) {
        setScannerStatus(readableError(error), "error");
      }
    })
    .finally(() => {
      if (scannerRequest.isCurrent()) {
        scannerRequest.complete();
      }
    });

  await Promise.allSettled([levelsLoad, scannerLoad]);
  setRunControlsDisabled(false);
}

async function fetchLevels(request) {
  const report = await postJson("/api/levels", buildPayload(), { signal: request.signal });
  if (!request.isCurrent()) return;
  renderReport(report);
  setStatus("", "");
  loadScoreHistory();
  loadChartHistory().catch((error) => {
    if (!isAbortError(error)) setStatus(readableError(error), "error");
  });
}

async function fetchScanner(request) {
  const scanner = await postJson("/api/scanner", buildScannerPayload(), { signal: request.signal });
  if (!request.isCurrent()) return;
  renderScanner(scanner);
  setScannerStatus(scanner.warnings?.length ? scanner.warnings.join(" ") : "", scanner.warnings?.length ? "error" : "");
  loadScoreHistory();
}

function setRunControlsDisabled(disabled) {
  runControlsDisableDepth = disabled
    ? runControlsDisableDepth + 1
    : Math.max(0, runControlsDisableDepth - 1);
  const shouldDisable = runControlsDisableDepth > 0;
  generateButton.disabled = shouldDisable;
  pdfButton.disabled = shouldDisable;
}

async function loadScoreHistory() {
  if (!watchlistTickers.length) {
    currentScoreHistory = null;
    scoreAnalyticsError = "";
    renderScoreAnalytics();
    return;
  }
  const request = startRequest("score");
  try {
    const scoreHistory = await postJson("/api/score-history", buildScoreHistoryPayload(), { signal: request.signal });
    if (!request.isCurrent()) return;
    currentScoreHistory = scoreHistory;
    scoreAnalyticsError = "";
    renderScoreAnalytics();
  } catch (error) {
    if (isAbortError(error)) return;
    currentScoreHistory = null;
    scoreAnalyticsError = readableError(error);
    renderScoreAnalytics();
  } finally {
    request.complete();
  }
}

function updateScoreAnalyticsSetting(key, value) {
  if (key === "levelBasis") {
    setLevelFilter(value);
    return;
  }
  const next = normalizeScoreAnalyticsSettings({
    ...scoreAnalyticsSettings,
    [key]: value,
  });
  scoreAnalyticsSettings = next;
  updateSettings({ scoreAnalytics: next });
  renderScoreAnalytics();
  if (["range", "scoreMetric"].includes(key)) {
    loadScoreHistory();
  }
}

async function loadSectorAnalytics() {
  const request = startRequest("analytics");
  await withAnalyticsBusyState("Refreshing sector analytics...", async () => {
    const analytics = await postJson("/api/sector-analytics", buildSectorAnalyticsPayload(), { signal: request.signal });
    if (!request.isCurrent()) return;
    renderSectorAnalytics(analytics);
    setAnalyticsStatus(analytics.warnings?.length ? analytics.warnings.join(" ") : "", analytics.warnings?.length ? "error" : "");
  }, request);
}

async function loadMarketSnapshot() {
  if (!watchlistTickers.length) {
    renderMarketSnapshotEmptyState();
    return;
  }
  const request = startRequest("snapshot");
  renderMarketSnapshotLoadingState();
  try {
    const snapshot = await postJson("/api/market-snapshot", buildMarketSnapshotPayload(), { signal: request.signal });
    if (!request.isCurrent()) return;
    renderMarketSnapshot(snapshot);
  } catch (error) {
    if (isAbortError(error)) return;
    currentMarketSnapshot = null;
    marketSnapshotEl.className = "market-strip empty";
    marketSnapshotEl.textContent = readableError(error);
    watchlistPerformanceEl.className = "performance-grid empty";
    watchlistPerformanceEl.textContent = "Watchlist performance could not be loaded.";
  } finally {
    request.complete();
  }
}

async function autoloadSavedWatchlist() {
  if (!watchlistTickers.length) return;
  setStatus("Loading saved levels...", "");
  await loadLevels();
  if (!watchlistTickers.length) return;
  setScannerStatus("Loading saved scanner...", "");
  setNewsStatus("Loading saved news and market snapshot...", "");
  loadMarketSnapshot();
  loadScanner();
  loadNews();
  if (appSettings.defaultView === "analytics" || currentAnalytics) {
    setAnalyticsStatus("Loading saved sector analytics...", "");
    loadSectorAnalytics();
  }
}

function startAutoRefreshTimer() {
  clearInterval(autoRefreshTimer);
  autoRefreshTimer = null;
  if (!appSettings.autoRefresh) return;
  autoRefreshTimer = window.setInterval(() => {
    if (!watchlistTickers.length) return;
    if (!currentReport && !currentScanner && !currentNews && !currentMarketSnapshot && !currentAnalytics) return;
    autoloadSavedWatchlist();
  }, AUTO_REFRESH_SECONDS * 1000);
}

function renderReport(report) {
  currentReport = {
    ...report,
    metrics: applyStoredCardOrder(report.metrics),
  };
  generatedAtEl.textContent = `Generated ${new Date(report.generated_at).toLocaleString()}`;
  renderCurrentReport();
}

function applyReportSearch(options = {}) {
  if (options.normalizeInput && reportSearchEl) {
    reportSearchEl.value = searchTickerTerms(reportSearchEl.value).join(", ");
  }
  renderCurrentReport();
}

function renderCurrentReport() {
  if (!currentReport?.metrics?.length) {
    resultsEl.className = "results empty";
    resultsEl.textContent = "";
    updateReportSearchStatus(0, 0);
    renderCharts();
    renderScoreAnalytics();
    return;
  }
  const visibleMetrics = filteredReportMetrics();
  updateReportSearchStatus(visibleMetrics.length, currentReport.metrics.length);
  if (!visibleMetrics.length) {
    resultsEl.className = "results empty";
    const terms = searchTickerTerms(reportSearchEl?.value || "");
    resultsEl.textContent = terms.length ? `No ticker matching "${terms.join(", ")}".` : "";
    renderCharts();
    renderScoreAnalytics();
    return;
  }
  resultsEl.className = `results report-layout-${reportLayout.replace("_", "-")}`;
  resultsEl.innerHTML = renderMetrics(visibleMetrics, reportLayout, {
    levelFilter,
    levelTypeWeights: activeLevelTypeWeights(),
  });
  persistCardOrder(currentReport.metrics.map((metric) => metric.ticker));
  renderCharts();
  renderScoreAnalytics();
}

function filteredReportMetrics() {
  const metrics = currentReport?.metrics || [];
  const terms = searchTickerTerms(reportSearchEl?.value || "");
  if (!terms.length) return metrics;
  return metrics.filter((metric) => terms.some((term) => String(metric.ticker || "").toUpperCase().includes(term)));
}

function updateReportSearchStatus(visibleCount, totalCount) {
  if (!reportSearchStatusEl) return;
  if (!totalCount) {
    reportSearchStatusEl.textContent = "";
    return;
  }
  const terms = searchTickerTerms(reportSearchEl?.value || "");
  reportSearchStatusEl.textContent = terms.length
    ? `${visibleCount} of ${totalCount}`
    : `${totalCount} total`;
}

function renderNews(news, options = {}) {
  currentNews = news;
  if (!options.preserveExpanded) {
    expandedNewsTickers.clear();
  }
  newsGeneratedAtEl.textContent = `News refreshed ${new Date(news.generated_at).toLocaleString()}`;
  updateNewsInfoTooltips(news.generated_at);
  renderWarningStatus(news.warnings || []);
  renderMarketNews(news.general_market || []);
  renderWatchlistNews(news.ticker_news || []);
}

function renderNewsEmptyState() {
  if (currentNews) return;
  newsGeneratedAtEl.textContent = "";
  updateNewsInfoTooltips();
  marketNewsEl.className = "news-list empty";
  marketNewsEl.textContent = "";
  watchlistNewsEl.className = "ticker-news-grid empty";
  watchlistNewsEl.textContent = "";
  setNewsStatus("", "");
}

function renderMarketSnapshotEmptyState() {
  if (currentMarketSnapshot) return;
  marketSnapshotEl.className = "market-strip empty";
  marketSnapshotEl.textContent = "";
  watchlistPerformanceEl.className = "performance-grid empty";
  watchlistPerformanceEl.textContent = "";
}

function renderMarketSnapshotLoadingState() {
  marketSnapshotEl.className = "market-strip empty";
  marketSnapshotEl.textContent = "Loading market performance...";
  watchlistPerformanceEl.className = "performance-grid empty";
  watchlistPerformanceEl.textContent = "Loading watchlist performance...";
}

function renderScannerEmptyState() {
  if (currentScanner) return;
  scannerGeneratedAtEl.textContent = "";
  scannerSetupEl.className = "scanner-empty";
  scannerSetupEl.textContent = "";
  setScannerStatus("", "");
}

function renderAnalyticsEmptyState() {
  if (currentAnalytics) return;
  analyticsGeneratedAtEl.textContent = "";
  sectorCoverageEl.className = "analytics-grid empty";
  sectorCoverageEl.textContent = "";
  sectorRecommendationsEl.className = "recommendation-grid empty";
  sectorRecommendationsEl.textContent = "";
  sectorTrendsEl.className = "scanner-empty";
  sectorTrendsEl.textContent = "";
  analyticsPatternEl.className = "scanner-empty";
  analyticsPatternEl.textContent = "";
  setAnalyticsStatus("", "");
}

function renderScanner(scanner) {
  currentScanner = scanner;
  scannerGeneratedAtEl.textContent = `Scanner generated ${new Date(scanner.generated_at).toLocaleString()}`;
  renderScannerSetup(scanner.setup_rows || []);
}

function renderScannerSetup(rows) {
  if (!rows.length) {
    scannerSetupEl.className = "scanner-empty";
    scannerSetupEl.textContent = "";
    return;
  }
  const sorted = [...rows].sort((left, right) => compareScannerRows(left, right, scannerSort.key, scannerSort.direction));
  const dataNotes = sorted.flatMap((row) => (row.data_notes || []).map((note) => ({ ticker: row.ticker, note })));
  const viewMode = normalizeScannerView(appSettings.scannerView);
  scannerSetupEl.className = `scanner-results scanner-view-${viewMode}`;
  scannerSetupEl.innerHTML = `
    <section class="scanner-table-section" aria-label="Scanner table">
      ${renderScannerTable(sorted)}
    </section>
    <section class="scanner-card-results" aria-label="Scanner cards">
      ${renderScannerCardSortControls()}
      <div class="scanner-card-list">
        ${sorted.map(renderScannerCard).join("")}
      </div>
    </section>
    ${renderScannerDataNotes(dataNotes)}
  `;
}

function renderScannerTable(rows) {
  return `
    <div class="scanner-table-wrap">
      <table class="scanner-table">
      <thead>
        <tr>${SCANNER_COLUMNS.map(renderScannerHeaderCell).join("")}</tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr class="tone-${scannerScoreTone(row.score)}">
            ${SCANNER_COLUMNS.map((column) => `<td class="${scannerColumnClass(column)}">${renderScannerTableCell(row, column)}</td>`).join("")}
          </tr>
          ${row.warnings?.length ? `<tr class="scanner-warning-row"><td colspan="${SCANNER_COLUMNS.length}"><strong>${escapeHtml(row.ticker)}:</strong> ${row.warnings.map(escapeHtml).join(" ")}</td></tr>` : ""}
        `).join("")}
      </tbody>
      </table>
    </div>
  `;
}

function renderScannerHeaderCell(column) {
  const active = scannerSort.key === column.key;
  const direction = scannerSort.direction === "desc" ? "desc" : "asc";
  return `
    <th class="${scannerColumnClass(column)}" title="${escapeHtml(column.title)}">
      <button type="button" data-scanner-sort="${escapeHtml(column.key)}" aria-label="Sort scanner by ${escapeHtml(column.title)}">
        ${escapeHtml(column.label)}
        ${active ? `<span class="scanner-sort-indicator">${direction}</span>` : ""}
      </button>
    </th>
  `;
}

function renderScannerCardSortControls() {
  return `
    <div class="scanner-card-toolbar">
      <label for="scanner-card-sort">
        <span>Sort</span>
        <select id="scanner-card-sort" data-scanner-sort-select>
          ${SCANNER_COLUMNS.map((column) => `
            <option value="${escapeHtml(column.key)}" ${scannerSort.key === column.key ? "selected" : ""}>${escapeHtml(column.title)}</option>
          `).join("")}
        </select>
      </label>
      <button type="button" data-scanner-sort-direction aria-label="Toggle scanner sort direction">
        ${scannerSort.direction === "desc" ? "Desc" : "Asc"}
      </button>
    </div>
  `;
}

function renderScannerCard(row) {
  const tone = scannerScoreTone(row.score);
  return `
    <article class="scanner-card tone-${tone}">
      <header class="scanner-card-header">
        <div>
          <h3>${escapeHtml(row.ticker)}</h3>
          <span>${formatValue(row.price)}</span>
        </div>
        ${renderScore(row.score)}
      </header>
      <div class="scanner-card-primary">
        ${renderScannerCardMetric("Signal", renderSignal(row.signal), { wide: true })}
        ${renderScannerCardMetric("R/R", renderRiskReward(row.risk_reward))}
        ${renderScannerCardMetric("Setup", formatScannerText(row.setup_level))}
        ${renderScannerCardMetric("Away", renderPercentText(row.setup_distance_percent, scannerSetupDistanceTone(row.setup_distance_percent)))}
      </div>
      <div class="scanner-card-zones">
        ${renderScannerCardMetric("Support", renderScannerZone(row.best_support), { wide: true })}
        ${renderScannerCardMetric("S Conf", renderConfidence(row.support_confidence))}
        ${renderScannerCardMetric("Resist", renderScannerZone(row.best_resistance), { wide: true })}
        ${renderScannerCardMetric("R Conf", renderConfidence(row.resistance_confidence))}
      </div>
      <div class="scanner-card-secondary">
        ${renderScannerCardMetric("VWAP", renderVwap(row.vwap_extension_percent, row.vwap_extension_label))}
        ${renderScannerCardMetric("RS SPY", renderRelativeStrength(row.rs_vs_spy_percent, row.rs_vs_spy_label))}
        ${renderScannerCardMetric("RS Sec", renderRelativeStrength(row.rs_vs_sector_percent, row.rs_vs_sector_label))}
        ${renderScannerCardMetric("Lows", renderLowsHeld(row.lows_held))}
        ${renderScannerCardMetric("Range", renderRange(row.range_compression))}
        ${renderScannerCardMetric("High", renderPercentText(row.off_high_percent, scannerOffHighTone(row.off_high_percent)))}
        ${renderScannerCardMetric("Mom", renderMomentum(row.momentum))}
      </div>
      ${row.warnings?.length ? `<p class="scanner-card-warning"><strong>${escapeHtml(row.ticker)}:</strong> ${row.warnings.map(escapeHtml).join(" ")}</p>` : ""}
    </article>
  `;
}

function renderScannerCardMetric(label, value, options = {}) {
  return `
    <div class="scanner-card-metric${options.wide ? " wide" : ""}">
      <span>${escapeHtml(label)}</span>
      <div>${value}</div>
    </div>
  `;
}

function scannerColumnClass(column) {
  return [
    `scanner-cell-${column.cell}`,
    column.align ? `align-${column.align}` : "",
    column.wrap ? "wrap" : "",
  ].filter(Boolean).join(" ");
}

function renderScannerTableCell(row, column) {
  const cells = {
    score: () => renderScore(row.score),
    ticker: () => `<span class="scanner-ticker">${escapeHtml(row.ticker)}</span>`,
    price: () => formatValue(row.price),
    signal: () => renderSignal(row.signal),
    vwap: () => renderVwap(row.vwap_extension_percent, row.vwap_extension_label),
    rsSpy: () => renderRelativeStrength(row.rs_vs_spy_percent, row.rs_vs_spy_label),
    rsSector: () => renderRelativeStrength(row.rs_vs_sector_percent, row.rs_vs_sector_label),
    support: () => renderScannerZone(row.best_support),
    supportConfidence: () => renderConfidence(row.support_confidence),
    resistance: () => renderScannerZone(row.best_resistance),
    resistanceConfidence: () => renderConfidence(row.resistance_confidence),
    riskReward: () => renderRiskReward(row.risk_reward),
    setupLevel: () => formatScannerText(row.setup_level),
    setupDistance: () => renderPercentText(row.setup_distance_percent, scannerSetupDistanceTone(row.setup_distance_percent)),
    lowsHeld: () => renderLowsHeld(row.lows_held),
    range: () => renderRange(row.range_compression),
    offHigh: () => renderPercentText(row.off_high_percent, scannerOffHighTone(row.off_high_percent)),
    momentum: () => renderMomentum(row.momentum),
  };
  return cells[column.cell]?.() || "&mdash;";
}

function renderScannerDataNotes(notes) {
  if (!notes.length) return "";
  return `
    <details class="scanner-data-notes">
      <summary>${notes.length} scanner data note${notes.length === 1 ? "" : "s"}</summary>
      <ul>
        ${notes.map(({ ticker, note }) => `<li><strong>${escapeHtml(ticker)}:</strong> ${escapeHtml(note)}</li>`).join("")}
      </ul>
    </details>
  `;
}

function renderSectorAnalytics(analytics) {
  currentAnalytics = analytics;
  analyticsGeneratedAtEl.textContent = `Analytics refreshed ${new Date(analytics.generated_at).toLocaleString()}`;
  renderSectorCoverage(analytics.sector_rows || []);
  renderSectorRecommendations(analytics.recommendations || []);
  renderSectorTrendTable(analytics.sector_rows || []);
  renderPatternAnalysis(analytics, analyticsPatternEl);
}

function renderSectorCoverage(rows) {
  if (!rows.length) {
    sectorCoverageEl.className = "analytics-grid empty";
    sectorCoverageEl.textContent = "No sector coverage was returned.";
    return;
  }
  sectorCoverageEl.className = "analytics-grid";
  sectorCoverageEl.innerHTML = rows.map((row) => `
    <article class="analytics-tile">
      <div>
        <h4>${escapeHtml(row.sector || "Other")}</h4>
        <span>${escapeHtml(row.etf || "No ETF")}</span>
      </div>
      <strong>${formatPercent(row.weight_percent)}</strong>
      <p>${row.ticker_count} ticker${row.ticker_count === 1 ? "" : "s"}: ${(row.tickers || []).map(escapeHtml).join(", ")}</p>
    </article>
  `).join("");
}

function renderSectorRecommendations(items) {
  if (!items.length) {
    sectorRecommendationsEl.className = "recommendation-grid empty";
    sectorRecommendationsEl.textContent = "No sector recommendations were returned.";
    return;
  }
  sectorRecommendationsEl.className = "recommendation-grid";
  sectorRecommendationsEl.innerHTML = items.map((item) => `
    <article class="recommendation-card ${escapeHtml(item.tone || "watch")}">
      <span>${escapeHtml(item.tone || "watch")}</span>
      <h4>${escapeHtml(item.title || "Sector note")}</h4>
      <p>${escapeHtml(item.message || "")}</p>
      ${(item.tickers || []).length ? `<div class="chips">${item.tickers.map((ticker) => `<span>${escapeHtml(ticker)}</span>`).join("")}</div>` : ""}
    </article>
  `).join("");
}

function renderSectorTrendTable(rows) {
  if (!rows.length) {
    sectorTrendsEl.className = "scanner-empty";
    sectorTrendsEl.textContent = "No sector trends were returned.";
    return;
  }
  sectorTrendsEl.className = "scanner-table-wrap";
  sectorTrendsEl.innerHTML = `
    <table class="scanner-table compact">
      <thead>
        <tr><th>Sector</th><th>ETF</th><th>Weight</th><th>Tickers</th><th>Avg Day</th><th>ETF Day</th><th>RS vs SPY</th><th>RS vs Sec</th><th>Setup</th><th>Strong</th><th>Pattern</th><th>Avg Dip</th><th>Recovery</th><th>Low Times</th><th>Read</th></tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td><strong>${escapeHtml(row.sector || "Other")}</strong></td>
            <td>${formatScannerText(row.etf)}</td>
            <td>${formatPercent(row.weight_percent)}</td>
            <td>${(row.tickers || []).map(escapeHtml).join(", ") || "&mdash;"}</td>
            <td>${formatSignedPercent(row.average_day_change_percent)}</td>
            <td>${formatSignedPercent(row.sector_etf_day_change_percent)}</td>
            <td>${formatSignedPercent(row.average_rs_vs_spy_percent)}</td>
            <td>${formatSignedPercent(row.average_rs_vs_sector_percent)}</td>
            <td>${formatValue(row.average_setup_score)}</td>
            <td>${row.strong_setup_count ?? 0}</td>
            <td>${formatPercent(row.average_pattern_consistency_percent)}</td>
            <td>${formatPercent(row.average_dip_percent)}</td>
            <td>${formatSignedPercent(row.average_recovery_percent)}</td>
            <td>${(row.common_low_times || []).map(escapeHtml).join(", ") || "&mdash;"}</td>
            <td>${renderRecommendationTone(row.recommendation_tone)}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderPatternAnalysis(scanner, targetEl) {
  const summary = scanner.pattern_summary || [];
  if (!summary.length) {
    targetEl.className = "scanner-empty";
    targetEl.textContent = "No pattern analysis was returned.";
    return;
  }
  targetEl.className = "scanner-patterns";
  const buckets = scanner.pattern_bucket_labels || scanner.pattern_buckets || [];
  targetEl.innerHTML = `
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

function renderMarketSnapshot(snapshot) {
  currentMarketSnapshot = snapshot;
  renderMarketPerformance(snapshot.market || []);
  renderWatchlistPerformance(snapshot.watchlist || []);
}

function renderMarketPerformance(rows) {
  if (!rows.length) {
    marketSnapshotEl.className = "market-strip empty";
    marketSnapshotEl.textContent = "No market performance was returned.";
    return;
  }
  marketSnapshotEl.className = "market-strip";
  marketSnapshotEl.innerHTML = rows.map((row) => renderPerformanceTile(row, { compact: true })).join("");
}

function renderWatchlistPerformance(rows) {
  if (!rows.length) {
    watchlistPerformanceEl.className = "performance-grid empty";
    watchlistPerformanceEl.textContent = "No watchlist performance was returned.";
    return;
  }
  watchlistPerformanceEl.className = "performance-grid";
  watchlistPerformanceEl.innerHTML = rows.map((row) => renderPerformanceTile(row)).join("");
}

function renderPerformanceTile(row, options = {}) {
  const changeClass = Number(row.change) < 0 || Number(row.change_percent) < 0 ? "negative" : "positive";
  const hasChange = row.change !== null && row.change !== undefined && row.change_percent !== null && row.change_percent !== undefined;
  const warnings = row.warnings?.length ? `<span class="performance-warning" title="${escapeHtml(row.warnings.join(" "))}">!</span>` : "";
  return `
    <article class="performance-tile ${options.compact ? "compact" : ""}">
      <div>
        <h4>${escapeHtml(row.label || row.symbol)}</h4>
        <strong>${formatValue(row.price)}</strong>
        <span class="performance-change ${hasChange ? changeClass : ""}">
          ${hasChange ? `${formatSignedValue(row.change)} ${formatSignedPercent(row.change_percent)}` : "&mdash;"}
        </span>
      </div>
      ${buildSparkline(row.sparkline || [], changeClass)}
      ${warnings}
    </article>
  `;
}

function buildSparkline(points, changeClass) {
  if (!points.length) return '<div class="sparkline empty"></div>';
  const width = 116;
  const height = 42;
  const values = points.map((point) => Number(point.close)).filter(Number.isFinite);
  if (!values.length) return '<div class="sparkline empty"></div>';
  let minValue = Math.min(...values);
  let maxValue = Math.max(...values);
  if (minValue === maxValue) {
    minValue -= 1;
    maxValue += 1;
  }
  const xFor = (index) => (points.length === 1 ? width / 2 : (index / (points.length - 1)) * width);
  const yFor = (value) => height - ((value - minValue) / (maxValue - minValue)) * height;
  const polyline = points.map((point, index) => `${xFor(index).toFixed(2)},${yFor(Number(point.close)).toFixed(2)}`).join(" ");
  return `
    <svg class="sparkline ${changeClass}" viewBox="0 0 ${width} ${height}" aria-hidden="true" focusable="false">
      <polyline points="${polyline}"></polyline>
    </svg>
  `;
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
  const filteredNews = filterTickerNewsGroups(tickerNews, watchlistNewsSearchEl?.value);
  const terms = searchTickerTerms(watchlistNewsSearchEl?.value || "");
  if (!filteredNews.length) {
    watchlistNewsEl.className = "ticker-news-grid empty";
    watchlistNewsEl.textContent = terms.length
      ? `No ticker matching "${terms.join(", ")}".`
      : "No watchlist news was returned.";
    return;
  }
  watchlistNewsEl.className = "ticker-news-grid";
  watchlistNewsEl.innerHTML = filteredNews.map(renderTickerNews).join("");
}

function filterTickerNewsGroups(tickerNews, query) {
  const terms = searchTickerTerms(query || "");
  if (!terms.length) return tickerNews;
  return tickerNews.filter((group) => terms.some((term) => String(group.ticker || "").toUpperCase().includes(term)));
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
    snapshot: `${refreshed} Major market instruments and saved watchlist day-to-date performance.`,
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
  const timelineTheme = isDarkMode() ? "dark" : "light";
  xNewsEl.innerHTML = `
    <a
      class="twitter-timeline"
      data-height="520"
      data-theme="${timelineTheme}"
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
  const imageUrl = safeUrl(article.thumbnail_url);
  const articleUrl = safeUrl(article.url);
  const image = imageUrl && !options.compact
    ? `<img src="${escapeHtml(imageUrl)}" alt="" loading="lazy" />`
    : "";
  const title = articleUrl
    ? `<a href="${escapeHtml(articleUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(article.title)}</a>`
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

function safeUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(String(value));
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch (_) {
    return null;
  }
}

function renderCharts() {
  const metrics = filteredReportMetrics();
  if (!currentReport?.metrics?.length || !metrics.length) {
    disposeCharts();
    chartsSectionEl.hidden = true;
    chartsSectionEl.className = "charts-section empty";
    chartsSectionEl.innerHTML = "";
    return;
  }

  chartsSectionEl.hidden = false;
  chartsSectionEl.className = "charts-section";
  chartsSectionEl.innerHTML = `
    <div class="charts-header">
      <h3>Charts</h3>
      ${renderGlobalChartToolbar()}
    </div>
    <div class="charts-grid">
      ${metrics.map(renderTickerChart).join("")}
    </div>
    <p class="chart-attribution">Charts use Lightweight Charts by <a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView</a>.</p>
  `;
  window.requestAnimationFrame(hydrateAllCharts);
}

function renderTickerChart(metric) {
  const settings = getEffectiveChartSettings(metric.ticker);
  const chart = getCachedChart(metric.ticker, settings);
  const warnings = chart?.warnings?.length
    ? `<details class="chart-warning"><summary>${chart.warnings.length} note${chart.warnings.length === 1 ? "" : "s"}</summary><ul>${chart.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul></details>`
    : "";
  const empty = chart && !chart.points?.length
    ? '<p class="chart-empty">No chart data returned.</p>'
    : '<p class="chart-empty">Loading chart...</p>';

  return `
    <article class="chart-card" data-chart-ticker="${escapeHtml(metric.ticker)}">
      <div class="chart-card-header">
        <h4>${escapeHtml(metric.ticker)}</h4>
        ${chartOverrides[metric.ticker] ? `<button class="chart-reset" type="button" data-chart-reset="${escapeHtml(metric.ticker)}">Reset</button>` : ""}
      </div>
      ${renderChartOverrideControls(metric.ticker, settings)}
      <div class="broker-chart" data-chart-canvas="${escapeHtml(metric.ticker)}">${chart?.points?.length ? "" : empty}</div>
      ${warnings}
    </article>
  `;
}

function renderGlobalChartToolbar() {
  return `
    <div class="chart-toolbar" aria-label="Chart defaults">
      ${renderChartSelect("Type", "type", chartSettings.type, CHART_TYPES, { global: true })}
      ${renderChartSelect("Range", "range", chartSettings.range, Object.keys(RANGE_INTERVALS), { global: true })}
      ${renderChartSelect("Interval", "interval", chartSettings.interval, RANGE_INTERVALS[chartSettings.range], { global: true })}
    </div>
  `;
}

function renderChartOverrideControls(ticker, settings) {
  return `
    <div class="chart-card-controls" aria-label="${escapeHtml(ticker)} chart controls">
      ${renderChartSelect("Type", "type", settings.type, CHART_TYPES, { ticker })}
      ${renderChartSelect("Range", "range", settings.range, Object.keys(RANGE_INTERVALS), { ticker })}
      ${renderChartSelect("Interval", "interval", settings.interval, RANGE_INTERVALS[settings.range], { ticker })}
    </div>
  `;
}

function renderChartSelect(label, key, value, options, context) {
  const attribute = context.global
    ? `data-chart-global="${escapeHtml(key)}"`
    : `data-chart-override="${escapeHtml(key)}" data-ticker="${escapeHtml(context.ticker)}"`;
  return `
    <label class="chart-select">
      <span>${escapeHtml(label)}</span>
      <select ${attribute}>
        ${options.map((option) => `<option value="${escapeHtml(option)}" ${option === value ? "selected" : ""}>${escapeHtml(formatChartOption(option))}</option>`).join("")}
      </select>
    </label>
  `;
}

async function loadChartHistory(settings = chartSettings, tickers = orderedPayloadTickers({ useCurrentReportOrder: true })) {
  if (!tickers.length) {
    currentChartHistory = null;
    renderCharts();
    return;
  }
  const request = startRequest("chart");
  try {
    const response = await postJson("/api/chart-history", buildChartHistoryPayload(settings, tickers), { signal: request.signal });
    if (!request.isCurrent()) return;
    currentChartHistory = response;
    cacheChartResponse(response);
    renderCharts();
  } finally {
    request.complete();
  }
}

async function loadTickerChartHistory(ticker, settings) {
  const key = chartCacheKey(ticker, settings);
  if (chartDataCache.has(key)) return;
  const request = startTickerChartRequest(ticker);
  try {
    const response = await postJson("/api/chart-history", buildChartHistoryPayload(settings, [ticker]), { signal: request.signal });
    if (!request.isCurrent()) return;
    cacheChartResponse(response);
    renderCharts();
  } finally {
    request.complete();
  }
}

function cacheChartResponse(response) {
  (response.charts || []).forEach((chart) => {
    chartDataCache.set(chartCacheKey(chart.ticker, chart), chart);
  });
}

function chartCacheKey(ticker, settings) {
  return `${ticker}|${settings.range}|${settings.interval}`;
}

function getCachedChart(ticker, settings) {
  return chartDataCache.get(chartCacheKey(ticker, settings));
}

function getEffectiveChartSettings(ticker) {
  return chartOverrides[ticker] || chartSettings;
}

function loadStoredChartSettings() {
  return normalizeChartSettings(appSettings.chartSettings);
}

function normalizeChartSettings(candidate = {}) {
  const type = CHART_TYPES.includes(candidate.type) ? candidate.type : DEFAULT_CHART_SETTINGS.type;
  const range = RANGE_INTERVALS[candidate.range] ? candidate.range : DEFAULT_CHART_SETTINGS.range;
  const supportedIntervals = RANGE_INTERVALS[range];
  const interval = supportedIntervals.includes(candidate.interval) ? candidate.interval : RANGE_DEFAULT_INTERVAL[range];
  return { type, range, interval };
}

function persistChartSettings() {
  updateSettings({ chartSettings });
  localStorage.setItem(CHART_SETTINGS_STORAGE_KEY, JSON.stringify(chartSettings));
}

async function updateGlobalChartSetting(key, value) {
  chartSettings = normalizeChartSettings({ ...chartSettings, [key]: value });
  persistChartSettings();
  renderChartSettingsControls();
  renderCharts();
  try {
    await loadChartHistory(chartSettings);
    setStatus("", "");
  } catch (error) {
    if (isAbortError(error)) return;
    setStatus(readableError(error), "error");
  }
}

async function updateChartOverride(ticker, key, value) {
  chartOverrides[ticker] = normalizeChartSettings({ ...(chartOverrides[ticker] || chartSettings), [key]: value });
  renderCharts();
  try {
    await loadTickerChartHistory(ticker, chartOverrides[ticker]);
    setStatus("", "");
  } catch (error) {
    if (isAbortError(error)) return;
    setStatus(readableError(error), "error");
  }
}

function resetChartOverride(ticker) {
  delete chartOverrides[ticker];
  renderCharts();
}

function hydrateAllCharts() {
  disposeCharts();
  if (!window.LightweightCharts) {
    chartsSectionEl.querySelectorAll(".broker-chart").forEach((container) => {
      container.textContent = "Chart library could not be loaded.";
    });
    return;
  }
  filteredReportMetrics().forEach((metric) => hydrateTickerChart(metric.ticker));
}

function hydrateTickerChart(ticker) {
  const settings = getEffectiveChartSettings(ticker);
  const chart = getCachedChart(ticker, settings);
  const container = chartsSectionEl.querySelector(`[data-chart-canvas="${cssEscape(ticker)}"]`);
  if (!container || !chart?.points?.length) return;
  container.textContent = "";
  const seriesData = formatChartSeriesData(chart.points, settings.type, settings.interval);
  const barSpacing = chartBarSpacing(container, seriesData.length);
  const theme = chartTheme();

  const api = LightweightCharts.createChart(container, {
    width: container.clientWidth || 360,
    height: 238,
    layout: {
      background: { type: "solid", color: theme.background },
      textColor: theme.text,
      fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
    },
    grid: {
      vertLines: { color: theme.grid },
      horzLines: { color: theme.grid },
    },
    rightPriceScale: { borderColor: theme.border },
    timeScale: {
      barSpacing,
      borderColor: theme.border,
      fixLeftEdge: true,
      fixRightEdge: true,
      minBarSpacing: 0.5,
      rightOffset: 0,
      timeVisible: isIntradayChartInterval(settings.interval),
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: theme.crosshair },
      horzLine: { color: theme.crosshair },
    },
  });
  const series = settings.type === "candles"
    ? api.addSeries(LightweightCharts.CandlestickSeries, {
      upColor: "#059669",
      downColor: "#dc2626",
      borderVisible: false,
      wickUpColor: "#059669",
      wickDownColor: "#dc2626",
    })
    : api.addSeries(LightweightCharts.LineSeries, {
      color: "#0f766e",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });

  series.setData(seriesData);
  api.timeScale().fitContent();
  window.requestAnimationFrame(() => {
    api.applyOptions({ width: container.clientWidth || 360, height: 238 });
    api.timeScale().applyOptions({ barSpacing: chartBarSpacing(container, seriesData.length), rightOffset: 0 });
    api.timeScale().fitContent();
  });
  chartInstances.set(ticker, api);

  if (window.ResizeObserver) {
    const observer = new ResizeObserver(() => {
      api.applyOptions({ width: container.clientWidth || 360, height: 238 });
      api.timeScale().applyOptions({ barSpacing: chartBarSpacing(container, seriesData.length), rightOffset: 0 });
      api.timeScale().fitContent();
    });
    observer.observe(container);
    chartResizeObservers.set(ticker, observer);
  }
}

function chartTheme() {
  if (!isDarkMode()) {
    return {
      background: "#ffffff",
      border: "#e2e8f0",
      crosshair: "#94a3b8",
      grid: "#eef2f7",
      text: "#475569",
    };
  }
  return {
    background: "#111827",
    border: "#263241",
    crosshair: "#64748b",
    grid: "#1f2937",
    text: "#94a3b8",
  };
}

function isDarkMode() {
  return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches || false;
}

function disposeCharts() {
  chartResizeObservers.forEach((observer) => observer.disconnect());
  chartResizeObservers.clear();
  chartInstances.forEach((chart) => chart.remove());
  chartInstances.clear();
}

function formatChartSeriesData(points, type, interval) {
  const data = points
    .map((point) => ({
      time: chartTimeFromTimestamp(point.timestamp, interval),
      open: Number(point.open),
      high: Number(point.high),
      low: Number(point.low),
      close: Number(point.close),
    }))
    .filter((point) => isValidChartTime(point.time) && Number.isFinite(point.close))
    .sort(compareChartTimes);
  if (type === "candles") return data;
  return data.map((point) => ({ time: point.time, value: point.close }));
}

function chartTimeFromTimestamp(timestamp, interval) {
  if (!isIntradayChartInterval(interval)) {
    return String(timestamp || "").slice(0, 10);
  }
  const parts = Object.fromEntries(
    EASTERN_CHART_TIME_FORMATTER
      .formatToParts(new Date(timestamp))
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  );
  return Math.floor(Date.UTC(
    Number(parts.year),
    Number(parts.month) - 1,
    Number(parts.day),
    Number(parts.hour),
    Number(parts.minute),
    Number(parts.second),
  ) / 1000);
}

function isIntradayChartInterval(interval) {
  return !["1d", "1wk", "1mo"].includes(interval);
}

function isValidChartTime(value) {
  return Number.isFinite(value) || /^\d{4}-\d{2}-\d{2}$/.test(String(value));
}

function compareChartTimes(left, right) {
  if (typeof left.time === "number" && typeof right.time === "number") {
    return left.time - right.time;
  }
  return String(left.time).localeCompare(String(right.time));
}

function chartBarSpacing(container, pointCount) {
  const width = container.clientWidth || 360;
  return Math.max(0.8, Math.min(24, (width - 24) / Math.max(pointCount, 1)));
}

function formatChartOption(option) {
  if (option === "line") return "Line";
  if (option === "candles") return "Candles";
  if (option === "1Y") return "1YR";
  return option;
}

function cssEscape(value) {
  return window.CSS?.escape ? window.CSS.escape(value) : String(value).replace(/["\\]/g, "\\$&");
}

function renderScoreAnalytics() {
  if (!scoreAnalyticsSectionEl) return;
  const shouldShow = Boolean(currentReport?.metrics?.length || currentScanner?.setup_rows?.length || currentScoreHistory || scoreAnalyticsError);
  if (!shouldShow) {
    scoreAnalyticsSectionEl.hidden = true;
    scoreAnalyticsSectionEl.className = "score-analytics-section empty";
    scoreAnalyticsSectionEl.innerHTML = "";
    return;
  }

  scoreAnalyticsSectionEl.hidden = false;
  scoreAnalyticsSectionEl.className = "score-analytics-section";
  const controls = renderScoreAnalyticsControls();
  if (scoreAnalyticsError) {
    scoreAnalyticsSectionEl.innerHTML = `
      ${controls}
      <div class="score-empty">${escapeHtml(scoreAnalyticsError)}</div>
    `;
    return;
  }
  if (!currentScoreHistory) {
    scoreAnalyticsSectionEl.innerHTML = `
      ${controls}
      <div class="score-empty">Score history will appear after levels or scanner data refreshes.</div>
    `;
    return;
  }

  const rows = sortedScoreRows(filteredScoreRows(currentScoreHistory.tickers || []));
  const warnings = [
    ...(currentScoreHistory.warnings || []),
    ...rows.flatMap((row) => row.warnings || []),
  ];
  const warningMarkup = warnings.length
    ? `<details class="score-warning"><summary>${warnings.length} score history note${warnings.length === 1 ? "" : "s"}</summary><ul>${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul></details>`
    : "";

  if (!rows.length) {
    const terms = searchTickerTerms(reportSearchEl?.value || "");
    scoreAnalyticsSectionEl.innerHTML = `
      ${controls}
      ${warningMarkup}
      <div class="score-empty">${terms.length ? `No score history matching "${terms.join(", ")}".` : "No score history matches the selected filters."}</div>
    `;
    return;
  }

  scoreAnalyticsSectionEl.innerHTML = `
    ${controls}
    ${warningMarkup}
    ${renderScoreSummary(rows)}
    ${renderScoreLineChart(rows)}
    <div class="score-trend-grid">
      ${rows.map(renderScoreTrendCard).join("")}
    </div>
  `;
}

function renderScoreAnalyticsControls() {
  return `
    <div class="score-analytics-header">
      <div>
        <h3>Score Analytics</h3>
        <p>Daily setup and weighted level score trends for the visible tickers.</p>
      </div>
      <div class="score-toolbar" aria-label="Score analytics controls">
        ${renderScoreSelect("Range", "range", scoreAnalyticsSettings.range, SCORE_ANALYTICS_RANGES, scoreOptionLabel)}
        ${renderScoreSelect("Metric", "scoreMetric", scoreAnalyticsSettings.scoreMetric, SCORE_ANALYTICS_METRICS, scoreOptionLabel)}
        ${renderScoreSelect("Chart", "chartMetric", scoreAnalyticsSettings.chartMetric, SCORE_ANALYTICS_CHART_METRICS, scoreOptionLabel)}
        ${renderScoreSelect("Basis", "levelBasis", levelFilter, LEVEL_FILTERS.map((filter) => filter.id), scoreOptionLabel)}
        ${renderScoreSelect("Move", "movement", scoreAnalyticsSettings.movement, SCORE_ANALYTICS_MOVEMENTS, scoreOptionLabel)}
        ${renderScoreSelect("Sort", "sort", scoreAnalyticsSettings.sort, SCORE_ANALYTICS_SORTS, scoreOptionLabel)}
      </div>
    </div>
  `;
}

function renderScoreSelect(label, key, value, options, labelFor = (item) => item) {
  return `
    <label class="score-select">
      <span>${escapeHtml(label)}</span>
      <select data-score-setting="${escapeHtml(key)}">
        ${options.map((option) => `<option value="${escapeHtml(option)}" ${option === value ? "selected" : ""}>${escapeHtml(labelFor(option))}</option>`).join("")}
      </select>
    </label>
  `;
}

function scoreOptionLabel(option) {
  const labels = {
    "7D": "7D",
    "30D": "30D",
    "90D": "90D",
    "1Y": "1Y",
    All: "All",
    setup: "Setup",
    level: "Level",
    both: "Both",
    heat: "Heat",
    all: "All",
    scanner: "Scanner",
    weight_20: "Weight 20+",
    improving: "Improving",
    declining: "Declining",
    flat: "Flat/New",
    watchlist: "Watchlist",
    gain: "Biggest Gain",
    drop: "Biggest Drop",
  };
  return labels[option] || option;
}

function filteredScoreRows(rows) {
  const visibleTickers = visibleScoreTickers();
  const visibleSet = visibleTickers === null ? null : new Set(visibleTickers);
  const movementFilter = scoreAnalyticsSettings.movement;
  return rows
    .filter((row) => !visibleSet || visibleSet.has(row.ticker))
    .filter((row) => movementFilter === "all" || scoreMovement(row) === movementFilter);
}

function visibleScoreTickers() {
  if (currentReport?.metrics?.length) {
    return filteredReportMetrics().map((metric) => metric.ticker);
  }
  const terms = searchTickerTerms(reportSearchEl?.value || "");
  const tickers = (currentScoreHistory?.tickers || []).map((row) => row.ticker);
  if (!terms.length) return null;
  return tickers.filter((ticker) => terms.some((term) => String(ticker || "").toUpperCase().includes(term)));
}

function sortedScoreRows(rows) {
  const order = orderedPayloadTickers({ useCurrentReportOrder: true });
  const indexFor = (ticker) => {
    const index = order.indexOf(ticker);
    return index === -1 ? Number.MAX_SAFE_INTEGER : index;
  };
  const valueOrEmpty = (value) => value === null || value === undefined ? Number.NEGATIVE_INFINITY : Number(value);
  return [...rows].sort((left, right) => {
    if (scoreAnalyticsSettings.sort === "setup") {
      return valueOrEmpty(right.latest_setup_score) - valueOrEmpty(left.latest_setup_score);
    }
    if (scoreAnalyticsSettings.sort === "level") {
      return valueOrEmpty(right.latest_level_score_normalized) - valueOrEmpty(left.latest_level_score_normalized);
    }
    if (scoreAnalyticsSettings.sort === "gain") {
      return valueOrEmpty(scoreMovementAmount(right)) - valueOrEmpty(scoreMovementAmount(left));
    }
    if (scoreAnalyticsSettings.sort === "drop") {
      const leftValue = scoreMovementAmount(left);
      const rightValue = scoreMovementAmount(right);
      const leftSort = leftValue === null || leftValue === undefined ? Number.POSITIVE_INFINITY : Number(leftValue);
      const rightSort = rightValue === null || rightValue === undefined ? Number.POSITIVE_INFINITY : Number(rightValue);
      return leftSort - rightSort;
    }
    return indexFor(left.ticker) - indexFor(right.ticker);
  });
}

function renderScoreSummary(rows) {
  const setupValues = rows.map((row) => row.latest_setup_score).filter((value) => value !== null && value !== undefined);
  const levelValues = rows.map((row) => row.latest_level_score_normalized).filter((value) => value !== null && value !== undefined);
  const heatValues = rows.map((row) => latestHeatScore(row)).filter((value) => value !== null && value !== undefined);
  const improving = rows.filter((row) => scoreMovement(row) === "improving").length;
  const declining = rows.filter((row) => scoreMovement(row) === "declining").length;
  const flat = rows.length - improving - declining;
  return `
    <div class="score-summary-strip">
      ${renderScoreSummaryTile("Tracked", rows.filter((row) => row.points?.length).length, `${rows.length} visible`)}
      ${renderScoreSummaryTile("Avg Heat", averageValue(heatValues), "hot/cold")}
      ${renderScoreSummaryTile("Avg Setup", averageValue(setupValues), "0-8")}
      ${renderScoreSummaryTile("Avg Level", averageValue(levelValues), "normalized")}
      ${renderScoreSummaryTile("Improving", improving, "1D")}
      ${renderScoreSummaryTile("Declining", declining, "1D")}
      ${renderScoreSummaryTile("Flat/New", flat, "1D")}
    </div>
  `;
}

function renderScoreSummaryTile(label, value, meta) {
  return `
    <div class="score-summary-tile">
      <span>${escapeHtml(label)}</span>
      <strong>${formatScoreSummaryValue(value)}</strong>
      <small>${escapeHtml(meta)}</small>
    </div>
  `;
}

function renderScoreLineChart(rows) {
  const metric = scoreAnalyticsSettings.chartMetric || "heat";
  const metricLabel = scoreOptionLabel(metric);
  const series = rows
    .map((row, rowIndex) => {
      const points = (row.points || [])
        .map((point) => ({
          date: point.date,
          value: scorePointMetricValue(point, metric),
        }))
        .filter((point) => point.date && Number.isFinite(point.value));
      return {
        ticker: row.ticker,
        color: SCORE_SERIES_COLORS[rowIndex % SCORE_SERIES_COLORS.length],
        points,
      };
    })
    .filter((row) => row.points.length);
  const dates = [...new Set(series.flatMap((row) => row.points.map((point) => point.date)))].sort();
  if (!series.length || !dates.length) {
    return `
      <section class="score-line-panel">
        <div class="score-line-header">
          <h4>${escapeHtml(metricLabel)} Trend</h4>
          <span>No ${escapeHtml(metricLabel.toLowerCase())} chart data</span>
        </div>
        <div class="score-line-empty"></div>
      </section>
    `;
  }

  const width = 760;
  const height = 190;
  const left = 42;
  const right = 12;
  const top = 14;
  const bottom = 30;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const xForDate = (date) => {
    const index = dates.indexOf(date);
    return dates.length === 1 ? left + plotWidth / 2 : left + (index / (dates.length - 1)) * plotWidth;
  };
  const yForValue = (value) => top + ((100 - clampPercent(value)) / 100) * plotHeight;
  const gridLines = [0, 25, 50, 75, 100].map((value) => {
    const y = yForValue(value);
    return `
      <g class="score-line-grid">
        <line x1="${left}" y1="${y.toFixed(2)}" x2="${width - right}" y2="${y.toFixed(2)}"></line>
        <text x="8" y="${(y + 4).toFixed(2)}">${value}</text>
      </g>
    `;
  }).join("");
  const seriesMarkup = series.map((row) => {
    const coordinates = row.points.map((point) => `${xForDate(point.date).toFixed(2)},${yForValue(point.value).toFixed(2)}`);
    const markerMarkup = row.points.length === 1
      ? `<circle cx="${xForDate(row.points[0].date).toFixed(2)}" cy="${yForValue(row.points[0].value).toFixed(2)}" r="4"></circle>`
      : "";
    return `
      <g class="score-line-series" style="--score-series-color:${escapeHtml(row.color)}">
        <polyline points="${coordinates.join(" ")}"></polyline>
        ${markerMarkup}
      </g>
    `;
  }).join("");
  const legend = series.map((row) => {
    const latest = row.points[row.points.length - 1];
    return `
      <span class="score-line-legend-item" style="--score-series-color:${escapeHtml(row.color)}">
        <i></i>${escapeHtml(row.ticker)} ${formatScoreSummaryValue(latest?.value)}
      </span>
    `;
  }).join("");
  const firstDate = dates[0];
  const lastDate = dates[dates.length - 1];

  return `
    <section class="score-line-panel">
      <div class="score-line-header">
        <h4>${escapeHtml(metricLabel)} Trend</h4>
        <span>${escapeHtml(firstDate)}${firstDate === lastDate ? "" : ` - ${escapeHtml(lastDate)}`}</span>
      </div>
      <svg class="score-line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(metricLabel)} trend for visible tickers">
        <title>${escapeHtml(metricLabel)} trend for visible tickers</title>
        ${gridLines}
        ${seriesMarkup}
      </svg>
      <div class="score-line-legend">${legend}</div>
    </section>
  `;
}

function renderScoreTrendCard(row) {
  const showSetup = scoreAnalyticsSettings.scoreMetric !== "level";
  const showLevel = scoreAnalyticsSettings.scoreMetric !== "setup";
  const movement = scoreMovement(row);
  return `
    <article class="score-trend-card movement-${movement}">
      <header>
        <div>
          <h4>${escapeHtml(row.ticker)}</h4>
          <span>${(row.points || []).length} point${(row.points || []).length === 1 ? "" : "s"}</span>
        </div>
        <span class="score-movement ${movement}">${escapeHtml(scoreOptionLabel(movement))}</span>
      </header>
      <div class="score-latest-grid">
        ${showSetup ? renderScoreLatest("Setup", formatSetupScore(row.latest_setup_score), row.setup_delta_1d, row.setup_delta_5d) : ""}
        ${showLevel ? renderScoreLatest("Level", formatLevelScore(row.latest_level_score, row.latest_level_score_normalized, row.latest_level_count), row.level_normalized_delta_1d, row.level_normalized_delta_5d) : ""}
      </div>
      ${renderScoreHeatThermometer(row)}
      ${renderScoreHeatStrip(row)}
      <div class="score-sparkline-grid">
        ${showSetup ? renderScoreSparkline(row.points || [], "setup_score", "Setup score") : ""}
        ${showLevel ? renderScoreSparkline(row.points || [], "level_score_normalized", "Level score") : ""}
      </div>
    </article>
  `;
}

function renderScoreLatest(label, value, delta1, delta5) {
  return `
    <div class="score-latest">
      <span>${escapeHtml(label)}</span>
      <strong>${value}</strong>
      <small>1D ${formatScoreDelta(delta1)} / 5D ${formatScoreDelta(delta5)}</small>
    </div>
  `;
}

function renderScoreSparkline(points, field, label) {
  const series = (points || [])
    .map((point, index) => ({ index, date: point.date, value: Number(point[field]) }))
    .filter((point) => Number.isFinite(point.value));
  if (series.length < 2) {
    return `
      <div class="score-sparkline-card">
        <span>${escapeHtml(label)}</span>
        <div class="score-sparkline-empty"></div>
      </div>
    `;
  }
  const width = 180;
  const height = 48;
  let minValue = Math.min(...series.map((point) => point.value));
  let maxValue = Math.max(...series.map((point) => point.value));
  if (minValue === maxValue) {
    minValue -= 1;
    maxValue += 1;
  }
  const pointsText = series.map((point, index) => {
    const x = series.length === 1 ? width / 2 : (index / (series.length - 1)) * width;
    const y = height - ((point.value - minValue) / (maxValue - minValue)) * height;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
  return `
    <div class="score-sparkline-card">
      <span>${escapeHtml(label)}</span>
      <svg class="score-sparkline" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(label)} trend">
        <title>${escapeHtml(label)} trend from ${escapeHtml(series[0].date)} to ${escapeHtml(series[series.length - 1].date)}</title>
        <polyline points="${pointsText}"></polyline>
      </svg>
    </div>
  `;
}

function renderScoreHeatThermometer(row) {
  const heat = latestHeatScore(row);
  const band = heatBand(heat);
  const width = heat === null ? 0 : clampPercent(heat);
  return `
    <div class="score-thermometer heat-${band.id}">
      <div>
        <span>Heat</span>
        <strong>${formatHeatScore(heat)}</strong>
      </div>
      <div class="score-thermometer-track" aria-label="Heat score ${escapeHtml(formatHeatScore(heat))}">
        <span style="width:${width.toFixed(1)}%"></span>
      </div>
      <small>${escapeHtml(band.label)}</small>
    </div>
  `;
}

function renderScoreHeatStrip(row) {
  const points = (row.points || []).filter((point) => point.date);
  if (!points.length) {
    return `
      <div class="score-heat-strip-card">
        <span>Daily Heat</span>
        <div class="score-heat-strip empty"></div>
      </div>
    `;
  }
  return `
    <div class="score-heat-strip-card">
      <span>Daily Heat</span>
      <div class="score-heat-strip">
        ${points.map((point) => {
          const heat = scorePointHeat(point);
          const band = heatBand(heat);
          const title = `${point.date}: ${formatHeatScore(heat)} ${band.label}`;
          return `<i class="heat-${band.id}" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}"></i>`;
        }).join("")}
      </div>
    </div>
  `;
}

function scorePointMetricValue(point, metric) {
  if (metric === "setup") return setupScoreNormalized(point.setup_score);
  if (metric === "level") return numericOrNull(point.level_score_normalized);
  return scorePointHeat(point);
}

function scorePointHeat(point) {
  const storedHeat = numericOrNull(point.heat_score);
  if (storedHeat !== null) return storedHeat;
  return heatScore(point.setup_score, point.level_score_normalized);
}

function latestHeatScore(row) {
  const storedHeat = numericOrNull(row.latest_heat_score);
  if (storedHeat !== null) return storedHeat;
  const points = row.points || [];
  for (let index = points.length - 1; index >= 0; index -= 1) {
    const heat = scorePointHeat(points[index]);
    if (heat !== null) return heat;
  }
  return heatScore(row.latest_setup_score, row.latest_level_score_normalized);
}

function heatScore(setupScore, levelScoreNormalized) {
  const setup = setupScoreNormalized(setupScore);
  const level = numericOrNull(levelScoreNormalized);
  const components = [];
  if (setup !== null) components.push({ value: setup, weight: 0.6 });
  if (level !== null) components.push({ value: clampPercent(level), weight: 0.4 });
  if (!components.length) return null;
  const weight = components.reduce((sum, item) => sum + item.weight, 0);
  const value = components.reduce((sum, item) => sum + item.value * item.weight, 0) / weight;
  return Math.round(value * 10) / 10;
}

function setupScoreNormalized(value) {
  const number = numericOrNull(value);
  if (number === null) return null;
  return Math.round((Math.max(0, Math.min(8, number)) / 8) * 1000) / 10;
}

function numericOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function clampPercent(value) {
  return Math.max(0, Math.min(100, Number(value)));
}

function heatBand(value) {
  const number = numericOrNull(value);
  if (number === null) return { id: "none", label: "No heat" };
  if (number < 40) return { id: "cold", label: "Cold" };
  if (number < 60) return { id: "cool", label: "Cool" };
  if (number < 75) return { id: "warm", label: "Warm" };
  return { id: "hot", label: "Hot" };
}

function formatHeatScore(value) {
  const number = numericOrNull(value);
  if (number === null) return "&mdash;";
  return `${number.toFixed(1).replace(/\.0$/, "")}`;
}

function scoreMovement(row) {
  const movement = scoreMovementAmount(row);
  if (movement === null || movement === undefined || Math.abs(Number(movement)) < 0.01) return "flat";
  return Number(movement) > 0 ? "improving" : "declining";
}

function scoreMovementAmount(row) {
  if (scoreAnalyticsSettings.scoreMetric === "setup") return row.setup_delta_1d;
  if (scoreAnalyticsSettings.scoreMetric === "level") return row.level_normalized_delta_1d;
  const heatDelta = numericOrNull(row.heat_delta_1d);
  if (heatDelta !== null) return heatDelta;
  const heatValues = (row.points || [])
    .map(scorePointHeat)
    .filter((value) => value !== null);
  return heatValues.length > 1 ? heatValues[heatValues.length - 1] - heatValues[heatValues.length - 2] : null;
}

function averageValue(values) {
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + Number(value), 0) / values.length;
}

function formatScoreSummaryValue(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "&mdash;";
  return Number(value).toFixed(1).replace(/\.0$/, "");
}

function formatSetupScore(value) {
  if (value === null || value === undefined) return "&mdash;";
  return `${Number(value)}/8`;
}

function formatLevelScore(score, normalized, count) {
  if (score === null || score === undefined) return "&mdash;";
  const normalizedText = normalized === null || normalized === undefined ? "" : ` (${Number(normalized).toFixed(1)}%)`;
  const countText = Number(count) > 0 ? ` / ${Number(count)} levels` : "";
  return `${Number(score).toLocaleString()}${normalizedText}${countText}`;
}

function formatScoreDelta(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '<span class="score-delta neutral">&mdash;</span>';
  const number = Number(value);
  const tone = number > 0 ? "positive" : number < 0 ? "negative" : "neutral";
  const formatted = `${number > 0 ? "+" : ""}${Number.isInteger(number) ? number : number.toFixed(1)}`;
  return `<span class="score-delta ${tone}">${escapeHtml(formatted)}</span>`;
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

function scannerDash() {
  return '<span class="scanner-muted">&mdash;</span>';
}

function scannerToneClass(tone) {
  return ["strong", "good", "watch", "danger", "neutral", "info"].includes(tone) ? tone : "neutral";
}

function scannerScoreTone(score) {
  if (score === null || score === undefined) return "neutral";
  const number = Number(score);
  if (number >= 7) return "strong";
  if (number >= 5) return "good";
  if (number >= 3) return "watch";
  return "danger";
}

function renderScore(score) {
  if (score === null || score === undefined) return scannerPill("&mdash;", "neutral", "Missing setup score");
  const number = Math.max(0, Math.min(8, Number(score)));
  const width = Math.round((number / 8) * 1000) / 10;
  const tone = scannerScoreTone(number);
  const label = `${number}/8`;
  return `
    <span class="scanner-score tone-${tone}" style="--score-width:${width}%;" title="${escapeHtml(label)} setup score" aria-label="${escapeHtml(number)} out of 8 setup score">
      <span>${escapeHtml(label)}</span>
    </span>
  `;
}

function scannerPill(label, tone, title = label, extraClass = "") {
  return `<span class="scanner-pill ${scannerToneClass(tone)} ${extraClass}" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}">${label}</span>`;
}

function scannerSymbol(symbol, tone, title) {
  return scannerPill(escapeHtml(symbol), tone, title, "scanner-symbol");
}

function renderScannerText(value, tone = "neutral", title = value) {
  if (value === null || value === undefined || value === "") return scannerDash();
  return `<span class="scanner-text tone-${scannerToneClass(tone)}" title="${escapeHtml(title)}">${escapeHtml(value)}</span>`;
}

function renderSignal(signal) {
  if (!signal) return scannerDash();
  const text = String(signal);
  if (text.startsWith("Reclaimed ")) {
    const level = text.replace("Reclaimed ", "");
    return renderScannerText(`+ ${level}`, "strong", text);
  }
  if (text.startsWith("Rejecting ")) {
    const level = text.replace("Rejecting ", "");
    return renderScannerText(`- ${level}`, "danger", text);
  }
  return renderScannerText(text, "neutral", text);
}

function renderMetricCombo(value, symbol, tone, title) {
  if (value === null || value === undefined || value === "") return scannerDash();
  return `
    <span class="scanner-metric-combo" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}">
      <span>${escapeHtml(value)}</span>
      ${scannerSymbol(symbol, tone, title)}
    </span>
  `;
}

function renderVwap(percent, label) {
  if (percent === null || percent === undefined || percent === "") return label ? renderScannerText(label, "neutral", label) : scannerDash();
  const text = String(label || "");
  const value = formatSignedPercent(percent);
  if (/chase|extended/i.test(text) || Number(percent) >= 0.75) return renderMetricCombo(value, "!", "watch", text || "VWAP extended");
  if (/below/i.test(text) || Number(percent) < -0.75) return renderMetricCombo(value, "-", "danger", text || "Below VWAP");
  if (/near|inline/i.test(text) || Number(percent) < 0) return renderMetricCombo(value, "0", "info", text || "Near VWAP");
  return renderMetricCombo(value, "+", "good", text || "Healthy VWAP extension");
}

function relativeStrengthSymbol(percent, label) {
  const text = String(label || "");
  const number = Number(percent);
  if (/very weak|↓↓/.test(text.toLowerCase()) || number <= -2) return ["--", "danger"];
  if (/weak/.test(text.toLowerCase()) || number < -0.75) return ["-", "danger"];
  if (/↑↑/.test(text) || number >= 2) return ["++", "strong"];
  if (/strong/i.test(text) || number > 0.75) return ["+", "good"];
  return ["0", "neutral"];
}

function renderRelativeStrength(percent, label) {
  if (percent === null || percent === undefined || percent === "") return label ? renderScannerText(label, "neutral", label) : scannerDash();
  const [symbol, tone] = relativeStrengthSymbol(percent, label);
  return renderMetricCombo(formatSignedPercent(percent), symbol, tone, label || "Relative strength inline");
}

function renderScannerZone(zone) {
  if (!zone) return scannerDash();
  return `<span class="scanner-zone" title="${escapeHtml(zone)}">${escapeHtml(zone)}</span>`;
}

function scannerConfidenceTone(value) {
  if (value === null || value === undefined) return "neutral";
  const number = Number(value);
  if (number >= 80) return "strong";
  if (number >= 65) return "good";
  if (number >= 50) return "watch";
  return "danger";
}

function renderConfidence(value) {
  if (value === null || value === undefined || value === "") return scannerDash();
  return scannerPill(escapeHtml(value), scannerConfidenceTone(value), `${value} confidence`);
}

function scannerRiskRewardTone(value) {
  if (value === null || value === undefined) return "neutral";
  const number = Number(value);
  if (number >= 3) return "strong";
  if (number >= 2) return "good";
  if (number >= 1) return "watch";
  return "danger";
}

function renderRiskReward(value) {
  if (value === null || value === undefined || value === "") return scannerDash();
  const label = `${formatValue(value)}R`;
  return scannerPill(escapeHtml(label), scannerRiskRewardTone(value), `${label} risk/reward`);
}

function renderLowsHeld(lowsHeld) {
  if (!lowsHeld) return scannerDash();
  const number = Number(lowsHeld);
  const tone = number >= 3 ? "strong" : number >= 2 ? "good" : "watch";
  return scannerPill(`${escapeHtml(number)}x`, tone, `${number} lows held`);
}

function renderRange(range) {
  if (!range) return scannerDash();
  const normalized = String(range).toLowerCase();
  const symbol = normalized === "tight" ? "T" : normalized === "wide" ? "W" : "0";
  const tone = normalized === "tight" ? "good" : normalized === "wide" ? "danger" : "neutral";
  return scannerSymbol(symbol, tone, range);
}

function renderMomentum(momentum) {
  if (!momentum) return scannerDash();
  const normalized = String(momentum).toLowerCase();
  if (normalized === "turning up") return scannerSymbol("++", "strong", momentum);
  if (normalized === "ticking up") return scannerSymbol("+", "good", momentum);
  if (normalized === "still falling") return scannerSymbol("--", "danger", momentum);
  return scannerSymbol("0", "neutral", momentum);
}

function scannerSetupDistanceTone(value) {
  if (value === null || value === undefined) return "neutral";
  const distance = Math.abs(Number(value));
  if (distance <= 0.25) return "strong";
  if (distance <= 0.5) return "good";
  if (distance <= 1) return "watch";
  return "neutral";
}

function scannerOffHighTone(value) {
  if (value === null || value === undefined) return "neutral";
  const number = Number(value);
  if (number > 0) return "strong";
  if (number >= -3 && number <= -0.5) return "good";
  if (number > -0.5 && number <= 0) return "watch";
  return "danger";
}

function renderPercentText(value, tone = "neutral") {
  if (value === null || value === undefined || value === "") return scannerDash();
  return renderScannerText(formatPercent(value), tone, formatPercent(value));
}

function renderRecommendationTone(tone) {
  const normalized = ["focus", "watch", "wait", "note"].includes(tone) ? tone : "watch";
  const pillTone = normalized === "focus" ? "strong" : normalized === "wait" ? "danger" : normalized === "note" ? "good" : "watch";
  return `<span class="scanner-pill ${pillTone}">${escapeHtml(normalized)}</span>`;
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

function formatSignedValue(value) {
  if (value === null || value === undefined || value === "") return "&mdash;";
  const number = Number(value);
  return `${number >= 0 ? "+" : ""}${number.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function heatmapColor(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return isDarkMode() ? "#1f2937" : "#f8fafc";
  const bounded = Math.max(-3, Math.min(3, Number(value)));
  const intensity = Math.abs(bounded) / 3;
  if (bounded < 0) {
    return isDarkMode()
      ? `rgba(248, 113, 113, ${0.16 + intensity * 0.50})`
      : `rgba(185, 28, 28, ${0.12 + intensity * 0.62})`;
  }
  return isDarkMode()
    ? `rgba(45, 212, 191, ${0.16 + intensity * 0.50})`
    : `rgba(15, 118, 110, ${0.12 + intensity * 0.62})`;
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
  setTimedStatus(statusEl, message, type);
}

function setNewsStatus(message, type) {
  setTimedStatus(newsStatusEl, message, type);
}

function setScannerStatus(message, type) {
  setTimedStatus(scannerStatusEl, message, type);
}

function setAnalyticsStatus(message, type) {
  setTimedStatus(analyticsStatusEl, message, type);
}

function setTimedStatus(element, message, type) {
  const existingTimer = statusTimers.get(element);
  if (existingTimer) window.clearTimeout(existingTimer);
  element.textContent = message;
  element.className = `status ${type}`.trim();
  if (message && type === "success") {
    statusTimers.set(element, window.setTimeout(() => {
      if (element.textContent === message) {
        element.textContent = "";
        element.className = "status";
      }
    }, 3200));
  }
}

function filenameFromDisposition(header) {
  const match = header?.match(/filename="?([^";]+)"?/);
  return match?.[1] || "equity-levels.pdf";
}

function readableError(error) {
  try {
    const parsed = JSON.parse(error.message);
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail)) {
      return parsed.detail
        .map((item) => item.msg || item.message || String(item))
        .join(" ");
    }
    if (parsed.detail) return JSON.stringify(parsed.detail);
  } catch (_) {
    // Keep the original message below when the server did not return JSON.
  }
  return error.message || "Request failed.";
}
