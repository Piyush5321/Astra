// ASTRA frontend entry point: hash router and backend status indicator.

import { api } from "./api.js";
import { esc } from "./ui.js";
import { renderMission } from "./views/mission.js";
import { renderDiscovery } from "./views/discovery.js";
import { renderLocation } from "./views/location.js";
import { renderAgent } from "./views/agent.js";
import { renderReports } from "./views/reports.js";
import { renderData } from "./views/data.js";

const routes = {
  mission: renderMission,
  discovery: renderDiscovery,
  location: renderLocation,
  agent: renderAgent,
  reports: renderReports,
  data: renderData,
};

let cleanup = null;

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "") || "mission";
  const [path, query = ""] = raw.split("?");
  const [name, ...rest] = path.split("/");
  return { name, params: rest.map(decodeURIComponent), query: new URLSearchParams(query) };
}

async function route() {
  const { name, params, query } = parseHash();
  const view = document.getElementById("view");
  const render = routes[name];
  document.querySelectorAll("[data-nav]").forEach((a) => {
    a.classList.toggle("active", a.dataset.nav === name);
    a.toggleAttribute("aria-current", a.dataset.nav === name);
  });
  if (typeof cleanup === "function") cleanup();
  cleanup = null;
  if (!render) {
    view.innerHTML = `<div class="state empty"><strong>Page not found</strong>
      <p>No view called “${esc(name)}”.</p><a class="btn" href="#/mission">Go to mission setup</a></div>`;
    return;
  }
  window.scrollTo(0, 0);
  cleanup = (await render(view, params, query)) || null;
}

async function pollStatus() {
  const el = document.getElementById("status");
  try {
    const h = await api.health();
    el.className = `status ${h.status === "healthy" ? "ok" : "warn"}`;
    el.querySelector(".status-text").textContent =
      `${h.status === "healthy" ? "Backend online" : "Degraded"} · ${h.llm_enabled ? "LLM agent" : "deterministic agent"}`;
    el.title = `API v${h.version} · database ${h.database.status}`;
  } catch (err) {
    el.className = "status err";
    el.querySelector(".status-text").textContent = "Backend offline";
    el.title = err.message;
  }
}

window.addEventListener("hashchange", route);
route();
pollStatus();
setInterval(pollStatus, 30000);
