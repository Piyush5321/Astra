// Step 4: AI research agent chat with visible tool calls and sources.

import { api } from "../api.js";
import { esc, miniMarkdown, state } from "../ui.js";

const history = []; // kept for this page session only

export async function renderAgent(view, _params, query) {
  const s = state.read();
  const context = { run_id: s.runId || null, target_id: s.targetId || null, candidate_id: s.candidateId || null };
  let status = { llm_enabled: false, tools: [] };
  try {
    status = await api.agentStatus();
  } catch {
    /* status badge shows offline below */
  }

  view.innerHTML = `
    <section class="page-head row">
      <div>
        <h1>Research agent</h1>
        <p class="lead">Ask about the findings. The agent answers only from ASTRA's tools: stored
        datasets and deterministic scoring. It cannot invent measurements or change scores.</p>
      </div>
      <div class="agent-mode ${status.llm_enabled ? "llm" : "det"}">
        <strong>${status.llm_enabled ? `LLM mode · ${esc(status.model)}` : "Deterministic mode"}</strong>
        <span>${status.llm_enabled ? "Claude plans validated tool calls" : "No LLM configured; rule-based routing over the same tools"}</span>
      </div>
    </section>
    <div class="agent-layout">
      <section class="panel chat">
        <div class="context-chips" id="ctx">${chips(context)}</div>
        <div class="messages" id="messages" aria-live="polite"></div>
        <form id="chat-form" class="chat-form">
          <textarea name="message" rows="2" maxlength="4000" required placeholder="e.g. Why is the Atacama similar to Gale crater?"></textarea>
          <button class="btn primary" type="submit">Send</button>
        </form>
      </section>
      <aside class="panel">
        <h2>Try asking</h2>
        <div class="suggestions" id="suggestions">
          ${[
            "What are the top candidates?",
            "Why is Atacama Desert similar to Gale crater?",
            "Show terrain slope for the Lunar South Pole",
            "Climate at Wright Valley",
            "Which candidates have evaporite geology?",
            "Generate a PDF report",
          ].map((q) => `<button class="chip" data-q="${esc(q)}">${esc(q)}</button>`).join("")}
        </div>
        <h2>Tools available</h2>
        <ul class="tool-list">${status.tools.map((t) => `<li><code>${esc(t)}</code></li>`).join("")}</ul>
      </aside>
    </div>`;

  const messages = view.querySelector("#messages");
  const form = view.querySelector("#chat-form");
  const renderAll = () => {
    messages.innerHTML = history.length
      ? history.map(renderMessage).join("")
      : `<div class="state empty"><strong>No messages yet</strong><p>Ask a question or pick a suggestion.</p></div>`;
    messages.scrollTop = messages.scrollHeight;
  };

  async function send(text) {
    const turns = history.filter((h) => !h.pending && !h.error).map((h) => ({ role: h.role, content: h.content }));
    history.push({ role: "user", content: text });
    history.push({ role: "assistant", content: "", pending: true });
    renderAll();
    form.querySelector("button").disabled = true;
    try {
      const ctx = Object.fromEntries(Object.entries(context).filter(([, v]) => v !== null));
      const reply = await api.chat({ message: text, history: turns.slice(-20), context: ctx });
      history[history.length - 1] = { role: "assistant", content: reply.answer, reply };
    } catch (err) {
      history[history.length - 1] = { role: "assistant", content: err.message, error: true };
    }
    form.querySelector("button").disabled = false;
    renderAll();
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = form.message.value.trim();
    if (!text) return;
    form.message.value = "";
    send(text);
  });
  form.message.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });
  view.querySelector("#suggestions").addEventListener("click", (e) => {
    const b = e.target.closest("[data-q]");
    if (b) send(b.dataset.q);
  });
  renderAll();
  const ask = query.get("ask");
  if (ask) {
    window.history.replaceState(null, "", "#/agent");
    send(ask);
  }
}

function chips(ctx) {
  const items = [
    ["Run", ctx.run_id && `#${ctx.run_id}`],
    ["Target", ctx.target_id],
    ["Candidate", ctx.candidate_id],
  ];
  return `<span class="muted">Context:</span> ${items
    .map(([k, v]) => `<span class="chip static">${k}: ${v ? esc(v) : "<em>none</em>"}</span>`)
    .join("")}`;
}

function renderMessage(m) {
  if (m.pending) return `<div class="msg assistant"><span class="spinner"></span> Working with ASTRA tools…</div>`;
  if (m.role === "user") return `<div class="msg user">${esc(m.content)}</div>`;
  if (m.error) return `<div class="msg assistant error">${esc(m.content)}</div>`;
  const r = m.reply;
  const calls = r.tool_calls.length
    ? `<details class="trace"><summary>${r.tool_calls.length} tool call(s) · ${esc(r.mode)} mode</summary><ul>${r.tool_calls
        .map((c) => `<li class="${c.ok ? "" : "fail"}"><code>${esc(c.tool)}</code> <span class="mono small">${esc(JSON.stringify(c.input))}</span>${c.ok ? "" : ` — ${esc(c.error)}`}</li>`)
        .join("")}</ul></details>`
    : "";
  const sources = r.sources.length
    ? `<details class="trace"><summary>${r.sources.length} source(s)</summary><ul>${r.sources.map((s) => `<li class="small">${esc(s)}</li>`).join("")}</ul></details>`
    : "";
  return `<div class="msg assistant">${r.notice ? `<p class="notice small">${esc(r.notice)}</p>` : ""}${miniMarkdown(r.answer)}${calls}${sources}</div>`;
}
