// Data sources, provenance, scoring methods and a live NASA POWER query.

import { api } from "../api.js";
import { DIM_COLORS, errorState, esc, fmtValue, loading, toast } from "../ui.js";

export async function renderData(view) {
  view.innerHTML = loading("Loading datasets and methods…");
  let datasets, ref;
  try {
    [datasets, ref] = await Promise.all([api.datasets(), api.reference()]);
  } catch (err) {
    view.innerHTML = errorState(err, "Retry");
    view.querySelector("[data-retry]").onclick = () => renderData(view);
    return;
  }
  const byKind = (k) => datasets.filter((d) => d.kind === k);

  view.innerHTML = `
    <section class="page-head">
      <h1>Data sources and methods</h1>
      <p class="lead">Every score traces back to these datasets and formulas. No synthetic or
      sample data are stored in the database.</p>
    </section>
    <section class="panel">
      <h2>Scoring formula</h2>
      <p class="formula">score = 100 × Σ<sub>valid</sub> w<sub>f</sub>·s<sub>f</sub> / Σ<sub>valid</sub> w<sub>f</sub>,
      &nbsp; s<sub>f</sub> = exp(−½ (Δ<sub>f</sub>/σ<sub>f</sub>)²) for continuous features, Jaccard index for curated tags.</p>
      <p class="hint">A feature is valid only when both sites have a value. Missing features are reported through
      coverage and through bounds that treat them as 0 (lower) or 1 (upper). Full methods: <code>docs/SCIENCE.md</code>.</p>
      <div class="table-wrap"><table class="data">
        <thead><tr><th>Feature</th><th>Dimension</th><th>Unit</th><th>Transform</th><th>Scale σ</th><th>Sub-weight</th><th>Rationale</th></tr></thead>
        <tbody>${ref.features.map((f) => `<tr><td>${esc(f.label)}</td>
          <td><span class="dimdot" style="--c:${DIM_COLORS[f.dimension]}"></span>${esc(f.dimension)}</td>
          <td>${esc(f.unit)}</td><td>${f.kind === "categorical" ? "Jaccard" : esc(f.transform)}</td>
          <td>${f.kind === "categorical" ? "–" : f.scale}</td><td>${f.subweight}</td>
          <td class="small">${esc(f.description)} ${esc(f.rationale)}</td></tr>`).join("")}</tbody>
      </table></div>
      <h3>Mission profiles</h3>
      <div class="table-wrap"><table class="data"><thead><tr><th>Profile</th>${Object.values(ref.dimensions).map((d) => `<th>${esc(d)}</th>`).join("")}</tr></thead>
      <tbody>${Object.entries(ref.profiles).map(([, p]) => `<tr><td>${esc(p.label)}</td>${Object.keys(ref.dimensions).map((d) => `<td>${(p.weights[d] * 100).toFixed(0)}%</td>`).join("")}</tr>`).join("")}</tbody></table></div>
    </section>

    <section class="panel">
      <h2>Elevation datasets (${byKind("elevation").length})</h2>
      ${datasetTable(byKind("elevation"))}
      <h2>Climate datasets (${byKind("climate").length})</h2>
      ${datasetTable(byKind("climate"))}
    </section>

    <section class="panel">
      <h2>Live NASA POWER query</h2>
      <p class="hint">Fetch daily POWER data for any Earth point (validated, with a timeout, and cached in SQLite).
      Results are reanalysis-based grid-cell estimates (~0.5° × 0.625°).</p>
      <form id="power" class="form inline-form">
        <label>Latitude <input name="lat" type="number" step="0.01" min="-90" max="90" value="34.15" required /></label>
        <label>Longitude <input name="lon" type="number" step="0.01" min="-180" max="180" value="77.58" required /></label>
        <label>Year <input name="year" type="number" min="1981" max="2024" value="2023" required /></label>
        <button class="btn primary" type="submit">Fetch</button>
      </form>
      <div id="power-out"></div>
    </section>

    <section class="panel">
      <h2>Curated vocabularies</h2>
      <p class="hint">${esc(ref.vocabulary_note)}</p>
      <div class="grid-3">${Object.entries(ref.vocabularies).map(([k, v]) => `<div><h3>${esc(k)}</h3><dl class="vocab">${Object.entries(v)
        .map(([t, d]) => `<dt>${esc(t)}</dt><dd>${esc(d)}</dd>`).join("")}</dl></div>`).join("")}</div>
    </section>`;

  const form = view.querySelector("#power");
  const out = view.querySelector("#power-out");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const y = form.year.value;
    out.innerHTML = loading("Querying NASA POWER…");
    try {
      const r = await api.climate(form.lat.value, form.lon.value, `${y}0101`, `${y}1231`);
      const rows = Object.entries(r.summary)
        .map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v ? fmtValue(v.value, k.endsWith("_k") ? "K" : "mm/yr") : "insufficient data"}</td></tr>`)
        .join("");
      out.innerHTML = `<table class="data"><tbody>${rows}</tbody></table>
        <p class="small muted">Period ${esc(r.start)}–${esc(r.end)} · POWER API ${esc(r.api_version)} · sources ${esc(r.sources.join(", "))} · ${r.from_cache ? "served from cache" : "fetched live"} ${esc(r.fetched_at)}</p>`;
    } catch (err) {
      out.innerHTML = errorState(err);
      toast(err.message, "error");
    }
  });
}

function datasetTable(list) {
  return `<div class="table-wrap"><table class="data"><thead><tr><th>Site</th><th>Product</th><th>Provider</th><th>Native res.</th><th>Retrieved</th><th>SHA-256</th><th>Notes</th></tr></thead>
    <tbody>${list.map((d) => `<tr><td><a href="#/location/${esc(d.site_id)}">${esc(d.site_id)}</a></td><td>${esc(d.product_id)}</td>
      <td class="small">${esc(d.provider)}</td><td>${d.native_resolution_m ? `${d.native_resolution_m} m` : "~50 km grid"}</td>
      <td>${esc(d.retrieved_at.slice(0, 10))}</td><td class="mono small">${esc(d.sha256.slice(0, 12))}…</td>
      <td class="small">${d.notes.map(esc).join("<br>")}</td></tr>`).join("")}</tbody></table></div>`;
}
