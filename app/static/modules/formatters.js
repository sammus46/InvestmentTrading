export function formatDisplayValue(value) {
  if (value === null || value === undefined || value === "" || value === "-") return "&mdash;";
  return escapeHtml(value);
}

export function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[char]);
}
