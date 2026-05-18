const STORAGE_KEY = "equity-levels-watchlist";

const tickersInput = document.querySelector("#tickers");
const generateButton = document.querySelector("#generate");
const pdfButton = document.querySelector("#download-pdf");
const statusEl = document.querySelector("#status");
const resultsEl = document.querySelector("#results");
const generatedAtEl = document.querySelector("#generated-at");
const saveStateEl = document.querySelector("#save-state");

tickersInput.value = localStorage.getItem(STORAGE_KEY) || "";

tickersInput.addEventListener("input", () => {
  localStorage.setItem(STORAGE_KEY, tickersInput.value);
  saveStateEl.textContent = "Saved locally";
});

generateButton.addEventListener("click", async () => {
  await withBusyState("Generating levels...", async () => {
    const report = await postJson("/api/levels", { tickers: tickersInput.value });
    renderReport(report);
    setStatus("Report generated successfully.", "success");
  });
});

pdfButton.addEventListener("click", async () => {
  await withBusyState("Preparing PDF...", async () => {
    const response = await fetch("/api/reports/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tickers: tickersInput.value }),
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
  generatedAtEl.textContent = `Generated ${new Date(report.generated_at).toLocaleString()}`;
  resultsEl.className = "results";
  resultsEl.innerHTML = report.metrics.map(renderMetricCard).join("");
}

function renderMetricCard(metric) {
  const rows = [
    ["Prev Open", metric.previous_day.open],
    ["Prev High", metric.previous_day.high],
    ["Prev Low", metric.previous_day.low],
    ["Prev Close", metric.previous_day.close],
    ["Premarket High", metric.premarket.high],
    ["Premarket Low", metric.premarket.low],
    ["VWAP 5m", metric.previous_session_vwap_5m],
    ["52W High", metric.fifty_two_week.high],
    ["52W Low", metric.fifty_two_week.low],
    ["Earnings Date", formatDate(metric.earnings_gap.date)],
    ["Earnings Gap", metric.earnings_gap.gap],
    ["Earnings Gap %", metric.earnings_gap.gap_percent],
    ["First 5m High", metric.first_five_minutes.high],
    ["First 5m Low", metric.first_five_minutes.low],
    ["BB Upper", metric.bollinger_bands.upper],
    ["BB Middle", metric.bollinger_bands.middle],
    ["BB Lower", metric.bollinger_bands.lower],
  ];
  const warningHtml = metric.warnings.length
    ? `<div class="warning">${escapeHtml(metric.warnings.join(" "))}</div>`
    : "";
  return `
    <article class="card">
      <h3>${escapeHtml(metric.ticker)}</h3>
      <div class="metric-grid">
        ${rows.map(([label, value]) => `<div class="metric"><span>${label}</span><strong>${formatValue(value)}</strong></div>`).join("")}
      </div>
      <div class="level-lists">
        ${renderLevelList("Swing Highs", metric.swing_levels.highs)}
        ${renderLevelList("Swing Lows", metric.swing_levels.lows)}
      </div>
      ${warningHtml}
    </article>
  `;
}

function renderLevelList(label, levels) {
  if (!levels?.length) return "";
  return `
    <section class="level-list">
      <h4>${escapeHtml(label)}</h4>
      <div class="chips">
        ${levels.map((level) => `<span>${formatValue(level)}</span>`).join("")}
      </div>
    </section>
  `;
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return escapeHtml(value);
  return Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 });
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
