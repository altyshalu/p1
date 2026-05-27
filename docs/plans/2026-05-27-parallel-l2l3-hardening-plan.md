# Parallel L2/L3 Hardening Plan

**Date:** 2026-05-27  
**Target:** finish the current non-UI L2/L3 self-improvement loop by Friday, May 29, 2026.  
**Scope:** backend runtime, workers, evals, memory, proof scripts, API/reporting, docs. UI is explicitly out of scope for this plan.

## Context

The YC self-improving-company talk describes a loop:

1. sensor layer collects real-world signals,
2. policy layer decides what may happen automatically and what needs approval,
3. tool layer executes deterministic or bounded actions,
4. quality gates evaluate the result,
5. learning mechanism records failures and turns them into improvements.

Our current `build-in-public-trend-radar` pipeline now maps to that loop:

- **Sensors:** real GitHub, arXiv, and Hugging Face source collection.
- **Policy:** Playbooks, Taskforce Hub, Work Orders, external-action rules, approval gates.
- **Tools/workers:** registered L3 worker profiles and sandboxed subprocess/Hermes execution.
- **Quality gates:** claim grounding and draft-quality eval workers.
- **Learning:** diagnosis artifacts, failure learnings, system reviews, improvement proposals, implementation/proof lifecycle.

The strongest real proof so far:

- Baseline run `8d3fb1a1-9c57-408c-8337-e10f9034a243` failed/waited on Hugging Face provider-no-results.
- Proposal `bec43eb7-e98e-4bed-b76e-3f129707d928` was approved, implemented, and proven.
- After run `3bfc00a7-6aaf-413b-b5f9-76c923fb71e5` no longer repeated the Hugging Face provider failure. It found a real Hugging Face dataset through approved repair attempts.
- The after run exposed the next real issue: claim grounding failed because claims reached the eval without proper non-empty `text`.

That means the first loop is real, but it is not yet hardened. The next two days should turn it from a proven prototype into a reliable operating model for this one process.

## Non-Negotiables

- No mocks, fakes, demos, fallback success paths, or synthetic provider data for acceptance proof.
- Unit tests are allowed for small logic, but they do not count as release proof.
- Real proof must use real API, Postgres, Hermes/model credentials, source APIs, workers, evals, and stored run evidence.
- Behavior-changing improvements require approval before implementation.
- Unsupported implementation proposals must fail explicitly.
- Keep UI out of scope. Expose backend/reporting data now; design UI later.
- Work in separate branches and avoid overlapping write ownership.

## Branch Strategy

Use two feature branches from updated `main`:

- Developer A branch: `feat/trend-radar-runtime-hardening`
- Developer B branch: `feat/self-improvement-memory-reporting`

Merge order:

1. Developer A merges first if runtime contracts or worker payload shapes change.
2. Developer B rebases after A if report/proof summaries need the new payloads.
3. Final integration branch: `feat/l2l3-friday-proof`
4. Run full proof from final integration branch before merging to `main`.

Do not touch `taskforce-landing/` in either branch.

## Developer A: Runtime And Proof Owner

Primary responsibility: make the current trend-radar process run cleanly through the core L2/L3 loop and fix the next real blocker.

### A1. Fix claim-grounding input shape

Problem:

- The proven Hugging Face provider fix allowed the run to progress.
- The next failure is `trend-claim-grounding`: claims have `claim_text` or ids/source URLs, but the eval requires non-empty `text`.

Tasks:

- Make draft normalization preserve/derive claim `text` from `claim_text`, atom claim text, or associated draft text.
- Ensure every claim passed to `claim-grounding-judge` has:
  - non-empty `text`,
  - `source_url` or `evidence_urls`,
  - no synthetic claim content.
- Keep source URLs grounded in prior artifacts only.
- Add a failure-pattern or worker-level repair rule if L2 keeps choosing the wrong repair shape.

Success criteria:

- A comparable real trend-radar run no longer fails on empty claim text.
- Claim-grounding eval passes with real source URLs.
- No claim text is invented without evidence from source artifacts, content atoms, or drafts.

Owned files:

- `src/l2l3_protocol/workers/build_in_public_worker.py`
- `registries/failure-patterns/*`
- `registries/worker-profiles/draft-schema-normalizer.yaml`
- `registries/worker-profiles/claim-grounding-judge.yaml`
- `tests/test_trend_radar_process.py`
- focused worker tests as needed

### A2. Stabilize trend-radar terminal path

Problem:

- The pipeline can progress deeply, but L2 may loop too long or spawn weak repair tasks.

Tasks:

- Ensure repair budgets stop bad branches deterministically.
- Make terminal states clear: `completed`, `waiting_approval`, or explicit `failed` with diagnosis.
- Prevent L2 from re-running equivalent normalizer tasks without new evidence.
- Ensure successful content run reaches approval gate, not silent finish/publish.

Success criteria:

- Real run reaches `waiting_approval` or `completed` without provider failure or claim-grounding failure.
- If it fails, diagnosis is precise and creates the next proposal.
- No endless L2 repair loop.

Owned files:

- `src/l2l3_protocol/runtime/process_runtime.py`
- `src/l2l3_protocol/runtime/l2_supervisor.py`
- `registries/playbooks/build-in-public-trend-radar/playbook.yaml`
- `tests/test_process_runtime.py`
- `tests/test_eval_retry_registry.py`

### A3. Extend implementation worker only for proven narrow handlers

Problem:

- The first implementation worker supports the Hugging Face provider repair case.
- We need a disciplined path for the next approved runtime/worker improvements without letting it mutate arbitrary code.

Tasks:

- Add controlled handler only after a proposal is well-defined and approved.
- Keep unsupported proposals failing explicitly.
- Store implementation result with:
  - applied change,
  - approval boundary,
  - risk,
  - proof required,
  - worker execution metadata.
- Do not auto-merge, auto-deploy, or silently modify registry/code.

Success criteria:

- New supported implementation handler can be tested by approved proposal + real before/after proof.
- Unsupported proposal returns clear API conflict.

Owned files:

- `src/l2l3_protocol/workers/proposal_implementation_worker.py`
- `src/l2l3_protocol/api/main.py`
- `tests/test_proposal_implementation_worker.py`
- targeted API tests

### A4. Real proof pack

Tasks:

- Run `uv run pytest`.
- Run real API stack.
- Sync Hub from YAML.
- Run baseline/comparable trend-radar proof.
- Run before/after proof for any approved implemented proposal.
- Capture run IDs and proposal IDs in the final PR notes.

Success criteria:

- Full tests pass.
- At least one clean real trend-radar run reaches approval/completion.
- At least one before/after proof passes after the current claim-grounding fix.

## Developer B: Memory, Review, Reporting, And Regression Owner

Primary responsibility: turn real run experience into durable lessons, review output, and future checks.

### B1. Improve failure learning aggregation

Problem:

- Failure learnings exist, but they need better grouping and prioritization for repeated L2/L3 issues.

Tasks:

- Improve grouping by:
  - failure signature,
  - target component,
  - playbook,
  - root cause,
  - worker/eval/tool family.
- Track repeated repair attempts and human-intervention points.
- Make learning summaries concise and evidence-based.
- Avoid storing vague or duplicate lessons.

Success criteria:

- `/failure-learnings` clearly shows active vs resolved lessons.
- Proven proposal resolves the matching learning.
- Repeated failures increase occurrence count instead of creating noisy duplicates.

Owned files:

- `src/l2l3_protocol/runtime/self_improvement.py`
- `src/l2l3_protocol/db/store.py`
- `tests/test_self_improvement_memory.py`
- `tests/test_run_diagnostics.py`

### B2. Make recent system reviews useful enough to run daily

Problem:

- `POST /system-reviews/recent` exists, but it is still a manual API path.

Tasks:

- Add a CLI or script command to run recent review from terminal.
- The review should output:
  - top repeated failures,
  - weak components,
  - excess repair attempts,
  - human interruptions,
  - needed tools/evals/process changes,
  - concrete proposed improvements.
- Keep this non-UI. Markdown/stdout or JSON is enough.

Success criteria:

- One command can generate a recent-review report from real Postgres data.
- Report contains concrete improvements, not generic summaries.
- It can be run daily by a human or later automation.

Owned files:

- `src/l2l3_protocol/live/cli.py` or a new `scripts/real-system-review.py`
- `src/l2l3_protocol/live/client.py`
- `src/l2l3_protocol/workers/self_improvement_worker.py`
- `tests/test_self_improvement_worker.py`

### B3. Create backend report: "what the system learned"

Problem:

- UI is later, but the backend should already expose a clean report for self-development.

Tasks:

- Add an API/reporting path or script that returns:
  - current active learnings,
  - proposed improvements,
  - approved/implemented/proven proposals,
  - risks,
  - proof commands,
  - last before/after proof result,
  - resolved learnings.
- Make it human-readable enough to paste into a team update.

Success criteria:

- A teammate can run one command and understand what the system learned this week.
- It references real run IDs/proposal IDs/eval evidence.
- It does not require opening the future UI.

Owned files:

- `src/l2l3_protocol/api/main.py`
- `src/l2l3_protocol/db/store.py`
- `scripts/*`
- `tests/test_api_surface.py`

### B4. Regression case catalog

Problem:

- Before/after proof exists, but proven failures should become durable regression cases.

Tasks:

- Define a lightweight regression case record:
  - baseline run id,
  - proposal id,
  - failure signature,
  - target component,
  - comparable run inputs,
  - proof command,
  - expected absent failure.
- Store/generate it after proposal becomes proven.
- Add a script that lists or reruns regression cases against real API.

Success criteria:

- The Hugging Face provider fix becomes a reusable real regression case.
- Future runs can prove we did not regress the old failure.
- No fake provider data or mocked HTTP.

Owned files:

- `src/l2l3_protocol/runtime/self_improvement.py`
- `scripts/real-before-after-proof.py`
- new script if needed
- `tests/test_self_improvement_memory.py`

## Integration Contract Between Developers

Developer A may change worker output shape only if:

- the change is documented in the PR,
- tests are updated,
- Developer B has a stable field to reference in reports.

Developer B may add reporting/API fields only if:

- they are derived from persisted real data,
- they do not create fake summaries,
- they do not change runtime behavior without A reviewing.

Shared rule:

- If a change affects `ImprovementProposal`, `FailureLearning`, or diagnosis payloads, both developers review before merge.

## Final Friday Proof

Run this from the integration branch:

1. `docker compose up -d postgres qdrant agentmemory`
2. `uv run alembic upgrade head`
3. start real API
4. `curl -X POST /hub/sync/yaml`
5. `uv run pytest`
6. run real `build-in-public-trend-radar` with GitHub, arXiv, Hugging Face
7. verify terminal state is `waiting_approval` or `completed`
8. verify diagnosis exists if anything fails
9. verify active learnings/proposals are evidence-backed
10. approve + implement one safe proposal if available
11. run real before/after proof
12. generate "what the system learned" report

Final success means:

- trend-radar can run with real sources,
- L2 delegates to L3 through bounded Work Orders,
- evals catch quality failures,
- failures become diagnosis + learning + proposal,
- approved improvement can be implemented by controlled worker,
- proof can mark it proven,
- report shows what was learned,
- no UI is required to operate the loop.

## Friday Demo Narrative

"We started the week designing an L2/L3 protocol. By Friday we have a working operating model: L2 supervises, L3 executes bounded tasks, the runtime validates and evaluates, failures become structured incident briefs, the system stores real lessons, proposes improvements, requires approval for behavior changes, applies approved narrow improvements, and proves them with real before/after runs. We proved this on the build-in-public trend-radar workflow using real GitHub, arXiv, and Hugging Face data."

