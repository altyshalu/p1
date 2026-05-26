# YC Coding Agent Session: Building a Disciplined L2/L3 Agent Runtime

This is a curated, sanitized excerpt from a longer Codex Desktop session.

The original session was mostly in Russian. The transcript excerpts below are translated or lightly compressed for readability, while preserving the actual sequence: critique -> plan -> implementation -> verification. Secrets, local paths, long tool logs, binary payloads, and unrelated compaction dumps were removed.

Full sanitized export available locally:

`docs/yc-codex-session-019e5c94-sanitized.md`

## Why This Session Is Representative

This session is a good example of how we use coding agents: not as autocomplete, but as an engineering partner that can critique architecture, turn a product philosophy into runtime constraints, write tests first, implement the missing system layer, and verify the result.

The project is an early infrastructure system for coordinating AI work. The core idea is an L2/L3 split:

- L2 is the supervisor / reasoning layer. It decides what should happen next.
- L3 is the execution layer. It contains bounded workers, tools, evaluators, deterministic scripts, and human gates.
- The hard part is not “calling an LLM.” The hard part is making AI work safe, inspectable, repeatable, evaluated, and repairable.

The important engineering principle in this session was: no fake success. No hidden mocks, no production fallbacks, no demo paths that make the system appear to work when the real path is broken.

## Outcome

The session moved the system from a mostly declarative protocol skeleton to a runtime with real enforcement:

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

The useful part of the session had four phases:

1. Audit the implementation against the L2/L3 philosophy.
2. Identify where the code was too decorative: eval fields, retry policy, side-effect policy, and registry evolution existed mostly as data/prompt discipline, not runtime behavior.
3. Convert that critique into a concrete implementation plan.
4. Implement with a TDD loop and verify the full suite.

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

# 6. Why This Matters

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

## Residual Caveats

This was still an early v1 implementation:

- `build-in-public` remained the first dogfood process.
- Marketplace UI was intentionally deferred.
- Community-driven registry distribution was intentionally deferred.
- Some operational hardening still belongs in later milestones.

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

Sanitization note:

```text
Secrets, local paths, binary payloads, unrelated compaction summaries,
and verbose tool logs were removed from this curated version.
```
