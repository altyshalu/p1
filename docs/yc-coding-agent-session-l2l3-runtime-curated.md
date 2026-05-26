# YC Coding Agent Session: Building a Disciplined L2/L3 Agent Runtime

This is a curated, sanitized excerpt from a longer Codex Desktop session. The original export is much larger; this file is meant to be readable while still showing enough of the real engineering loop to be useful for YC's optional coding-agent-session prompt.

The original session was mostly in Russian. The transcript excerpts below are translated or lightly compressed for readability, while preserving the actual sequence: critique -> plan -> implementation -> verification. Secrets, local paths, long tool logs, binary payloads, and unrelated compaction dumps were removed.

## Why This Session Is Representative

This session is a good example of how we use coding agents: not as autocomplete, but as an engineering partner that can critique architecture, turn a product philosophy into runtime constraints, write tests first, implement the missing system layer, and verify the result.

The project is an early infrastructure system for coordinating AI work. The core idea is an L2/L3 split:

- L2 is the supervisor / reasoning layer. It decides what should happen next.
- L3 is the execution layer. It contains bounded workers, tools, evaluators, deterministic scripts, and human gates.
- The hard part is not “calling an LLM.” The hard part is making AI work safe, inspectable, repeatable, evaluated, and repairable.

The important engineering principle in this session was: no fake success. No hidden mocks, no production fallbacks, no demo paths that make the system appear to work when the real path is broken.

## Outcome

The larger session moved the system through several layers:

- First, we clarified the product philosophy: L2 should be the thinking/supervision layer and L3 should be the bounded execution layer.
- Then we designed an external memory stack instead of using Hermes-native memory.
- Then we implemented the first real runtime with FastAPI, Postgres working memory, agentmemory episodic memory, Mem0/Qdrant semantic memory, and Git-backed procedural registries.
- Then we built and iterated on cockpit/live observability so the user could watch L2/L3 runs.
- Then we audited the implementation against the philosophy and found that too much of the discipline was still decorative.
- Then we implemented the missing runtime discipline: contract enforcement, eval enforcement, retry/failure context, and DB/API-backed registry marketplace.
- Finally, we removed demo/fallback behavior, fixed a real async blocking bug around Hermes/LLM calls, rebuilt the Docker stack, and verified real services.

The most important coding milestone in the session moved the system from a mostly declarative protocol skeleton to a runtime with real enforcement:

- DB/API-backed registry marketplace for tools, workers, evals, process packs, failure patterns, and registry change candidates.
- Contract validation before and after L3 execution.
- Tool and side-effect policy checks.
- Eval enforcement that loads registry eval specs and applies thresholds instead of trusting worker self-reporting.
- Failure classification and structured failure context for L2.
- Registry evolution lifecycle with safe auto-applied metadata and approval-required executable changes.
- Test coverage for the new discipline layer.

Final verification in the session:

```text
uv run pytest
24 passed
```

## Session Arc

The central implementation arc had four phases:

1. Audit the implementation against the L2/L3 philosophy.
2. Identify where the code was too decorative: eval fields, retry policy, side-effect policy, and registry evolution existed mostly as data/prompt discipline, not runtime behavior.
3. Convert that critique into a concrete implementation plan.
4. Implement with a TDD loop and verify the full suite.

---

# 0. Broader Session Context

This section gives the surrounding context that led to the implementation excerpt. It is included because the full session was not just a single feature request; it was a progression from product philosophy to system architecture to real runtime behavior.

## Product Thesis: L2/L3 Communication

The initial philosophy was that AI work should be split into two layers:

- L2: a supervisor/reasoning layer that decides what should happen.
- L3: a bounded execution layer made of workers, scripts, tools, evaluators, adapters, and human gates.

The user wanted a system where humans primarily answer “what” and agents handle “how,” without losing visibility or safety.

The working thesis became:

> L2 should not directly do all work. It should inspect run state, choose bounded actions, delegate to registered L3 workers, receive artifacts/evals/failures, and decide whether to retry, repair, ask the user, finish, or escalate.

The critical constraint:

> The system should create agentic leverage without letting agents silently invent reality. L2 can be dynamic, but L3 execution must be contract-bound, observable, evaluated, and constrained by registries and approval policies.

## Memory Architecture

A major early decision was to avoid relying on Hermes built-in memory. The session separated memory into four explicit layers:

- Working memory: short-lived run state, tasks, events, artifacts, approvals.
- Episodic memory: traces, failures, retries, outcomes, run history.
- Semantic memory: durable knowledge about projects, tools, entities, rules.
- Procedural memory: skills, runbooks, process packs, worker profiles, eval specs, policies.

The chosen v1 stack:

```text
working memory   = Postgres state store
episodic memory  = agentmemory REST sidecar
semantic memory  = Mem0 with local Qdrant
procedural memory = Git-backed registry files
```

Later, procedural registry moved toward DB/API-backed marketplace while keeping YAML as explicit seed/import data.

The runtime setup document captured this:

```text
This runtime keeps protocol memory outside Hermes built-in memory:

- working memory: Postgres
- episodic memory: agentmemory REST sidecar
- semantic memory: Mem0 library with local Qdrant
- procedural memory: Git-backed registries/
```

That memory split mattered because the system was not supposed to be “one chatbot with context.” It was supposed to be a traceable runtime where each kind of state has a purpose.

## First Runtime Shape

Before the marketplace/enforcement work, the system already had a real local stack:

```text
Python 3.13
uv
FastAPI
Hermes
Postgres
agentmemory
Mem0
Qdrant
Docker Compose
JSONL logs
```

The local setup flow was:

```text
docker compose up --build
uv run l2l3-cockpit
```

The first generic API shape included:

```text
POST /runs
GET  /runs/{id}
POST /runs/{id}/messages
POST /runs/{id}/control
GET  /runs/{id}/events/stream
```

The first dogfood process was `build-in-public`: use trend/source signals, produce content drafts, evaluate them, and stop before external publishing for human approval.

The system stored run/task state in Postgres so the process could be inspected:

> Runtime creates a `TaskContract` and stores it in Postgres. It also stores events, artifacts, and eval results, so the whole process is trackable.

## Observability And Cockpit Work

The user wanted the system to be transparent and friendly, not a black box. The session explored both TUI and web cockpit directions. The original TUI experiment was rejected by the user as not good enough, which led to a cleaner direction:

- API-first runtime.
- Web cockpit or live terminal watcher as visibility layer.
- No separate fancy UI until the runtime semantics were correct.
- Show chat/messages, events, worker tasks, artifacts, evals, and run controls.

The important point was not the UI aesthetics. The important product requirement was:

> The user should be able to see the internal kitchen of the L2/L3 run in a user-understandable way, with enough detail to debug or trust the system.

That observability requirement later shaped the live CLI changes: full event payload toggle, compact/full event view, better task/event rendering, and run controls.

## No-Fallback Trust Boundary

A central rule emerged during the session:

> No demos, no fallbacks, no mocks, no fake/example data, no synthetic stand-ins, no silent degraded behavior unless explicitly requested.

The reason was practical, not aesthetic:

> Demo/fallback/mock behavior can make the owner believe the system works when only a substitute path works. That is a trust failure.

This rule was later saved into agentmemory and project instructions, and it affected implementation decisions:

- Missing inputs should fail explicitly.
- Missing workers/evals/tools should fail explicitly.
- Runtime should not fabricate artifacts.
- CLI should not create runs from embedded demo data.
- Tests may use fakes, but production paths must not.

The session later enforced this in code by removing a `demo` path from the live CLI and requiring real source files for real runs.

---

# 1. Architectural Audit

## User Request

The user asked Codex to compare the current implementation against the original L2/L3 philosophy and answer honestly whether the system actually matched it.

## Codex Response

> Verdict: No, the implementation does not fully match the philosophy yet. It points in the right direction, but it is closer to a protocol skeleton / v1 dogfood than a complete L2/L3 execution fabric.

Codex estimated that the philosophy was only partially implemented:

> I would rate it around 55-65%. The foundation is right, but the most important discipline pieces are still partly declarative.

What was already aligned:

- A `TaskContract` existed with fields like `task_type`, `goal`, `inputs`, `output_schema`, `allowed_tools`, `budget`, `stop_conditions`, `grader_spec`, `retry_policy`, `memory_policy`, and `side_effect_policy`.
- L2 did not do the work directly. It selected bounded actions validated through JSON/schema constraints.
- L3 existed as a separate execution layer: subprocess workers, evaluators, human gates, and Hermes agent workers.
- The system already had a registry-centric shape: process packs, worker profiles, eval specs.
- Memory was conceptually separated through artifacts and learning writes.

What did not yet match:

- The eval loop was weak. `grader_spec` and eval registry existed, but runtime did not load eval specs or enforce thresholds. It mostly recorded `passed/score` from the judge worker payload.
- `retry_policy` was decorative. The contract stored it, but runtime did not formally retry, rebrief, or reassign after failure.
- Input schema and side-effect policy were not systematically enforced.
- Registry evolution was candidate-only. The runtime could create a `registry_change_candidate`, but there was no review/apply lifecycle.
- The implementation was still strongly tied to the first `build-in-public` dogfood process.

Codex summarized the architectural gap:

> The foundation is right. This is not a monolithic smart agent; it already separates L2, L3, contracts, registries, artifacts, and memory routing. But the most important part of the philosophy - discipline through evals, retries, policies, and registry evolution - is implemented more as data structure and prompt discipline than as hard runtime behavior.

The recommended next step:

> Do not add more agents. Add a real contract enforcement layer: validate inputs and outputs, apply eval specs, block failed evals, run retry policy, and only then allow finish or memory writes.

Baseline verification at that point:

```text
uv run pytest
17 passed
```

---

# 2. Plan: Bring The Runtime Up To The Philosophy

Codex proposed a plan to implement the missing discipline layer.

## Summary

Implement real eval enforcement, retry/failure learning, input/output/side-effect validation, and an API-backed registry marketplace for tools, workers, evals, process packs, and failure patterns.

Keep `build-in-public` as the first dogfood process. Do not overgeneralize yet. The goal is to make the underlying runtime capable of supporting many future Lego-style processes.

## Key Plan Elements

### API-Backed Registry Marketplace

Add DB-backed registry tables and API endpoints while keeping YAML files as seed/bootstrap data.

Core registry item types:

- `tool`: callable capability metadata, runtime type, side-effect class, auth requirements, toolset name, tags.
- `worker`: deterministic/agentic/judge/adapter/human-gate profile, compatible tool ids, input/output schemas, budgets, retry policy, side-effect policy.
- `eval`: eval spec with eval type, threshold, dataset path, or runtime check config.
- `process_pack`: process definition with allowed workers, required inputs, completion criteria, memory policy.
- `failure_pattern`: known failure class, scope, frequency, root cause, mitigation, status.

Registry API:

```text
GET  /registry/{kind}
GET  /registry/{kind}/{key}
POST /registry/change-candidates
POST /registry/change-candidates/{id}/approve
POST /registry/change-candidates/{id}/reject
POST /registry/sync/yaml
```

Change policy:

- Safe auto-apply: eval run stats, failure pattern frequency, worker health metadata.
- Approval required: new tools, worker profile changes, executable entrypoint changes, process pack changes, side-effect policy changes.

### Contract Enforcement Layer

Before L3 execution:

- Validate task inputs against worker `input_schema`.
- Validate requested tools against worker-compatible tools and process-pack constraints.
- Reject contracts that request tools with side-effect classes not allowed by policy.
- Record `contract_validation_failed` events instead of running invalid tasks.

After L3 execution:

- Validate output against `output_schema`.
- Validate side-effect report if the worker/tool can produce external effects.
- Fail if output claims unauthorized side effects.

### Real Eval Loop

Replace passive eval recording with active eval enforcement:

- Load eval spec by `grader_spec.eval_key`.
- Apply `minimum_score` / `pass_threshold` from the eval spec.
- Store normalized eval result with eval id, type, threshold, score, passed, checks, reasons.
- If eval fails, mark the task failed or `needs_repair`.
- Return structured failure context to L2 so L2 can retry, rebrief, reassign, message the user, or fail.

### Retry And Failure Pattern Registry

Make retry policy operational:

- Classify failure type: input validation, worker exception, timeout, invalid JSON, output schema, eval failed, side-effect violation, tool denied.
- Look up matching failure pattern.
- Apply safe mitigation if allowed.
- Respect retry budget.
- Record retry attempts and failure metadata as events.

### Registry Evolution Lifecycle

Turn `registry_change_candidate` into a real lifecycle:

```text
proposed
auto_applied_safe
approved
rejected
superseded
```

Runtime rule:

> L2 must never directly mutate executable registry state without approval.

## Test Plan

The plan called for tests covering:

- Input schema rejection before worker execution.
- Output schema rejection after worker execution.
- Tool denial when worker/process/side-effect policy disallows a tool.
- Eval spec threshold overriding judge-worker self-reported `passed`.
- Retry policy stopping at budget.
- Failure pattern matching.
- Registry change candidate auto-applying only safe metadata changes.
- Registry API list/get/sync/approve/reject behavior.

---

# 3. User Approval

The user then gave the implementation command:

```text
PLEASE IMPLEMENT THIS PLAN
```

The plan included:

- API-backed registry marketplace.
- Runtime contract enforcement.
- Real eval loop.
- Retry and failure pattern registry.
- Registry evolution lifecycle.
- No marketplace UI in v1.
- Full test suite passing.

---

# 4. Implementation Loop

## Codex Starts With TDD

Codex explicitly chose a TDD + execution-plan flow:

> I am using test-driven development and executing-plans. This is a large implementation with a clear plan, and we cannot just throw code at it, otherwise the protocol discipline becomes decorative again. I will start with tests for marketplace/enforcement/eval/retry, then implementation, then full pytest.

It also identified a repository/worktree constraint:

> Worktree isolation is not appropriate here because the project is inside a parent repository. I will work in place, but limit changes strictly to the project directory.

## Scope Control

Before implementation, Codex constrained the v1:

> I am taking a realistic v1 slice: DB/API marketplace plus runtime enforcement, without trying to build “npm for agents” immediately. If we try to add community install semantics now, this will balloon; but we can make the current runtime disciplined.

## RED Tests

Codex added tests for the missing pieces and ran them:

```text
uv run pytest tests/test_contract_enforcement.py tests/test_eval_retry_registry.py tests/test_registry_marketplace_api.py
```

The tests failed as expected:

```text
ERROR collecting tests/test_contract_enforcement.py
ModuleNotFoundError: No module named 'l2l3_protocol.runtime.contracts'

ERROR collecting tests/test_registry_marketplace_api.py
ImportError: cannot import name 'RegistryChangeCandidateCreate'
```

Codex interpreted this as a useful RED state:

> RED confirmed: `runtime.contracts` and registry schemas/API are missing. Now I will build the minimal GREEN layer: registry/change candidate types, contract validator, API routes, DB models/store, then connect eval/retry in `ProcessRuntime`.

## GREEN Layer 1: Schemas And Contract Validator

Codex implemented:

- Registry schemas.
- Change candidate schemas.
- Contract validation module.

Then moved to storage:

> The first GREEN layer is ready: registry schemas and contract validator. Next I am adding DB-backed storage: new tables, store methods, and YAML seed.

## GREEN Layer 2: DB-Backed Marketplace

Codex added:

- Registry DB models.
- Store methods.
- YAML seed/sync flow.
- API routes.

It also caught that this was not enough:

> DB marketplace is added as a separate layer, but runtime is not using discipline yet. The next patch is the important one: `ProcessRuntime` will validate contracts before L3, validate outputs after L3, apply eval thresholds, and write failure context for L2.

## GREEN Layer 3: Runtime Enforcement

Codex connected the runtime to the discipline layer:

- Validate task contract inputs before worker execution.
- Validate worker outputs after execution.
- Validate tool policy and side-effect policy.
- Load eval spec and enforce threshold.
- Classify failures and pass structured context back to L2.

Then it ran targeted tests:

```text
uv run pytest tests/test_contract_enforcement.py tests/test_eval_retry_registry.py tests/test_registry_marketplace_api.py
```

Targeted tests passed:

```text
collected 7 items

tests/test_contract_enforcement.py ...       [ 42%]
tests/test_eval_retry_registry.py ..         [ 71%]
tests/test_registry_marketplace_api.py ..    [100%]

7 passed in 0.36s
```

## Full Suite

Codex then ran the full test suite:

```text
uv run pytest
```

Result:

```text
collected 24 items

tests/test_alembic_async.py .                          [  4%]
tests/test_api_surface.py .                            [  8%]
tests/test_contract_enforcement.py ...                 [ 20%]
tests/test_eval_retry_registry.py ..                   [ 29%]
tests/test_l2_supervisor_and_l3_executor_edges.py ..... [ 50%]
tests/test_memory_adapters.py ..                       [ 58%]
tests/test_process_runtime.py ...                      [ 70%]
tests/test_registry.py .                               [ 75%]
tests/test_registry_marketplace_api.py ..              [ 83%]
tests/test_settings_and_logging.py ..                  [ 91%]
tests/test_web_cockpit.py ..                           [100%]

24 passed in 0.44s
```

## Codex Finds A Remaining Weakness

After the tests passed, Codex did not stop. It noticed a mismatch with the plan:

> One important weakness: API-backed registry exists, but runtime still prefers YAML. That is weak relative to the plan. I will strengthen it: `ProcessRuntime` should read process/worker/eval/tool/failure-pattern from DB if the store supports registry and data has been seeded. YAML should remain an explicit bootstrap seed/import source, not the primary runtime source of truth.

This was a good example of the agent pushing beyond “tests green” toward the architecture intent.

Codex implemented DB-first registry lookup and reran the suite:

```text
uv run pytest
```

Result:

```text
24 passed in 0.44s
```

## Documentation

Codex then added setup documentation:

> Tests are green after DB-first runtime. Last useful step: update setup docs so it is clear how to sync YAML registry into the API-backed marketplace and which endpoints exist.

Final verification:

```text
uv run pytest
24 passed in 0.71s
```

---

# 5. Final Session Report

Codex summarized the completed work:

> Implemented the plan in a v1 slice: runtime no longer just stores contract fields, it actually applies the discipline layer.

What shipped:

- DB/API-backed registry marketplace: `tool`, `worker`, `eval`, `process_pack`, `failure_pattern`, change candidates, YAML sync.
- Contract enforcement: input/output schema validation, tool policy checks, side-effect guardrails.
- Eval loop: runtime loads eval spec, applies threshold, writes normalized eval result and failure context.
- Retry/failure context: failures are classified and passed back to L2 through events.
- Registry evolution lifecycle: safe metadata changes auto-apply; unsafe registry changes require approval.
- Marketplace sync/API docs added.

Verification:

```text
uv run pytest
24 passed
```

---

# 6. Real Services, Debugging, And Follow-Through

The larger session did not stop at “tests pass.” Several follow-up loops mattered because they showed whether the runtime worked as a system, not just as code.

## Docker Stack Verification

After implementation, the user started Docker and asked Codex to run the system. Codex brought up the real services rather than substituting a local fake path.

The verified services included:

```text
app        = FastAPI runtime
postgres   = working memory database
qdrant     = semantic memory vector store
agentmemory = episodic memory sidecar
```

Codex reported:

```text
docker compose up -d --build
app running on localhost
Postgres healthy
Qdrant running
agentmemory running
API health OK
Registry synced: 23 items
```

This part mattered because it validated that the protocol runtime was not just a local Python object graph. It had actual service boundaries, migrations, registry sync, and runtime APIs.

## Real LLM Path

The user asked which LLM was writing drafts.

Codex traced the real path:

```text
worker: trend-draft-writer
worker_type: hermes_agent
runtime: HermesRuntime
model: deepseek-v4-flash
base URL: DeepSeek-compatible API endpoint
```

The answer made the execution path explicit: drafts were written by a Hermes agent worker through the configured model provider, not by a hidden stub.

## Bug: Hermes Blocking The FastAPI Event Loop

During a real live run, the user hit a timeout in the live dashboard.

The user-visible symptom:

```text
uv run l2l3-live demo trend-radar
Status: running
Dashboard polling /runs/{id} times out
```

Codex investigated and diagnosed that the issue was not simply a TUI rendering problem:

> The cause looks like the server, not the TUI: the LLM/Hermes call was running synchronously inside the async runtime and could block the FastAPI event loop. The pipeline was running, but `/runs/{id}` could not respond to polling, so the dashboard timed out.

Fix:

- Move Hermes conversation execution off the FastAPI event loop into a separate thread.
- Keep the runtime path real; do not replace Hermes with a fake provider.
- Add tests around the Hermes runtime behavior.
- Improve live event rendering.

Codex summarized the fix:

```text
Main timeout cause: Hermes/LLM call blocked the async API event loop.
Now Hermes conversation runs in a separate thread.
```

It also improved the live watcher:

- `f` toggles compact/full event payload.
- `q` exits watcher without stopping the run.
- Event payloads render as JSON rather than truncated Python repr.
- The dashboard shows clearer colors, controls, task tables, and event details.

Verification after the fix:

```text
uv run pytest
28 passed

docker compose up -d --build
GET /health -> ok
registry sync -> {"synced": 23}
```

Commits from that loop:

```text
fix(runtime): offload hermes conversations
feat(cli): toggle expanded event payloads
```

This was a useful example of the agent debugging a production-shaped integration issue: the code was “working,” but the observability layer could not poll because blocking I/O froze the API loop.

## No-Fallback Enforcement In The CLI

The session also found a trust-boundary problem: a `demo` command and embedded example data could make the system look operational without real inputs.

The user challenged that pattern. Codex agreed and fixed it:

> This was a bad pattern: `demo` plus embedded `example/*` data could create the false feeling that a real pipeline works.

Changes:

- Removed `l2l3-live demo`.
- Removed hardcoded fake/example sources.
- Required real input files for real runs.
- Updated help text to make the real command explicit.
- Added tests to make sure the demo path was gone.
- Saved the no-demo/no-fallback rule into agentmemory and project instructions.

New CLI shape:

```text
l2l3-live start trend-radar --sources-file ./trend-sources.json --channel x
```

If there is no real source file, no run is created.

Verification:

```text
uv run pytest
30 passed

curl /health
{"status":"ok","service":"l2l3-protocol"}
```

Commit from that loop:

```text
fix(cli): require real trend radar inputs
```

This mattered because it turned a philosophical rule into product behavior. The runtime should not let a user accidentally confuse a demo with a real process.

## Real Migration Verification

Later in the session, Codex also checked migrations against a real Postgres instance rather than relying only on unit tests.

When the default local Postgres port was occupied by another container, Codex did not mutate the unknown database. It started a temporary isolated Postgres on a random port, ran the actual Alembic upgrade, then removed the container.

The reasoning:

> The port is occupied by another local container, so I will not mutate that database. I will start a separate temporary Postgres with a random port, run the real `alembic upgrade head`, then delete the container.

Verification:

```text
INFO [alembic.runtime.migration] Context impl PostgresqlImpl.
alembic upgrade head completed on temporary Postgres
container removed
```

This was another no-fallback example: real migration, real database engine, isolated from unrelated local services.

---

# 7. Why This Matters

The session is not impressive because the agent wrote a lot of code. The useful signal is that the agent helped convert an abstract product philosophy into enforceable runtime behavior.

The before state had the right nouns:

- contracts
- workers
- registries
- evals
- retry policies
- memory policies
- side-effect policies

But many of them were still soft. They existed as schemas, prompts, or configuration fields.

The after state made those concepts harder:

- Invalid contracts fail before execution.
- Worker output is checked after execution.
- Evals are enforced by registry thresholds.
- Failure context is structured for L2.
- Registry changes have lifecycle boundaries.
- The runtime is DB-first for marketplace state.

That is the core product philosophy: AI autonomy should be bounded by contracts, registries, evals, memory, approval gates, and observable failure repair. The agent did not just implement a feature; it helped strengthen the system’s trust boundary.

## What This Shows About Our Use Of AI Coding Tools

This session demonstrates several working habits:

- We use agents to challenge architecture, not just generate code.
- We prefer explicit failure over hidden fallbacks.
- We convert fuzzy product philosophy into runtime invariants.
- We ask the agent to inspect existing code before proposing changes.
- We use tests as the interface between intent and implementation.
- We let the agent continue past the first green test when it detects an architectural gap.
- We keep the human in charge of strategic scope while delegating implementation detail.
- We verify real services after code changes instead of stopping at a mocked success.
- We treat observability and operator experience as part of the runtime, not as decoration.
- We encode learned operating rules into memory and project instructions so they persist beyond one turn.

## Residual Caveats

This was still an early v1 implementation:

- `build-in-public` remained the first dogfood process.
- Marketplace UI was intentionally deferred.
- Community-driven registry distribution was intentionally deferred.
- Some operational hardening still belongs in later milestones.
- Some fakes remained inside tests, but production runtime paths were tightened to require real inputs/integrations.

Those caveats were deliberate scope control, not hidden limitations.

---

# Appendix: Minimal Raw Test Evidence

Targeted tests:

```text
uv run pytest tests/test_contract_enforcement.py tests/test_eval_retry_registry.py tests/test_registry_marketplace_api.py

tests/test_contract_enforcement.py ...       [ 42%]
tests/test_eval_retry_registry.py ..         [ 71%]
tests/test_registry_marketplace_api.py ..    [100%]

7 passed in 0.36s
```

Full suite:

```text
uv run pytest

tests/test_alembic_async.py .                          [  4%]
tests/test_api_surface.py .                            [  8%]
tests/test_contract_enforcement.py ...                 [ 20%]
tests/test_eval_retry_registry.py ..                   [ 29%]
tests/test_l2_supervisor_and_l3_executor_edges.py ..... [ 50%]
tests/test_memory_adapters.py ..                       [ 58%]
tests/test_process_runtime.py ...                      [ 70%]
tests/test_registry.py .                               [ 75%]
tests/test_registry_marketplace_api.py ..              [ 83%]
tests/test_settings_and_logging.py ..                  [ 91%]
tests/test_web_cockpit.py ..                           [100%]

24 passed in 0.71s
```

Additional verification from the larger session:

```text
uv run pytest
28 passed

docker compose up -d --build
GET /health -> ok
registry sync -> {"synced": 23}
```

After removing the demo path and requiring real input files:

```text
uv run pytest
30 passed

uv run l2l3-live --help
usage: l2l3-live [-h] [--api-url API_URL] {start,watch} ...

uv run l2l3-live start trend-radar --help
--sources-file SOURCES_FILE
--channel CHANNELS
```

Docker health evidence:

```text
curl /health
{"status":"ok","service":"l2l3-protocol"}

docker compose ps
agentmemory running
app running
postgres healthy
qdrant running
```

Representative commits from the broader session:

```text
feat(runtime): add review control actions
feat(cli): add live run dashboard
fix(runtime): offload hermes conversations
feat(cli): toggle expanded event payloads
fix(cli): require real trend radar inputs
feat(runtime): adopt taskforce hub terminology
feat(runtime)!: add explicit l2 execution and design modes
fix(db): move local postgres to port 5434
docs: add sanitized YC agent session export
docs: add curated YC coding agent session
```

Sanitization note:

```text
Secrets, local paths, binary payloads, unrelated compaction summaries,
and verbose tool logs were removed from this curated version.
```
