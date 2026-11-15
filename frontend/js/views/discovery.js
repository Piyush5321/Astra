// Step 2: map of candidate locations and the ranked, transparent results of a run.

import { api } from "../api.js";
import {
  DIM_COLORS,
  confidenceBadge,
  emptyState,
  errorState,
  esc,
  loading,
  num,
  scoreBar,
  scoreColor,
  state,
} from "../ui.js";

export async function renderDiscovery(view, params) {
  let runId = Number(params[0]) || state.read().runId;
  if (!runId) runId = (await api.runs().catch(() => []))[0]?.id;
  if (!runId) {
    view.innerHTML = emptyState(
      "No discovery run yet",
      "Configure a mission and start a discovery to see ranked Earth candidates.",
      `<a class="btn primary" href="#/mission">Configure mission</a>`
    );
    return;
  }
  view.innerHTML = loading("Loading discovery results…");
  let run, runs;
  try {
    [run, runs] = await Promise.all([api.results(runId), api.runs()]);
  } catch (err) {
    view.innerHTML = errorState(err, "Back to mission setup");
    view.querySelector("[data-retry]").onclick = () => (location.hash = "#/mission");
    return;
  }
  state.write({ runId: run.id, targetId: run.target.id, missionId: run.mission_id });

  const weights = Object.entries(run.weights)
    .map(([d, w]) => `<span style="--c:${DIM_COLORS[d]}">${esc(d)} ${(w * 100).toFixed(0)}%</span>`)
    .join("");
  view.innerHTML = `
    <section class="page-head row">
      <div>
        <span class="kicker">${esc(run.target.body.toUpperCase())} target · run #${run.id} · engine v${esc(run.engine_version)}</span>
        <h1>${esc(run.mission_name)}</h1>
        <p class="lead">Earth candidates ranked by similarity to <a href="#/location/${esc(run.target.id)}">${esc(run.target.name)}</a>.
        Bars show the score; the shaded band shows bounds including missing data.</p>
        <div class="weight-chips">${weights}</div>
      </div>
      <div class="actions">
        <label class="inline">Run history
          <select id="run-select">${runs
            .map((r) => `<option value="${r.id}" ${r.id === run.id ? "selected" : ""}>#${r.id} · ${esc(r.mission_name)}</option>`)
            .join("")}</select>
        </label>
        <a class="btn" href="#/agent">Ask the agent</a>
        <a class="btn primary" href="#/reports">PDF report</a>
      </div>
    </section>

    <div class="discovery-grid">
      <section class="panel map-panel">
        <h2>Candidate map</h2>
        <div id="map" class="map" role="region" aria-label="Map of Earth candidate locations"></div>
        <p class="hint">Marker colour = score. Click a marker for details.</p>
      </section>
      <section class="panel">
        <h2>Ranked candidates</h2>
        <ol class="ranking" id="ranking">${run.results.map(renderRow).join("")}</ol>
      </section>
    </div>

    <section class="panel warning-panel">
      <h2>What these scores cannot capture</h2>
      <ul>${run.limitations.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>
    </section>`;

  view.querySelector("#run-select").addEventListener("change", (e) => {
    location.hash = `#/discovery/${e.target.value}`;
  });

  // Map
  const map = L.map("map", { worldCopyJump: true, scrollWheelZoom: false }).setView([15, 30], 2);
  const relief = L.tileLayer(
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg",
    { attribution: "Blue Marble shaded relief: NASA EOSDIS GIBS", maxNativeZoom: 8, maxZoom: 12 }
  ).addTo(map);
  const osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 12,
  });
  L.control.layers({ "NASA Blue Marble relief": relief, OpenStreetMap: osm }).addTo(map);
  const bounds = [];
  for (const r of run.results) {
    const marker = L.circleMarker([r.latitude, r.longitude], {
      radius: 8 + (r.score || 0) / 8,
      color: "#0b1020",
      weight: 1.5,
      fillColor: scoreColor(r.score),
      fillOpacity: 0.9,
    }).addTo(map);
    marker.bindTooltip(`#${r.rank} ${esc(r.name)} · ${num(r.score)}`);
    marker.bindPopup(`<strong>#${r.rank} ${esc(r.name)}</strong><br>${esc(r.region)}<br>
      Score <b>${num(r.score)}</b> (bounds ${num(r.bound_low)}–${num(r.bound_high)})<br>
      Coverage ${(r.coverage * 100).toFixed(0)}% · ${esc(r.confidence)} confidence<br>
      <a href="#/location/${esc(r.site_id)}?run=${run.id}">Open evidence →</a>`);
    bounds.push([r.latitude, r.longitude]);
  }
  if (bounds.length) map.fitBounds(bounds, { padding: [30, 30] });
  setTimeout(() => map.invalidateSize(), 50);

  return () => map.remove();

  function renderRow(r) {
    const dims = r.dimensions
      .filter((d) => d.weight > 0)
      .map(
        (d) => `<span class="dim" title="${esc(d.label)}: ${d.score === null ? "no data" : num(d.score)} (weight ${(d.weight * 100).toFixed(0)}%, coverage ${(d.coverage * 100).toFixed(0)}%)">
          <i style="--c:${DIM_COLORS[d.dimension]};--v:${d.score ?? 0}%" class="${d.score === null ? "nodata" : ""}"></i>${esc(d.dimension.slice(0, 4))}</span>`
      )
      .join("");
    return `<li class="rank-row">
      <a href="#/location/${esc(r.site_id)}?run=${run.id}">
        <span class="rank">${r.rank}</span>
        <span class="rank-main">
          <span class="rank-title"><strong>${esc(r.name)}</strong><span class="muted">${esc(r.region)}</span></span>
          ${scoreBar(r)}
          <span class="rank-meta">
            <span class="score" style="color:${scoreColor(r.score)}">${num(r.score)}</span>
            <span>range ${num(r.score_low)}–${num(r.score_high)}</span>
            <span>bounds ${num(r.bound_low)}–${num(r.bound_high)}</span>
            <span>coverage ${(r.coverage * 100).toFixed(0)}%</span>
            ${confidenceBadge(r.confidence)}
          </span>
          <span class="dims">${dims}</span>
        </span>
      </a></li>`;
  }
}
