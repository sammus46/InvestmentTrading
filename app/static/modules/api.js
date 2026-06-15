export async function getJson(url, options = {}) {
  const response = await fetch(url, { signal: options.signal });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function postJson(url, payload, options = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal: options.signal,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}
