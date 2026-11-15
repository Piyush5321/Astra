// Shared DOM, formatting and state helpers.

export const DIM_COLORS = {
  geology: "#f59e0b",
  terrain: "#38bdf8",
  thermal: "#f87171",
  resources: "#34d399",
  hazards: "#a78bfa",
};

export const SOURCE_LABELS = {
  measured_dataset: "Measured dataset",
  derived: "Derived (DEM analysis)",
  literature_reference: "Literature reference",
  curated_classification: "Curated classification",
  physical_constraint: "Physical constraint",
  none: "No source",
};

export function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function html(strings, ...values) {
  return strings.reduce((out, s, i) => out + s + (i < values.length ? values[i] : ""), "");
}

export function num(v, digits = 1) {
  return v === null || v === undefined || Number.isNaN(v) ? "n/a" : Number(v).toFixed(digits);
}

export function fmtValue(value, unit, key = "") {
  if (value === null || value === undefined) return "n/a";
  if (unit === "fraction") return `${(value * 100).toFixed(1)}%`;
  // Temperature differences (ranges) are not converted to °C.
  if (unit === "K" && key.includes("range")) return `${value.toFixed(0)} K`;
  if (unit === "K") return `${value.toFixed(0)} K (${(value - 273.15).toFixed(0)} °C)`;
  if (Math.abs(value) >= 100) return `${Math.round(value).toLocaleString()} ${unit}`;
  return `${value.toFixed(2)} ${unit}`;
}

export function scoreColor(score) {
  if (score === null || score === undefined) return "#64748b";
  if (score >= 50) return "#34d399";
  if (score >= 30) return "#fbbf24";
  if (score >= 15) return "#fb923c";
  return "#f87171";
}

export function confidenceBadge(c) {
  return `<span class="badge conf-${esc(c)}" title="Confidence combines data coverage and the width of the score bounds">${esc(c)} confidence</span>`;
}

export function sourceBadge(type) {
  return `<span class="badge src-${esc(type)}">${esc(SOURCE_LABELS[type] || type)}</span>`;
}

export function loading(label = "Loading…") {
  return `<div class="state loading" role="status"><span class="spinner"></span>${esc(label)}</div>`;
}

export function errorState(err, retryLabel) {
  return `<div class="state error" role="alert"><strong>Something went wrong.</strong>
    <p>${esc(err.message || err)}</p>${retryLabel ? `<button class="btn" data-retry>${esc(retryLabel)}</button>` : ""}</div>`;
}

export function emptyState(title, body, action) {
  return `<div class="state empty"><strong>${esc(title)}</strong><p>${body}</p>${action || ""}</div>`;
}

export function scoreBar(r) {
  if (r.score === null || r.score === undefined) return `<div class="scorebar empty"></div>`;
  const lo = Math.max(0, r.bound_low);
  const hi = Math.min(100, r.bound_high);
  return `<div class="scorebar" title="Score ${num(r.score)}; bounds incl. missing data ${num(r.bound_low)}–${num(r.bound_high)}">
    <span class="range" style="left:${lo}%;width:${Math.max(0.5, hi - lo)}%"></span>
    <span class="fill" style="width:${r.score}%;background:${scoreColor(r.score)}"></span>
  </div>`;
}

// Minimal, safe markdown: escape first, then bold, code, lists, links to reports.
export function miniMarkdown(text) {
  const lines = esc(text).split("\n");
  let out = "";
  let list = null;
  const inline = (s) =>
    s
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/(\/api\/reports\/[a-f0-9]+\/pdf)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  for (const raw of lines) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*] (.*)/);
    const ordered = line.match(/^\s*\d+\. (.*)/);
    const kind = bullet ? "ul" : ordered ? "ol" : null;
    if (kind !== list) {
      if (list) out += `</${list}>`;
      if (kind) out += `<${kind}>`;
      list = kind;
    }
    if (kind) out += `<li>${inline((bullet || ordered)[1])}</li>`;
    else if (line.startsWith("### ")) out += `<h4>${inline(line.slice(4))}</h4>`;
    else if (line.startsWith("## ")) out += `<h4>${inline(line.slice(3))}</h4>`;
    else if (line) out += `<p>${inline(line)}</p>`;
  }
  if (list) out += `</${list}>`;
  return out;
}

// Small persisted UI state (per browser); everything scientific lives in the backend.
const KEY = "astra-state-v1";
export const state = {
  read() {
    try {
      return JSON.parse(localStorage.getItem(KEY) || "{}");
    } catch {
      return {};
    }
  },
  write(patch) {
    const next = { ...this.read(), ...patch };
    try {
      localStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      /* storage unavailable: state is per page load only */
    }
    return next;
  },
};

export function toast(message, kind = "info") {
  const t = document.createElement("div");
  t.className = `toast ${kind}`;
  t.textContent = message;
  document.body.appendChild(t);
  setTimeout(() => t.classList.add("show"), 10);
  setTimeout(() => {
    t.classList.remove("show");
    setTimeout(() => t.remove(), 300);
  }, 4000);
}
