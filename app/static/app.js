const STORAGE_KEY = "equity-levels-watchlist";
const METRICS_STORAGE_KEY = "equity-levels-selected-metrics";
const CARD_ORDER_STORAGE_KEY = "equity-levels-card-order";
const DEFAULT_CHART_WINDOW_DAYS = 365;

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
const saveStateEl = document.querySelector("#save-state");
const chartsSectionEl = document.querySelector("#charts-section");

let currentReport = null;
let draggedTicker = null;
const chartWindows = {};
const hiddenChartGroups = {};

tickersInput.value = localStorage.getItem(STORAGE_KEY) || "";
renderMetricSelector();

metricSelectorEl.addEventListener("change", () => {
  persistSelectedMetrics();
  saveStateEl.textContent = "Saved locally";
});

tickersInput.addEventListener("input", () => {
  localStorage.setItem(STORAGE_KEY, tickersInput.value);
  saveStateEl.textContent = "Saved locally";
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

chartsSectionEl.addEventListener("input", (event) => {
  const slider = event.target.closest("[data-window-bound]");
  if (!slider) return;
  updateChartWindowBound(slider.dataset.ticker, slider.dataset.windowBound, Number(slider.value));
  renderCharts();
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
          <span class="drag-handle" aria-hidden="true">⋮⋮</span>
          <h3>${escapeHtml(metric.ticker)}</h3>
        </div>
        <div class="card-actions" aria-label="Reorder ${escapeHtml(metric.ticker)} card">
          <button type="button" data-move="up" data-ticker="${escapeHtml(metric.ticker)}" ${index === 0 ? "disabled" : ""}>↑</button>
          <button type="button" data-move="down" data-ticker="${escapeHtml(metric.ticker)}" ${index === currentReport.metrics.length - 1 ? "disabled" : ""}>↓</button>
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
      <article class="chart-card">
        <div class="chart-card-header"><h4>${escapeHtml(metric.ticker)}</h4></div>
        <p class="chart-empty">No daily close history was returned for this ticker.</p>
      </article>
    `;
  }

  const maxWindow = Math.min(DEFAULT_CHART_WINDOW_DAYS, history.length);
  const range = normalizeChartWindow(metric.ticker, maxWindow);
  const selectedWindow = range.end - range.start + 1;
  const visibleHistory = history.slice(range.start - 1, range.end);
  const levels = getChartLevels(metric);
  const hiddenGroups = getHiddenChartGroups(metric.ticker);
  const visibleLevels = levels.filter((level) => !hiddenGroups.has(level.group));
  const showClose = !hiddenGroups.has("close");

  return `
    <article class="chart-card">
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
      <rect class="chart-bg" x="0" y="0" width="${width}" height="${height}" rx="18"></rect>
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
          <div class="range-slider" style="--range-start:${((range.start - 1) / Math.max(1, maxWindow - 1)) * 100}%; --range-end:${((range.end - 1) / Math.max(1, maxWindow - 1)) * 100}%">
            <input class="chart-window chart-window-start" data-ticker="${escapeHtml(ticker)}" data-window-bound="start" type="range" min="1" max="${maxWindow}" value="${range.start}" aria-label="First visible session" />
            <input class="chart-window chart-window-end" data-ticker="${escapeHtml(ticker)}" data-window-bound="end" type="range" min="1" max="${maxWindow}" value="${range.end}" aria-label="Last visible session" />
          </div>
          <output>${selectedWindow} session${selectedWindow === 1 ? "" : "s"}</output>
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
  const metric = currentReport?.metrics?.find((item) => item.ticker === ticker);
  const maxWindow = Math.min(DEFAULT_CHART_WINDOW_DAYS, metric?.price_history?.length || 1);
  const range = normalizeChartWindow(ticker, maxWindow);
  if (bound === "start") {
    range.start = Math.min(Math.max(Math.round(value), 1), range.end);
  } else {
    range.end = Math.max(Math.min(Math.round(value), maxWindow), range.start);
  }
  chartWindows[ticker] = range;
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
  renderCharts();
}

function applyChartWindowPreset(ticker, preset) {
  const metric = currentReport?.metrics?.find((item) => item.ticker === ticker);
  if (!metric?.price_history?.length) return;
  const maxWindow = Math.min(DEFAULT_CHART_WINDOW_DAYS, metric.price_history.length);
  const windowSize = getPresetWindow(metric.price_history, preset);
  chartWindows[ticker] = { start: maxWindow - windowSize + 1, end: maxWindow };
  renderCharts();
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

function sortLevels(levels, direction) {
  const sorted = [...(levels || [])].sort((left, right) => left - right);
  return direction === "desc" ? sorted.reverse() : sorted;
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "—";
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
