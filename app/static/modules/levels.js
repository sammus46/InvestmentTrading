import { escapeHtml, formatDisplayValue } from "./formatters.js";

export function renderMetricCard(metric, index, totalCount) {
  const sections = metric.display_sections || [];

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
          <button type="button" data-move="down" data-ticker="${escapeHtml(metric.ticker)}" ${index === totalCount - 1 ? "disabled" : ""} aria-label="Move ${escapeHtml(metric.ticker)} down">&darr;</button>
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
