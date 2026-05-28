# ABRT Cross-Process Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the L2/L3 self-improvement runtime to the point where we can safely test the same loop on a second ABRT process, not only on `build-in-public-trend-radar`.

**Architecture:** Keep `build-in-public-trend-radar` as the proven dogfood workflow, but extract the readiness, proof, review, and regression mechanics so they work for any registered Playbook with real workers, real tools, real evals, and real stored run evidence. Do not add mocks, fallback success paths, synthetic provider data, demo commands, or hidden alternate execution paths.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy/Postgres, Alembic, Docker Compose, Hermes/DeepSeek, AgentMemory/Qdrant, YAML-backed Taskforce Hub seed data, `uv`, pytest, real API proof scripts.

---

## Owner

This plan is written for the teammate taking the next backend readiness pass.

Recommended branch:

```bash
git switch main
git pull --ff-only origin main
git switch -c feat/abrt-cross-process-readiness
```

Do not touch `taskforce-landing/`.

Commit after every coherent block using Conventional Commits, for example:

```bash
git commit -m "feat(proof): add generic playbook acceptance runner"
git commit -m "feat(runtime): add playbook readiness checks"
git commit -m "docs: add cross-process testing runbook"
```

## Current Baseline

As of `main` commit `71812540336d8caa07688663244bd76a4943218d`, the system has a proven narrow loop:

- `build-in-public-trend-radar` runs through real GitHub, arXiv, Hugging Face source collection.
- L2 creates bounded Work Orders.
- L3 executes registered workers.
- Runtime validates worker inputs, allowed tools, output schemas, eval gates, retry budgets, and external action policy.
- Failed or low-quality runs create diagnosis artifacts.
- Evidence-backed improvement proposals are stored.
- Behavior-changing proposals require approval.
- Controlled implementation worker can implement narrow approved improvements.
- Real before/after proof can mark proposals `proven`.
- Regression cases can be listed and rerun.

Known real proof from the merged work:

- Fresh clean acceptance run: `d12a1ba2-051e-415a-ad72-eb130716dbb4`
  - Status: `waiting_approval`
  - Diagnosis root cause: `none`
  - Proposals: `0`
- Regression proof run: `59378867-1eb1-4bbd-a960-43a3479ed68e`
  - Before: `failed / quality_gate_failed`
  - After: `waiting_user / none`
  - Proposal: `081bc8a6-4849-4c32-9128-73ea25062e0a`
  - Proposal status after proof: `proven`

The important limitation:

The loop is operationally proven on Trend Radar, but not yet cleanly packaged as a cross-process testing harness. Some scripts, proof assumptions, and readiness checks still assume the Trend Radar shape.

## Definition Of Done

This plan is done when a developer can take a second real ABRT process and start testing it through the runtime without inventing ad hoc commands.

Minimum success criteria:

- There is a clear checklist that tells whether a Playbook is ready for real L2/L3 execution.
- There is a generic real acceptance runner for any Playbook, not only Trend Radar.
- There is a generic system review command/report that can be scoped by Playbook.
- Regression cases can be created, listed, and rerun without Trend Radar-only assumptions.
- Diagnosis and improvement proposal creation work for non-Trend Playbooks.
- Proof scripts fail explicitly when a Playbook lacks real workers, tools, evals, credentials, required inputs, or services.
- No new fallback, mock, fake, demo, synthetic data, or silent degraded path is introduced.
- `build-in-public-trend-radar` still passes its existing real acceptance and regression proof after the changes.
- A second Playbook can be dry-readiness-checked, then real-run-tested once real inputs and credentials exist.

Important distinction:

- Unit tests may use small in-memory fixtures to check pure logic.
- Readiness proof for this plan must use real API, real Postgres, real Hub sync, real workers, real evals, and real stored run evidence.
- If a second ABRT process depends on an external provider or credential that is missing, the real test must fail explicitly with the missing dependency. Do not fake it.

---

## Files And Responsibilities

### Existing Files To Understand Before Coding

- `src/l2l3_protocol/runtime/process_runtime.py`
  - Owns execution loop, Work Order creation, worker execution, eval recording, failure context, post-run diagnosis.
- `src/l2l3_protocol/runtime/diagnostics.py`
  - Turns stored run state into diagnosis artifacts and improvement proposals.
- `src/l2l3_protocol/runtime/self_improvement.py`
  - Builds failure learnings, recent reviews, proof specs, regression cases, system learning reports.
- `src/l2l3_protocol/workers/proposal_implementation_worker.py`
  - Implements approved proposals through controlled handlers only.
- `src/l2l3_protocol/api/main.py`
  - Exposes runs, Hub, proposals, system reviews, learning reports, regression cases.
- `src/l2l3_protocol/db/store.py`
  - Stores runs, tasks, artifacts, evals, events, proposals, learnings, reviews, regression cases.
- `src/l2l3_protocol/live/cli.py`
  - CLI entrypoint for live workflows.
- `scripts/real-trend-radar-acceptance.py`
  - Current Trend Radar-specific acceptance proof.
- `scripts/real-before-after-proof.py`
  - Current real before/after proof helper.
- `scripts/real-regression-cases.py`
  - Current real regression case list/rerun helper.
- `registries/playbooks/build-in-public-trend-radar/playbook.yaml`
  - Proven Playbook shape.
- `registries/worker-profiles/*.yaml`
  - Worker profile contracts.
- `registries/tools/*.yaml`
  - Tool contracts.
- `registries/evals/*.yaml`
  - Eval specs.
- `registries/failure-patterns/*.yaml`
  - Known failure patterns used in incident briefs.

### New Files This Plan Should Add

- `scripts/real-playbook-acceptance.py`
  - Generic real acceptance runner for any registered Playbook.
- `scripts/real-playbook-readiness.py`
  - Generic Playbook readiness checker against the live API/Hub.
- `docs/cross-process-testing.md`
  - Human runbook for testing any new ABRT process through the L2/L3 runtime.
- `tests/test_real_playbook_scripts.py`
  - Logic tests for the new scripts. These are not release proof.

### Existing Files This Plan May Modify

- `src/l2l3_protocol/api/main.py`
  - Add readiness/report endpoints only if CLI scripts cannot get enough data from existing endpoints.
- `src/l2l3_protocol/runtime/self_improvement.py`
  - Make review/report/proof metadata less Trend-specific where needed.
- `src/l2l3_protocol/runtime/diagnostics.py`
  - Keep diagnosis process-agnostic; fix any Trend-only target naming that leaks into generic failures.
- `src/l2l3_protocol/db/store.py`
  - Add store helpers only if existing API cannot retrieve needed real state.
- `src/l2l3_protocol/live/cli.py`
  - Optional: expose generic readiness/review commands through `l2l3-live`.
- `README.md`
  - Add a short pointer to the new cross-process testing runbook.

Do not restructure the repo.

---

## Non-Negotiables

- No mocks, fakes, fallback success paths, demo commands, synthetic providers, embedded fake example runs, or silent degraded behavior.
- Do not add runtime fallback from database Hub to YAML.
- YAML sync may remain an explicit bootstrap command.
- Do not auto-apply behavior-changing proposals.
- Do not auto-merge, auto-push, auto-deploy, or mutate registry/code without explicit approval path.
- Do not mark a Playbook ready if it lacks real registered workers/tools/evals.
- Do not call a unit test “proof”.
- Do not broaden the implementation worker into arbitrary code editing.
- Keep UI out of scope.

---

## Phase 0: Branch, Baseline, And Safety

### Task 0.1: Create The Branch

- [ ] **Step 1: Start from fresh main**

```bash
git switch main
git pull --ff-only origin main
git status --short --branch
```

Expected:

```text
## main...origin/main
```

It is acceptable if `taskforce-landing/` appears as untracked. Do not add or modify it.

- [ ] **Step 2: Create the work branch**

```bash
git switch -c feat/abrt-cross-process-readiness
```

Expected:

```text
Switched to a new branch 'feat/abrt-cross-process-readiness'
```

### Task 0.2: Verify Current Baseline

- [ ] **Step 1: Run the fast test suite**

```bash
uv run pytest
```

Expected:

```text
80 passed
```

If the exact count changes because another teammate merged tests, use the current full passing suite as the baseline. Do not continue with a red baseline.

- [ ] **Step 2: Start real infrastructure**

```bash
docker compose up -d postgres qdrant agentmemory
```

Expected:

```text
Container abrt-postgres-1    Running
Container abrt-qdrant-1      Running
Container abrt-agentmemory-1 Running
```

- [ ] **Step 3: Run migrations**

```bash
set -a; source .env; set +a; uv run alembic upgrade head
```

Expected:

```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
```

- [ ] **Step 4: Start the API on a clean port**

Use `8093` if available:

```bash
set -a; source .env; set +a; uv run uvicorn l2l3_protocol.api.main:app --host 127.0.0.1 --port 8093
```

In another terminal:

```bash
curl -sS http://127.0.0.1:8093/health
curl -sS -X POST http://127.0.0.1:8093/hub/sync/yaml
```

Expected:

```json
{"status":"ok","service":"l2l3-protocol"}
{"synced":29}
```

If `synced` changes because registry entries changed, it must still be greater than zero.

- [ ] **Step 5: Re-run current real Trend Radar acceptance**

```bash
uv run python scripts/real-trend-radar-acceptance.py \
  --api-url http://127.0.0.1:8093 \
  --query "agent runtime eval memory" \
  --channel x \
  --max-results 2 \
  --timeout-seconds 900
```

Expected:

- Terminal run status is `waiting_approval`, `waiting_user`, or `completed`.
- Diagnosis exists.
- If diagnosis root cause is not `none`, it has real evidence and at least one proposal.
- If root cause is `none`, proposals may be `0`.

This step proves the branch starts from a real working system.

---

## Phase 1: Inventory Trend-Specific Coupling

Purpose: before generalizing anything, find exactly where current proof/reporting assumes Trend Radar.

### Task 1.1: Create A Coupling Inventory

**Files:**

- Create: `docs/plans/2026-05-28-cross-process-coupling-inventory.md`

- [ ] **Step 1: Search for hardcoded Trend Radar references**

```bash
rg -n "build-in-public-trend-radar|trend-radar|trend-|claim-grounding|draft-quality|huggingface|github|arxiv" \
  scripts src tests docs registries
```

- [ ] **Step 2: Create the inventory document**

Write the file with this exact structure:

```markdown
# Cross-Process Coupling Inventory

## Must Stay Trend-Specific

- `scripts/real-trend-radar-acceptance.py`: dedicated dogfood acceptance runner for the current proven process.
- `registries/playbooks/build-in-public-trend-radar/playbook.yaml`: the proven Playbook.
- `registries/worker-profiles/trend-*.yaml`: Trend Radar worker contracts.
- `registries/evals/trend-*.yaml`: Trend Radar eval contracts.

## Must Become Generic Before Testing Other Processes

- `scripts/real-before-after-proof.py`: verify that it recreates comparable runs from persisted baseline run state, not from Trend Radar-specific fields.
- `scripts/real-regression-cases.py`: verify that it reruns cases by proposal/baseline IDs, not by Trend Radar-specific query/provider/channel assumptions.
- `src/l2l3_protocol/runtime/self_improvement.py`: verify proof specs and regression cases work for any `playbook_key`.
- `src/l2l3_protocol/runtime/diagnostics.py`: verify target components and failure signatures are derived from actual workers/evals, not from Trend Radar names.

## Already Generic Enough

- `src/l2l3_protocol/runtime/process_runtime.py`: run execution, Work Order validation, eval recording, and post-run diagnosis are Playbook-driven.
- `src/l2l3_protocol/api/main.py`: run, Hub, proposal, learning, review, and regression endpoints are not inherently Trend Radar-specific.
- `src/l2l3_protocol/db/store.py`: persisted runs, tasks, artifacts, evals, events, proposals, learnings, reviews, and regression cases already include `playbook_key` or run IDs.

## Open Decisions

- Candidate process for first cross-process pilot: use `vc-research-pilot` if the real Playbook and inputs exist; otherwise run readiness preflight against that key and stop on explicit missing dependencies.
- UI scope: keep UI out of this branch; ship CLI/scripts/docs only.
- New process creation: do not create a placeholder Playbook in this branch unless the owner separately provides real process requirements, real workers, real tools, real evals, and real inputs.
```

Adjust the inventory with real findings from the search before committing it.

- [ ] **Step 3: Commit the inventory**

```bash
git add docs/plans/2026-05-28-cross-process-coupling-inventory.md
git commit -m "docs: inventory cross-process runtime coupling"
```

Success criteria:

- The inventory clearly separates dogfood-specific code from runtime infrastructure.
- No generic proof path is secretly dependent on Trend Radar fields.

---

## Phase 2: Add A Generic Playbook Readiness Checker

Purpose: before running another ABRT process, we need a command that says whether a Playbook has enough real registry support to be tested.

### Task 2.1: Add `scripts/real-playbook-readiness.py`

**Files:**

- Create: `scripts/real-playbook-readiness.py`
- Create/Modify: `tests/test_real_playbook_scripts.py`

The readiness checker must use the live API and database-backed Hub. It must not read YAML directly except through explicit `/hub/sync/yaml`.

Minimum command:

```bash
uv run python scripts/real-playbook-readiness.py \
  --api-url http://127.0.0.1:8093 \
  --playbook-key build-in-public-trend-radar
```

Expected successful output shape:

```json
{
  "playbook_key": "build-in-public-trend-radar",
  "ready": true,
  "missing": [],
  "workers": {
    "required": ["..."],
    "registered": ["..."],
    "missing": []
  },
  "tools": {
    "required": ["..."],
    "registered": ["..."],
    "missing": []
  },
  "evals": {
    "required": ["..."],
    "registered": ["..."],
    "missing": []
  },
  "required_inputs": ["query", "providers", "channels", "max_results"],
  "approval_required": true,
  "notes": []
}
```

If a Playbook is not ready, exit non-zero and print exact missing dependencies.

- [ ] **Step 1: Inspect the current Hub API payloads**

Run:

```bash
curl -sS http://127.0.0.1:8093/hub/playbook/build-in-public-trend-radar | jq .
curl -sS http://127.0.0.1:8093/hub/worker | jq '.[0]'
curl -sS http://127.0.0.1:8093/hub/tool | jq '.[0]'
curl -sS http://127.0.0.1:8093/hub/eval | jq '.[0]'
```

Use the actual payload shape. Do not guess field names.

- [ ] **Step 2: Implement live API helper functions**

In `scripts/real-playbook-readiness.py`, add:

```python
from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None, timeout: int = 60) -> dict[str, Any] | list[Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=data, headers={"content-type": "application/json"} if payload is not None else {}, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"real API request failed: {method} {url} -> {exc.code}: {body}") from exc
```

- [ ] **Step 3: Implement readiness extraction**

The script must:

- call `/health`,
- call `/hub/sync/yaml` unless `--skip-sync` is passed,
- fetch the Playbook through `/hub/playbook/{key}`,
- fetch registered workers/tools/evals,
- derive required worker profiles from the Playbook allowed workers and step definitions,
- derive required tools from Playbook allowed tools and worker profile allowed tools,
- derive required evals from worker profile grader specs and Playbook completion/eval references,
- list missing dependencies explicitly.

If the Playbook payload shape makes one of these impossible, do not silently ignore it. Add the missing API/store method in Task 2.2.

- [ ] **Step 4: Add tests for pure extraction logic**

In `tests/test_real_playbook_scripts.py`, import the script with `importlib.util.spec_from_file_location`, like `tests/test_real_proof_scripts.py`.

Add pure tests for:

- ready Playbook returns `ready: true`,
- missing worker returns `ready: false`,
- missing tool returns `ready: false`,
- missing eval returns `ready: false`,
- missing required input metadata is reported in `notes` instead of silently ignored.

These tests may use small dict fixtures because they are checking extraction logic only. They do not count as real proof.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_real_playbook_scripts.py -v
uv run pytest
```

Expected:

- New tests pass.
- Full suite passes.

- [ ] **Step 6: Run the real readiness check**

```bash
uv run python scripts/real-playbook-readiness.py \
  --api-url http://127.0.0.1:8093 \
  --playbook-key build-in-public-trend-radar
```

Expected:

- JSON output says `ready: true`.
- `missing` is empty.
- Exit code is `0`.

- [ ] **Step 7: Commit**

```bash
git add scripts/real-playbook-readiness.py tests/test_real_playbook_scripts.py
git commit -m "feat(proof): add generic playbook readiness checker"
```

Success criteria:

- A teammate can check whether any Playbook is runnable before spending model time.
- Missing dependencies are named exactly.
- The checker fails explicitly when dependencies are missing.

### Task 2.2: Add API Support Only If Needed

**Files:**

- Modify: `src/l2l3_protocol/api/main.py`
- Modify: `src/l2l3_protocol/db/store.py`
- Modify: `tests/test_api_surface.py`

Only do this task if the current Hub endpoints do not expose enough data for Task 2.1.

- [ ] **Step 1: Add a read-only readiness endpoint**

Preferred endpoint:

```text
GET /hub/playbook/{key}/readiness
```

The endpoint must not mutate state.

Response shape:

```json
{
  "playbook_key": "build-in-public-trend-radar",
  "ready": true,
  "missing": [],
  "workers": {"required": [], "registered": [], "missing": []},
  "tools": {"required": [], "registered": [], "missing": []},
  "evals": {"required": [], "registered": [], "missing": []},
  "required_inputs": [],
  "approval_required": true,
  "notes": []
}
```

- [ ] **Step 2: Test endpoint with existing real Hub seed data**

Add API tests that call the endpoint after registry sync and assert:

- known Playbook is ready,
- unknown Playbook returns 404,
- missing dependency returns `ready: false` if you can construct the condition in a focused store test.

- [ ] **Step 3: Commit**

```bash
git add src/l2l3_protocol/api/main.py src/l2l3_protocol/db/store.py tests/test_api_surface.py
git commit -m "feat(api): expose playbook readiness report"
```

Success criteria:

- The readiness script can be thin and rely on API state.
- The API does not create or modify runs.

---

## Phase 3: Add A Generic Real Playbook Acceptance Runner

Purpose: `scripts/real-trend-radar-acceptance.py` proves Trend Radar. We need a generic runner that can launch any real Playbook with real inputs and inspect the same diagnosis/proposal contract.

### Task 3.1: Add `scripts/real-playbook-acceptance.py`

**Files:**

- Create: `scripts/real-playbook-acceptance.py`
- Modify: `tests/test_real_playbook_scripts.py`

Minimum command:

```bash
uv run python scripts/real-playbook-acceptance.py \
  --api-url http://127.0.0.1:8093 \
  --playbook-key build-in-public-trend-radar \
  --goal "Real generic acceptance run for cross-process readiness." \
  --inputs-json '{"query":"agent runtime eval memory","providers":["github","arxiv","huggingface"],"channels":["x"],"max_results":2}' \
  --require-human-approval true \
  --timeout-seconds 900
```

The runner must:

- call `/health`,
- sync Hub unless `--skip-sync` is passed,
- optionally call the readiness checker before creating the run,
- create `/runs`,
- poll `/runs/{id}`,
- require terminal status plus diagnosis,
- accept only `completed`, `waiting_approval`, or `waiting_user` as non-error terminal states,
- fail on `failed` unless `--allow-failure-with-proposal` is explicitly passed,
- require evidence when root cause is not `none`,
- require at least one proposal when `improvement_needed` is true,
- optionally require specific eval keys with `--require-eval-key`.

- [ ] **Step 1: Reuse the request helper from the readiness script**

If duplication is small, keep both scripts standalone. Do not create a utility package unless duplication becomes painful.

- [ ] **Step 2: Parse real inputs**

Support:

```text
--inputs-json '{"key":"value"}'
--inputs-file /absolute/or/relative/path.json
```

Rules:

- exactly one of `--inputs-json` or `--inputs-file` is required,
- parsed inputs must be a JSON object,
- empty inputs are allowed only if the Playbook declares no required inputs,
- invalid JSON exits non-zero with a useful error.

- [ ] **Step 3: Implement terminal validation**

Terminal success rule:

```python
NON_ERROR_TERMINAL = {"completed", "waiting_approval", "waiting_user"}
ERROR_TERMINAL = {"failed", "cancelled"}
```

If status is `failed`, print diagnosis and proposals, then exit non-zero unless `--allow-failure-with-proposal` is passed and at least one proposal exists.

- [ ] **Step 4: Add tests for pure validation**

Add tests for:

- `root_cause != "none"` without evidence fails,
- `improvement_needed=true` without proposals fails,
- `failed` status fails by default,
- `failed` status passes only with `--allow-failure-with-proposal` and real proposals in payload,
- missing required eval key fails,
- `waiting_approval/root_cause none` passes.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_real_playbook_scripts.py -v
uv run pytest
```

- [ ] **Step 6: Run generic acceptance against current proven Playbook**

```bash
uv run python scripts/real-playbook-acceptance.py \
  --api-url http://127.0.0.1:8093 \
  --playbook-key build-in-public-trend-radar \
  --goal "Real generic acceptance run for cross-process readiness." \
  --inputs-json '{"query":"agent runtime eval memory","providers":["github","arxiv","huggingface"],"channels":["x"],"max_results":2}' \
  --require-human-approval true \
  --require-eval-key trend-claim-grounding \
  --require-eval-key trend-draft-quality \
  --timeout-seconds 900
```

Expected:

- Run reaches `waiting_approval`, `waiting_user`, or `completed`.
- Diagnosis exists.
- Required eval keys exist in the run.
- If root cause is `none`, proposals may be `0`.
- If root cause is not `none`, evidence and proposal exist.

- [ ] **Step 7: Commit**

```bash
git add scripts/real-playbook-acceptance.py tests/test_real_playbook_scripts.py
git commit -m "feat(proof): add generic real playbook acceptance runner"
```

Success criteria:

- Trend Radar still works through the generic runner.
- The runner is ready to execute a second Playbook as soon as real inputs are provided.
- The runner does not know about GitHub, arXiv, Hugging Face, draft quality, or claim grounding except through optional command-line eval requirements.

---

## Phase 4: Make System Review And Learning Report Cross-Process

Purpose: we need a clear non-UI report for any Playbook: what happened, what broke, what the system learned, what needs approval, and what proof exists.

### Task 4.1: Add A Script For Recent Review

**Files:**

- Create: `scripts/real-system-review.py`
- Modify: `tests/test_real_playbook_scripts.py`

Minimum command:

```bash
uv run python scripts/real-system-review.py \
  --api-url http://127.0.0.1:8093 \
  --limit 20 \
  --playbook-key build-in-public-trend-radar \
  --format markdown
```

The script must call real API endpoints. Prefer existing endpoints:

- `POST /system-reviews/recent`
- `GET /system-learning-report`
- `GET /failure-learnings`
- `GET /improvement-proposals`
- `GET /regression-cases`

If an endpoint is missing or underpowered, add the smallest API change needed.

- [ ] **Step 1: Inspect current endpoint payloads**

```bash
curl -sS -X POST http://127.0.0.1:8093/system-reviews/recent \
  -H 'content-type: application/json' \
  -d '{"limit":20,"playbook_key":"build-in-public-trend-radar"}' | jq .

curl -sS http://127.0.0.1:8093/system-learning-report | jq .
curl -sS http://127.0.0.1:8093/failure-learnings | jq .
curl -sS http://127.0.0.1:8093/improvement-proposals | jq .
curl -sS http://127.0.0.1:8093/regression-cases | jq .
```

- [ ] **Step 2: Implement markdown/stdout rendering**

The report must contain:

- Playbook scope,
- runs reviewed,
- active learnings,
- resolved learnings,
- repeated failures,
- weak components,
- excess repairs,
- human interruptions,
- active proposals,
- approved proposals,
- implemented proposals,
- proven proposals,
- regression cases,
- proof commands,
- risks,
- next recommended action.

If data is empty, write that explicitly:

```text
No evidence-backed active failures found for this Playbook.
```

Do not invent recommendations when there is no evidence.

- [ ] **Step 3: Add JSON mode**

Support:

```bash
--format json
```

This prints raw structured output for later automation.

- [ ] **Step 4: Add tests for rendering**

Test pure rendering:

- empty report,
- report with one active learning,
- report with one proven proposal and regression case,
- scoped playbook label.

- [ ] **Step 5: Run real report**

```bash
uv run python scripts/real-system-review.py \
  --api-url http://127.0.0.1:8093 \
  --limit 20 \
  --playbook-key build-in-public-trend-radar \
  --format markdown
```

Expected:

- Human-readable markdown prints.
- It references real run IDs/proposal IDs when data exists.
- It does not output generic filler.

- [ ] **Step 6: Commit**

```bash
git add scripts/real-system-review.py tests/test_real_playbook_scripts.py
git commit -m "feat(reporting): add real system review script"
```

Success criteria:

- A teammate can run one command and understand what the system learned for a specific Playbook.
- This works for any Playbook key, not only Trend Radar.

### Task 4.2: Ensure Reviews Are Playbook-Scoped

**Files:**

- Modify: `src/l2l3_protocol/runtime/self_improvement.py`
- Modify: `src/l2l3_protocol/api/main.py`
- Modify: `tests/test_self_improvement_memory.py`
- Modify: `tests/test_api_surface.py`

Only do this task if Task 4.1 shows that scoping is incomplete.

- [ ] **Step 1: Verify `playbook_key` scoping in `build_recent_system_review`**

Confirm:

- `recent_runs` are filtered by `playbook_key`,
- `learnings` are filtered by `playbook_key`,
- markdown output includes the scoped Playbook.

- [ ] **Step 2: Add failing tests for cross-process isolation**

Create a test with:

- one learning for `build-in-public-trend-radar`,
- one learning for `vc-research-pilot`,
- review requested for `vc-research-pilot`,
- output includes only the VC learning.

- [ ] **Step 3: Implement the minimal scoping fix**

Do not change proposal behavior unless the test proves it is necessary.

- [ ] **Step 4: Run tests and commit**

```bash
uv run pytest tests/test_self_improvement_memory.py tests/test_api_surface.py -v
uv run pytest
git add src/l2l3_protocol/runtime/self_improvement.py src/l2l3_protocol/api/main.py tests/test_self_improvement_memory.py tests/test_api_surface.py
git commit -m "fix(reporting): scope system reviews by playbook"
```

Success criteria:

- A noisy Trend Radar failure does not pollute a second process report.
- A second process failure does not pollute the Trend Radar report.

---

## Phase 5: Make Regression Cases Process-Agnostic

Purpose: every serious error in any process should become a future real proof case.

### Task 5.1: Audit Regression Case Data Shape

**Files:**

- Modify if needed: `src/l2l3_protocol/runtime/self_improvement.py`
- Modify if needed: `scripts/real-regression-cases.py`
- Modify if needed: `tests/test_self_improvement_memory.py`
- Modify if needed: `tests/test_real_playbook_scripts.py`

- [ ] **Step 1: Inspect current regression cases**

```bash
uv run python scripts/real-regression-cases.py \
  --api-url http://127.0.0.1:8093 \
  list
```

Confirm each case contains:

- `id`,
- `proposal_id`,
- `baseline_run_id`,
- `failure_signature`,
- `target_component`,
- `comparable_run_input`,
- `proof_command`,
- `expected_absent_failure`,
- `last_after_run_id`,
- `last_proof_status`,
- `last_proof_result`.

- [ ] **Step 2: Verify no Trend Radar assumption is required**

Check `scripts/real-before-after-proof.py`.

The script may copy `playbook_key`, `l2_mode`, `goal`, `input`, and `require_human_approval` from the baseline run.

It must not require:

- Trend Radar query fields,
- providers,
- channels,
- specific eval names,
- specific worker names,
- GitHub/arXiv/Hugging Face.

- [ ] **Step 3: Add tests if assumptions exist**

Add a fake payload test where:

- baseline Playbook is `vc-research-pilot`,
- failure signature is `eval_failed:founder-source-quality-judge`,
- after run root cause is `none`,
- proof passes without Trend Radar fields.

This is a pure script test. It does not prove the VC process works.

- [ ] **Step 4: Run real regression rerun**

```bash
uv run python scripts/real-regression-cases.py \
  --api-url http://127.0.0.1:8093 \
  rerun \
  --limit 1 \
  --timeout-seconds 900
```

Expected:

- Existing real Trend Radar regression case still passes.
- If it fails with a new real root cause, fix the root cause or record the new proposal. Do not ignore it.

- [ ] **Step 5: Commit**

```bash
git add src/l2l3_protocol/runtime/self_improvement.py scripts/real-regression-cases.py scripts/real-before-after-proof.py tests/test_self_improvement_memory.py tests/test_real_playbook_scripts.py
git commit -m "fix(proof): keep regression cases playbook agnostic"
```

If no code changes are needed, commit nothing for this task and record the result in the final PR notes.

Success criteria:

- Existing regression cases still rerun.
- New regression case shape is not tied to Trend Radar.

---

## Phase 6: Add Cross-Process Testing Runbook

Purpose: make the next process test executable by any teammate without reverse-engineering the runtime.

### Task 6.1: Add `docs/cross-process-testing.md`

**Files:**

- Create: `docs/cross-process-testing.md`
- Modify: `README.md`

The document must contain the exact operational path below.

- [ ] **Step 1: Write the runbook**

Use this structure:

```markdown
# Cross-Process Testing Runbook

## Goal

Use this runbook to test any real ABRT Playbook through the L2/L3 runtime.

## What Counts As Ready

- The Playbook is registered in Hub.
- All required workers are registered.
- All required tools are registered.
- All required evals are registered.
- Required inputs are known.
- Real credentials/services are available.
- The Playbook has an approval boundary for external actions.

## What Does Not Count

- Unit tests alone.
- Mocked providers.
- Synthetic worker output.
- Fallback data.
- Demo commands.
- Silent skipped evals.

## Step 1: Start Real Infrastructure

```bash
docker compose up -d postgres qdrant agentmemory
set -a; source .env; set +a; uv run alembic upgrade head
set -a; source .env; set +a; uv run uvicorn l2l3_protocol.api.main:app --host 127.0.0.1 --port 8093
```

## Step 2: Sync Hub

```bash
curl -sS http://127.0.0.1:8093/health
curl -sS -X POST http://127.0.0.1:8093/hub/sync/yaml
```

## Step 3: Check Playbook Readiness

```bash
uv run python scripts/real-playbook-readiness.py \
  --api-url http://127.0.0.1:8093 \
  --playbook-key build-in-public-trend-radar
```

## Step 4: Run Generic Acceptance

```bash
uv run python scripts/real-playbook-acceptance.py \
  --api-url http://127.0.0.1:8093 \
  --playbook-key build-in-public-trend-radar \
  --goal "Real generic acceptance run for cross-process readiness." \
  --inputs-json '{"query":"agent runtime eval memory","providers":["github","arxiv","huggingface"],"channels":["x"],"max_results":2}' \
  --require-human-approval true \
  --timeout-seconds 900
```

## Step 5: Inspect Diagnosis And Proposals

```bash
curl -sS http://127.0.0.1:8093/runs/RUN_ID | jq '{status, diagnosis, improvement_proposals}'
curl -sS http://127.0.0.1:8093/improvement-proposals | jq .
```

## Step 6: Approve Only If The Evidence Is Good

```bash
curl -sS -X POST http://127.0.0.1:8093/improvement-proposals/PROPOSAL_ID/approve | jq .
```

## Step 7: Implement Approved Proposal

```bash
curl -sS -X POST http://127.0.0.1:8093/improvement-proposals/PROPOSAL_ID/implement | jq .
```

## Step 8: Run Before/After Proof

```bash
uv run python scripts/real-before-after-proof.py \
  --api-url http://127.0.0.1:8093 \
  --baseline-run-id BASELINE_RUN_ID \
  --proposal-id PROPOSAL_ID \
  --timeout-seconds 900
```

## Step 9: Rerun Regression Cases

```bash
uv run python scripts/real-regression-cases.py \
  --api-url http://127.0.0.1:8093 \
  rerun \
  --limit 1 \
  --timeout-seconds 900
```

## Step 10: Generate System Review

```bash
uv run python scripts/real-system-review.py \
  --api-url http://127.0.0.1:8093 \
  --limit 20 \
  --playbook-key build-in-public-trend-radar \
  --format markdown
```

## Decision: Can We Test This Process Further?

The answer is yes only if:

- readiness check passes,
- real acceptance reaches terminal state with diagnosis,
- failures create evidence-backed proposals,
- proof path can repeat comparable run,
- no hidden fallback or mock path was used.
```

- [ ] **Step 2: Add README pointer**

In `README.md`, add one paragraph near “Current Self-Improvement Loop”:

```markdown
For testing another ABRT process through the same loop, use `docs/cross-process-testing.md`. It defines the readiness check, generic acceptance runner, proposal approval boundary, before/after proof, regression reruns, and system review commands.
```

- [ ] **Step 3: Commit**

```bash
git add docs/cross-process-testing.md README.md
git commit -m "docs: add cross-process testing runbook"
```

Success criteria:

- A teammate can follow the runbook without asking which command comes next.
- The runbook says exactly when to stop and fix missing dependencies.

---

## Phase 7: Second Process Preflight Without Pretending

Purpose: prove that the new readiness and acceptance tooling can be pointed at another Playbook, while still failing honestly if the process is not yet registered.

Important:

This phase does not require inventing a fake second process. If no real second ABRT Playbook is registered yet, the correct result is an explicit readiness failure that names what is missing.

### Task 7.1: Pick The Candidate Process

Recommended candidates, in order:

1. `vc-research-pilot`
2. `startup-scouting-pilot`
3. `market-research-pilot`

Pick one with the owner. If no Playbook exists, use the intended key only for readiness failure:

```bash
uv run python scripts/real-playbook-readiness.py \
  --api-url http://127.0.0.1:8093 \
  --playbook-key vc-research-pilot
```

Expected if it is not registered:

- non-zero exit,
- exact message that Playbook is missing,
- no run created.

### Task 7.2: If The Candidate Playbook Exists, Run Real Acceptance

Only run this if readiness passes.

Example command:

```bash
uv run python scripts/real-playbook-acceptance.py \
  --api-url http://127.0.0.1:8093 \
  --playbook-key vc-research-pilot \
  --goal "Real pilot run for VC research cross-process readiness." \
  --inputs-file docs/private-or-local/vc-research-input.json \
  --require-human-approval true \
  --timeout-seconds 900
```

Do not commit private input files.

Expected:

- terminal status with diagnosis,
- evidence-backed proposals if anything fails,
- no hidden fallback.

### Task 7.3: If The Candidate Playbook Does Not Exist, Stop Correctly

Do not create a placeholder Playbook.

Record in the PR notes:

```text
Second process readiness preflight was executed against `vc-research-pilot`.
Result: not ready.
Reason: copy the exact missing dependency from `scripts/real-playbook-readiness.py`, for example `playbook not found: vc-research-pilot`.
No fake Playbook, worker, tool, eval, or input was created.
```

Success criteria:

- We can point the tooling at another process and get a trustworthy answer.
- If the answer is “not ready”, it is precise enough to plan the next implementation.

---

## Phase 8: Final Real Proof Pack

Purpose: before merging, prove that the system is ready for cross-process testing and that Trend Radar did not regress.

Run from `feat/abrt-cross-process-readiness`.

### Task 8.1: Full Test Suite

```bash
uv run pytest
```

Expected:

- Full suite passes.

### Task 8.2: Real Infrastructure

```bash
docker compose up -d postgres qdrant agentmemory
set -a; source .env; set +a; uv run alembic upgrade head
set -a; source .env; set +a; uv run uvicorn l2l3_protocol.api.main:app --host 127.0.0.1 --port 8093
```

In another terminal:

```bash
curl -sS http://127.0.0.1:8093/health
curl -sS -X POST http://127.0.0.1:8093/hub/sync/yaml
```

### Task 8.3: Generic Readiness On Proven Playbook

```bash
uv run python scripts/real-playbook-readiness.py \
  --api-url http://127.0.0.1:8093 \
  --playbook-key build-in-public-trend-radar
```

Expected:

- `ready: true`
- `missing: []`

### Task 8.4: Generic Acceptance On Proven Playbook

```bash
uv run python scripts/real-playbook-acceptance.py \
  --api-url http://127.0.0.1:8093 \
  --playbook-key build-in-public-trend-radar \
  --goal "Real generic acceptance run for cross-process readiness." \
  --inputs-json '{"query":"agent runtime eval memory","providers":["github","arxiv","huggingface"],"channels":["x"],"max_results":2}' \
  --require-human-approval true \
  --require-eval-key trend-claim-grounding \
  --require-eval-key trend-draft-quality \
  --timeout-seconds 900
```

Expected:

- terminal status is `waiting_approval`, `waiting_user`, or `completed`,
- diagnosis exists,
- no evidence-less root cause,
- no improvement-needed-without-proposal state.

### Task 8.5: Existing Trend Radar Acceptance Still Works

```bash
uv run python scripts/real-trend-radar-acceptance.py \
  --api-url http://127.0.0.1:8093 \
  --query "agent runtime eval memory" \
  --channel x \
  --max-results 2 \
  --timeout-seconds 900
```

Expected:

- same acceptance guarantees as before.

### Task 8.6: Regression Catalog Still Works

```bash
uv run python scripts/real-regression-cases.py \
  --api-url http://127.0.0.1:8093 \
  list

uv run python scripts/real-regression-cases.py \
  --api-url http://127.0.0.1:8093 \
  rerun \
  --limit 1 \
  --timeout-seconds 900
```

Expected:

- list returns real cases,
- rerun returns passed proof,
- after run root cause is `none`.

### Task 8.7: System Review Works

```bash
uv run python scripts/real-system-review.py \
  --api-url http://127.0.0.1:8093 \
  --limit 20 \
  --playbook-key build-in-public-trend-radar \
  --format markdown
```

Expected:

- report prints,
- report is evidence-backed,
- report references real IDs where data exists.

### Task 8.8: Second Process Preflight

Run readiness against the selected second process key:

```bash
uv run python scripts/real-playbook-readiness.py \
  --api-url http://127.0.0.1:8093 \
  --playbook-key vc-research-pilot
```

Expected:

One of:

- `ready: true`, then run real generic acceptance with real inputs;
- or explicit non-zero “not ready” with exact missing dependency.

Both are acceptable for this plan. What matters is that the system gives a trustworthy answer without pretending.

### Task 8.9: Commit Final Docs Or Proof Notes

If the proof generated run IDs that should be preserved, add them to `docs/cross-process-testing.md` under a short “Latest verification” section.

Commit:

```bash
git add docs/cross-process-testing.md
git commit -m "docs: record cross-process readiness proof"
```

Skip this commit if no file changed.

---

## Final PR / Merge Checklist

Before asking for review:

- [ ] Branch is `feat/abrt-cross-process-readiness`.
- [ ] `git status --short --branch` has no tracked modifications.
- [ ] `taskforce-landing/` is not staged.
- [ ] `uv run pytest` passes.
- [ ] Real API health passes.
- [ ] Hub sync passes.
- [ ] Generic readiness passes for `build-in-public-trend-radar`.
- [ ] Generic acceptance passes for `build-in-public-trend-radar`.
- [ ] Existing Trend Radar acceptance still passes.
- [ ] Regression case rerun passes.
- [ ] System review script works.
- [ ] Second process preflight produces a trustworthy ready/not-ready result.
- [ ] No mocks, fallbacks, fake data, demo paths, or silent degraded behavior were added.

Push:

```bash
git push -u origin feat/abrt-cross-process-readiness
```

Merge only after review and proof.

After merge to `main`, rerun at least:

```bash
uv run pytest
uv run python scripts/real-playbook-readiness.py --api-url http://127.0.0.1:8093 --playbook-key build-in-public-trend-radar
uv run python scripts/real-playbook-acceptance.py \
  --api-url http://127.0.0.1:8093 \
  --playbook-key build-in-public-trend-radar \
  --goal "Post-merge generic acceptance run." \
  --inputs-json '{"query":"agent runtime eval memory","providers":["github","arxiv","huggingface"],"channels":["x"],"max_results":2}' \
  --require-human-approval true \
  --timeout-seconds 900
```

---

## What “Ready To Test Other ABRT Processes” Means

After this plan, we are allowed to say:

The runtime is ready to test another ABRT process if that process has a real Playbook, real workers, real tools, real evals, real inputs, and real credentials/services. The system can check readiness, run the Playbook, produce diagnosis, create proposals, protect behavior changes behind approval, generate review reports, and rerun regression cases.

We are not allowed to say:

The runtime can magically run any process without registry work.

The honest statement is:

The self-improvement loop is process-portable. Each new process still needs real capabilities and evals.
