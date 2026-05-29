# Parallel Plan A: P1/L2L3 Control Room UI

Owner: Nikita  
Branch: `feat/p1-control-room-html`  
Scope: UX/UI only. Single static HTML file. No backend/runtime/registry changes.

## Goal

Build a polished operator-facing control room for the current L2/L3 + P1 system as a standalone HTML file. The file should make the real system understandable in one screen: what ran, where it is stuck, what was written, what needs approval, what the system learned, and which artifacts were produced.

This UI must not pretend the backend works. It should read real API data when an API URL and run ID are provided. If the API is unavailable, it must show an explicit connection failure, not fake content.

## Why This Is Parallel-Safe

This lane should avoid touching:

- `src/l2l3_protocol/**`
- `registries/**`
- `tests/**`
- database migrations
- worker code
- Google Sheets behavior

Suggested files:

- Add `docs/ui/p1-control-room.html`
- Optional: add `docs/ui/README.md`

This should merge cleanly with Altinay's backend branch because it only adds static docs/UI assets.

## Current Backend Facts To Design Around

The backend already exposes:

- `GET /health`
- `GET /runs/{id}`
- `POST /runs`
- `POST /runs/{id}/control`
- `GET /improvement-proposals`
- `POST /system-reviews/recent`
- `GET /runtime/capabilities`

The latest real proof run:

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
- Eval: passed, score `1.0`, threshold `0.86`
- Sheet tab/range used in the proof: `04_THE_FORGE_FINAL!A1666:J1675`
- Outreach Master: `/root/sovereign-os/OS_Operational/Outreach_Drafts_Master.json`

Altinay's backend lane will likely move new L2/L3 writes into a separate Google Sheets tab. Design the UI so the sheet tab/range are read from API output/events, not hard-coded.

## Hard Rules

- No mock data in the UI.
- No fake "connected" state.
- No synthetic sample run shown as if real.
- If using the latest proof run as a convenience default, label it as a real proof run ID.
- If the API request fails, show the exact failure and keep the empty state honest.
- Do not add a frontend build system for this lane. The deliverable is a simple static HTML file.

## Recommended Stack

- Single HTML file.
- Tailwind CSS v4 browser CDN:

```html
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
```

- Use plain JavaScript modules for API calls and rendering.
- Use CSS transitions or a tiny browser animation library only if it materially improves clarity.
- Avoid React/Framer Motion unless you intentionally bring React via CDN inside the same file. For this deliverable, plain JS is probably faster and less fragile.

## UX Shape

### 1. Top Bar

Purpose: orient the operator immediately.

Include:

- Product name: `ABRT L2/L3 Control Room`
- Environment selector/input: API base URL, default `http://127.0.0.1:8093`
- Run ID input, default latest proof run ID
- Buttons:
  - Load run
  - Refresh
  - Approve pending writes
  - Reject / request edit, disabled unless relevant
- Connection status:
  - healthy
  - unreachable
  - API error
  - stale data

Success criteria:

- Operator can paste a run ID and load real data.
- If `/health` fails, the UI says so clearly.
- No UI state implies success unless the backend returned it.

### 2. Run Summary Band

Purpose: make status visible in five seconds.

Show:

- Run status: completed / running / waiting approval / failed / cancelled
- Playbook key
- Goal
- Created/updated timestamps if present
- Diagnosis summary
- "Improvement needed" flag if diagnosis says so
- Number of tasks, artifacts, evals, events, proposals

Visual treatment:

- Status pill with restrained color.
- Compact cards, not marketing hero cards.
- Dense operational layout.

Success criteria:

- A founder can see whether the run worked without opening JSON.
- A developer can see whether the next action is approval, fix, or rerun.

### 3. P1 Funnel Metrics

Purpose: show the P1 business result.

Read from `run.output.metrics` if available.

Show:

- Raw leads
- Normalized leads
- Triage qualified
- Gateway approved
- Gateway rejected
- Drafted
- Data Lake written
- Sheet written
- Outreach Master written
- Eval passed

Suggested layout:

- Horizontal funnel: `Raw -> Normalized -> Qualified -> Approved -> Drafted -> Synced`
- Each stage shows count and conversion percentage from previous stage.
- Red/yellow indicators only for real failed or zero-critical stages.

Success criteria:

- For run `643eaceb...`, the UI shows `30 -> 30 -> 30 -> 10 -> 10`.
- It shows `Sheet 10`, `Data Lake 30`, `Outreach Master 10`.

### 4. Timeline / Work Orders

Purpose: make the L2/L3 process inspectable.

Show tasks in order:

- worker profile
- task type
- status
- artifact type
- eval result if attached
- failure context if failed

Show events in a collapsible timeline:

- `p1_workflow_started`
- `task_created`
- `task_completed`
- `p1_external_sync_waiting_approval`
- `p1_outreach_master_sync_waiting_approval`
- `p1_metrics_report_created`
- `run_diagnosis_created`
- `p1_checkpoint_reused`

Success criteria:

- A failed run tells the operator exactly which worker failed.
- A resumed run visibly shows checkpoint reuse events.
- A completed run shows all major stages without scrolling through raw JSON first.

### 5. Artifacts Panel

Purpose: expose what the system produced.

Tabs:

- Lead candidates
- Normalized leads
- Triage scores
- Dossiers
- Live intelligence
- Gateway evaluations
- Forge queue
- Outreach drafts
- Approval package
- Sync results
- Metrics report
- Diagnosis

Behavior:

- Each tab reads real artifacts from `run.artifacts`.
- JSON viewer should be readable, collapsible, and copyable.
- For outreach drafts, render human-friendly cards with:
  - name
  - LinkedIn URL
  - draft text
  - claims
  - evidence URLs
  - publish flag

Success criteria:

- The 10 generated outreach drafts can be read without opening the raw JSON file.
- Evidence URLs are clickable.
- `publish: false` is visible.

### 6. Approval Preview

Purpose: make external writes safe.

When a run is `waiting_approval`, show:

- Which external actions are requested:
  - Google Sheets append
  - Outreach Master append
  - Data Lake write, if relevant
- Which worker will execute the action.
- What rows/drafts/files are expected to be written if preview data exists.
- A prominent approval boundary: "This changes external state."

Buttons:

- Approve
- Reject
- Request edit

Important:

- The UI should call `POST /runs/{id}/control`.
- It should not fake a local approval.
- After approval, reload the run and show the resulting sync artifacts.

Success criteria:

- A `waiting_approval` run can be approved from the UI against a real backend.
- After approval, the UI updates to completed and shows actual sync result.

### 7. Self-Improvement / Learning Panel

Purpose: connect this UI to the "system learns from work" thesis.

Show:

- Diagnosis summary
- Root cause
- Evidence
- Improvement proposals
- Proposal status
- Proposal risk
- Verification plan
- Failure learnings if exposed

Success criteria:

- A failed run does not look like a vague failure.
- The UI shows "what the system understood" separately from raw logs.

### 8. Real Proof View

Purpose: presentation mode.

Create a compact mode or section called `Founder Proof`.

Show:

- Latest real P1 proof run ID
- Funnel metrics
- Output locations:
  - Google Sheet URL
  - Data Lake path
  - Outreach Master path
- Evaluation result
- Diagnosis
- "No fake data" note in calm professional language

Success criteria:

- This can be opened in a call and explained in under two minutes.

## Implementation Checklist

- [ ] Create branch `feat/p1-control-room-html` from fresh `main`.
- [ ] Add `docs/ui/p1-control-room.html`.
- [ ] Add static layout with Tailwind v4 browser CDN.
- [ ] Add API base URL input.
- [ ] Add run ID input.
- [ ] Add `loadRun(runId)` real fetch flow.
- [ ] Add `/health` check.
- [ ] Add status summary rendering.
- [ ] Add P1 metrics funnel rendering.
- [ ] Add tasks table.
- [ ] Add events timeline.
- [ ] Add artifacts tab viewer.
- [ ] Add outreach draft card renderer.
- [ ] Add diagnosis/proposals panel.
- [ ] Add approval controls for `waiting_approval`.
- [ ] Add explicit error states for failed API calls.
- [ ] Add no-data states that say what is missing.
- [ ] Test against real local or server API.
- [ ] Add `docs/ui/README.md` with how to open and use the file.
- [ ] Do not commit generated screenshots unless intentionally needed.

## Manual Verification

Use the already proven run:

```text
643eaceb-4720-481d-a245-8bbd2ff523be
```

Verify:

- [ ] UI loads `/health` from the configured API.
- [ ] UI loads `GET /runs/643eaceb-4720-481d-a245-8bbd2ff523be`.
- [ ] Status shows `completed`.
- [ ] Metrics show:
  - raw leads `30`
  - gateway approved `10`
  - drafted `10`
  - sheet written `10`
  - data lake written `30`
  - outreach master written `10`
- [ ] Eval shows passed with score `1.0`.
- [ ] Diagnosis says no incidents or failed evals.
- [ ] Outreach drafts are readable as cards.
- [ ] Sheet link is visible.

Optional real approval verification:

- Start a new P1 run that stops at `waiting_approval`.
- Open it in the UI.
- Confirm approval preview shows exact external actions.
- Click approve.
- Confirm the backend returns `completed`.
- Confirm sync result appears after reload.

## Acceptance Criteria

The UI lane is complete when:

- [ ] A single static HTML file exists and opens locally.
- [ ] It uses real API calls, not embedded fake run data.
- [ ] It can inspect a completed P1 run end to end.
- [ ] It can inspect a failed or waiting-approval run without crashing.
- [ ] It shows P1 funnel metrics, tasks, events, artifacts, diagnosis, and outreach drafts.
- [ ] It can perform approval through the real API.
- [ ] It fails visibly when API/backend is missing.
- [ ] It does not modify backend/runtime/registry code.

## Merge Plan

Before merging with Altinay's backend branch:

- Rebase UI branch on latest `main`.
- Resolve only docs/UI conflicts.
- Re-test the UI against the latest backend API.
- If Altinay changes output fields, adapt the UI to read the new fields but keep backward assumptions out of the backend.

Expected conflict risk: low.

