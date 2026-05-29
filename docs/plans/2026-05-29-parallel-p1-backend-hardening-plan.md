# Parallel Plan B: P1 Backend Hardening, Observability, And Smart Operations

Owner: Altinay  
Branch: `feat/p1-backend-hardening`  
Scope: backend/runtime/worker/registry/tests only. No UX/UI HTML work.

## Goal

Take the current working P1 L2/L3 pipeline and make it harder, cleaner, faster to rerun, easier to inspect, and safer around external writes.

The current system already works end to end. This plan is about turning the proof into a reliable operating process:

- cleaner Google Sheets output,
- separate tab for new L2/L3 leads,
- better idempotency,
- more granular resume,
- stronger observability,
- stronger quality gates,
- clearer failure evidence,
- no hidden fallback behavior.

## Why This Is Parallel-Safe

Nikita's lane owns the static UI file only.

This lane should avoid:

- `docs/ui/**`
- static HTML/CSS/JS UI work
- frontend styling decisions

This lane may touch:

- `src/l2l3_protocol/runtime/**`
- `src/l2l3_protocol/workers/**`
- `src/l2l3_protocol/api/**`
- `src/l2l3_protocol/core/**`
- `src/l2l3_protocol/db/**`
- `registries/**`
- `tests/**`
- `README.md`
- backend proof docs

Expected merge strategy: backend branch lands first or second safely because UI should consume API fields dynamically.

## Current System Facts

Latest proven P1 run:

- Run ID: `643eaceb-4720-481d-a245-8bbd2ff523be`
- Status: `completed`
- Metrics:
  - raw leads: `30`
  - normalized leads: `30`
  - triage qualified: `30`
  - gateway approved: `10`
  - gateway rejected: `20`
  - drafted: `10`
  - Data Lake written: `30`
  - Sheet written: `10`
  - Outreach Master written: `10`
- Eval passed: score `1.0`, threshold `0.86`
- Current Sheet write target from proof: `04_THE_FORGE_FINAL!A1666:J1675`
- Current issue: new L2/L3 proof rows are mixed into legacy tab.

Relevant code:

- Runtime: `src/l2l3_protocol/runtime/process_runtime.py`
- P1 worker: `src/l2l3_protocol/workers/p1_operator_worker.py`
- Schemas: `src/l2l3_protocol/core/schemas.py`
- API: `src/l2l3_protocol/api/main.py`
- P1 playbook: `registries/playbooks/p1-operator-outreach/playbook.yaml`
- P1 worker profiles: `registries/worker-profiles/p1-*.yaml`
- P1 evals: `registries/evals/p1-*.yaml`
- Tests: `tests/test_p1_operator_worker.py`, `tests/test_process_runtime.py`, `tests/test_run_controls.py`

## Non-Negotiables

- No mocks/fakes/synthetic provider responses as proof.
- Unit tests can isolate small logic, but acceptance proof must be real.
- Missing credentials, services, actor permissions, tab names, or paths must fail explicitly.
- No fallback to legacy scripts.
- No silent "best effort" external writes.
- External behavior changes need tests and proof.
- Do not break Nikita's UI branch by forcing UI-specific backend assumptions.

## Workstream 1: Separate Google Sheets Tab For New L2/L3 Leads

### Problem

The real proof appended new rows into legacy tab `04_THE_FORGE_FINAL`. That proves write capability, but it mixes new L2/L3 output with old data. For demos and operations, new runtime output should land in a clearly named tab.

### Target Behavior

New P1 L2/L3 writes should default to a separate tab, for example:

```text
P1_L2L3_NEW_LEADS
```

The old tab can still be used only when explicitly passed in inputs.

### Implementation Steps

- [ ] Add input support for `google_sheet_tab`.
- [ ] Set default P1 L2/L3 tab to `P1_L2L3_NEW_LEADS`.
- [ ] Update the Google Sheets sync worker to target that tab by default.
- [ ] Add a real "ensure tab exists" step:
  - read spreadsheet metadata;
  - if tab missing, create it through Sheets API;
  - write headers once;
  - do not silently create a wrong tab if API permission fails.
- [ ] Define stable headers for the new tab.
- [ ] Include `run_id`, `lead_id`, `synced_at`, `runtime_source`, and `artifact_refs`.
- [ ] Return sync result with:
  - spreadsheet ID,
  - tab name,
  - updated range,
  - row count,
  - skipped duplicate count,
  - created tab true/false.
- [ ] Update docs and proof notes.

### Suggested Columns

Use an explicit schema, not inherited legacy ambiguity:

1. `run_id`
2. `lead_id`
3. `name`
4. `linkedin_url`
5. `identity_status`
6. `current_role`
7. `gateway_decision`
8. `triage_score`
9. `archetype`
10. `outreach_status`
11. `draft_text`
12. `evidence_urls`
13. `claims_json`
14. `runtime_source`
15. `synced_at`

### Acceptance Criteria

- [ ] A new run writes to `P1_L2L3_NEW_LEADS` by default.
- [ ] Legacy `04_THE_FORGE_FINAL` is not touched unless explicitly requested.
- [ ] If the tab does not exist, the worker creates it and writes headers.
- [ ] If the service account lacks permission, run fails explicitly.
- [ ] Sync result includes tab name and updated range.
- [ ] Real Google Sheets API proof confirms rows are visible in the new tab.

## Workstream 2: Idempotent External Writes

### Problem

Approval retry or accidental double approval can append duplicate Sheet rows or duplicate Outreach Master drafts.

### Target Behavior

External writes should be idempotent by run and lead. Retrying the same approval should not duplicate rows.

### Implementation Steps

- [ ] Define deterministic `lead_id` for every normalized lead/dossier/draft.
- [ ] Include `run_id` and `lead_id` in:
  - Google Sheet rows,
  - Outreach Master entries,
  - Data Lake dossiers,
  - sync result artifacts.
- [ ] Google Sheets sync:
  - read existing `run_id + lead_id` pairs from target tab;
  - append only missing rows;
  - return `skipped_duplicate_count`.
- [ ] Outreach Master sync:
  - read existing entries;
  - skip entries with same `run_id + lead_id`;
  - return `skipped_duplicate_count`.
- [ ] Data Lake sync:
  - file names should include or store deterministic lead ID;
  - if file exists for same run/lead, update or skip deterministically;
  - return written/updated/skipped counts.
- [ ] Add explicit events:
  - `p1_external_sync_duplicate_skipped`
  - `p1_outreach_master_duplicate_skipped`
  - `p1_data_lake_duplicate_skipped`

### Acceptance Criteria

- [ ] Approving the same run twice does not create duplicate rows/drafts.
- [ ] A second approval attempt returns skipped duplicates.
- [ ] Events show what was skipped.
- [ ] Metrics distinguish written vs skipped.
- [ ] Real proof uses actual Sheet and actual JSON file.

## Workstream 3: More Granular Source Resume

### Problem

Runtime checkpointing now works per artifact. Provider cache helps. But `p1-source-collector` is still one large source step. If one provider fails late, the stage is less inspectable than it should be.

### Target Behavior

Each source should be separately tracked and resumable:

- Crunchbase source
- Funding tracker source
- LinkedIn source
- Exa source

Then a merge/normalize step combines them.

### Implementation Options

Preferred option:

- Keep one worker implementation file, but have runtime create one Work Order per source.
- Add artifact type `p1_source_batch`.
- Add source merge step that creates `p1_lead_candidates`.

Alternative:

- Keep current artifact type but execute source collector once per source and aggregate in runtime.

Preferred option is cleaner for observability and UI.

### Implementation Steps

- [ ] Add `P1_SOURCE_BATCH` artifact type.
- [ ] Add worker task type `collect_source_batch`.
- [ ] Runtime loops over requested `sources`.
- [ ] Each source batch gets its own task and artifact.
- [ ] Add `p1-source-merger` worker or internal merge task.
- [ ] Merge step dedupes candidates before `p1-lead-normalizer`.
- [ ] Source-level failures should name the exact provider.
- [ ] Existing provider cache should remain visible in each source batch output.

### Acceptance Criteria

- [ ] A run with three sources creates three source tasks.
- [ ] If LinkedIn fails, Crunchbase/Funding artifacts remain reusable.
- [ ] Resume does not rerun successful source batches unless `force_rerun` is true.
- [ ] Metrics include per-source raw count and cache hit count.
- [ ] Real mixed-source proof shows source-level task history.

## Workstream 4: Approval Preview Artifact

### Problem

The runtime stops at approval, but operators need a backend-generated preview of exactly what will be written before approval.

### Target Behavior

Before `waiting_approval`, backend stores an approval preview artifact:

- Google Sheet target spreadsheet/tab/range estimate
- rows to write
- Outreach Master path and entries
- Data Lake path and files
- risk summary
- idempotency keys

### Implementation Steps

- [ ] Add artifact type `p1_external_action_preview`.
- [ ] Generate preview after quality eval and before waiting approval.
- [ ] Include exact rows/entries/files.
- [ ] Include whether each action is approval-required.
- [ ] Include idempotency keys.
- [ ] Expose preview in `GET /runs/{id}` as a normal artifact.
- [ ] Add tests for preview payload shape.

### Acceptance Criteria

- [ ] Waiting-approval run always has preview artifact.
- [ ] Preview is generated from real approval package, not recomputed loosely.
- [ ] Approval execution writes exactly the entries previewed, minus duplicates.
- [ ] UI can render preview without guessing.

## Workstream 5: Stronger P1 Quality Gates

### Problem

The proof passed, but quality can be better. Some rows have awkward values like `current_role: TRUE`, and triage can over-qualify. We need stricter schema and better lead quality.

### Target Behavior

P1 should favor fewer stronger leads over many weak ones.

### Implementation Steps

- [ ] Normalize booleans/strings:
  - `current_role` should be `yes/no/unknown` or true boolean consistently.
  - `identity_status` should use a known enum.
  - `gateway_decision` should use a known enum.
- [ ] Add stricter LinkedIn URL validation:
  - person URLs only for person identity;
  - company URLs preserved only as evidence, not identity.
- [ ] Add evidence sufficiency scoring:
  - identity confidence,
  - current role confidence,
  - investor/operator signal confidence,
  - ABRT relevance.
- [ ] Add rejection reasons:
  - no person LinkedIn,
  - weak evidence,
  - too corporate/full-time,
  - low ABRT relevance,
  - duplicate.
- [ ] Improve `p1-outreach-draft-quality` eval:
  - must mention ABRT/Limpid;
  - must include sourced claims;
  - must not overclaim;
  - must be under target length;
  - must have a clear CTA;
  - must not include placeholder signoff.
- [ ] Add metrics:
  - rejected by evidence,
  - rejected by gateway,
  - duplicate skipped,
  - weak draft rejected.

### Acceptance Criteria

- [ ] A mixed-source real run produces fewer but cleaner gateway-approved leads.
- [ ] Every rejection bucket is visible in metrics.
- [ ] Drafts have no dangling `Best,` without sender.
- [ ] Sheet rows use normalized schema values.
- [ ] Eval failures create diagnosis and improvement proposal.

## Workstream 6: Observability And Timing

### Problem

We need to see where time and cost go: provider calls, Gemini calls, Sheet writes, retries, cache hits, approval waits.

### Target Behavior

Every P1 stage should have structured operational telemetry.

### Implementation Steps

- [ ] Add per-task timing:
  - started_at,
  - completed_at,
  - duration_ms.
- [ ] Add provider call telemetry:
  - provider,
  - actor/model,
  - query hash or safe query summary,
  - attempt count,
  - retry count,
  - cache hit,
  - result count,
  - duration_ms.
- [ ] Add metrics artifact fields:
  - total duration,
  - source duration,
  - triage duration,
  - gateway duration,
  - drafting duration,
  - sync duration.
- [ ] Do not log secrets or raw tokens.
- [ ] Redact provider credentials in all error messages.

### Acceptance Criteria

- [ ] A real run can answer: which stage was slowest?
- [ ] A provider failure includes provider name, safe request context, and retry count.
- [ ] Cache hit rate is visible.
- [ ] Logs and artifacts do not contain API tokens.

## Workstream 7: Real Acceptance Scripts

### Problem

Manual curl/python proofs work, but repeatable operator commands are better.

### Target Behavior

Have scripts that run real P1 acceptance scenarios and fail explicitly when services/credentials are missing.

### Implementation Steps

- [ ] Add `scripts/real-p1-full-proof.py`.
- [ ] Add required flags:
  - API URL,
  - spreadsheet ID,
  - sheet tab,
  - Data Lake path,
  - Outreach Master path,
  - source list,
  - limit.
- [ ] Script should:
  - verify health;
  - verify registry sync/capabilities;
  - start run;
  - poll to terminal state;
  - approve if requested;
  - fetch final run;
  - verify metrics;
  - verify Sheet rows through real Sheets API;
  - verify Outreach Master file through server path if local/server path is available;
  - print a concise proof report.
- [ ] Add `scripts/real-p1-cache-proof.py`.
- [ ] Add `scripts/real-p1-idempotency-proof.py`.

### Acceptance Criteria

- [ ] Scripts do not create fake leads.
- [ ] Scripts fail if real credentials are missing.
- [ ] Scripts prove new tab write.
- [ ] Scripts prove idempotency.
- [ ] Scripts prove cache hit on second comparable source run.

## Workstream 8: Backend API Polish For UI

### Problem

The UI can read raw run state, but a few backend conveniences will make it more reliable without coupling frontend to internal artifact order.

### Target Behavior

Add a compact, derived run summary endpoint or field.

### Implementation Steps

Option A: Extend `GET /runs/{id}` with `summary`.

Option B: Add `GET /runs/{id}/summary`.

Recommended: Option B to avoid bloating the raw run payload.

Summary should include:

- status
- playbook
- goal
- latest metrics
- latest diagnosis
- latest approval preview
- external sync status
- artifact type counts
- task status counts
- latest eval results
- pending actions

### Acceptance Criteria

- [ ] UI can render the top dashboard without scanning every artifact.
- [ ] Raw artifacts remain available.
- [ ] Summary endpoint does not hide failures.
- [ ] Tests cover completed, failed, and waiting-approval runs.

## Suggested Execution Order

Do these in order. Do not start with broad refactors.

1. Separate Google Sheets tab for new L2/L3 leads.
2. Idempotent external writes.
3. Approval preview artifact.
4. Backend summary endpoint for UI.
5. Source-level resume.
6. Observability/timing.
7. Quality gate improvements.
8. Real acceptance scripts.
9. Final proof run and docs update.

Why this order:

- The separate tab fixes the immediate demo/ops confusion.
- Idempotency prevents dangerous duplicates before more demos.
- Approval preview makes the UI safer.
- Summary endpoint helps Nikita's UI without blocking him.
- Source-level resume and observability improve speed and operations.
- Quality gate improvements are easier once metrics and previews are stable.

## Branch Checklist

- [ ] Create branch `feat/p1-backend-hardening` from fresh `main`.
- [ ] Confirm `taskforce-landing/` remains untouched.
- [ ] Make small commits per coherent change.
- [ ] Run `uv run pytest -q` after each meaningful block.
- [ ] Keep docs updated as behavior changes.

## Real Verification Matrix

### Baseline

- [ ] `uv run pytest -q`
- [ ] API health OK.
- [ ] Hub sync from YAML OK.
- [ ] Registry contains P1 playbook/workers/tools/evals.

### New Tab Proof

- [ ] Run full P1 with real providers.
- [ ] Approve writes.
- [ ] Verify rows are in `P1_L2L3_NEW_LEADS`.
- [ ] Verify legacy `04_THE_FORGE_FINAL` was not touched by default.

### Idempotency Proof

- [ ] Approve the same run once.
- [ ] Approve or resume approval path again.
- [ ] Verify row/draft counts do not duplicate.
- [ ] Verify skipped duplicate counts are reported.

### Resume Proof

- [ ] Trigger a real provider failure or stop after partial source success.
- [ ] Resume.
- [ ] Verify successful source batches are reused.
- [ ] Verify failed/missing source batch is the only one retried.

### Quality Proof

- [ ] Real run produces gateway-approved leads with person identity and evidence.
- [ ] Weak leads are rejected with reasons.
- [ ] Draft quality eval catches bad/unsupported drafts.

### UI Contract Proof

- [ ] `GET /runs/{id}/summary` or equivalent field supports:
  - completed run,
  - failed run,
  - waiting approval run.
- [ ] Nikita's static UI can consume the fields without custom backend hacks.

## Acceptance Criteria For This Backend Lane

The lane is complete when:

- [ ] New L2/L3 P1 rows default to a separate Google Sheets tab.
- [ ] External writes are idempotent.
- [ ] Approval preview artifact exists before approval.
- [ ] Run summary API or summary field exists for UI.
- [ ] Source-level resume is at least designed and preferably implemented.
- [ ] Metrics include enough information to explain speed, cache, and rejection behavior.
- [ ] Real acceptance scripts exist for the critical proof paths.
- [ ] A real full P1 run proves the new behavior.
- [ ] Documentation records the new proof run IDs and exact sheet tab/range.

## Merge Plan

Before merge:

- Rebase on latest `main`.
- Run `uv run pytest -q`.
- Run at least one real P1 proof using the new tab.
- Update `README.md` and P1 proof docs.
- Coordinate with Nikita if API field names changed.

After merge:

- Nikita rebases UI branch.
- UI consumes new tab/range/preview/summary fields.
- Run one final combined demo:
  - backend full P1 run,
  - approval from UI,
  - Sheet new tab verified,
  - Outreach Master verified,
  - diagnosis and metrics visible in UI.

Expected conflict risk: medium in docs, low in code if UI lane stays in `docs/ui/**`.

