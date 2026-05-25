const state = {
  runId: null,
  eventSource: null,
};

const $ = (id) => document.getElementById(id);

function setError(message) {
  $("form-error").textContent = message || "";
}

function lines(value) {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function csv(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

function renderRun(run) {
  state.runId = run.id;
  $("run-id").textContent = run.id ? run.id.slice(0, 8) : "no run";
  $("run-status").textContent = run.status || "idle";
  $("run-status").className = `status-pill ${run.status || ""}`;
  $("event-count").textContent = `${run.events?.length || 0} events`;
  $("task-count").textContent = `${run.tasks?.length || 0} tasks`;
  $("artifact-count").textContent = `${run.artifacts?.length || 0} artifacts`;
  $("trace").innerHTML = (run.events || []).map(renderEvent).join("");
  $("tasks").innerHTML = run.tasks?.length ? run.tasks.map(renderTask).join("") : "No worker contracts yet.";
  $("tasks").className = run.tasks?.length ? "cards" : "cards empty";
  $("artifacts").innerHTML = run.artifacts?.length ? run.artifacts.map(renderArtifact).join("") : "No artifacts yet.";
  $("artifacts").className = run.artifacts?.length ? "cards" : "cards empty";
}

function renderEvent(event) {
  const time = event.created_at ? new Date(event.created_at).toLocaleTimeString() : "--:--:--";
  return `<li><time>${escapeHtml(time)} · ${escapeHtml(event.event_type)}</time><pre>${escapeHtml(JSON.stringify(event.payload || {}, null, 2))}</pre></li>`;
}

function renderTask(task) {
  return `<div class="card"><strong>${escapeHtml(task.task_type)} · ${escapeHtml(task.status)}</strong><div class="meta">${escapeHtml(task.worker_profile)}</div><p>${escapeHtml(task.goal || "")}</p></div>`;
}

function renderArtifact(artifact) {
  return `<div class="card"><strong>${escapeHtml(artifact.artifact_type)}</strong><div class="meta">${escapeHtml(artifact.task_id || "run artifact")}</div><pre>${escapeHtml(JSON.stringify(artifact.payload || {}, null, 2))}</pre></div>`;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[char]);
}

async function loadRun() {
  if (!state.runId) return;
  renderRun(await request(`/runs/${state.runId}`));
}

function connectEvents(runId) {
  if (state.eventSource) {
    state.eventSource.close();
  }
  state.eventSource = new EventSource(`/runs/${runId}/events/stream`);
  state.eventSource.addEventListener("run_event", loadRun);
  state.eventSource.addEventListener("run_status", loadRun);
  state.eventSource.onerror = () => {
    state.eventSource.close();
  };
}

$("start-run").addEventListener("click", async () => {
  setError("");
  try {
    const signals = lines($("signals").value);
    const channels = csv($("channels").value);
    if (!signals.length || !channels.length) {
      throw new Error("Signals and channels are required. Synthetic data is not allowed.");
    }
    const run = await request("/runs", {
      method: "POST",
      body: JSON.stringify({
        process_key: $("process-key").value.trim(),
        goal: $("goal").value.trim(),
        inputs: { signals, channels },
        require_human_approval: $("approval").checked,
      }),
    });
    state.runId = run.id;
    renderRun({ ...run, events: [], tasks: [], artifacts: [] });
    connectEvents(run.id);
    await loadRun();
  } catch (error) {
    setError(error.message);
  }
});

$("send-message").addEventListener("click", async () => {
  setError("");
  try {
    if (!state.runId) throw new Error("Start or load a run first.");
    const message = $("message").value.trim();
    if (!message) throw new Error("Message is required.");
    renderRun(await request(`/runs/${state.runId}/messages`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }));
    $("message").value = "";
  } catch (error) {
    setError(error.message);
  }
});

$("refresh").addEventListener("click", () => loadRun().catch((error) => setError(error.message)));
$("pause-run").addEventListener("click", () => control("pause"));
$("resume-run").addEventListener("click", () => control("resume"));
$("stop-run").addEventListener("click", () => control("stop"));

async function control(action) {
  setError("");
  try {
    if (!state.runId) throw new Error("Start or load a run first.");
    renderRun(await request(`/runs/${state.runId}/control`, {
      method: "POST",
      body: JSON.stringify({ action, payload: {} }),
    }));
  } catch (error) {
    setError(error.message);
  }
}
