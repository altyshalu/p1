const canvas = document.querySelector("#opsCanvas");
const ctx = canvas.getContext("2d");

const ui = {
  selectedLabel: document.querySelector("#selectedLabel"),
  selectedTitle: document.querySelector("#selectedTitle"),
  selectedState: document.querySelector("#selectedState"),
  agentName: document.querySelector("#agentName"),
  agentDesk: document.querySelector("#agentDesk"),
  agentTask: document.querySelector("#agentTask"),
  workOrderId: document.querySelector("#workOrderId"),
  workOrderText: document.querySelector("#workOrderText"),
  workProgress: document.querySelector("#workProgress"),
  artifactName: document.querySelector("#artifactName"),
  artifactSize: document.querySelector("#artifactSize"),
  evalRate: document.querySelector("#evalRate"),
  evalChecks: document.querySelector("#evalChecks"),
  incidentText: document.querySelector("#incidentText"),
  pauseButton: document.querySelector("#pauseButton"),
  speedButton: document.querySelector("#speedButton"),
  assignButton: document.querySelector("#assignButton"),
  completedCount: document.querySelector("#completedCount"),
  pendingCount: document.querySelector("#pendingCount"),
  failedCount: document.querySelector("#failedCount"),
  passRate: document.querySelector("#passRate"),
  opsClock: document.querySelector("#opsClock"),
  runList: document.querySelector("#runList"),
  eventRow: document.querySelector("#eventRow")
};

const sourceRepo = {
  repo: "github.com/altyshalu/p1",
  playbook: "p1-operator-outreach",
  strategy: "deterministic_p1_operator_outreach",
  maxTurns: 16,
  maxTasksPerTurn: 2
};

const stages = [
  {
    id: "source",
    label: "Source Batches",
    sub: "Exa + Apify",
    worker: "p1-source-collector",
    taskType: "collect_source_batch",
    artifact: "p1_source_batch",
    input: "mode, sources, limit, query",
    output: "lead_candidates + source_attempts",
    tools: ["exa-search-tool", "apify-actor-tool"],
    color: "#22d4f5",
    x: 88,
    y: 88,
    w: 205,
    h: 126
  },
  {
    id: "merge",
    label: "Merge",
    sub: "Deduplicate",
    worker: "p1-source-merger",
    taskType: "merge_source_batches",
    artifact: "p1_lead_candidates",
    input: "source_batches",
    output: "merged lead_candidates",
    tools: [],
    color: "#7dd3fc",
    x: 345,
    y: 74,
    w: 172,
    h: 112
  },
  {
    id: "normalize",
    label: "Normalize",
    sub: "Human leads only",
    worker: "p1-lead-normalizer",
    taskType: "normalize_leads",
    artifact: "p1_normalized_leads",
    input: "lead_candidates",
    output: "normalized_leads + rejected_leads",
    tools: [],
    color: "#86efac",
    x: 568,
    y: 78,
    w: 190,
    h: 118
  },
  {
    id: "triage",
    label: "Triage",
    sub: "B2C/PLG rubric",
    worker: "p1-triage-scorer",
    taskType: "score_triage",
    artifact: "p1_triage_scores",
    input: "normalized_leads",
    output: "triage_scores",
    tools: [],
    color: "#ffd15c",
    x: 822,
    y: 86,
    w: 205,
    h: 132
  },
  {
    id: "dossiers",
    label: "Dossiers",
    sub: "Canonical state",
    worker: "p1-dossier-writer",
    taskType: "write_dossiers",
    artifact: "p1_dossiers",
    input: "triage_scores",
    output: "p1_dossiers",
    tools: ["p1-dossier-store-tool"],
    color: "#c4b5fd",
    x: 1020,
    y: 260,
    w: 188,
    h: 136
  },
  {
    id: "intel",
    label: "Live Intel",
    sub: "Real evidence",
    worker: "p1-live-intel-gatherer",
    taskType: "gather_live_intelligence",
    artifact: "p1_live_intelligence",
    input: "p1_dossiers",
    output: "enriched dossiers",
    tools: ["exa-search-tool"],
    color: "#38bdf8",
    x: 812,
    y: 292,
    w: 178,
    h: 132
  },
  {
    id: "gateway",
    label: "Gateway Eval",
    sub: "Fit + identity",
    worker: "p1-gateway-evaluator",
    taskType: "evaluate_gateway",
    artifact: "p1_gateway_evaluations",
    input: "p1_dossiers",
    output: "gateway_evaluations",
    tools: [],
    color: "#58de78",
    x: 574,
    y: 292,
    w: 190,
    h: 138
  },
  {
    id: "queue",
    label: "Forge Queue",
    sub: "Approved ops",
    worker: "p1-forge-queue-builder",
    taskType: "build_forge_queue",
    artifact: "p1_forge_queue",
    input: "gateway_evaluations",
    output: "forge_queue",
    tools: [],
    color: "#fbbf24",
    x: 336,
    y: 296,
    w: 190,
    h: 126
  },
  {
    id: "drafts",
    label: "Outreach Drafts",
    sub: "Grounded copy",
    worker: "p1-outreach-draft-writer",
    taskType: "write_outreach_drafts",
    artifact: "p1_outreach_drafts",
    input: "forge_queue, channels",
    output: "outreach_drafts",
    tools: [],
    color: "#f472b6",
    x: 104,
    y: 312,
    w: 200,
    h: 142
  },
  {
    id: "quality",
    label: "Quality Judge",
    sub: "Eval gate",
    worker: "p1-outreach-quality-judge",
    taskType: "judge_outreach_quality",
    artifact: "p1_outreach_approval_package",
    input: "outreach_drafts",
    output: "passed, score, checks",
    tools: [],
    color: "#58de78",
    x: 214,
    y: 532,
    w: 198,
    h: 122
  },
  {
    id: "approval",
    label: "Approval Preview",
    sub: "Human gate",
    worker: "approval-adapter",
    taskType: "record_approval_gate",
    artifact: "p1_external_action_preview",
    input: "approval_package",
    output: "waiting_approval",
    tools: [],
    color: "#ffd15c",
    x: 520,
    y: 538,
    w: 214,
    h: 126
  },
  {
    id: "external",
    label: "External Sync",
    sub: "Sheets + master",
    worker: "p1-google-sheets-syncer",
    taskType: "sync_google_sheets",
    artifact: "p1_external_sync_result",
    input: "approval_package + approval",
    output: "idempotent writes",
    tools: ["google-sheets-write-tool"],
    color: "#22d4f5",
    x: 842,
    y: 532,
    w: 226,
    h: 126
  }
];

const metricsStage = {
  id: "metrics",
  label: "Metrics Reporter",
  sub: "Run summary",
  worker: "p1-metrics-reporter",
  taskType: "report_metrics",
  artifact: "p1_metrics_report",
  input: "runtime artifacts",
  output: "summary + funnel metrics",
  tools: [],
  color: "#a78bfa",
  x: 1100,
  y: 78,
  w: 132,
  h: 118
};

const allRooms = [...stages, metricsStage];
const runners = ["exa", "apify_funding", "apify_crunchbase", "apify_linkedin"];
const events = [];
const sourceCounts = {
  raw_leads: 0,
  normalized_leads: 0,
  rejected_leads: 0,
  triage_qualified: 0,
  dossiers: 0,
  gateway_approved: 0,
  drafted: 0,
  eval_passed: 0,
  sheet_written: 0,
  outreach_master_written: 0
};

const agentColors = ["#7dd3fc", "#38bdf8", "#86efac", "#fbbf24", "#c4b5fd", "#f472b6", "#fb7185", "#60a5fa", "#a3e635", "#f97316", "#e879f9", "#22d3ee"];
const agents = stages.map((stage, index) => {
  const spot = centerOf(stage);
  return {
    id: stage.worker,
    desk: stage.id.toUpperCase(),
    x: spot.x + (Math.random() - 0.5) * 38,
    y: spot.y + (Math.random() - 0.5) * 30,
    tx: spot.x,
    ty: spot.y,
    stageIndex: index,
    station: stage,
    orderNo: index + 1,
    progress: index * 4,
    state: index < 2 ? "working" : "queued",
    color: agentColors[index],
    hair: ["#2d1d16", "#6b4226", "#24160f", "#805233", "#322214"][index % 5],
    phase: Math.random() * 10,
    source: runners[index % runners.length],
    wait: index * 34
  };
});

const state = {
  selectedAgent: agents[0],
  paused: false,
  speed: 1,
  tick: 0,
  completed: 0,
  pending: stages.length,
  failed: 0,
  passScore: 86,
  flash: null,
  approvalWaiting: false,
  externalUnlocked: false
};

function centerOf(stage) {
  return { x: stage.x + stage.w / 2, y: stage.y + stage.h / 2 + 16 };
}

function drawRect(x, y, w, h, color) {
  ctx.fillStyle = color;
  ctx.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h));
}

function strokeRect(x, y, w, h, color, width = 2) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.strokeRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h));
}

function drawPixelPanel(x, y, w, h, fill, edge, hi = "rgba(255,255,255,0.08)") {
  drawRect(x + 7, y + 7, w, h, "rgba(0, 0, 0, 0.42)");
  drawRect(x, y, w, h, fill);
  drawRect(x, y, w, 4, hi);
  drawRect(x, y, 4, h, hi);
  drawRect(x, y + h - 5, w, 5, "rgba(0,0,0,0.36)");
  drawRect(x + w - 5, y, 5, h, "rgba(0,0,0,0.3)");
  strokeRect(x, y, w, h, edge, 2);
  drawRect(x - 4, y + 10, 4, h - 20, edge);
  drawRect(x + w, y + 10, 4, h - 20, edge);
}

function drawTinyBars(x, y, color, count = 3) {
  for (let i = 0; i < count; i += 1) {
    drawRect(x, y + i * 7, 26 + ((state.tick + i * 11) % 20), 3, color);
  }
}

function drawText(text, x, y, color = "#d9edf4", size = 14, align = "left") {
  ctx.fillStyle = color;
  ctx.font = `700 ${size}px "JetBrains Mono", monospace`;
  ctx.textAlign = align;
  ctx.fillText(text, Math.round(x), Math.round(y));
}

function addEvent(kind, title, text) {
  const now = new Date();
  const time = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(now);
  events.unshift({ time, title, text, kind });
  events.splice(8);
  renderEvents();
}

function stationById(id) {
  return allRooms.find((stage) => stage.id === id);
}

function assignAgent(agent, station = null) {
  const target = station || stages[(agent.stageIndex + 1) % stages.length];
  const center = centerOf(target);
  agent.station = target;
  agent.stageIndex = stages.indexOf(target) >= 0 ? stages.indexOf(target) : agent.stageIndex;
  agent.tx = center.x + (Math.random() - 0.5) * Math.min(82, target.w * 0.48);
  agent.ty = center.y + (Math.random() - 0.5) * Math.min(52, target.h * 0.36);
  agent.state = "moving";
  state.flash = { x: agent.tx, y: agent.ty, age: 0, text: target.taskType };
}

function completeStage(agent) {
  const stage = agent.station;
  agent.progress = 0;
  state.completed += 1;
  state.pending = Math.max(0, stages.length - Math.min(stages.length, state.completed % (stages.length + 1)));
  state.passScore = Math.min(98, state.passScore + (stage.id === "quality" ? 2 : 0.4));

  if (stage.id === "source") sourceCounts.raw_leads += 6 + Math.floor(Math.random() * 8);
  if (stage.id === "normalize") {
    sourceCounts.normalized_leads += 7;
    sourceCounts.rejected_leads += 2;
  }
  if (stage.id === "triage") sourceCounts.triage_qualified += 4;
  if (stage.id === "dossiers") sourceCounts.dossiers += 4;
  if (stage.id === "gateway") sourceCounts.gateway_approved += 3;
  if (stage.id === "drafts") sourceCounts.drafted += 3;
  if (stage.id === "quality") sourceCounts.eval_passed += 1;
  if (stage.id === "approval") {
    state.approvalWaiting = true;
    state.externalUnlocked = true;
  }
  if (stage.id === "external") {
    sourceCounts.sheet_written += 3;
    sourceCounts.outreach_master_written += 3;
  }

  addEvent(stage.id === "external" ? "complete" : stage.id === "approval" ? "pending" : "complete", stage.artifact, `${stage.worker} finished ${stage.taskType}`);
  const next = stage.id === "approval" && !state.externalUnlocked ? stationById("approval") : stages[(agent.stageIndex + 1) % stages.length];
  assignAgent(agent, next);
}

function drawFloor() {
  const grad = ctx.createLinearGradient(0, 0, 1280, 720);
  grad.addColorStop(0, "#0b1218");
  grad.addColorStop(0.48, "#202b33");
  grad.addColorStop(1, "#080d12");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 1280, 720);

  for (let x = 0; x < 1280; x += 24) {
    drawRect(x, 0, 1, 720, x % 96 === 0 ? "rgba(134, 239, 172, 0.08)" : "rgba(201, 225, 232, 0.045)");
  }
  for (let y = 0; y < 720; y += 24) {
    drawRect(0, y, 1280, 1, y % 96 === 0 ? "rgba(34, 212, 245, 0.08)" : "rgba(201, 225, 232, 0.045)");
  }

  drawRect(34, 28, 1212, 664, "#0d151c");
  strokeRect(44, 38, 1192, 644, "#72808d", 12);
  strokeRect(56, 50, 1168, 620, "#1b252d", 6);

  drawPipelineLines();
  drawPixelPanel(548, 628, 170, 48, "#15100c", "#8f6d22");
  drawText(sourceRepo.playbook.toUpperCase(), 633, 620, "#ffd15c", 13, "center");
}

function drawPipelineLines() {
  ctx.strokeStyle = "rgba(2, 5, 7, 0.72)";
  ctx.lineWidth = 12;
  ctx.setLineDash([]);
  ctx.beginPath();
  stages.forEach((stage, index) => {
    const p = centerOf(stage);
    if (index === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  });
  ctx.stroke();

  ctx.strokeStyle = "rgba(34, 212, 245, 0.62)";
  ctx.lineWidth = 4;
  ctx.setLineDash([9, 8]);
  ctx.beginPath();
  stages.forEach((stage, index) => {
    const p = centerOf(stage);
    if (index === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  });
  ctx.stroke();
  ctx.setLineDash([]);

  stages.forEach((stage, index) => {
    const p = centerOf(stage);
    drawRect(p.x - 6, p.y - 6, 12, 12, index % 2 ? "#ffd15c" : "#22d4f5");
    strokeRect(p.x - 8, p.y - 8, 16, 16, "#020507", 2);
  });
}

function drawRoom(stage) {
  drawPixelPanel(stage.x, stage.y, stage.w, stage.h, "#101a20", "#69717a");
  drawRect(stage.x + 8, stage.y + 8, stage.w - 16, 12, "rgba(255, 255, 255, 0.045)");
  strokeRect(stage.x + 10, stage.y + 10, stage.w - 20, stage.h - 20, stage.color, 2);

  const labelW = Math.min(stage.w - 16, 178);
  drawPixelPanel(stage.x + stage.w / 2 - labelW / 2, stage.y - 31, labelW, 46, "#071219", stage.color);
  drawText(stage.label, stage.x + stage.w / 2, stage.y - 10, stage.color, 12, "center");
  drawText(stage.sub, stage.x + stage.w / 2, stage.y + 8, "#d9edf4", 10, "center");

  for (let i = 0; i < 4; i += 1) {
    const px = stage.x + 22 + (i % 2) * 54;
    const py = stage.y + 38 + Math.floor(i / 2) * 38;
    drawPixelPanel(px, py, 40, 25, "#061017", "#203844");
    drawRect(px + 5, py + 5, 28, 4, stage.color);
    drawRect(px + 5, py + 14, 12 + ((state.tick + i * 9) % 18), 3, stage.color);
  }

  drawRect(stage.x + stage.w - 22, stage.y + 26, 8, 8, stage.color);
  drawRect(stage.x + stage.w - 34, stage.y + 26, 8, 8, "rgba(217, 237, 244, 0.32)");
  drawText(stage.artifact.replace("p1_", ""), stage.x + stage.w / 2, stage.y + stage.h - 16, "#8fa8b4", 10, "center");
}

function drawHubWall() {
  drawPixelPanel(470, 210, 340, 54, "#061017", "#22d4f5");
  drawText("TASKFORCE HUB REGISTRY", 640, 232, "#22d4f5", 14, "center");
  drawText("workers 17 | tools 6 | evals 2 | failures explicit", 640, 252, "#d9edf4", 11, "center");

  drawPixelPanel(1038, 430, 186, 70, "#210f10", "#ff615a");
  drawText("INCIDENT BRIEFS", 1131, 456, "#ff615a", 13, "center");
  drawText("no fake fallback", 1131, 478, "#ffd15c", 11, "center");
}

function drawDesk(x, y, color = "#22d4f5") {
  drawRect(x - 35, y + 17, 70, 8, "rgba(0,0,0,0.35)");
  drawRect(x - 31, y - 14, 62, 28, "#b9aa8f");
  drawRect(x - 26, y - 9, 52, 18, "#766b5e");
  drawRect(x - 18, y - 33, 36, 22, "#061017");
  strokeRect(x - 18, y - 33, 36, 22, "#203844", 2);
  drawRect(x - 13, y - 27, 26, 4, color);
  drawRect(x - 13, y - 19, 20, 3, color);
  drawRect(x - 42, y - 3, 8, 17, "#d8c8aa");
  drawRect(x + 34, y - 3, 8, 17, "#d8c8aa");
}

function drawAgent(agent) {
  const bob = Math.sin(agent.phase) * (agent.state === "moving" ? 3 : 1);
  const x = agent.x;
  const y = agent.y + bob;
  const selected = state.selectedAgent === agent;

  if (selected) {
    strokeRect(x - 20, y - 47, 40, 56, "#020507", 4);
    strokeRect(x - 18, y - 45, 36, 52, "#ffd15c", 2);
  }

  drawRect(x - 16, y + 13, 32, 6, "rgba(0,0,0,0.34)");
  drawRect(x - 10, y - 25, 20, 23, agent.color);
  drawRect(x - 10, y - 25, 20, 5, "rgba(255,255,255,0.16)");
  drawRect(x + 6, y - 25, 4, 23, "rgba(0,0,0,0.22)");
  drawRect(x - 9, y - 42, 18, 16, "#f0b57a");
  drawRect(x - 10, y - 45, 20, 8, agent.hair);
  drawRect(x - 5, y - 36, 3, 3, "#111");
  drawRect(x + 4, y - 36, 3, 3, "#111");
  drawRect(x - 12, y - 2, 8, 17, "#1f2937");
  drawRect(x + 4, y - 2, 8, 17, "#1f2937");
  drawRect(x - 15, y - 19, 6, 15, "#f0b57a");
  drawRect(x + 9, y - 19, 6, 15, "#f0b57a");

  if (agent.state === "working") {
    drawPixelPanel(x - 25, y - 61, 50, 17, "#071219", agent.station.color);
    drawRect(x - 19, y - 54, 38, 4, "#0c1f28");
    drawRect(x - 19, y - 54, Math.max(3, agent.progress * 0.38), 4, agent.station.color);
  }

  drawText(agent.id.replace("p1-", "").replace("-writer", ""), x, y + 29, selected ? "#ffd15c" : "#9bb5bf", 9, "center");
}

function drawFlash() {
  if (!state.flash) return;
  const alpha = Math.max(0, 1 - state.flash.age / 90);
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = "#ffd15c";
  ctx.lineWidth = 3;
  ctx.strokeRect(state.flash.x - 24 - state.flash.age * 0.15, state.flash.y - 24 - state.flash.age * 0.15, 48 + state.flash.age * 0.3, 48 + state.flash.age * 0.3);
  drawText(state.flash.text, state.flash.x, state.flash.y - 34 - state.flash.age * 0.1, "#ffd15c", 12, "center");
  ctx.globalAlpha = 1;
}

function renderCanvas() {
  drawFloor();
  allRooms.forEach(drawRoom);
  drawHubWall();
  allRooms.forEach((stage) => {
    const c = centerOf(stage);
    drawDesk(c.x, c.y + 18, stage.color);
  });
  agents.slice().sort((a, b) => a.y - b.y).forEach(drawAgent);
  drawFlash();
}

function updateAgents() {
  agents.forEach((agent) => {
    agent.phase += 0.12 * state.speed;
    if (agent.wait > 0) {
      agent.wait -= state.speed;
      return;
    }
    if (agent.state === "queued") {
      assignAgent(agent, agent.station);
      return;
    }
    if (agent.state === "moving") {
      const dx = agent.tx - agent.x;
      const dy = agent.ty - agent.y;
      const dist = Math.hypot(dx, dy);
      if (dist < 2) {
        agent.state = "working";
      } else {
        const step = Math.min(dist, 1.25 + state.speed * 0.65);
        agent.x += (dx / dist) * step;
        agent.y += (dy / dist) * step;
      }
    } else {
      const heavy = ["triage", "intel", "gateway", "drafts"].includes(agent.station.id) ? 0.2 : 0.34;
      agent.progress += heavy * state.speed;
      if (agent.progress >= 100) completeStage(agent);
      if (agent.station.id === "approval" && agent.progress > 55) state.approvalWaiting = true;
    }
  });

  if (state.flash) {
    state.flash.age += state.speed;
    if (state.flash.age > 90) state.flash = null;
  }
}

function renderPanels() {
  const agent = state.selectedAgent;
  const stage = agent.station;
  const order = `WO-P1-${String(agent.orderNo).padStart(3, "0")}`;
  ui.selectedLabel.textContent = `Selected: ${agent.id}`;
  ui.selectedTitle.textContent = `Selected: ${order}`;
  ui.agentName.textContent = agent.id;
  ui.agentDesk.textContent = `Stage: ${stage.label}`;
  ui.agentTask.textContent = `${stage.taskType} -> ${stage.artifact}`;
  ui.workOrderId.textContent = order;
  ui.workOrderText.textContent = `${stage.worker} / ${stage.taskType}`;
  ui.workProgress.style.width = `${Math.round(agent.progress)}%`;
  ui.artifactName.textContent = stage.artifact;
  ui.artifactSize.textContent = `${stage.output}`;
  ui.evalRate.textContent = `${Math.min(99, Math.round(state.passScore + agent.progress * 0.04))}%`;
  ui.evalChecks.textContent = stage.id === "quality" ? "5 / 5" : `${Math.min(6, 2 + Math.floor(agent.progress / 22))} / 6`;
  ui.selectedState.textContent = agent.state === "moving" ? "Moving" : agent.state === "queued" ? "Queued" : stage.id === "approval" && state.approvalWaiting ? "Waiting Approval" : "In Progress";
  ui.incidentText.textContent = stage.tools.length
    ? `Allowed tools: ${stage.tools.join(", ")}`
    : `No external tools. Input: ${stage.input}`;
  ui.completedCount.textContent = state.completed;
  ui.pendingCount.textContent = state.pending;
  ui.failedCount.textContent = state.failed;
  ui.passRate.textContent = `${Math.round(state.passScore)}%`;
}

function renderRuns() {
  const runs = [
    ["RUN-P1-2026-06-21-0042", "full_pipeline", "EXECUTION", "now", "active"],
    ["source: exa", "collect_source_batch", "RUNNING", "L3", "pending"],
    ["source: apify_funding", "collect_source_batch", "RUNNING", "L3", "pending"],
    ["p1-outreach-quality", "required eval", "READY", "gate", "complete"],
    ["google_sheets_write", "approval required", "WAITING", "policy", "pending"],
    ["outreach_send", "approval required", "BLOCKED", "policy", "failed"]
  ];
  ui.runList.innerHTML = runs.map(([id, playbook, status, time, kind]) => `
    <div class="run-item ${kind === "active" ? "active" : kind}">
      <i class="run-dot"></i>
      <div><strong>${id}</strong><span>${playbook}</span></div>
      <em>${time}<br />${status}</em>
    </div>
  `).join("");
}

function renderEvents() {
  const visible = events.length ? events : [
    { time: "P1", title: "Playbook", text: sourceRepo.strategy, kind: "complete" },
    { time: "L2", title: "Supervisor", text: "max 2 tasks per turn", kind: "pending" },
    { time: "Hub", title: "Registry", text: "workers/tools/evals loaded", kind: "complete" },
    { time: "Policy", title: "External Actions", text: "writes gated", kind: "failed" }
  ];
  ui.eventRow.innerHTML = visible.map((event) => `
    <div class="event-card ${event.kind}">
      <strong>${event.time}</strong>
      <span>${event.title}</span>
      <span>${event.text}</span>
    </div>
  `).join("");
}

function updateClock() {
  const now = new Date();
  ui.opsClock.textContent = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).format(now);
}

function tick() {
  if (!state.paused) {
    state.tick += state.speed;
    updateAgents();
  }
  renderCanvas();
  renderPanels();
  requestAnimationFrame(tick);
}

function canvasPoint(event) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) / rect.width) * canvas.width,
    y: ((event.clientY - rect.top) / rect.height) * canvas.height
  };
}

canvas.addEventListener("click", (event) => {
  const point = canvasPoint(event);
  const clickedAgent = agents.find((agent) => Math.hypot(agent.x - point.x, agent.y - point.y) < 34);
  if (clickedAgent) {
    state.selectedAgent = clickedAgent;
    return;
  }
  const clickedStage = allRooms.find((stage) => point.x >= stage.x && point.x <= stage.x + stage.w && point.y >= stage.y && point.y <= stage.y + stage.h);
  if (clickedStage) assignAgent(state.selectedAgent, clickedStage);
});

ui.pauseButton.addEventListener("click", () => {
  state.paused = !state.paused;
  ui.pauseButton.textContent = state.paused ? "Run" : "Pause";
  ui.pauseButton.classList.toggle("active", !state.paused);
});

ui.speedButton.addEventListener("click", () => {
  state.speed = state.speed === 1 ? 2 : state.speed === 2 ? 4 : 1;
  ui.speedButton.textContent = `${state.speed}x`;
});

ui.assignButton.addEventListener("click", () => {
  const agent = state.selectedAgent;
  const nextStage = stages[(agent.stageIndex + 1) % stages.length];
  assignAgent(agent, nextStage);
});

document.querySelector("#newIncidentButton").addEventListener("click", () => {
  state.failed += 1;
  addEvent("failed", "Incident Brief", "missing credential fails explicitly");
  agents.filter((agent) => ["source", "external"].includes(agent.station.id)).forEach((agent) => assignAgent(agent, stationById("source")));
});

window.addEventListener("keydown", (event) => {
  if (event.code === "Space") {
    event.preventDefault();
    ui.pauseButton.click();
  }
  const number = Number(event.key);
  if (number >= 1 && number <= Math.min(agents.length, 9)) {
    state.selectedAgent = agents[number - 1];
    assignAgent(state.selectedAgent);
  }
});

renderRuns();
renderEvents();
updateClock();
window.setInterval(updateClock, 1000);
agents.forEach((agent, index) => {
  window.setTimeout(() => assignAgent(agent, stages[index]), index * 220);
});
tick();
