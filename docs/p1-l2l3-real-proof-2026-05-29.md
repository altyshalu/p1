# P1 L2/L3 Real Proof, 2026-05-29

This note records real proof runs for the P1 operator outreach migration and the adjacent L2/L3 coordination layer. It is intentionally evidence-oriented: no mock run, synthetic provider response, fallback path, or demo dataset counts as proof here.

## What Is Proven

The P1 operator outreach process now runs through the L2/L3 protocol runtime using real worker profiles, real stored run artifacts, real eval results, and real approval boundaries.

The current P1 path supports two practical entry modes:

- Existing ABRT/Limpid dossier migration: read real dossier files, enrich with Exa, evaluate via Gemini, build forge queue, write outreach drafts, run quality eval, stop before external action, then write to Google Sheets only after approval.
- Fresh sourcing: collect real Crunchbase data through Apify, normalize leads, score or dossier them, then continue through the same P1 runtime chain.

## Current Real Provider Coverage

- Gemini: used by the P1 gateway evaluator and outreach draft writer in real P1 runs.
- Exa: used by the P1 live intelligence gatherer in real existing-dossier runs.
- Apify: used by the P1 source collector through the real `parseforge/crunchbase-scraper` actor.
- Google Sheets: used by the P1 external sync worker after explicit approval.
- DeepSeek/Hermes: available on the deployed runtime and exercised by the real trend-radar L2 supervisor path.

## Proof Runs

### 1. Crunchbase Through Apify

- Run: `c5e7c0c2-79cf-481f-a9a6-4bd5f2db47bd`
- Playbook: `p1-operator-outreach`
- Mode: `source_only`
- Source: Apify Crunchbase actor
- Status: `completed`
- Evidence:
  - Produced `p1_lead_candidates`.
  - Candidate: Naval Ravikant.
  - Source URL: `https://www.crunchbase.com/person/naval-ravikant`.
  - Headline normalized from real Crunchbase fields: `Founder at AngelList`.
  - Produced downstream normalized leads, triage scores, dossiers, and run diagnosis.
- Diagnosis:
  - Outcome: `completed`.
  - Improvement needed: `false`.

### 2. Full P1 Pipeline From Crunchbase Source

- Run: `cd32fd94-c457-49a8-8a74-ddf69cdda5ef`
- Playbook: `p1-operator-outreach`
- Mode: `full_pipeline`
- Source: Apify Crunchbase actor
- Status: `waiting_approval`
- Evidence:
  - Produced real Crunchbase lead candidates.
  - Produced outreach draft for Naval Ravikant.
  - Draft claims include source URLs and evidence URLs.
  - Quality eval passed.
  - Runtime stopped before external action.
- Diagnosis:
  - Outcome: `waiting_approval`.
  - Root cause: `none`.
  - Improvement needed: `false`.

### 3. Existing Dossier To Google Sheets After Approval

- Run: `1e4930f2-6f1c-46b4-86b0-bc48097b81ef`
- Playbook: `p1-operator-outreach`
- Mode: `existing_dossiers`
- Status before approval: `waiting_approval`
- Status after approval: `completed`
- Evidence:
  - Read a real dossier from `/root/sovereign-os/OS_Core/Data_Lake/Dossiers`.
  - Gathered live intelligence through Exa.
  - Evaluated and drafted outreach with real provider calls.
  - Eval `p1-outreach-draft-quality` passed with score `1.0`.
  - Runtime created `p1_external_sync_waiting_approval` and did not write externally before approval.
  - After `approve`, runtime executed `p1-google-sheets-syncer`.
  - Google Sheets append result: row count `1`, updated range `'04_THE_FORGE_FINAL'!A1665:J1665`.
- Diagnosis:
  - Before approval: `waiting_approval`, no incident.
  - After approval: `completed`, no incident.

### 4. L2/L3 Coordination Edge Case

- Run: `2a497c84-6235-421c-acba-dcafbc873b76`
- Playbook: `build-in-public-trend-radar`
- Status: `waiting_approval`
- Purpose:
  - Real L2/Hermes coordination proof, separate from deterministic P1.
- Evidence:
  - GitHub provider returned real results.
  - Hugging Face initially returned no model results, then L2 repair found dataset results.
  - arXiv hit a real provider limit: timeout followed by HTTP `429 Rate exceeded`.
  - System did not hide the failure or invent source data.
  - System created an improvement proposal for `trend-source-collector/provider:arxiv`.
- Proposal:
  - ID: `6335d124-5fdd-4a9e-9289-7c1b1dad4af1`
  - Type: `improve_tool`
  - Signature: `provider_request_failed:trend-source-collector`
  - Status: `proposed`
  - Approval required before behavior change: `true`

## Verification Commands

Local verification:

```sh
uv run pytest -q
```

Result:

```text
110 passed
```

Server verification after deploy:

```sh
cd /root/l2l3-protocol
/root/.local/bin/uv run pytest -q
```

Result:

```text
110 passed
```

Runtime capability check:

```sh
curl http://127.0.0.1:8093/runtime/capabilities
```

Observed:

```text
Hermes enabled: true
Hermes configured: true
Hermes available: true
Model: deepseek-v4-pro
Memory enabled: true
```

## Presentation Status

P1 is ready to show as a real working ABRT process:

- It executes real operator/angel outreach work.
- It uses real providers.
- It produces persisted artifacts and evals.
- It stops at approval before external writes.
- It writes to the real Google Sheet only after approval.
- It creates run diagnoses.
- It does not silently degrade to fake data.

The broader L2/L3 coordination layer is also demonstrable, with one important caveat: real public providers can rate limit. The current trend-radar proof shows that the system detects this, stores evidence, and creates an approval-gated improvement proposal instead of pretending success.

## Next Hardening Item

The next approved improvement should target arXiv provider behavior in `trend-source-collector`: slower request pacing, clearer rate-limit classification, and a before/after proof run showing that comparable trend-radar runs no longer fail from aggressive arXiv retry behavior.
