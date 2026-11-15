// Step 1: choose body, target region, mission profile and weights; start discovery.

import { api } from "../api.js";
import { DIM_COLORS, esc, errorState, loading, state, toast } from "../ui.js";

export async function renderMission(view) {
  view.innerHTML = loading("Loading targets and mission profiles…");
  let targets, missions, ref;
  try {
    [targets, missions, ref] = await Promise.all([api.targets(), api.missions(), api.reference()]);
  } catch (err) {
    view.innerHTML = errorState(err, "Retry");
    view.querySelector("[data-retry]").onclick = () => renderMission(view);
    return;
  }

  const saved = state.read();
  const sel = {
    body: saved.body || "moon",
    target: saved.targetId || null,
    profile: "general_analog",
    weights: { ...ref.profiles.general_analog.weights },
  };

  view.innerHTML = `
    <section class="page-head">
      <h1>Configure an analog discovery mission</h1>
      <p class="lead">Choose a Moon or Mars target region and the scientific priorities. ASTRA
      then scores every Earth candidate deterministically against measured and curated
      properties of the target.</p>
    </section>

    <section class="panel">
      <h2><span class="step">1</span> Planetary body</h2>
      <div class="segmented" role="radiogroup" aria-label="Planetary body">
        <button role="radio" data-body="moon">Moon</button>
        <button role="radio" data-body="mars">Mars</button>
      </div>
    </section>

    <section class="panel">
      <h2><span class="step">2</span> Target region</h2>
      <div class="cards" id="target-cards"></div>
    </section>

    <section class="panel" id="config-panel">
      <h2><span class="step">3</span> Mission objectives and scientific priorities</h2>
      <div class="grid-2">
        <div>
          <h3>Preset missions for this target</h3>
          <div id="presets" class="preset-list"></div>
        </div>
        <form id="custom-form" class="form">
          <h3>Or configure a custom mission</h3>
          <label>Mission name
            <input name="name" required minlength="3" maxlength="200" placeholder="e.g. Rover dust-mitigation trial" />
          </label>
          <label>Mission profile
            <select name="profile">${Object.entries(ref.profiles)
              .map(([k, p]) => `<option value="${esc(k)}">${esc(p.label)}</option>`)
              .join("")}</select>
          </label>
          <p class="hint" id="profile-desc"></p>
          <fieldset class="weights">
            <legend>Dimension weights (normalised to 100%)</legend>
            <div id="weight-sliders"></div>
          </fieldset>
          <label>Objectives
            <textarea name="objectives" rows="3" maxlength="2000" placeholder="What should the analog support?"></textarea>
          </label>
          <button class="btn primary" type="submit">Save mission and run discovery</button>
        </form>
      </div>
    </section>`;

  const targetCards = view.querySelector("#target-cards");
  const presets = view.querySelector("#presets");
  const form = view.querySelector("#custom-form");
  const sliders = view.querySelector("#weight-sliders");

  function renderBody() {
    view.querySelectorAll("[data-body]").forEach((b) => {
      b.classList.toggle("active", b.dataset.body === sel.body);
      b.setAttribute("aria-checked", b.dataset.body === sel.body);
    });
    const list = targets.filter((t) => t.body === sel.body);
    if (!list.some((t) => t.id === sel.target)) {
      const withPreset = list.find((t) => missions.some((m) => m.target_site_id === t.id));
      sel.target = (withPreset || list[0])?.id || null;
    }
    targetCards.innerHTML = list
      .map(
        (t) => `<button class="card target-card ${t.id === sel.target ? "selected" : ""}" data-target="${esc(t.id)}" aria-pressed="${t.id === sel.target}">
          <span class="card-kicker">${esc(t.body.toUpperCase())} · ${esc(t.region)}</span>
          <strong>${esc(t.name)}</strong>
          <span class="card-body">${esc(t.description)}</span>
          <span class="tags">${(t.geology_tags || []).slice(0, 5).map((g) => `<span class="tag">${esc(g)}</span>`).join("")}</span>
          <span class="card-foot">${t.latitude.toFixed(2)}°, ${t.longitude.toFixed(2)}° · <a href="#/location/${esc(t.id)}">target data →</a></span>
        </button>`
      )
      .join("");
    renderPresets();
  }

  function renderPresets() {
    const list = missions.filter((m) => m.target_site_id === sel.target);
    presets.innerHTML = list.length
      ? list
          .map(
            (m) => `<div class="preset">
              <div><strong>${esc(m.name)}</strong>
              <span class="muted">${esc(m.profile_label)}${m.is_preset ? "" : " · custom"}</span>
              <p>${esc(m.objectives)}</p>
              <div class="weight-chips">${Object.entries(m.weights)
                .map(([d, w]) => `<span style="--c:${DIM_COLORS[d]}">${esc(d)} ${(w * 100).toFixed(0)}%</span>`)
                .join("")}</div></div>
              <button class="btn primary" data-run="${m.id}">Run discovery</button>
            </div>`
          )
          .join("")
      : `<p class="muted">No missions yet for this target. Configure one on the right.</p>`;
  }

  function renderSliders() {
    const total = Object.values(sel.weights).reduce((a, b) => a + b, 0) || 1;
    sliders.innerHTML = Object.entries(ref.dimensions)
      .map(
        ([d, label]) => `<label class="slider" style="--c:${DIM_COLORS[d]}">
          <span>${esc(label)}</span>
          <input type="range" min="0" max="100" step="5" value="${Math.round(sel.weights[d] * 100)}" data-dim="${d}" aria-label="${esc(label)} weight" />
          <output>${((sel.weights[d] / total) * 100).toFixed(0)}%</output>
        </label>`
      )
      .join("");
    view.querySelector("#profile-desc").textContent = ref.profiles[sel.profile]?.description || "Custom weights.";
  }

  async function startRun(missionId, button) {
    button.disabled = true;
    const original = button.textContent;
    button.textContent = "Scoring candidates…";
    try {
      const run = await api.runDiscovery({ mission_id: missionId });
      state.write({ runId: run.id, missionId, targetId: run.target.id, body: run.target.body, candidateId: run.results[0]?.site_id });
      location.hash = `#/discovery/${run.id}`;
    } catch (err) {
      toast(err.message, "error");
      button.disabled = false;
      button.textContent = original;
    }
  }

  view.querySelectorAll("[data-body]").forEach((b) =>
    b.addEventListener("click", () => {
      sel.body = b.dataset.body;
      state.write({ body: sel.body });
      renderBody();
    })
  );
  targetCards.addEventListener("click", (e) => {
    if (e.target.closest("a")) return;
    const card = e.target.closest("[data-target]");
    if (!card) return;
    sel.target = card.dataset.target;
    state.write({ targetId: sel.target });
    renderBody();
  });
  presets.addEventListener("click", (e) => {
    const b = e.target.closest("[data-run]");
    if (b) startRun(Number(b.dataset.run), b);
  });
  form.profile.addEventListener("change", () => {
    sel.profile = form.profile.value;
    sel.weights = { ...ref.profiles[sel.profile].weights };
    renderSliders();
  });
  sliders.addEventListener("input", (e) => {
    const d = e.target.dataset.dim;
    if (!d) return;
    sel.weights[d] = Number(e.target.value) / 100;
    const total = Object.values(sel.weights).reduce((a, b) => a + b, 0);
    sliders.querySelectorAll("output").forEach((o, i) => {
      const dim = Object.keys(ref.dimensions)[i];
      o.textContent = total ? `${((sel.weights[dim] / total) * 100).toFixed(0)}%` : "0%";
    });
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const total = Object.values(sel.weights).reduce((a, b) => a + b, 0);
    if (!total) return toast("At least one weight must be above zero.", "error");
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    const base = ref.profiles[sel.profile].weights;
    const changed = Object.keys(base).some((d) => Math.abs(base[d] - sel.weights[d]) > 1e-9);
    try {
      const mission = await api.createMission({
        name: form.name.value.trim(),
        target_site_id: sel.target,
        profile_key: changed ? "custom" : sel.profile,
        weights: changed ? sel.weights : null,
        objectives: form.objectives.value.trim(),
      });
      missions.push(mission);
      await startRun(mission.id, button);
    } catch (err) {
      toast(err.message, "error");
      button.disabled = false;
    }
  });

  renderBody();
  renderSliders();
}
