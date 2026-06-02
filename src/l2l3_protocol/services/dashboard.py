from __future__ import annotations


def operator_dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ABRT P1 Operator Dashboard</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #fbfbfa;
      --panel: #ffffff;
      --text: #20201f;
      --muted: #6f6d68;
      --line: #e8e6e1;
      --soft: #f4f3ef;
      --good: #16834a;
      --warn: #9a6212;
      --bad: #b42318;
      --focus: #2f5fef;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.5 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    button, input, textarea { font: inherit; }
    button {
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--text);
      border-radius: 8px;
      padding: 8px 11px;
      cursor: pointer;
    }
    button:hover { background: var(--soft); }
    button.primary { background: var(--text); color: white; border-color: var(--text); }
    button.danger { color: var(--bad); }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 22px;
      border-bottom: 1px solid var(--line);
      background: rgba(251, 251, 250, 0.88);
      position: sticky;
      top: 0;
      backdrop-filter: blur(12px);
      z-index: 2;
    }
    h1 { font-size: 16px; margin: 0; font-weight: 650; letter-spacing: 0; }
    main {
      display: grid;
      grid-template-columns: 320px 1fr;
      min-height: calc(100vh - 62px);
    }
    aside {
      border-right: 1px solid var(--line);
      padding: 16px;
      overflow: auto;
    }
    section { padding: 18px; min-width: 0; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .muted { color: var(--muted); }
    .run-list { display: grid; gap: 8px; margin-top: 14px; }
    .run-item {
      width: 100%;
      text-align: left;
      display: grid;
      gap: 4px;
    }
    .run-item.active { outline: 2px solid var(--focus); outline-offset: 1px; }
    .status {
      display: inline-flex;
      align-items: center;
      width: fit-content;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      color: var(--muted);
      background: var(--soft);
    }
    .status.completed { color: var(--good); }
    .status.failed { color: var(--bad); }
    .status.waiting_approval, .status.waiting_user { color: var(--warn); }
    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin: 14px 0;
    }
    .metric, .panel {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 12px;
    }
    .metric strong { display: block; font-size: 22px; line-height: 1.1; }
    .metric span { color: var(--muted); font-size: 12px; }
    .columns {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 12px;
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      color: #353431;
      background: var(--soft);
      border-radius: 8px;
      padding: 10px;
      max-height: 280px;
      overflow: auto;
    }
    .draft { display: grid; gap: 8px; margin-top: 10px; }
    .event { border-bottom: 1px solid var(--line); padding: 8px 0; }
    .event:last-child { border-bottom: 0; }
    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 8px;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 7px 6px;
      text-align: left;
      vertical-align: top;
    }
    th { color: var(--muted); font-weight: 600; }
    textarea {
      width: 100%;
      min-height: 74px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: var(--panel);
      resize: vertical;
    }
    input {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      background: var(--panel);
      min-width: 220px;
    }
    @media (max-width: 860px) {
      main { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      .grid, .columns { grid-template-columns: 1fr; }
      header { align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>ABRT P1 Operator Dashboard</h1>
      <div class="muted">Real P1 runs, evidence, approvals, drafts, and learning state.</div>
    </div>
    <div class="toolbar">
      <input id="apiKey" type="password" placeholder="Operator API key">
      <button class="primary" id="start">Start P1</button>
      <button id="refresh">Refresh</button>
    </div>
  </header>
  <main>
    <aside>
      <div class="muted">Recent P1 runs</div>
      <div id="runs" class="run-list"></div>
    </aside>
    <section>
      <div id="summary" class="panel">Select or start a P1 run.</div>
      <div class="grid" id="metrics"></div>
      <div class="toolbar" style="margin-bottom: 12px;">
        <button id="approve">Approve</button>
        <button class="danger" id="reject">Reject</button>
      </div>
      <textarea id="feedback" placeholder="Operator feedback for /messages"></textarea>
      <div class="toolbar" style="margin-top: 8px;"><button id="edit">Send Feedback</button></div>
      <div class="columns" style="margin-top: 14px;">
        <div class="panel">
          <strong>Drafts</strong>
          <div id="drafts"></div>
        </div>
        <div class="panel">
          <strong>Events</strong>
          <div id="events"></div>
        </div>
      </div>
      <div class="columns" style="margin-top: 14px;">
        <div class="panel">
          <strong>Source Quality</strong>
          <div id="sourceQuality" class="muted">No source-quality metrics yet.</div>
        </div>
        <div class="panel">
          <strong>Runtime Bottlenecks</strong>
          <div id="bottlenecks" class="muted">No timing metrics yet.</div>
        </div>
      </div>
      <div class="panel" style="margin-top: 12px;">
        <strong>Learning</strong>
        <pre id="learning">Loading...</pre>
      </div>
    </section>
  </main>
  <script>
    const state = { selectedRunId: null, eventSource: null };
    const metricKeys = ["raw_leads","normalized_leads","rejected_leads","triage_qualified","dossiers","gateway_approved","gateway_rejected","drafted","eval_passed","sheet_written","data_lake_written","outreach_master_written","provider_cache_hits"];

    async function api(path, options = {}) {
      const apiKey = localStorage.getItem("l2l3OperatorApiKey") || "";
      const headers = { "content-type": "application/json", ...(apiKey ? { "authorization": `Bearer ${apiKey}` } : {}) };
      const response = await fetch(path, { ...options, headers: { ...headers, ...(options.headers || {}) } });
      if (!response.ok) throw new Error(`${options.method || "GET"} ${path} ${response.status}`);
      return response.json();
    }

    function esc(value) {
      return String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    }

    async function loadRuns() {
      const runs = await api("/runs?playbook_key=p1-operator-outreach&limit=20");
      const list = document.getElementById("runs");
      list.innerHTML = runs.map(run => `
        <button class="run-item ${run.id === state.selectedRunId ? "active" : ""}" data-run="${esc(run.id)}">
          <span>${esc(run.goal || "P1 run")}</span>
          <span class="status ${esc(run.status)}">${esc(run.status)}</span>
          <span class="muted">${esc(run.id)}</span>
        </button>
      `).join("");
      list.querySelectorAll("[data-run]").forEach(button => button.addEventListener("click", () => selectRun(button.dataset.run)));
      if (!state.selectedRunId && runs[0]) await selectRun(runs[0].id);
    }

    async function selectRun(runId) {
      state.selectedRunId = runId;
      await Promise.all([loadSummary(runId), loadRun(runId), loadRuns(), loadLearning()]);
      connectEvents(runId);
    }

    async function loadSummary(runId) {
      const summary = await api(`/runs/${runId}/summary`);
      const diagnosis = summary.latest_diagnosis || {};
      const pending = summary.pending_actions || [];
      document.getElementById("summary").innerHTML = `
        <div class="toolbar" style="justify-content: space-between;">
          <div><strong>${esc(summary.goal)}</strong><div class="muted">${esc(summary.id)}</div></div>
          <span class="status ${esc(summary.status)}">${esc(summary.status)}</span>
        </div>
        <div class="muted" style="margin-top: 8px;">pending: ${pending.length} · diagnosis: ${esc(diagnosis.root_cause || "none")}</div>
      `;
      const metrics = summary.latest_metrics || {};
      document.getElementById("metrics").innerHTML = metricKeys.map(key => `
        <div class="metric"><strong>${esc(metrics[key] ?? 0)}</strong><span>${esc(key)}</span></div>
      `).join("");
      renderSourceQuality(metrics.source_quality_by_source || {});
      renderBottlenecks(metrics.duration_by_worker_ms || {});
    }

    function renderSourceQuality(sourceQuality) {
      const rows = Object.entries(sourceQuality || {});
      const target = document.getElementById("sourceQuality");
      if (!rows.length) {
        target.innerHTML = `<div class="muted">No source-quality metrics yet.</div>`;
        return;
      }
      target.innerHTML = `
        <table>
          <thead><tr><th>Source</th><th>Raw</th><th>Qualified</th><th>Approved</th><th>Rates</th></tr></thead>
          <tbody>${rows.map(([source, stats]) => `
            <tr>
              <td>${esc(source)}</td>
              <td>${esc(stats.raw ?? 0)}</td>
              <td>${esc(stats.triage_qualified ?? 0)}</td>
              <td>${esc(stats.gateway_approved ?? 0)}</td>
              <td>${esc(stats.triage_qualified_rate ?? 0)} / ${esc(stats.gateway_approved_rate ?? 0)}</td>
            </tr>
          `).join("")}</tbody>
        </table>
      `;
    }

    function renderBottlenecks(durationByWorker) {
      const rows = Object.entries(durationByWorker || {})
        .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
        .slice(0, 6);
      const target = document.getElementById("bottlenecks");
      if (!rows.length) {
        target.innerHTML = `<div class="muted">No timing metrics yet.</div>`;
        return;
      }
      target.innerHTML = `
        <table>
          <thead><tr><th>Worker</th><th>Seconds</th></tr></thead>
          <tbody>${rows.map(([worker, ms]) => `
            <tr><td>${esc(worker)}</td><td>${esc(Math.round(Number(ms || 0) / 100) / 10)}</td></tr>
          `).join("")}</tbody>
        </table>
      `;
    }

    async function loadRun(runId) {
      const run = await api(`/runs/${runId}`);
      const packagePayload = run.output?.approval_package || {};
      const drafts = packagePayload.outreach_drafts || [];
      document.getElementById("drafts").innerHTML = drafts.length ? drafts.slice(0, 10).map(draft => `
        <div class="draft">
          <strong>${esc(draft.name)} <span class="muted">${esc(draft.current_role || "")}</span></strong>
          <pre>${esc(draft.text)}</pre>
          <div class="muted">${(draft.evidence_urls || []).map(url => esc(url)).join("\\n")}</div>
        </div>
      `).join("") : `<div class="muted">No drafts yet.</div>`;
      renderEvents(run.events || []);
    }

    function renderEvents(events) {
      document.getElementById("events").innerHTML = events.slice(-80).reverse().map(event => `
        <div class="event">
          <strong>${esc(event.event_type)}</strong>
          <div class="muted">${esc(event.created_at || "")}</div>
          <pre>${esc(JSON.stringify(event.payload || {}, null, 2))}</pre>
        </div>
      `).join("");
    }

    function connectEvents(runId) {
      if (state.eventSource) state.eventSource.close();
      state.eventSource = new EventSource(`/runs/${runId}/events/stream`);
      state.eventSource.addEventListener("run_event", async () => {
        await Promise.all([loadSummary(runId), loadRun(runId)]);
      });
      state.eventSource.addEventListener("run_status", async () => {
        await Promise.all([loadSummary(runId), loadRun(runId), loadRuns()]);
      });
    }

    async function loadLearning() {
      const report = await api("/reports/system-learning?playbook_key=p1-operator-outreach&since_hours=168");
      document.getElementById("learning").textContent = JSON.stringify(report, null, 2);
    }

    document.getElementById("start").addEventListener("click", async () => {
      const created = await api("/p1/runs", { method: "POST", body: "{}" });
      await selectRun(created.id);
    });
    document.getElementById("refresh").addEventListener("click", loadRuns);
    document.getElementById("apiKey").value = localStorage.getItem("l2l3OperatorApiKey") || "";
    document.getElementById("apiKey").addEventListener("change", event => {
      localStorage.setItem("l2l3OperatorApiKey", event.target.value.trim());
    });
    document.getElementById("approve").addEventListener("click", async () => {
      if (!state.selectedRunId) return;
      await api(`/runs/${state.selectedRunId}/control`, { method: "POST", body: JSON.stringify({ action: "approve", payload: {} }) });
      await selectRun(state.selectedRunId);
    });
    document.getElementById("reject").addEventListener("click", async () => {
      if (!state.selectedRunId) return;
      const reason = document.getElementById("feedback").value || "Rejected from operator dashboard.";
      await api(`/runs/${state.selectedRunId}/control`, { method: "POST", body: JSON.stringify({ action: "reject", payload: { reason } }) });
      await selectRun(state.selectedRunId);
    });
    document.getElementById("edit").addEventListener("click", async () => {
      if (!state.selectedRunId) return;
      const message = document.getElementById("feedback").value.trim();
      if (!message) return;
      await api(`/runs/${state.selectedRunId}/messages`, { method: "POST", body: JSON.stringify({ message }) });
      document.getElementById("feedback").value = "";
      await selectRun(state.selectedRunId);
    });
    loadRuns().catch(error => {
      document.getElementById("summary").textContent = `Dashboard failed: ${error.message}`;
    });
  </script>
</body>
</html>"""
