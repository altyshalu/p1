#!/usr/bin/env node
const { spawnSync } = require("child_process");

const keyPath = process.env.SSH_KEY || `${process.env.HOME}/.ssh/hermes_desktop_wanderer`;
const remote = process.env.SSH_TARGET || "nik1t7n@wanderer";
const restoreBoard = process.env.KANBAN_RESTORE_BOARD || "cognee-external";

function shellQuote(value) {
  return `'${String(value).replace(/'/g, `'\"'\"'`)}'`;
}

function buildPatchedDesktopRemoteCmd(args, extraShell = "") {
  const candidates = [
    "$HOME/hermes-agent/.venv/bin/hermes",
    "$HOME/.hermes/hermes-agent/.venv/bin/hermes",
    "/opt/hermes/hermes-agent/.venv/bin/hermes",
  ];
  const quotedArgs = args.map((arg) => shellQuote(arg)).join(" ");
  const probe = candidates
    .map((path) => `[ -x ${path} ] && exec ${path} ${quotedArgs}${extraShell}`)
    .join("; ");
  const script = `${probe}; command -v hermes >/dev/null && exec hermes ${quotedArgs}${extraShell}; echo "ERR: hermes CLI not found on remote PATH or in any known venv location" >&2; exit 1`;
  return `bash -lc ${shellQuote(script)}`;
}

function runHermes(args, label) {
  const result = spawnSync(
    "ssh",
    ["-i", keyPath, "-o", "BatchMode=yes", remote, buildPatchedDesktopRemoteCmd(args)],
    { encoding: "utf8" },
  );
  if (result.status !== 0) {
    throw new Error(
      `${label} failed with ${result.status}\nSTDOUT:\n${result.stdout}\nSTDERR:\n${result.stderr}`,
    );
  }
  return result.stdout.trim();
}

function parseJson(output, label) {
  try {
    return JSON.parse(output);
  } catch {
    throw new Error(`${label} did not return JSON: ${output}`);
  }
}

const cleanupTasks = [];
let cleanupBoard = null;

try {
  console.log(runHermes(["kanban", "boards", "show"], "current board").split("\n")[0]);
  parseJson(runHermes(["kanban", "list", "--json"], "list tasks"), "list tasks");

  const task = parseJson(
    runHermes(
      [
        "kanban",
        "create",
        "UI smoke title with spaces",
        "--body",
        "Body has spaces, apostrophe ' and a newline\nsecond line",
        "--priority",
        "0",
        "--tenant",
        "ui smoke tenant",
        "--workspace",
        "dir:/tmp/hermes desktop smoke",
        "--json",
      ],
      "create rich task",
    ),
    "create rich task",
  );
  const id = task.id || task.task?.id;
  if (!id) throw new Error(`create returned no id: ${JSON.stringify(task)}`);
  cleanupTasks.push(id);
  console.log(`created ${id}`);

  parseJson(runHermes(["kanban", "show", id, "--json"], "show task"), "show task");
  runHermes(["kanban", "comment", id, "UI comment with spaces, apostrophe ' and newline\nok"], "comment task");
  runHermes(["kanban", "assign", id, "none"], "assign none");
  runHermes(["kanban", "block", id, "blocked because UI smoke has spaces"], "block task");
  runHermes(["kanban", "unblock", id], "unblock task");
  runHermes(["kanban", "reclaim", id, "--reason", "reclaim reason with spaces and quote '"], "reclaim task");
  runHermes(["kanban", "complete", id, "--result", "complete result with spaces and newline\nok"], "complete task");
  runHermes(["kanban", "archive", id], "archive task");
  runHermes(["kanban", "archive", "--rm", id], "remove task");
  cleanupTasks.pop();

  cleanupBoard = `desktop-smoke-${Date.now()}`;
  runHermes(["kanban", "boards", "create", cleanupBoard, "--name", "Desktop Smoke Board With Spaces"], "create board");
  runHermes(["kanban", "boards", "switch", cleanupBoard], "switch board");
  const boardTask = parseJson(
    runHermes(["kanban", "create", "Board switched task with spaces", "--json"], "create board task"),
    "create board task",
  );
  const boardTaskId = boardTask.id || boardTask.task?.id;
  if (!boardTaskId) throw new Error(`board task returned no id: ${JSON.stringify(boardTask)}`);
  runHermes(["kanban", "archive", "--rm", boardTaskId], "remove board task");
  runHermes(["kanban", "boards", "switch", restoreBoard], "restore board");
  runHermes(["kanban", "boards", "rm", cleanupBoard, "--delete"], "delete board");
  console.log(`deleted-board ${cleanupBoard}`);
  cleanupBoard = null;

  console.log("OK");
} finally {
  for (const id of cleanupTasks.reverse()) {
    try {
      runHermes(["kanban", "archive", id], `archive cleanup task ${id}`);
      runHermes(["kanban", "archive", "--rm", id], `remove cleanup task ${id}`);
    } catch (error) {
      console.error(error.message);
    }
  }
  try {
    runHermes(["kanban", "boards", "switch", restoreBoard], "restore board cleanup");
  } catch (error) {
    console.error(error.message);
  }
  if (cleanupBoard) {
    try {
      runHermes(["kanban", "boards", "rm", cleanupBoard, "--delete"], `cleanup board ${cleanupBoard}`);
    } catch (error) {
      console.error(error.message);
    }
  }
}
