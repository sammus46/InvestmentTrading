import { escapeHtml, formatDisplayValue } from "./formatters.js";

export function renderMetrics(metrics, layout) {
  if (layout === "price_ladder") return renderPriceLadder(metrics);
  if (layout === "compact") return renderCompact(metrics);
  if (layout === "compare") return renderCompare(metrics);
  return renderGrid(metrics);
}

function renderGrid(metrics) {
  return metrics.map((metric, index) => renderGridCard(metric, index, metrics.length)).join("");
}

function renderGridCard(metric, index, totalCount) {
  return `
    <article class="card" draggable="true" data-ticker="${escapeHtml(metric.ticker)}">
      ${renderCardHeader(metric, index, totalCount)}
      <div class="card-body">
        ${sectionsFor(metric).map(renderMetricSection).join("")}
        ${renderWarnings(metric)}
      </div>
    </article>
  `;
}

function renderMetricSection(section) {
  return `
    <section class="metric-section">
      <h4>${escapeHtml(section.title)}</h4>
      ${section.rows?.length ? `<div class="metric-grid">${section.rows.map((row) => `<div class="metric"><span>${escapeHtml(row.label)}</span><strong>${formatDisplayValue(row.value)}</strong></div>`).join("")}</div>` : ""}
      ${section.lists?.length ? `<div class="level-lists">${section.lists.map((row) => renderLevelList(row.label, row.values)).join("")}</div>` : ""}
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

function renderPriceLadder(metrics) {
  return metrics.map((metric, index) => {
    const { priceRows, currentPrice, nonPriceRows } = ladderRows(metric);
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

function renderCompact(metrics) {
  return metrics.map((metric, index) => {
    const rows = flattenDisplayRows(metric);
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

function renderCompare(metrics) {
  const rowsByTicker = metrics.map((metric) => ({ metric, rows: flattenDisplayRows(metric) }));
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

function flattenDisplayRows(metric) {
  return sectionsFor(metric).flatMap((section) => [
    ...(section.rows || []).map((row) => normalizeDisplayRow(row)),
    ...(section.lists || []).map((row) => normalizeDisplayRow({
      ...row,
      value: (row.values || []).join(", "),
    })),
  ]).filter((row) => row.value !== "" && row.value !== "-");
}

function ladderRows(metric) {
  const priceRows = [];
  const nonPriceRows = [];
  let currentPrice = null;

  sectionsFor(metric).forEach((section) => {
    (section.rows || []).forEach((rawRow) => {
      const row = normalizeDisplayRow(rawRow);
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
        if (Number.isFinite(Number(numericValue))) {
          priceRows.push(normalizeDisplayRow({
            ...rawRow,
            label: `${rawRow.label} ${index + 1}`,
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
