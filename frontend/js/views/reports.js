// Step 5: generate, view and download scientific PDF reports.

import { api } from "../api.js";
import { emptyState, errorState, esc, loading, num, state, toast } from "../ui.js";

export async function renderReports(view, _params, query) {
  view.innerHTML = loading("Loading reports…");
  const s = state.read();
  let reports, run;
  try {
    reports = await api.reports();
    // Fall back to the most recent run when this browser has no selection yet.
    const runId = s.runId || (await api.runs())[0]?.id;
    run = runId ? await api.results(runId).catch(() => null) : null;
  } catch (err) {
    view.innerHTML = errorState(err, "Retry");
    view.querySelector("[data-retry]").onclick = () => renderReports(view, _params, query);
    return;
  }
  const openId = query.get("open") || reports[0]?.id;

  view.innerHTML = `
    <section class="page-head">
      <h1>Scientific reports</h1>
      <p class="lead">PDF reports are built only from stored results, measurements and dataset
      provenance. They include methods, uncertainty, missing data and limitations.</p>
    </section>
    <div class="reports-layout">
      <section class="panel">
        <h2>Generate</h2>
        ${run ? `<form id="gen" class="form">
            <p>Discovery run <strong>#${run.id}</strong> · ${esc(run.mission_name)} → ${esc(run.target.name)}</p>
            <label>Focus location
              <select name="site">${run.results.map((r) => `<option value="${esc(r.site_id)}" ${r.site_id === s.candidateId ? "selected" : ""}>#${r.rank} ${esc(r.name)} (${num(r.score)})</option>`).join("")}</select>
            </label>
            <button class="btn primary" type="submit">Generate PDF</button>
          </form>`
          : emptyState("No discovery run selected", "Run a discovery first; reports summarise a run.", `<a class="btn primary" href="#/mission">Configure mission</a>`)}
        <h2>Generated reports</h2>
        ${reports.length ? `<ul class="report-list">${reports
          .map((r) => `<li class="${r.id === openId ? "active" : ""}"><a href="#/reports?open=${r.id}">${esc(r.title)}</a>
              <span class="muted small">${esc(r.created_at.slice(0, 16).replace("T", " "))} UTC · ${(r.size_bytes / 1024).toFixed(0)} KB · run #${r.run_id}</span>
              <a class="small" href="${r.download_url}?download=true">Download</a></li>`)
          .join("")}</ul>` : `<p class="muted">No reports yet.</p>`}
      </section>
      <section class="panel viewer">
        ${openId ? `<div class="viewer-head"><h2>Preview</h2><a class="btn" href="/api/reports/${esc(openId)}/pdf?download=true">Download PDF</a></div>
          <iframe title="Report preview" src="/api/reports/${esc(openId)}/pdf"></iframe>`
          : emptyState("Nothing to preview", "Generate a report to preview it here.")}
      </section>
    </div>`;

  const gen = view.querySelector("#gen");
  if (gen) {
    gen.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = gen.querySelector("button");
      btn.disabled = true;
      btn.textContent = "Generating…";
      try {
        const rep = await api.generateReport({ run_id: run.id, site_id: gen.site.value });
        toast("Report generated.", "ok");
        location.hash = `#/reports?open=${rep.id}`;
      } catch (err) {
        toast(err.message, "error");
        btn.disabled = false;
        btn.textContent = "Generate PDF";
      }
    });
  }
}
