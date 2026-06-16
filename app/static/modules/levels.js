import { escapeHtml, formatDisplayValue } from "./formatters.js";

export function renderMetrics(metrics, layout, options = {}) {
  const levelFilter = normalizeLevelFilter(options.levelFilter);
  const levelTypeWeights = activeLevelTypeWeights(options.levelTypeWeights);
  if (layout === "price_ladder") return renderPriceLadder(metrics, levelFilter, levelTypeWeights);
  if (layout === "compact") return renderCompact(metrics, levelFilter, levelTypeWeights);
  if (layout === "compare") return renderCompare(metrics, levelFilter, levelTypeWeights);
  return renderGrid(metrics, levelFilter, levelTypeWeights);
}

function renderGrid(metrics, levelFilter, levelTypeWeights) {
  return metrics.map((metric, index) => renderGridCard(metric, index, metrics.length, levelFilter, levelTypeWeights)).join("");
}

function renderGridCard(metric, index, totalCount, levelFilter, levelTypeWeights) {
  return `
    <article class="card" draggable="true" data-ticker="${escapeHtml(metric.ticker)}">
      ${renderCardHeader(metric, index, totalCount)}
      <div class="card-body">
        ${sectionsFor(metric).map((section) => renderMetricSection(section, levelFilter, levelTypeWeights)).join("")}
        ${renderWarnings(metric)}
      </div>
    </article>
  `;
}

function renderMetricSection(section, levelFilter, levelTypeWeights) {
  const rows = (section.rows || []).filter((row) => displayRowMatchesFilter(row, levelFilter, levelTypeWeights));
  const lists = (section.lists || []).map((row) => filterDisplayList(row, levelFilter, levelTypeWeights)).filter((row) => row.values?.length);
  if (!rows.length && !lists.length) return "";
  return `
    <section class="metric-section">
      <h4>${escapeHtml(section.title)}</h4>
      ${rows.length ? `<div class="metric-grid">${rows.map((row) => `<div class="metric"><span>${escapeHtml(row.label)}</span><strong>${formatDisplayValue(row.value)}</strong></div>`).join("")}</div>` : ""}
      ${lists.length ? `<div class="level-lists">${lists.map((row) => renderLevelList(row.label, row.values)).join("")}</div>` : ""}
    </section>
  `;
}

function renderLevelList(label, levels) {
  if (!levels?.length) return "";
  return `
    <section class="level-list">
      <h5>${escapeHtml(label)}</h5>
      <div class="chips">
        ${levels.map((level) => `<span>${formatDisplayValue(level)}</span>`).join("")}
      </div>
    </section>
  `;
}

function renderPriceLadder(metrics, levelFilter, levelTypeWeights) {
  return metrics.map((metric, index) => {
    const { priceRows, currentPrice, nonPriceRows } = ladderRows(metric, levelFilter, levelTypeWeights);
    return `
      <article class="card ladder-card" draggable="true" data-ticker="${escapeHtml(metric.ticker)}">
        ${renderCardHeader(metric, index, metrics.length)}
        <div class="ladder-body">
          ${renderLadderTable(priceRows, currentPrice)}
          ${renderNonPriceRows(nonPriceRows)}
          ${renderWarnings(metric)}
        </div>
      </article>
    `;
  }).join("");
}

function renderLadderTable(priceRows, currentPrice) {
  const rows = insertCurrentPrice(priceRows, currentPrice);
  if (!rows.length) return '<div class="metric-empty">No price levels returned.</div>';
  return `
    <table class="levels-table">
      <thead><tr><th>Level</th><th>Price</th><th>% From Now</th></tr></thead>
      <tbody>
        ${rows.map((row) => {
          const current = row.kind === "current";
          const side = current ? "current" : currentPrice === null ? "neutral" : row.numericValue > currentPrice ? "above" : "below";
          const priority = row.emphasis === "priority" ? " priority" : "";
          return `
            <tr class="ladder-row ${side}${priority}">
              <td>${escapeHtml(row.label)}</td>
              <td>${formatMoney(row.numericValue)}</td>
              <td>${current ? "&mdash;" : formatDistancePercent(currentPrice, row.numericValue)}</td>
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
  `;
}

function renderNonPriceRows(rows) {
  if (!rows.length) return "";
  return `
    <div class="ladder-notes">
      ${rows.map((row) => `
        <div><span>${escapeHtml(row.label)}</span><strong>${formatDisplayValue(row.value)}</strong></div>
      `).join("")}
    </div>
  `;
}

function renderCompact(metrics, levelFilter, levelTypeWeights) {
  return metrics.map((metric, index) => {
    const rows = flattenDisplayRows(metric, levelFilter, levelTypeWeights);
    return `
      <article class="card compact-card" draggable="true" data-ticker="${escapeHtml(metric.ticker)}">
        ${renderCardHeader(metric, index, metrics.length)}
        <div class="compact-body">
          ${rows.map((row) => `
            <div class="compact-metric ${row.emphasis === "priority" ? "priority" : ""} ${row.emphasis === "current" ? "current" : ""}">
              <span>${escapeHtml(row.label)}</span>
              <strong>${formatDisplayValue(row.value)}</strong>
            </div>
          `).join("")}
          ${renderWarnings(metric)}
        </div>
      </article>
    `;
  }).join("");
}

function renderCompare(metrics, levelFilter, levelTypeWeights) {
  const rowsByTicker = metrics.map((metric) => ({ metric, rows: flattenDisplayRows(metric, levelFilter, levelTypeWeights) }));
  const labels = [];
  rowsByTicker.forEach(({ rows }) => {
    rows.forEach((row) => {
      if (!labels.includes(row.label)) labels.push(row.label);
    });
  });
  if (!labels.length) return '<div class="metric-empty">No report rows returned.</div>';
  return `
    <div class="compare-wrap">
      <table class="compare-table">
        <thead>
          <tr><th>Ticker</th>${labels.map((label) => `<th>${escapeHtml(label)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${rowsByTicker.map(({ metric, rows }) => {
            const byLabel = Object.fromEntries(rows.map((row) => [row.label, row]));
            return `
              <tr>
                <th>${escapeHtml(metric.ticker)}</th>
                ${labels.map((label) => {
                  const row = byLabel[label];
                  return `<td>${row ? formatDisplayValue(row.value) : "&mdash;"}</td>`;
                }).join("")}
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderCardHeader(metric, index, totalCount) {
  return `
    <div class="card-header">
      <div>
        <span class="drag-handle" aria-hidden="true">&vellip;&vellip;</span>
        <h3>${escapeHtml(metric.ticker)}</h3>
      </div>
      <div class="card-actions" aria-label="Reorder ${escapeHtml(metric.ticker)} card">
        <button type="button" data-move="up" data-ticker="${escapeHtml(metric.ticker)}" ${index === 0 ? "disabled" : ""} aria-label="Move ${escapeHtml(metric.ticker)} up">&uarr;</button>
        <button type="button" data-move="down" data-ticker="${escapeHtml(metric.ticker)}" ${index === totalCount - 1 ? "disabled" : ""} aria-label="Move ${escapeHtml(metric.ticker)} down">&darr;</button>
      </div>
    </div>
  `;
}

function renderWarnings(metric) {
  return metric.warnings?.length
    ? `<details class="warning"><summary>${metric.warnings.length} data warning${metric.warnings.length === 1 ? "" : "s"}</summary><ul>${metric.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul></details>`
    : "";
}

function sectionsFor(metric) {
  return metric.display_sections || [];
}

function flattenDisplayRows(metric, levelFilter = "all", levelTypeWeights = LEVEL_TYPE_WEIGHTS) {
  return sectionsFor(metric).flatMap((section) => [
    ...(section.rows || []).map((row) => normalizeDisplayRow(row)),
    ...(section.lists || []).map((row) => normalizeDisplayRow({
      ...row,
      value: (row.values || []).join(", "),
    })),
  ]).filter((row) => row.value !== "" && row.value !== "-" && rowMatchesFilter(row, levelFilter, levelTypeWeights));
}

function ladderRows(metric, levelFilter = "all", levelTypeWeights = LEVEL_TYPE_WEIGHTS) {
  const priceRows = [];
  const nonPriceRows = [];
  let currentPrice = null;

  sectionsFor(metric).forEach((section) => {
    (section.rows || []).forEach((rawRow) => {
      const row = normalizeDisplayRow(rawRow);
      if (!rowMatchesFilter(row, levelFilter, levelTypeWeights)) return;
      if (row.kind === "price" && row.numericValue !== null) {
        if (row.emphasis === "current") {
          currentPrice = row.numericValue;
        } else {
          priceRows.push(row);
        }
      } else if (row.value && row.value !== "-") {
        nonPriceRows.push(row);
      }
    });
    (section.lists || []).forEach((rawRow) => {
      const values = rawRow.numeric_values || [];
      values.forEach((numericValue, index) => {
        const label = `${rawRow.label} ${index + 1}`;
        if (!labelMatchesFilter(label, levelFilter, levelTypeWeights)) return;
        if (Number.isFinite(Number(numericValue))) {
          priceRows.push(normalizeDisplayRow({
            ...rawRow,
            label,
            value: (rawRow.values || [])[index],
            numeric_value: Number(numericValue),
          }));
        }
      });
    });
  });

  priceRows.sort((left, right) => right.numericValue - left.numericValue);
  return { priceRows, currentPrice, nonPriceRows };
}

function normalizeDisplayRow(row) {
  return {
    label: row.label || "",
    value: row.value || "",
    kind: row.kind || "text",
    numericValue: Number.isFinite(Number(row.numeric_value)) ? Number(row.numeric_value) : null,
    emphasis: row.emphasis || "normal",
  };
}

function filterDisplayList(row, levelFilter, levelTypeWeights) {
  const values = row.values || [];
  const numericValues = row.numeric_values || [];
  const nextValues = [];
  const nextNumericValues = [];
  values.forEach((value, index) => {
    const label = `${row.label} ${index + 1}`;
    if (!labelMatchesFilter(label, levelFilter, levelTypeWeights)) return;
    nextValues.push(value);
    if (Number.isFinite(Number(numericValues[index]))) {
      nextNumericValues.push(Number(numericValues[index]));
    }
  });
  return { ...row, values: nextValues, numeric_values: nextNumericValues };
}

function displayRowMatchesFilter(row, levelFilter, levelTypeWeights) {
  return rowMatchesFilter(normalizeDisplayRow(row), levelFilter, levelTypeWeights);
}

function rowMatchesFilter(row, levelFilter, levelTypeWeights) {
  if (row.emphasis === "current") return true;
  return labelMatchesFilter(row.label, levelFilter, levelTypeWeights);
}

function labelMatchesFilter(label, levelFilter, levelTypeWeights) {
  if (levelFilter === "scanner") return isScannerLevelLabel(label);
  if (levelFilter === "weight_20") return levelTypeWeight(label, levelTypeWeights) >= 20;
  return true;
}

function normalizeLevelFilter(value) {
  return ["all", "scanner", "weight_20"].includes(value) ? value : "all";
}

const LEVEL_TYPE_WEIGHTS = {
  "VWAP (Today)": 30,
  "PM High": 28,
  "PM Low": 28,
  "Prev High": 26,
  "Prev Low": 26,
  "5-Min High": 22,
  "5-Min Low": 22,
  "Daily Swing High": 24,
  "Daily Swing Low": 24,
  "1-Month High": 20,
  "1-Month Low": 20,
  "VWAP (Prev Session)": 18,
  "Prev Close": 16,
  "200 SMA (Daily)": 16,
  "50 SMA (Daily)": 14,
  "Pivot": 10,
  "R1 (Pivot)": 10,
  "S1 (Pivot)": 10,
  "9 EMA (5-Min)": 14,
  "20 EMA (5-Min)": 12,
  "20 EMA (Daily)": 12,
  "R2 (Pivot)": 8,
  "S2 (Pivot)": 8,
  "Earnings Gap Open": 8,
  "Pre-Earnings Close": 8,
  "Fib 61.8%": 8,
  "Fib 50.0%": 7,
  "Fib 38.2%": 6,
};

const LEVEL_TYPE_WEIGHT_ALIASES = {
  "VWAP Today": "VWAP (Today)",
  "Today VWAP": "VWAP (Today)",
  "Premarket High": "PM High",
  "Premarket Low": "PM Low",
  "First 5m High": "5-Min High",
  "First 5m Low": "5-Min Low",
  "1M High": "1-Month High",
  "1M Low": "1-Month Low",
  "VWAP 5m": "VWAP (Prev Session)",
  "200 SMA": "200 SMA (Daily)",
  "50 SMA": "50 SMA (Daily)",
  "9 EMA 5m": "9 EMA (5-Min)",
  "20 EMA Daily": "20 EMA (Daily)",
  "20 EMA 5m": "20 EMA (5-Min)",
  "R1": "R1 (Pivot)",
  "S1": "S1 (Pivot)",
  "R2": "R2 (Pivot)",
  "S2": "S2 (Pivot)",
  "Earnings Open": "Earnings Gap Open",
};

const SCANNER_LEVEL_LABELS = new Set([
  "VWAP (Today)",
  "VWAP Today",
  "Today VWAP",
  "VWAP (Prev Session)",
  "VWAP 5m",
  "PM High",
  "Premarket High",
  "PM Low",
  "Premarket Low",
  "Prev High",
  "Prev Low",
  "Prev Close",
  "5-Min High",
  "First 5m High",
  "5-Min Low",
  "First 5m Low",
  "1-Month High",
  "1M High",
  "1-Month Low",
  "1M Low",
  "200 SMA (Daily)",
  "200 SMA",
  "50 SMA (Daily)",
  "50 SMA",
  "Pivot",
  "R1 (Pivot)",
  "R1",
  "S1 (Pivot)",
  "S1",
]);

function activeLevelTypeWeights(levelTypeWeights) {
  return levelTypeWeights && typeof levelTypeWeights === "object" ? levelTypeWeights : LEVEL_TYPE_WEIGHTS;
}

function levelTypeWeight(label, levelTypeWeights = LEVEL_TYPE_WEIGHTS) {
  const weightMap = activeLevelTypeWeights(levelTypeWeights);
  if (label.startsWith("Daily Swing High") || label.startsWith("Swing Highs")) {
    return weightMap["Daily Swing High"] ?? 24;
  }
  if (label.startsWith("Daily Swing Low") || label.startsWith("Swing Lows")) {
    return weightMap["Daily Swing Low"] ?? 24;
  }
  return weightMap[LEVEL_TYPE_WEIGHT_ALIASES[label] || label] ?? 5;
}

function isScannerLevelLabel(label) {
  return SCANNER_LEVEL_LABELS.has(label) || label.startsWith("Daily Swing High") || label.startsWith("Daily Swing Low") || label.startsWith("Swing Highs") || label.startsWith("Swing Lows");
}

function insertCurrentPrice(priceRows, currentPrice) {
  if (currentPrice === null) return priceRows;
  const rows = [];
  let inserted = false;
  priceRows.forEach((row) => {
    if (!inserted && currentPrice >= row.numericValue) {
      rows.push({ kind: "current", label: "Current Price", numericValue: currentPrice, emphasis: "current" });
      inserted = true;
    }
    rows.push(row);
  });
  if (!inserted) {
    rows.push({ kind: "current", label: "Current Price", numericValue: currentPrice, emphasis: "current" });
  }
  return rows;
}

function formatMoney(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "&mdash;";
  return `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatDistancePercent(currentPrice, value) {
  if (currentPrice === null || !currentPrice || value === null || value === undefined) return "&mdash;";
  const percent = ((Number(value) - Number(currentPrice)) / Number(currentPrice)) * 100;
  return `${percent >= 0 ? "+" : ""}${percent.toFixed(2)}%`;
}
