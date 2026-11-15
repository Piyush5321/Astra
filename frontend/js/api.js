// Thin client for the ASTRA REST API. Throws ApiError with a readable message.

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function detailMessage(body, status) {
  if (!body) return `Request failed (HTTP ${status})`;
  const d = body.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d.map((e) => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`).join("; ");
  }
  return `Request failed (HTTP ${status})`;
}

async function request(method, path, body) {
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    throw new ApiError("Cannot reach the ASTRA backend. Is the server running?", 0);
  }
  let data = null;
  const text = await res.text();
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) throw new ApiError(detailMessage(data, res.status), res.status);
  return data;
}

export const api = {
  health: () => request("GET", "/api/health"),
  reference: () => request("GET", "/api/reference"),
  targets: (body) => request("GET", `/api/targets${body ? `?body=${body}` : ""}`),
  locations: () => request("GET", "/api/locations"),
  location: (id) => request("GET", `/api/location/${encodeURIComponent(id)}`),
  terrain: (id) => request("GET", `/api/location/${encodeURIComponent(id)}/terrain`),
  datasets: () => request("GET", "/api/datasets"),
  missions: () => request("GET", "/api/missions"),
  createMission: (payload) => request("POST", "/api/missions", payload),
  runDiscovery: (payload) => request("POST", "/api/discovery/run", payload),
  runs: () => request("GET", "/api/discovery/runs"),
  results: (id) => request("GET", `/api/discovery/results/${id}`),
  compare: (payload) => request("POST", "/api/analysis/compare", payload),
  agentStatus: () => request("GET", "/api/agent/status"),
  chat: (payload) => request("POST", "/api/agent/chat", payload),
  reports: () => request("GET", "/api/reports"),
  generateReport: (payload) => request("POST", "/api/reports/generate", payload),
  climate: (lat, lon, start, end) =>
    request("GET", `/api/climate?lat=${lat}&lon=${lon}&start=${start}&end=${end}`),
};
