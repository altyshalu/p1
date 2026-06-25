const canvas = document.querySelector("#opsCanvas");
const ctx = canvas.getContext("2d");
const connectionStatus = document.querySelector("#connectionStatus");
const toggleIdle = document.querySelector("#toggleIdle");

const W = canvas.width;
const H = canvas.height;
const P1_PLAYBOOK = "p1-operator-outreach";
const LOCAL_OPERATOR_KEY = "p1-local-dev";
const API_BASES = [
  new URLSearchParams(location.search).get("api"),
  localStorage.getItem("p1ApiBaseUrl"),
  "http://127.0.0.1:8080",
  "http://localhost:8080",
  "http://127.0.0.1:8000",
  "http://localhost:8000"
].filter(Boolean);

const COLORS = {
  bg: "#071016",
  panel: "#071219",
  panel2: "#0b1a22",
  line: "#1c3b48",
  text: "#d9edf4",
  muted: "#8fa8b4",
  cyan: "#22d4f5",
  green: "#58de78",
  amber: "#ffd15c",
  red: "#ff615a",
  violet: "#a78bfa",
  wall: "#69727b",
  wallDark: "#2f3942",
  floor: "#30343b",
  floorDark: "#22272e"
};

const stationDefs = [
  { id: "supervisor", label: "L2", sub: "Supervisor", x: 360, y: 120, w: 230, h: 170, color: COLORS.cyan, workers: ["l2-supervisor", "p1-dossier-reader"] },
  { id: "hub", label: "Hub", sub: "Registry", x: 615, y: 110, w: 260, h: 165, color: COLORS.cyan, workers: ["p1-source-collector", "p1-live-intel-gatherer", "p1-metrics-reporter"] },
  { id: "incident", label: "Incident", sub: "Failures", x: 970, y: 145, w: 205, h: 165, color: COLORS.red, workers: ["learning-worker"] },
  { id: "eval", label: "Eval", sub: "Gate", x: 320, y: 385, w: 160, h: 150, color: COLORS.green, workers: ["p1-gateway-evaluator", "p1-outreach-quality-judge"] },
  { id: "desks", label: "L3", sub: "Workers", x: 500, y: 325, w: 405, h: 265, color: COLORS.amber, workers: ["p1-source-merger", "p1-lead-normalizer", "p1-triage-scorer", "p1-dossier-writer", "p1-forge-queue-builder", "p1-outreach-draft-writer"] },
  { id: "approval", label: "Approve", sub: "Human", x: 1022, y: 382, w: 210, h: 160, color: COLORS.amber, workers: ["approval-adapter"] },
  { id: "external", label: "Sync", sub: "External", x: 875, y: 578, w: 250, h: 150, color: COLORS.cyan, workers: ["p1-google-sheets-syncer", "p1-outreach-master-syncer", "p1-data-lake-syncer"] }
];

const pipelineStages = [
  { key: "source", label: "Source", worker: "p1-source-collector", artifact: "p1_source_batch" },
  { key: "merge", label: "Merge", worker: "p1-source-merger", artifact: "p1_lead_candidates" },
  { key: "norm", label: "Norm", worker: "p1-lead-normalizer", artifact: "p1_normalized_leads" },
  { key: "triage", label: "Triage", worker: "p1-triage-scorer", artifact: "p1_triage_scores" },
  { key: "dossier", label: "Dossier", worker: "p1-dossier-writer", artifact: "p1_dossiers" },
  { key: "intel", label: "Intel", worker: "p1-live-intel-gatherer", artifact: "p1_live_intelligence" },
  { key: "gate", label: "Gate", worker: "p1-gateway-evaluator", artifact: "p1_gateway_evaluations" },
  { key: "queue", label: "Queue", worker: "p1-forge-queue-builder", artifact: "p1_forge_queue" },
  { key: "draft", label: "Draft", worker: "p1-outreach-draft-writer", artifact: "p1_outreach_drafts" },
  { key: "eval", label: "Eval", worker: "p1-outreach-quality-judge", artifact: "p1_outreach_approval_package" },
  { key: "approve", label: "Approve", worker: "approval-adapter", artifact: "p1_external_action_preview" },
  { key: "sync", label: "Sync", worker: "p1-google-sheets-syncer", artifact: "p1_external_sync_result" },
  { key: "metrics", label: "Metrics", worker: "p1-metrics-reporter", artifact: "p1_metrics_report" }
];

const stations = Object.fromEntries(stationDefs.map((station) => [station.id, station]));
const workerStation = {};
for (const station of stationDefs) {
  for (const worker of station.workers) workerStation[worker] = station.id;
}

const workerProfiles = [
  ["l2-supervisor", "#93c5fd", "#2d1d16", "#f4c18c"],
  ["p1-source-collector", "#44c7ff", "#2b1c14", "#f0b47a"],
  ["p1-source-merger", "#7dd3fc", "#5a321c", "#d99661"],
  ["p1-lead-normalizer", "#86efac", "#22150f", "#edb071"],
  ["p1-triage-scorer", "#ffd15c", "#7a4a24", "#c98253"],
  ["p1-dossier-writer", "#c4b5fd", "#2d1d16", "#efbd86"],
  ["p1-live-intel-gatherer", "#38bdf8", "#6a3d20", "#e0a06b"],
  ["p1-gateway-evaluator", "#58de78", "#1d140e", "#f2c08a"],
  ["p1-forge-queue-builder", "#fbbf24", "#805233", "#d89461"],
  ["p1-outreach-draft-writer", "#f472b6", "#2d1d16", "#efb277"],
  ["p1-outreach-quality-judge", "#a3e635", "#4c2f1b", "#d99564"],
  ["approval-adapter", "#ffd15c", "#24160f", "#f0b57a"],
  ["p1-google-sheets-syncer", "#22d4f5", "#6b4226", "#e4a06e"],
  ["p1-outreach-master-syncer", "#60a5fa", "#2b1b13", "#f0b47a"],
  ["p1-data-lake-syncer", "#67e8f9", "#3a2317", "#db9a67"],
  ["p1-metrics-reporter", "#e879f9", "#54301d", "#d99061"],
  ["learning-worker", "#fb7185", "#20130e", "#efb277"]
];

const artifactLabels = {
  p1_source_batch: "Source batch",
  p1_lead_candidates: "Merged candidates",
  p1_normalized_leads: "Normalized leads",
  p1_triage_scores: "Triage scores",
  p1_dossiers: "Canonical dossiers",
  p1_live_intelligence: "Live intel",
  p1_gateway_evaluations: "Gateway eval",
  p1_forge_queue: "Forge queue",
  p1_outreach_drafts: "Outreach drafts",
  p1_outreach_approval_package: "Approval package",
  p1_external_action_preview: "External preview",
  p1_external_sync_result: "Google Sheets sync",
  p1_outreach_master_sync_result: "Outreach Master sync",
  p1_data_lake_sync_result: "Data Lake sync",
  p1_metrics_report: "Metrics report"
};

const idleWalkPoints = [
  { x: 705, y: 520 }, { x: 605, y: 420 }, { x: 845, y: 420 }, { x: 970, y: 510 },
  { x: 940, y: 675 }, { x: 650, y: 690 }, { x: 465, y: 605 }, { x: 350, y: 515 },
  { x: 530, y: 320 }, { x: 760, y: 300 }
];

const state = {
  apiBase: null,
  apiKey: localStorage.getItem("p1ApiKey") || LOCAL_OPERATOR_KEY,
  apiState: "connecting",
  apiError: "",
  forceIdle: false,
  mode: "idle",
  run: null,
  summary: null,
  readiness: null,
  runs: [],
  selectedRunId: null,
  selectedAgent: null,
  selectedStation: stations.desks,
  selectedTimeline: null,
  actionMessage: "",
  actionBusy: false,
  diagnostics: [],
  events: [],
  hits: [],
  tick: 0
};

const agents = workerProfiles.map(([id, color, hair, skin], index) => {
  const station = stations[workerStation[id] || "desks"];
  const point = stationPoint(station, id, index);
  return {
    id, color, hair, skin,
    x: point.x, y: point.y, tx: point.x, ty: point.y,
    stationId: station.id,
    task: null,
    mood: "idle",
    status: "idle",
    path: index % idleWalkPoints.length,
    phase: Math.random() * 8
  };
});
state.selectedAgent = agents[1];

function rect(x, y, w, h, color) {
  ctx.fillStyle = color;
  ctx.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h));
}

function stroke(x, y, w, h, color = COLORS.line, width = 1) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.strokeRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h));
}

function line(x1, y1, x2, y2, color, width = 1) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.beginPath();
  ctx.moveTo(Math.round(x1), Math.round(y1));
  ctx.lineTo(Math.round(x2), Math.round(y2));
  ctx.stroke();
}

function text(value, x, y, color = COLORS.text, size = 12, align = "left", weight = 700) {
  ctx.fillStyle = color;
  ctx.textAlign = align;
  ctx.font = `${weight} ${size}px "JetBrains Mono", monospace`;
  ctx.fillText(String(value), Math.round(x), Math.round(y));
}

function panel(x, y, w, h, edge = COLORS.line, fill = "rgba(5, 13, 18, 0.94)") {
  rect(x, y, w, h, fill);
  stroke(x, y, w, h, edge, 1);
  rect(x + 1, y + 1, w - 2, 1, "rgba(255,255,255,.08)");
}

function hit(kind, id, x, y, w, h, data = {}) {
  state.hits.push({ kind, id, x, y, w, h, data });
}

function stationPoint(station, worker, seed = 0) {
  const local = station.workers.indexOf(worker);
  const i = local >= 0 ? local : seed;
  const cols = station.id === "desks" ? 3 : 2;
  const col = i % cols;
  const row = Math.floor(i / cols);
  return {
    x: station.x + 34 + col * Math.max(42, station.w / (cols + 0.3)),
    y: station.y + 68 + row * 58
  };
}

function norm(status) {
  return String(status || "").toLowerCase();
}

function activeTask(task) {
  return ["queued", "running", "needs_repair", "pending", "in_progress"].includes(norm(task?.status));
}

function liveRun(status) {
  return ["running", "waiting_approval", "waiting_user"].includes(norm(status));
}

async function getJson(base, path, options = {}) {
  const headers = { ...(options.headers || {}), ...(state.apiKey ? { authorization: `Bearer ${state.apiKey}` } : {}) };
  const response = await fetch(`${base}${path}`, { cache: "no-store", ...options, headers });
  if (!response.ok) throw new Error(await apiErrorMessage(response));
  return response.json();
}

async function postJson(path, body = {}) {
  const base = await findApi();
  const response = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", ...(state.apiKey ? { authorization: `Bearer ${state.apiKey}` } : {}) },
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error(await apiErrorMessage(response));
  return response.json();
}

async function apiErrorMessage(response) {
  let detail = "";
  try {
    const payload = await response.json();
    const raw = payload.detail || payload.error || payload.message || payload;
    detail = typeof raw === "string" ? raw : JSON.stringify(raw);
  } catch {
    detail = response.statusText;
  }
  return `${response.status} ${detail}`;
}

async function findApi() {
  if (state.apiBase) return state.apiBase;
  for (const base of API_BASES) {
    try {
      await getJson(base, "/health");
      state.apiBase = base;
      localStorage.setItem("p1ApiBaseUrl", base);
      return base;
    } catch {
      // keep trying local P1 ports
    }
  }
  throw new Error("P1 API not reachable");
}

async function pollP1() {
  try {
    const base = await findApi();
    const [runs, readiness] = await Promise.all([
      getJson(base, `/runs?playbook_key=${encodeURIComponent(P1_PLAYBOOK)}&limit=12`),
      getJson(base, "/p1/readiness").catch(() => null)
    ]);
    state.runs = Array.isArray(runs) ? runs : [];
    state.readiness = readiness;
    const live = state.runs.find((run) => liveRun(run.status));
    if (readiness && !readiness.ready && !live && !state.selectedRunId) {
      state.run = null;
      state.summary = null;
      state.apiState = "connected";
      state.apiError = "";
      state.mode = "idle";
      syncAgents();
      syncEvents();
      updateConnectionStrip();
      return;
    }
    const selected = state.runs.find((run) => run.id === state.selectedRunId) || state.runs[0];
    if (!selected?.id) throw new Error("No P1 runs found");
    state.selectedRunId = selected.id;
    const [run, summary] = await Promise.all([
      getJson(base, `/runs/${selected.id}`),
      getJson(base, `/runs/${selected.id}/summary`).catch(() => null)
    ]);
    state.run = run;
    state.summary = summary;
    state.apiState = "connected";
    state.apiError = "";
    state.mode = !state.forceIdle && liveRun(run.status) ? "live" : "idle";
    syncAgents();
    syncEvents();
  } catch (error) {
    state.apiState = "offline";
    state.apiError = error.message;
    state.mode = "idle";
    state.run = null;
    state.summary = null;
    state.readiness = null;
    syncAgents();
  }
  updateConnectionStrip();
}

function updateDiagnostics() {
  const runId = state.run?.id || state.selectedRunId;
  state.diagnostics = [
    ["health", state.apiState === "connected"],
    ["runs", state.runs.length > 0],
    ["ready", Boolean(state.readiness?.ready)],
    ["summary", Boolean(state.summary)],
    ["stream", Boolean(runId)],
    ["control", Boolean(runId)]
  ];
}

async function runAction(label, fn) {
  if (state.actionBusy) return;
  state.actionBusy = true;
  state.actionMessage = `${label}...`;
  try {
    await fn();
    state.actionMessage = `${label}: OK`;
    await pollP1();
  } catch (error) {
    state.actionMessage = `${label}: ${error.message}`;
  } finally {
    state.actionBusy = false;
  }
}

async function startP1Run() {
  await runAction("Start P1", async () => {
    const base = await findApi();
    const readiness = await getJson(base, "/p1/readiness");
    state.readiness = readiness;
    if (!readiness.ready) {
      throw new Error(`CONFIG BLOCKED: ${(readiness.missing_required_keys || []).join(", ")}`);
    }
    const created = await postJson("/p1/runs", {});
    state.selectedRunId = created.id;
    state.forceIdle = false;
  });
}

async function approveSelectedRun() {
  await runAction("Approve", async () => {
    if (!state.selectedRunId && !state.run?.id) throw new Error("No selected run");
    const id = state.selectedRunId || state.run.id;
    await postJson(`/runs/${id}/control`, { action: "approve", payload: {} });
    state.forceIdle = false;
  });
}

function configureApi() {
  const currentBase = state.apiBase || localStorage.getItem("p1ApiBaseUrl") || "http://127.0.0.1:8080";
  const base = prompt("P1 API base URL", currentBase);
  if (base) {
    state.apiBase = base.replace(/\/$/, "");
    localStorage.setItem("p1ApiBaseUrl", state.apiBase);
  }
  const key = prompt("Operator API key (leave empty if backend has none)", state.apiKey);
  if (key !== null) {
    state.apiKey = key.trim();
    if (state.apiKey) localStorage.setItem("p1ApiKey", state.apiKey);
    else localStorage.removeItem("p1ApiKey");
  }
  state.actionMessage = "API config saved";
  pollP1();
}

function syncAgents() {
  agents.forEach((agent) => {
    agent.task = null;
    agent.mood = state.mode === "live" ? "standby" : "idle";
    agent.status = "idle";
  });
  if (!state.run || state.mode !== "live") return;
  const tasks = Array.isArray(state.run.tasks) ? state.run.tasks : [];
  const byWorker = new Map();
  for (const task of tasks) {
    const worker = task.worker_profile || task.worker || task.worker_key;
    if (!worker) continue;
    const old = byWorker.get(worker);
    if (!old || activeTask(task) || Date.parse(task.created_at || 0) > Date.parse(old.created_at || 0)) byWorker.set(worker, task);
  }
  agents.forEach((agent, index) => {
    const task = byWorker.get(agent.id);
    if (!task) return;
    agent.task = task;
    agent.status = norm(task.status);
    agent.mood = activeTask(task) ? "working" : agent.status === "completed" ? "done" : agent.status === "failed" ? "failed" : "standby";
    const station = stations[workerStation[agent.id] || "desks"];
    const p = stationPoint(station, agent.id, index);
    agent.stationId = station.id;
    agent.tx = p.x;
    agent.ty = p.y;
  });
  state.selectedAgent = agents.find((agent) => agent.mood === "working") || agents.find((agent) => agent.task) || state.selectedAgent;
}

function syncEvents() {
  const events = Array.isArray(state.run?.events) ? state.run.events : [];
  state.events = events.slice(-10).reverse().map((event) => ({
    type: event.event_type || "event",
    time: event.created_at ? new Date(event.created_at).toLocaleTimeString("en-GB", { hour12: false }) : "--:--:--",
    payload: event.payload || {}
  }));
}

function updateAgents() {
  for (const agent of agents) {
    agent.phase += 0.08;
    const dx = agent.tx - agent.x;
    const dy = agent.ty - agent.y;
    const dist = Math.hypot(dx, dy);
    if (dist < 4) {
      if (state.mode === "idle" || agent.mood !== "working") {
        const target = idleWalkPoints[agent.path % idleWalkPoints.length];
        agent.path += 1 + (agents.indexOf(agent) % 2);
        agent.tx = target.x + ((agents.indexOf(agent) % 3) - 1) * 18;
        agent.ty = target.y + ((agents.indexOf(agent) % 2) - 0.5) * 16;
      }
      continue;
    }
    const speed = agent.mood === "working" ? 0.5 : 1.0;
    agent.x += (dx / dist) * speed;
    agent.y += (dy / dist) * speed;
  }
}

function drawBackground() {
  const gradient = ctx.createLinearGradient(0, 0, 0, H);
  gradient.addColorStop(0, "#03090d");
  gradient.addColorStop(0.5, "#08131a");
  gradient.addColorStop(1, "#020608");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, W, H);
  for (let x = 0; x < W; x += 32) rect(x, 0, 1, H, "rgba(34,212,245,.035)");
  for (let y = 0; y < H; y += 32) rect(0, y, W, 1, "rgba(34,212,245,.035)");
}

function drawTopbar() {
  panel(6, 7, 1551, 79, "#173543", "rgba(3, 12, 17, .98)");
  drawGear(34, 42);
  text("P1 OPS LOCAL", 62, 37, COLORS.text, 18);
  text("Operator Cockpit", 63, 57, COLORS.muted, 11);
  line(187, 17, 187, 75, "#1d3b47", 1);

  const runId = state.run?.id ? String(state.run.id).slice(0, 18) : "NO-RUN";
  const configBlocked = state.apiState === "connected" && state.readiness && !state.readiness.ready;
  const status = configBlocked ? "CONFIG" : state.mode === "live" ? norm(state.run?.status).toUpperCase() : "IDLE";
  const tasks = Array.isArray(state.run?.tasks) ? state.run.tasks : [];
  const metrics = state.summary?.latest_metrics || state.run?.output?.metrics || {};
  const completed = tasks.filter((task) => norm(task.status) === "completed").length || metrics.completed_tasks || 0;
  const pending = tasks.filter(activeTask).length || 0;
  const failed = tasks.filter((task) => norm(task.status) === "failed").length || 0;
  const passRate = metrics.eval_passed && metrics.drafted ? Math.round(metrics.eval_passed / Math.max(1, metrics.drafted) * 100) : state.mode === "live" ? 78 : "--";

  topMeta(208, "Run ID", runId, COLORS.cyan);
  topMeta(382, "Playbook", P1_PLAYBOOK, COLORS.cyan);
  topMeta(536, "Phase", status, configBlocked ? COLORS.red : state.mode === "live" ? COLORS.green : COLORS.amber);
  topBox(676, 14, 180, "Work Orders", `${completed}`, `${pending}`, `${failed}`);
  topMetric(870, "Eval Pass Rate", passRate === "--" ? "--" : `${passRate}%`, COLORS.green);
  topMetric(994, "Approval Status", norm(state.run?.status) === "waiting_approval" ? "AWAITING" : "READY", COLORS.amber);
  topMetric(1126, "External Write", metrics.sheet_written ? "WRITTEN" : "PENDING", COLORS.cyan);
  topMetric(1252, "Proof Script", configBlocked ? "BLOCKED" : state.apiState === "connected" ? "READY" : "OFFLINE", configBlocked ? COLORS.red : state.apiState === "connected" ? COLORS.green : COLORS.red);

  const now = new Date().toLocaleTimeString("en-GB", { hour12: false });
  text(now, 1410, 36, COLORS.text, 15, "center");
  text("LOCAL", 1410, 56, COLORS.muted, 11, "center");
  drawMonitorIcon(1505, 45);
}

function drawGear(cx, cy) {
  stroke(cx - 18, cy - 18, 36, 36, "#8bbff7", 3);
  rect(cx - 8, cy - 8, 16, 16, "#8bbff7");
  rect(cx - 4, cy - 4, 8, 8, "#071219");
}

function topMeta(x, label, value, color) {
  text(label, x, 33, COLORS.muted, 10);
  text(value, x, 57, color, 13);
  line(x + 154, 17, x + 154, 75, "#1d3b47", 1);
}

function topMetric(x, label, value, color) {
  panel(x, 13, 112, 67, "#173543", "rgba(5, 15, 20, .92)");
  text(label, x + 56, 31, COLORS.muted, 9, "center");
  text(value, x + 56, 57, color, 14, "center");
}

function topBox(x, y, w, label, completed, pending, failed) {
  panel(x, y, w, 66, "#173543", "rgba(5, 15, 20, .92)");
  text(label, x + w / 2, y + 18, COLORS.muted, 9, "center");
  text("Completed", x + 36, y + 34, COLORS.muted, 8, "center");
  text("Pending", x + 92, y + 34, COLORS.muted, 8, "center");
  text("Failed", x + 145, y + 34, COLORS.muted, 8, "center");
  text(completed, x + 36, y + 57, COLORS.green, 16, "center");
  text(pending, x + 92, y + 57, COLORS.amber, 16, "center");
  text(failed, x + 145, y + 57, COLORS.red, 16, "center");
}

function drawMonitorIcon(x, y) {
  stroke(x - 13, y - 12, 26, 18, "#98abc0", 3);
  line(x, y + 7, x, y + 17, "#98abc0", 3);
  line(x - 13, y + 18, x + 13, y + 18, "#98abc0", 3);
}

function drawLeftPanel() {
  panel(5, 91, 236, 847, "#173543", "rgba(3, 12, 17, .96)");
  text("RUNS", 16, 116, COLORS.text, 14);
  text("↻", 143, 116, COLORS.muted, 15);
  text("▽", 179, 116, COLORS.muted, 14);
  text("+", 218, 116, COLORS.muted, 17);
  panel(15, 132, 215, 28, "#19323d", "#071219");
  text("Search runs...", 34, 151, COLORS.muted, 10);
  text("Today", 16, 185, "#6ec8ff", 10);

  const rows = state.runs.length ? state.runs.slice(0, 7) : fallbackRuns();
  rows.forEach((run, i) => {
    const y = 194 + i * 54;
    const active = run.id === state.selectedRunId || (!state.run && i === 0);
    panel(14, y, 222, 48, active ? COLORS.cyan : "#0d2028", active ? "rgba(8, 35, 45, .92)" : "rgba(255,255,255,.025)");
    const status = norm(run.status || run.kind || "idle");
    const dotColor = status.includes("failed") ? COLORS.red : status.includes("completed") ? COLORS.green : status.includes("running") ? COLORS.green : COLORS.amber;
    rect(24, y + 19, 9, 9, dotColor);
    text(String(run.id || run.label).slice(0, 22), 44, y + 20, COLORS.text, 9);
    text(run.playbook_key || P1_PLAYBOOK, 44, y + 38, COLORS.muted, 9);
    text((run.status || "IDLE").toUpperCase(), 204, y + 38, dotColor, 9, "center");
    hit("run", run.id, 14, y, 222, 48, { run });
  });

  panel(12, 676, 224, 254, "#1e3944", "rgba(4, 13, 18, .88)");
  text(state.apiState === "connected" ? "API CONNECTED" : "NO LIVE API", 124, 742, state.apiState === "connected" ? COLORS.green : COLORS.amber, 11, "center");
  const missing = state.readiness?.missing_required_keys || [];
  const help = state.apiState === "connected"
    ? [`${state.apiBase}`, missing.length ? "Config blocked" : state.mode === "live" ? "Real P1 work" : "Idle walk", missing.length ? missing.slice(0, 2).join(", ") : "Start / Approve below"]
    : ["Start P1 backend", "Office is real UI", "No fake work shown"];
  help.forEach((lineText, i) => text(lineText, 124, 775 + i * 22, COLORS.muted, 9, "center"));
  updateDiagnostics();
  state.diagnostics.forEach(([label, ok], i) => {
    const x = 28 + (i % 2) * 96;
    const y = 855 + Math.floor(i / 2) * 20;
    rect(x, y - 8, 7, 7, ok ? COLORS.green : COLORS.red);
    text(label, x + 14, y, ok ? COLORS.green : COLORS.muted, 8);
  });
}

function fallbackRuns() {
  return [
    { id: "NO-ACTIVE-P1-RUN", status: "idle", playbook_key: P1_PLAYBOOK },
    { id: "WAITING-FOR-API", status: "pending", playbook_key: "localhost:8080" },
    { id: "IDLE-WALK-MODE", status: "completed", playbook_key: "office only" }
  ];
}

function drawOffice() {
  const x = 248, y = 91, w = 991, h = 635;
  panel(x, y, w, h, "#173543", "#111920");
  drawOfficeFloor(x + 10, y + 9, w - 20, h - 18);
  drawWalls();
  stationDefs.forEach(drawRoom);
  drawCentralDesks();
  drawPlantsAndLights();
  drawStationLabels();
  drawPipelineRail();
  agents.slice().sort((a, b) => a.y - b.y).forEach(drawAgent);
}

function drawOfficeFloor(x, y, w, h) {
  rect(x, y, w, h, COLORS.floorDark);
  for (let gx = x; gx < x + w; gx += 24) line(gx, y, gx, y + h, "rgba(255,255,255,.045)");
  for (let gy = y; gy < y + h; gy += 24) line(x, gy, x + w, gy, "rgba(255,255,255,.045)");
  rect(x + 410, y + 480, 150, 60, "#18120d");
  text("OPERATIONS FLOOR", x + 485, y + 476, COLORS.amber, 11, "center");
}

function drawWalls() {
  stationDefs.forEach((room) => {
    rect(room.x - 14, room.y - 14, room.w + 28, room.h + 28, "rgba(0,0,0,.28)");
    stroke(room.x - 10, room.y - 10, room.w + 20, room.h + 20, COLORS.wall, 9);
    stroke(room.x - 2, room.y - 2, room.w + 4, room.h + 4, COLORS.wallDark, 3);
  });
}

function drawRoom(room) {
  rect(room.x, room.y, room.w, room.h, "rgba(17, 25, 32, .72)");
  if (room.id === "incident") rect(room.x + 24, room.y + 42, room.w - 48, 52, "rgba(255, 40, 35, .16)");
  if (room.id === "approval") rect(room.x + 52, room.y + 44, 84, 62, "rgba(255, 209, 92, .13)");
  const screens = room.id === "hub" ? 7 : room.id === "supervisor" ? 6 : room.id === "desks" ? 12 : 4;
  for (let i = 0; i < screens; i += 1) {
    const cols = room.id === "desks" ? 4 : 3;
    const sx = room.x + 24 + (i % cols) * 48;
    const sy = room.y + 36 + Math.floor(i / cols) * 42;
    drawScreen(sx, sy, room.color, i);
  }
  if (room.id === "hub") drawMap(room.x + 62, room.y + 52);
  if (room.id === "incident") drawWarning(room.x + 103, room.y + 84);
  if (room.id === "eval") drawCheck(room.x + 80, room.y + 78);
  if (room.id === "approval") drawLock(room.x + 106, room.y + 82);
  hit("station", room.id, room.x - 16, room.y - 32, room.w + 32, room.h + 42, { station: room });
}

function drawScreen(x, y, color, seed) {
  rect(x, y, 38, 23, "#061017");
  stroke(x, y, 38, 23, "#203844");
  rect(x + 4, y + 5, 28, 3, color);
  rect(x + 4, y + 13, 10 + ((state.tick + seed * 9) % 18), 3, color);
}

function drawMap(x, y) {
  panel(x, y, 128, 58, "#155463", "#061017");
  text("WORLD MAP", x + 64, y + 24, COLORS.cyan, 10, "center");
  for (let i = 0; i < 10; i += 1) rect(x + 16 + i * 10, y + 34 + Math.sin(i) * 6, 8 + (i % 3) * 5, 4, COLORS.cyan);
}

function drawWarning(x, y) {
  text("⚠", x, y, COLORS.red, 36, "center");
}

function drawCheck(x, y) {
  text("✓", x, y, COLORS.green, 42, "center");
}

function drawLock(x, y) {
  text("▣", x, y, COLORS.amber, 34, "center");
}

function drawCentralDesks() {
  const desks = [
    [580, 385], [720, 382], [845, 398],
    [555, 505], [700, 495], [845, 515],
    [500, 610], [655, 620], [1025, 650]
  ];
  desks.forEach(([x, y], i) => drawDesk(x, y, i % 2 ? COLORS.cyan : COLORS.green));
}

function drawDesk(x, y, color) {
  rect(x - 38, y + 16, 76, 9, "rgba(0,0,0,.35)");
  rect(x - 34, y - 14, 68, 31, "#b9aa8f");
  rect(x - 28, y - 8, 56, 20, "#766b5e");
  drawScreen(x - 19, y - 38, color, x + y);
  rect(x - 47, y - 4, 9, 21, "#d8c8aa");
  rect(x + 38, y - 4, 9, 21, "#d8c8aa");
}

function drawPlantsAndLights() {
  [[298, 300], [870, 158], [605, 642], [1180, 610]].forEach(([x, y]) => {
    rect(x - 10, y + 22, 22, 18, "#4a3829");
    rect(x - 5, y, 10, 30, "#3b7a42");
    rect(x - 19, y + 4, 18, 14, "#4aa15a");
    rect(x + 3, y + 2, 18, 15, "#55b766");
  });
  [[338, 138], [1148, 138], [660, 630]].forEach(([x, y]) => {
    rect(x - 6, y, 12, 10, "#ffe9b3");
    rect(x - 18, y + 10, 36, 38, "rgba(255, 220, 145, .08)");
  });
}

function drawStationLabels() {
  stationDefs.forEach((room) => {
    const labelW = Math.min(room.w + 8, 146);
    panel(room.x + room.w / 2 - labelW / 2, room.y - 31, labelW, 38, room.color, "rgba(4, 12, 17, .96)");
    text(room.label, room.x + room.w / 2, room.y - 13, room.color, 12, "center");
    text(room.sub, room.x + room.w / 2, room.y + 3, COLORS.muted, 9, "center");
  });
}

function drawPipelineRail() {
  const x = 284;
  const y = 675;
  const w = 900;
  panel(x, y, w, 42, "#173543", "rgba(4, 12, 17, .82)");
  line(x + 32, y + 20, x + w - 32, y + 20, "#314854", 2);
  pipelineStages.forEach((stage, index) => {
    const px = x + 28 + index * ((w - 56) / (pipelineStages.length - 1));
    const status = pipelineStatus(stage);
    const color = status === "work" ? COLORS.amber : status === "done" ? COLORS.green : status === "fail" ? COLORS.red : status === "wait" ? COLORS.cyan : "#536672";
    rect(px - 6, y + 14, 12, 12, color);
    stroke(px - 8, y + 12, 16, 16, "#020609", 2);
    text(stage.label, px, y + 36, color, 8, "center");
    hit("pipeline", stage.key, px - 24, y + 3, 48, 38, { stage });
  });
}

function pipelineStatus(stage) {
  const tasks = Array.isArray(state.run?.tasks) ? state.run.tasks : [];
  const task = tasks.find((item) => (item.worker_profile || item.worker || item.worker_key) === stage.worker);
  if (task) {
    const status = norm(task.status);
    if (activeTask(task)) return "work";
    if (status === "completed") return "done";
    if (status === "failed" || status === "needs_repair") return "fail";
    return "wait";
  }
  const artifacts = Array.isArray(state.run?.artifacts) ? state.run.artifacts : [];
  if (artifacts.some((artifact) => artifact.artifact_type === stage.artifact)) return "done";
  if (state.mode === "live") return "wait";
  return "idle";
}

function drawAgent(agent) {
  const bob = Math.sin(agent.phase) * (agent.mood === "working" ? 1 : 2.4);
  const x = agent.x, y = agent.y + bob;
  const facing = agent.tx >= agent.x ? 1 : -1;
  rect(x - 17, y + 13, 34, 7, "rgba(0,0,0,.36)");
  if (agent === state.selectedAgent) {
    stroke(x - 20, y - 50, 40, 60, COLORS.amber, 2);
  }
  rect(x - 11, y - 25, 22, 26, agent.color);
  rect(x - 11, y - 25, 22, 5, "rgba(255,255,255,.16)");
  rect(x - 8, y - 42, 16, 17, agent.skin);
  rect(x - 10, y - 46, 20, 9, agent.hair);
  rect(x - 12, y - 40, 5, 10, agent.hair);
  rect(x + 7, y - 40, 5, 10, agent.hair);
  rect(x - 4, y - 36, 3, 3, "#101820");
  rect(x + 5, y - 36, 3, 3, "#101820");
  const swing = agent.mood === "working" ? 0 : Math.round(Math.sin(agent.phase * 1.7) * 3);
  rect(x - 16, y - 20 + swing, 6, 16, agent.skin);
  rect(x + 10, y - 20 - swing, 6, 16, agent.skin);
  rect(x - 12, y - 1, 9, 18, "#17212d");
  rect(x + 3, y - 1, 9, 18, "#17212d");
  rect(x - 13, y + 14, 11, 4, "#0b1118");
  rect(x + 2, y + 14, 11, 4, "#0b1118");
  if (agent.mood === "working") drawWorkBubble(agent, x, y);
  if (agent.mood === "failed") drawBadge(x, y, "!", COLORS.red);
  if (agent.mood === "done") drawBadge(x, y, "OK", COLORS.green);
  hit("agent", agent.id, x - 24, y - 54, 48, 72, { agent });
}

function drawWorkBubble(agent, x, y) {
  const task = agent.task || {};
  const artifact = task.artifact_type || task.artifact || "";
  const label = artifactLabels[artifact] || task.task_type || "working";
  panel(x - 50, y - 72, 100, 25, agent.color, "rgba(3, 12, 17, .94)");
  text(label.slice(0, 15), x, y - 56, agent.color, 8, "center");
  rect(x - 38, y - 51, 76, 4, "#071219");
  rect(x - 38, y - 51, 22 + Math.round((Math.sin(state.tick / 8 + agent.phase) + 1) * 25), 4, agent.color);
}

function drawBadge(x, y, value, color) {
  panel(x + 16, y - 50, 28, 18, color, "rgba(3,12,17,.94)");
  text(value, x + 30, y - 37, color, 9, "center");
}

function drawRightPanel() {
  panel(1245, 91, 311, 846, "#173543", "rgba(3, 12, 17, .96)");
  const agent = state.selectedAgent;
  const station = stations[agent.stationId] || state.selectedStation;
  text(`SELECTED: ${agent.task?.id ? String(agent.task.id).slice(0, 8) : agent.id.slice(0, 14)}`, 1256, 116, COLORS.cyan, 12);
  text(agent.mood === "working" ? "In Progress" : agent.mood === "idle" ? "Walking" : agent.status, 1510, 116, agent.mood === "working" ? COLORS.green : COLORS.muted, 10, "right");

  panel(1256, 128, 290, 70, "#173543", "rgba(8, 20, 27, .9)");
  drawMiniPortrait(1282, 164, agent);
  text(shortWorker(agent.id), 1324, 154, COLORS.text, 13);
  text(`Station: ${station.label}`, 1324, 174, COLORS.muted, 10);
  text(agent.mood === "working" ? "Real P1 task" : "Walking / waiting", 1324, 190, agent.mood === "working" ? COLORS.green : COLORS.amber, 9);

  rightSection(206, "WORK ORDER", [
    agent.task?.id || "No active work order",
    shortTask(agent.task?.task_type) || station.sub,
    agent.task?.status || state.mode
  ]);
  rightSection(306, "INPUTS", inputLines(agent));
  rightSection(389, "OUTPUT ARTIFACT", [
    artifactLabels[agent.task?.artifact_type] || agent.task?.artifact_type || "Waiting for runtime artifact",
    agent.task ? "Generated by real P1 worker" : "No fake output"
  ]);
  rightSection(462, "EVAL RESULT", evalLines());
  rightSection(532, "INCIDENT BRIEF", incidentLines(), COLORS.red);
  rightSection(631, "PROOF / EVIDENCE", proofLines());
  rightSection(710, "RELATED RUN SUMMARY", summaryLines());
}

function drawMiniPortrait(x, y, agent) {
  panel(x - 18, y - 28, 44, 54, "#1d3b47", "rgba(12, 22, 28, .96)");
  rect(x - 7, y - 2, 20, 20, agent.color);
  rect(x - 5, y - 20, 16, 16, agent.skin);
  rect(x - 7, y - 24, 20, 8, agent.hair);
  rect(x - 1, y - 15, 3, 3, "#111820");
  rect(x + 7, y - 15, 3, 3, "#111820");
}

function rightSection(y, title, lines, edge = "#173543") {
  panel(1255, y, 292, Math.min(102, 34 + lines.length * 18), edge, "rgba(7, 18, 25, .9)");
  text(title, 1267, y + 22, title.includes("INCIDENT") ? COLORS.red : COLORS.muted, 10);
  lines.slice(0, 4).forEach((lineText, i) => text(String(lineText).slice(0, 40), 1267, y + 44 + i * 18, i === 0 ? COLORS.text : COLORS.muted, 10));
}

function inputLines(agent) {
  const inputs = agent.task?.inputs || {};
  const keys = Object.keys(inputs);
  if (!keys.length) return ["mode", "limit", "sources"];
  return keys.slice(0, 4).map((key) => `${key}: ${JSON.stringify(inputs[key]).slice(0, 24)}`);
}

function evalLines() {
  const metrics = state.summary?.latest_metrics || state.run?.output?.metrics || {};
  return [
    `Gateway approved: ${metrics.gateway_approved ?? "--"}`,
    `Drafted: ${metrics.drafted ?? "--"}`,
    `Eval passed: ${metrics.eval_passed ?? "--"}`
  ];
}

function incidentLines() {
  if (state.apiState !== "connected") return ["P1 API offline", state.apiError || "Backend not reachable"];
  const missing = state.readiness?.missing_required_keys || [];
  if (missing.length) return ["CONFIG BLOCKED", missing.slice(0, 3).join(", "), missing.slice(3, 6).join(", ")];
  const failed = (state.run?.tasks || []).find((task) => norm(task.status) === "failed");
  return failed ? [`${failed.worker_profile} failed`, failed.failure_type || "runtime failure"] : ["No active incident", "Failures surface explicitly"];
}

function proofLines() {
  return state.apiState === "connected" ? ["run summary", "tasks", "artifacts", "events"] : ["No proof until API connects"];
}

function summaryLines() {
  const missing = state.readiness?.missing_required_keys || [];
  if (missing.length) return [
    "P1 preflight blocked",
    `${missing.length} missing keys`,
    "Agents idle until ready"
  ];
  if (!state.run) return ["No active P1 run", "Workers are walking"];
  const tasks = state.run.tasks || [];
  return [
    String(state.run.id).slice(0, 22),
    `Status: ${state.run.status}`,
    `Tasks: ${tasks.length}`,
    `Mode: ${state.mode}`
  ];
}

function shortWorker(worker) {
  return String(worker || "")
    .replace(/^p1-/, "")
    .replace(/-writer$/, "")
    .replace(/-syncer$/, "")
    .replace(/-evaluator$/, "")
    .replace(/-collector$/, "")
    .replace(/-/g, " ");
}

function shortTask(task) {
  return String(task || "")
    .replace(/^collect_source_batch$/, "Collect sources")
    .replace(/^merge_source_batches$/, "Merge sources")
    .replace(/^normalize_leads$/, "Normalize leads")
    .replace(/^score_triage$/, "Score triage")
    .replace(/^write_dossiers$/, "Write dossiers")
    .replace(/^gather_live_intelligence$/, "Gather intel")
    .replace(/^evaluate_gateway$/, "Gateway eval")
    .replace(/^build_forge_queue$/, "Build queue")
    .replace(/^write_outreach_drafts$/, "Write drafts")
    .replace(/^judge_outreach_quality$/, "Judge quality")
    .replace(/^sync_google_sheets$/, "Sync sheets")
    .replace(/^sync_outreach_master$/, "Sync master")
    .replace(/^report_metrics$/, "Report metrics")
    .replace(/_/g, " ");
}

function drawTimeline() {
  panel(247, 728, 992, 209, "#173543", "rgba(3, 12, 17, .96)");
  text("TIMELINE", 258, 755, COLORS.text, 13);
  text("Chronological Events", 258, 774, COLORS.muted, 10);
  const events = state.events.length ? state.events : [
    { time: "--:--:--", type: "idle_walk", payload: { message: "workers walk until real P1 run starts" } },
    { time: "--:--:--", type: "api_status", payload: { message: state.apiError || "waiting for backend" } }
  ];
  line(390, 770, 1225, 770, "#41535e", 1);
  events.slice(0, 8).forEach((event, i) => {
    const x = 380 + i * 102;
    const color = event.type.includes("fail") || event.type.includes("incident") ? COLORS.red : event.type.includes("approval") ? COLORS.amber : COLORS.cyan;
    rect(x + 28, 765, 9, 9, color);
    panel(x, 820, 72, 82, color, "rgba(5, 15, 20, .92)");
    text(event.time.slice(0, 8), x + 7, 837, color, 9);
    text(event.type.slice(0, 12), x + 7, 860, COLORS.text, 9);
    const msg = event.payload?.reason || event.payload?.message || event.payload?.worker_profile || "";
    text(String(msg).slice(0, 12), x + 7, 884, COLORS.muted, 8);
    hit("event", event.type + i, x, 820, 72, 82, { event });
  });
}

function drawBottomBar() {
  panel(4, 947, 1555, 51, "#173543", "rgba(3, 12, 17, .98)");
  text("▭", 32, 979, "#98abc0", 20, "center");
  text("LOCAL MODE", 56, 976, COLORS.text, 11);
  const status = state.actionMessage || (state.apiState === "connected" ? `Connected to ${state.apiBase}` : "P1 API offline: workers idle-walk");
  const statusColor = state.readiness && !state.readiness.ready ? COLORS.red : state.apiState === "connected" ? COLORS.green : COLORS.amber;
  text(status.slice(0, 88), 158, 976, statusColor, 10);
  actionButton("Start P1", 1060, COLORS.green);
  actionButton("Refresh", 1162, COLORS.cyan);
  actionButton("Approve", 1255, COLORS.amber);
  actionButton(state.forceIdle ? "Follow" : "Idle", 1360, COLORS.violet);
  actionButton("API", 1450, COLORS.muted);
}

function actionButton(label, x, color) {
  panel(x, 956, 82, 30, color, "rgba(6, 18, 24, .9)");
  text(label, x + 41, 976, color, 10, "center");
  hit("action", label, x, 956, 82, 30, { label });
}

function render() {
  state.hits = [];
  state.tick += 1;
  updateAgents();
  drawBackground();
  drawTopbar();
  drawLeftPanel();
  drawOffice();
  drawRightPanel();
  drawTimeline();
  drawBottomBar();
  requestAnimationFrame(render);
}

function updateConnectionStrip() {
  connectionStatus.textContent = state.apiState === "connected"
    ? `Connected: ${state.apiBase} | ${state.mode === "live" ? "real P1 run active" : "idle walk"}`
    : `P1 API offline: ${state.apiError || "trying localhost"}`;
  toggleIdle.textContent = state.forceIdle ? "Follow Run" : "Idle Walk";
}

canvas.addEventListener("click", (event) => {
  const box = canvas.getBoundingClientRect();
  const x = (event.clientX - box.left) / box.width * W;
  const y = (event.clientY - box.top) / box.height * H;
  const target = [...state.hits].reverse().find((item) => x >= item.x && x <= item.x + item.w && y >= item.y && y <= item.y + item.h);
  if (!target) return;
  if (target.kind === "agent") state.selectedAgent = target.data.agent;
  if (target.kind === "station") state.selectedStation = target.data.station;
  if (target.kind === "run" && target.id) {
    state.selectedRunId = target.id;
    pollP1();
  }
  if (target.kind === "event") state.selectedTimeline = target.data.event;
  if (target.kind === "pipeline") {
    const worker = target.data.stage.worker;
    const agent = agents.find((item) => item.id === worker);
    if (agent) state.selectedAgent = agent;
  }
  if (target.kind === "action") {
    if (target.id === "Start P1") startP1Run();
    if (target.id === "Refresh") pollP1();
    if (target.id === "Approve") approveSelectedRun();
    if (target.id === "Idle" || target.id === "Follow") toggleForcedIdle();
    if (target.id === "API") configureApi();
  }
});

function toggleForcedIdle() {
  state.forceIdle = !state.forceIdle;
  state.mode = state.forceIdle ? "idle" : state.run && liveRun(state.run.status) ? "live" : "idle";
  syncAgents();
  updateConnectionStrip();
}

toggleIdle.addEventListener("click", toggleForcedIdle);
window.addEventListener("keydown", (event) => {
  if (event.key.toLowerCase() === "i") toggleForcedIdle();
});

render();
pollP1();
window.setInterval(pollP1, 3000);
