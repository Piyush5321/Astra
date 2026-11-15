// Step 3: location detail - scientific evidence, comparison charts and provenance.

import { api } from "../api.js";
import {
  DIM_COLORS,
  confidenceBadge,
  emptyState,
  errorState,
  esc,
  fmtValue,
  loading,
  num,
  scoreColor,
  sourceBadge,
  state,
  toast,
} from "../ui.js";

const charts = [];

export async function renderLocation(view, params, query) {
  const s = state.read();
  const siteId = params[0] || s.candidateId;
  if (!siteId) {
    view.innerHTML = emptyState(
      "No location selected",
      "Open a candidate from the discovery ranking or the map.",
      `<a class="btn primary" href="#/discovery">Go to discovery</a>`
    );
    return;
  }
  view.innerHTML = loading("Loading scientific evidence…");
  const runId = Number(query.get("run")) || s.runId;
  let site, run;
  try {
    site = await api.location(siteId);
    run = runId ? await api.results(runId).catch(() => null) : null;
  } catch (err) {
    view.innerHTML = errorState(err, "Back to discovery");
    view.querySelector("[data-retry]").onclick = () => (location.hash = "#/discovery");
    return;
  }
  const result = site.role === "candidate" && run ? run.results.find((r) => r.site_id === site.id) : null;
  if (site.role === "candidate") state.write({ candidateId: site.id });

  view.innerHTML = `
    <section class="page-head row">
      <div>
        <span class="kicker">${esc(site.body.toUpperCase())} · ${site.role === "target" ? "target region" : "Earth candidate"} · ${esc(site.region)}</span>
        <h1>${esc(site.name)}</h1>
        <p class="lead">${esc(site.description)}</p>
        <p class="muted">${esc(site.scientific_context)}</p>
        <p class="muted small">${site.latitude.toFixed(4)}°, ${site.longitude.toFixed(4)}° — ${esc(site.coordinate_source)}</p>
      </div>
      <div class="actions">
        ${result ? `<a class="btn" href="#/discovery/${run.id}">← Ranking</a>
          <a class="btn" href="#/agent?ask=${encodeURIComponent(`Why is ${site.name} similar to ${run.target.name}?`)}">Ask the agent</a>
          <button class="btn primary" id="report-btn">Generate PDF report</button>` : ""}
      </div>
    </section>
    ${site.site_notes?.length ? `<div class="notice">${site.site_notes.map((n) => `<p>⚠ ${esc(n)}</p>`).join("")}</div>` : ""}
    ${result ? comparisonHtml(result, run) : site.role === "candidate" ? `<div class="notice">Run a discovery to compare this location with a target region. <a href="#/mission">Configure mission →</a></div>` : ""}
    <section class="panel">
      <h2>Terrain on the common 500 m analysis grid</h2>
      <p class="hint">Hillshade with elevation tint, 30 km × 30 km windows, computed from the stored DEM subsets. Absolute elevations are relative to different datums and are not compared.</p>
      <div class="terrain-pair" id="terrain-pair">
        <figure id="terrain-site">${loading("Rendering terrain…")}</figure>
        ${result ? `<figure id="terrain-target">${loading("Rendering terrain…")}</figure>` : ""}
      </div>
    </section>
    <section class="panel">
      <h2>Measurements and provenance</h2>
      ${measurementTable(site.measurements)}
    </section>
    <section class="panel">
      <h2>Datasets</h2>
      ${datasetList(site.datasets)}
      ${site.references?.length ? `<h3>References</h3><ul class="refs">${site.references
        .map((r) => `<li>${esc(r.citation)}${r.url ? ` <a href="${esc(r.url)}" target="_blank" rel="noopener">link</a>` : ""}</li>`)
        .join("")}</ul>` : `<p class="muted">No literature references curated for this site.</p>`}
    </section>`;

  drawTerrain(view.querySelector("#terrain-site"), site.id, site.name);
  if (result) {
    drawTerrain(view.querySelector("#terrain-target"), run.target.id, run.target.name);
    drawCharts(result);
    view.querySelector("#report-btn").addEventListener("click", async (e) => {
      e.target.disabled = true;
      e.target.textContent = "Generating…";
      try {
        const rep = await api.generateReport({ run_id: run.id, site_id: site.id });
        toast("Report generated.", "ok");
        location.hash = `#/reports?open=${rep.id}`;
      } catch (err) {
        toast(err.message, "error");
        e.target.disabled = false;
        e.target.textContent = "Generate PDF report";
      }
    });
  }
  return () => charts.splice(0).forEach((c) => c.destroy());
}

function comparisonHtml(r, run) {
  const ex = r.explanation;
  const section = (title, items, cls) =>
    items.length ? `<div class="evidence ${cls}"><h3>${title}</h3><ul>${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul></div>` : "";
  return `
    <section class="panel compare-head">
      <div class="big-score" style="--c:${scoreColor(r.score)}">
        <span class="value">${num(r.score)}</span><span class="label">similarity / 100</span>
      </div>
      <div class="compare-meta">
        <p>Compared with <a href="#/location/${esc(run.target.id)}">${esc(run.target.name)}</a> · rank ${r.rank} of ${run.results.length} · ${esc(run.mission_name)}</p>
        <dl class="stats">
          <div><dt>Measurement range</dt><dd>${num(r.score_low)} – ${num(r.score_high)}</dd></div>
          <div><dt>Bounds incl. missing data</dt><dd>${num(r.bound_low)} – ${num(r.bound_high)}</dd></div>
          <div><dt>Data coverage</dt><dd>${(r.coverage * 100).toFixed(0)}%</dd></div>
          <div><dt>Confidence</dt><dd>${confidenceBadge(r.confidence)}</dd></div>
        </dl>
        <p class="hint">${esc(ex.summary)}</p>
      </div>
    </section>
    <div class="grid-2">
      <section class="panel"><h2>Dimension scores</h2><div class="chart-box"><canvas id="radar"></canvas></div>
        <p class="hint">Dimensions without data for both sites are shown at 0 and labelled "no data". They are excluded from the score, not counted as matches.</p></section>
      <section class="panel"><h2>Feature similarity</h2><div class="chart-box tall"><canvas id="features"></canvas></div>
        <p class="hint">Bars show the similarity of each feature (0–1). Lighter bars show the range allowed by the stated uncertainties.</p></section>
    </div>
    <section class="panel">
      <h2>Earth vs ${esc(run.target.body === "moon" ? "Moon" : "Mars")}: feature comparison</h2>
      ${featureTable(r.features)}
    </section>
    <section class="panel evidence-grid">
      ${section("Strengths", ex.strengths, "good")}
      ${section("Partial matches", ex.partial, "mid")}
      ${section("Mismatches", ex.mismatches, "bad")}
      ${section("Missing data (not counted as a match)", ex.missing, "missing")}
    </section>
    <section class="panel warning-panel"><h2>Fundamental limitations</h2>
      <ul>${run.limitations.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>
      <table class="env"><thead><tr><th></th><th>Gravity (m/s²)</th><th>Atmosphere</th><th>Day length</th></tr></thead>
      <tbody>${Object.entries(run.environment).map(([b, e]) => `<tr><th>${esc(b)}</th><td>${e.gravity_m_s2}</td><td>${esc(e.atmosphere)}</td><td>${esc(e.day_length)}</td></tr>`).join("")}</tbody></table>
    </section>`;
}

function featureTable(features) {
  const rows = features
    .filter((f) => f.weight > 0)
    .map((f) => {
      const cand = f.kind === "categorical" ? tagList(f.candidate_tags, f.target_tags) : fmtValue(f.candidate_value, f.unit, f.key);
      const targ = f.kind === "categorical" ? tagList(f.target_tags, f.candidate_tags) : fmtValue(f.target_value, f.unit, f.key);
      const sim = f.similarity === null
        ? `<span class="badge missing">not scored</span>`
        : `<div class="simbar"><i style="width:${f.similarity * 100}%"></i></div><span>${f.similarity.toFixed(2)}${f.similarity_low !== f.similarity_high ? ` <small>(${f.similarity_low.toFixed(2)}–${f.similarity_high.toFixed(2)})</small>` : ""}</span>`;
      return `<tr class="${f.status !== "scored" ? "row-missing" : ""}">
        <td><span class="dimdot" style="--c:${DIM_COLORS[f.dimension]}"></span>${esc(f.label)}</td>
        <td>${cand}</td><td>${targ}</td><td class="sim">${sim}</td>
        <td class="small">${f.status !== "scored" ? esc(f.missing_reason) : `weight ${(f.weight * 100).toFixed(1)}%${f.scale ? ` · scale ${f.scale}${f.transform !== "identity" ? ` (${f.transform})` : ""}` : " · Jaccard"}`}</td>
      </tr>`;
    })
    .join("");
  return `<div class="table-wrap"><table class="data"><thead><tr><th>Feature</th><th>Earth candidate</th><th>Target</th><th>Similarity</th><th>Weight / note</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function tagList(tags, other) {
  if (tags === null || tags === undefined) return `<span class="badge missing">missing</span>`;
  if (!tags.length) return `<span class="muted">none</span>`;
  const o = new Set(other || []);
  return tags.map((t) => `<span class="tag ${o.has(t) ? "shared" : ""}">${esc(t)}</span>`).join("");
}

function measurementTable(ms) {
  const rows = ms
    .map((m) => {
      const value = m.quality_flag === "missing"
        ? `<span class="badge missing">missing</span>`
        : m.tags ? m.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join("") || "none" : fmtValue(m.value, m.unit, m.feature_key);
      const unc = m.uncertainty ? ` ± ${num(m.uncertainty, m.unit === "fraction" ? 3 : 1)}` : "";
      const note = m.quality_flag === "missing" ? m.missing_reason : [m.method, m.citation, m.uncertainty_note].filter(Boolean).join(" · ");
      return `<tr class="${m.quality_flag === "missing" ? "row-missing" : ""}">
        <td>${esc(m.label)}${m.scored ? "" : ' <small class="muted">(descriptive)</small>'}</td>
        <td>${value}${esc(unc)}</td><td>${sourceBadge(m.source_type)}</td>
        <td class="small">${m.dataset_id ? `<code>${esc(m.dataset_id)}</code> ` : ""}${m.observed_period ? `${esc(m.observed_period)} · ` : ""}${esc(note)}</td></tr>`;
    })
    .join("");
  return `<div class="table-wrap"><table class="data"><thead><tr><th>Feature</th><th>Value</th><th>Source type</th><th>Provenance / method</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function datasetList(ds) {
  if (!ds.length) return `<p class="muted">No datasets stored for this site.</p>`;
  return `<div class="datasets">${ds
    .map(
      (d) => `<article class="dataset">
        <header><strong>${esc(d.product_id)}</strong> ${d.is_sample ? '<span class="badge missing">SAMPLE DATA</span>' : '<span class="badge src-measured_dataset">real data</span>'}</header>
        <p>${esc(d.provider)} · retrieved ${esc(d.retrieved_at.slice(0, 10))}${d.native_resolution_m ? ` · native ${d.native_resolution_m} m` : ""}</p>
        <p class="small mono">sha256 ${esc(d.sha256.slice(0, 16))}… · ${esc(d.file_path)}</p>
        <p class="small break">${d.source_url.split("; ").map((u) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(u.length > 90 ? u.slice(0, 90) + "…" : u)}</a>`).join("<br>")}</p>
        ${d.notes.map((n) => `<p class="small">⚠ ${esc(n)}</p>`).join("")}
        <p class="small muted">${esc(d.attribution)}</p>
      </article>`
    )
    .join("")}</div>`;
}

async function drawTerrain(fig, siteId, name) {
  try {
    const t = await api.terrain(siteId);
    const n = t.info.size;
    const canvas = document.createElement("canvas");
    canvas.width = n;
    canvas.height = n;
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", `Hillshade of ${name}`);
    const ctx = canvas.getContext("2d");
    const img = ctx.createImageData(n, n);
    const flat = t.elevation.flat().filter((v) => v !== null);
    const lo = Math.min(...flat);
    const hi = Math.max(...flat);
    for (let r = 0; r < n; r++) {
      for (let c = 0; c < n; c++) {
        const i = (r * n + c) * 4;
        const z = t.elevation[r][c];
        const h = t.hillshade[r][c];
        if (z === null) {
          img.data.set([255, 0, 255, 255], i);
          continue;
        }
        const f = hi > lo ? (z - lo) / (hi - lo) : 0.5;
        const tint = [40 + 180 * f, 70 + 120 * f, 120 + 60 * (1 - f)];
        const s = 0.35 + 0.65 * h;
        img.data.set([tint[0] * s, tint[1] * s, tint[2] * s, 255], i);
      }
    }
    ctx.putImageData(img, 0, 0);
    fig.innerHTML = "";
    fig.appendChild(canvas);
    const cap = document.createElement("figcaption");
    cap.innerHTML = `<strong>${esc(name)}</strong><br>${esc(t.product)} · ${esc(t.info.method)} from ${t.info.native_spacing_m} m native · elevation ${Math.round(lo)} to ${Math.round(hi)} m (${esc(t.vertical_reference)})`;
    fig.appendChild(cap);
  } catch (err) {
    fig.innerHTML = `<div class="state error small">${esc(err.message)}</div>`;
  }
}

function drawCharts(r) {
  Chart.defaults.color = "#a9b5cc";
  Chart.defaults.borderColor = "rgba(148,163,184,0.18)";
  const dims = r.dimensions.filter((d) => d.weight > 0);
  charts.push(
    new Chart(document.getElementById("radar"), {
      type: "radar",
      data: {
        labels: dims.map((d) => `${d.label}${d.score === null ? " (no data)" : ""}`),
        datasets: [{
          label: "Dimension score",
          data: dims.map((d) => d.score ?? 0),
          backgroundColor: "rgba(56,189,248,0.2)",
          borderColor: "#38bdf8",
          pointBackgroundColor: dims.map((d) => DIM_COLORS[d.dimension]),
        }],
      },
      options: {
        maintainAspectRatio: false,
        scales: { r: { min: 0, max: 100, ticks: { stepSize: 25, backdropColor: "transparent" } } },
        plugins: { legend: { display: false } },
      },
    })
  );
  const feats = r.features.filter((f) => f.weight > 0);
  charts.push(
    new Chart(document.getElementById("features"), {
      type: "bar",
      data: {
        labels: feats.map((f) => f.label),
        datasets: [
          {
            label: "Similarity",
            data: feats.map((f) => f.similarity),
            backgroundColor: feats.map((f) => DIM_COLORS[f.dimension]),
            grouped: false,
            order: 1,
          },
          {
            label: "Uncertainty range",
            data: feats.map((f) => (f.similarity === null ? null : [f.similarity_low, f.similarity_high])),
            backgroundColor: "rgba(226,232,240,0.25)",
            grouped: false,
            order: 2,
          },
        ],
      },
      options: {
        indexAxis: "y",
        maintainAspectRatio: false,
        scales: { x: { min: 0, max: 1 } },
        plugins: {
          tooltip: {
            callbacks: {
              afterLabel: (ctx) => (feats[ctx.dataIndex].similarity === null ? `Not scored: ${feats[ctx.dataIndex].missing_reason}` : ""),
            },
          },
        },
      },
    })
  );
}
