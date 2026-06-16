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
  newsPerTicker: NEWS_EXPANDED_HEADLINE_COUNT,
};
const LEVEL_FILTERS = [
  { id: "all", label: "All Levels", shortLabel: "All" },
  { id: "scanner", label: "Scanner Levels Only", shortLabel: "Scanner" },
  { id: "weight_20", label: "Weight 20+ Only", shortLabel: "Weight 20+" },
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
const statusEl = document.querySelector("#status");
const resultsEl = document.querySelector("#results");
const generatedAtEl = document.querySelector("#generated-at");
const runScannerButton = document.querySelector("#run-scanner");
const scannerStatusEl = document.querySelector("#scanner-status");
const scannerGeneratedAtEl = document.querySelector("#scanner-generated-at");
const scannerSetupEl = document.querySelector("#scanner-setup-results");
const saveStateEl = document.querySelector("#save-state");
const chartsSectionEl = document.querySelector("#charts-section");
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
let appSettings = loadStoredSettings();
let watchlistTickers = loadStoredWatchlist();
let scannerSort = { key: "score", direction: "desc" };
let draggedTicker = null;
let expandedNewsTickers = new Set();
let chartSettings = loadStoredChartSettings();
let reportLayout = loadStoredReportLayout();
let levelFilter = appSettings.levelFilter;
let watchlistRefreshTimer = null;
let autoRefreshTimer = null;
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
  await loadLevels();
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

reportSearchEl?.addEventListener("input", () => {
  renderCurrentReport();
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

runScannerButton.addEventListener("click", async () => {
  await loadScanner();
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
    newsPerTicker: normalizeNewsCount(candidate.newsPerTicker),
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

function normalizeNewsCount(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return DEFAULT_SETTINGS.newsPerTicker;
  return Math.max(1, Math.min(NEWS_MAX_HEADLINE_COUNT, Math.round(number)));
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
}

function renderSettingsControls() {
  if (settingsDefaultViewEl) settingsDefaultViewEl.value = appSettings.defaultView;
  if (settingsAutoLoadEl) settingsAutoLoadEl.checked = appSettings.autoLoad;
  if (settingsAutoRefreshEl) settingsAutoRefreshEl.checked = appSettings.autoRefresh;
  renderReportLayoutControl();
  renderLevelFilterControl();
  renderChartSettingsControls();
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
  chartDataCache.clear();
  Object.keys(chartOverrides).forEach((ticker) => delete chartOverrides[ticker]);
  disposeCharts();
  expandedNewsTickers.clear();
  generatedAtEl.textContent = "";
  resultsEl.className = "results empty";
  resultsEl.textContent = "";
  renderCharts();
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
  generateButton.disabled = true;
  pdfButton.disabled = true;
  try {
    await callback();
  } catch (error) {
    if (isAbortError(error)) return;
    setStatus(readableError(error), "error");
  } finally {
    if (!request || request.isCurrent()) {
      generateButton.disabled = false;
      pdfButton.disabled = false;
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

async function withScannerBusyState(message, callback, request = null) {
  if (!watchlistTickers.length) {
    setScannerStatus("Enter at least one ticker symbol.", "error");
    return;
  }
  setScannerStatus(message, "");
  runScannerButton.disabled = true;
  try {
    await callback();
  } catch (error) {
    if (isAbortError(error)) return;
    setScannerStatus(readableError(error), "error");
  } finally {
    if (!request || request.isCurrent()) {
      runScannerButton.disabled = false;
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
  const request = startRequest("news");
  await withNewsBusyState("Loading market and watchlist news...", async () => {
    const news = await postJson("/api/news", buildNewsPayload(), { signal: request.signal });
    if (!request.isCurrent()) return;
    renderNews(news);
    if (!news.warnings?.length) {
      setNewsStatus("", "");
    }
  }, request);
}

async function loadLevels() {
  const request = startRequest("levels");
  await withBusyState("Generating levels...", async () => {
    const report = await postJson("/api/levels", buildPayload(), { signal: request.signal });
    if (!request.isCurrent()) return;
    renderReport(report);
    setStatus("", "");
    loadChartHistory().catch((error) => {
      if (!isAbortError(error)) setStatus(readableError(error), "error");
    });
  }, request);
}

async function loadScanner() {
  const request = startRequest("scanner");
  await withScannerBusyState("Running scanner for the shared watchlist...", async () => {
    const scanner = await postJson("/api/scanner", buildScannerPayload(), { signal: request.signal });
    if (!request.isCurrent()) return;
    renderScanner(scanner);
    setScannerStatus(scanner.warnings?.length ? scanner.warnings.join(" ") : "", scanner.warnings?.length ? "error" : "");
  }, request);
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

function renderCurrentReport() {
  if (!currentReport?.metrics?.length) {
    resultsEl.className = "results empty";
    resultsEl.textContent = "";
    renderCharts();
    return;
  }
  const visibleMetrics = filteredReportMetrics();
  if (!visibleMetrics.length) {
    resultsEl.className = "results empty";
    const terms = searchTickerTerms(reportSearchEl?.value || "");
    resultsEl.textContent = terms.length ? `No ticker matching "${terms.join(", ")}".` : "";
    renderCharts();
    return;
  }
  resultsEl.className = `results report-layout-${reportLayout.replace("_", "-")}`;
  resultsEl.innerHTML = renderMetrics(visibleMetrics, reportLayout, {
    levelFilter,
    levelTypeWeights: activeLevelTypeWeights(),
  });
  persistCardOrder(currentReport.metrics.map((metric) => metric.ticker));
  renderCharts();
}

function filteredReportMetrics() {
  const metrics = currentReport?.metrics || [];
  const terms = searchTickerTerms(reportSearchEl?.value || "");
  if (!terms.length) return metrics;
  return metrics.filter((metric) => terms.some((term) => String(metric.ticker || "").toUpperCase().includes(term)));
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
  const dataNotes = sorted.flatMap((row) => (row.data_notes || []).map((note) => ({ ticker: row.ticker, note })));
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
            <td>${renderLowsHeld(row.lows_held)}</td>
            <td>${formatScannerText(row.range_compression)}</td>
            <td>${formatPercent(row.off_high_percent)}</td>
            <td>${renderMomentum(row.momentum)}</td>
          </tr>
          ${row.warnings?.length ? `<tr class="scanner-warning-row"><td colspan="${columns.length}">${row.warnings.map(escapeHtml).join(" ")}</td></tr>` : ""}
        `).join("")}
      </tbody>
    </table>
    ${renderScannerDataNotes(dataNotes)}
  `;
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
  if (score === null || score === undefined) return '<span class="scanner-pill neutral">&mdash;</span>';
  const number = Number(score);
  let tone = "danger";
  if (number >= 7) tone = "strong";
  else if (number >= 5) tone = "good";
  else if (number >= 3) tone = "watch";
  return `<span class="scanner-pill ${tone}">${number}/8</span>`;
}

function renderLowsHeld(lowsHeld) {
  if (!lowsHeld) return '<span class="scanner-pill neutral">&mdash;</span>';
  const number = Number(lowsHeld);
  const tone = number >= 3 ? "strong" : number >= 2 ? "good" : "watch";
  return `<span class="scanner-pill ${tone}">${number}x</span>`;
}

function renderMomentum(momentum) {
  if (!momentum) return '<span class="scanner-pill neutral">&mdash;</span>';
  const normalized = String(momentum).toLowerCase();
  let tone = "neutral";
  if (normalized === "turning up") tone = "strong";
  else if (normalized === "ticking up") tone = "good";
  else if (normalized === "still falling") tone = "danger";
  return `<span class="scanner-pill ${tone}">${escapeHtml(momentum)}</span>`;
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
