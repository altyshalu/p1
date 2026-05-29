# P1 L2/L3 Real Proof, 2026-05-29

This note records the current state of real proof for the hardened P1 operator outreach backend on the server. It is intentionally evidence-oriented: no mock run, synthetic provider response, fallback path, or demo dataset counts as proof here.

## What Is Now Hardened

The P1 backend now includes these production-facing hardening changes:

- per-source resume via `p1_source_batch` plus `p1-source-merger`
- approval preview artifact `p1_external_action_preview`
- idempotent Google Sheets, Outreach Master, and Data Lake writes keyed by `run_id + lead_id`
- duplicate-skipped events for external syncs
- compact backend summary endpoint `GET /runs/{id}/summary`
- task timing fields `started_at`, `completed_at`, and `duration_ms`
- operator readiness and proof scripts for preflight, proof-pack, full flow, cache proof, and idempotency proof

## Verified On The Server

### 1. API Runtime Is Live

Checked on `127.0.0.1:8000`.

Observed:

- `GET /health` returned `{"status":"ok","service":"l2l3-protocol"}`
- `GET /runtime/capabilities` returned Hermes and memory capability data successfully

### 2. Backend Test Coverage Is Green

Targeted hardening slice:

```sh
uv run pytest tests/test_api_surface.py tests/test_process_runtime.py tests/test_p1_operator_worker.py -q
```

Result:

```text
31 passed in 4.09s
```

Full repository:

```sh
uv run pytest -q
```

Result:

```text
121 passed in 8.51s
```

### 3. Real Proof Scripts Are Executable

Validated on the server:

```sh
python3 scripts/real-p1-readiness.py --help
python3 scripts/real-p1-proof-pack.py --help
python3 scripts/real-p1-full-proof.py --help
python3 scripts/real-p1-cache-proof.py --help
python3 scripts/real-p1-idempotency-proof.py --help
```

All five scripts compiled and exposed the expected operator flags.

## Current Real-World Blocker

The server does not currently have the full P1 credential set configured.

Observed from `.env` on the server:

- `GEMINI_API_KEY`: set
- `EXA_API_KEY`: missing
- `APIFY_API_TOKEN`: missing
- `GOOGLE_SA_PATH`: missing
- `P1_GOOGLE_SHEET_ID`: missing
- `P1_OUTREACH_MASTER_PATH`: missing
- `P1_DOSSIER_OUTPUT_PATH`: missing
- `P1_DOSSIER_SOURCE_PATH`: missing

Because of that, full external real proof cannot be claimed yet.

## Explicit Failure Proof

The new proof scripts and hardened runtime were exercised against the live API to confirm explicit failure behavior instead of silent fallback.

### Readiness Preflight Against Live API

Command used:

```sh
python3 scripts/real-p1-readiness.py   --base-url http://127.0.0.1:8000   --env-file .env   --mode full_pipeline
```

Observed outcome:

- Health check passed
- Runtime capabilities request passed
- Hub sync and required registry keys were present
- Readiness failed explicitly with `missing_required_keys=["APIFY_API_TOKEN"]`
- No fallback sourcing or silent downgrade path was used

### Proof-Pack Against Live API

Command used:

```sh
python3 scripts/real-p1-proof-pack.py   --base-url http://127.0.0.1:8000   --env-file .env   --mode full_pipeline
```

Observed outcome:

- Overall status: `fail_external_config`
- Readiness step reported the real blocker `APIFY_API_TOKEN`
- Downstream proof steps were skipped because operator inputs were not supplied
- The pack makes the current proof matrix explicit instead of hiding missing prerequisites

### Source-Only Proof Without Apify Credential

Command used:

```sh
python3 scripts/real-p1-cache-proof.py   --base-url http://127.0.0.1:8000   --inputs-json /tmp/p1_source_only_inputs.json
```

Observed outcome:

- Run status: `failed`
- Worker: `p1-source-collector`
- Explicit error: `missing required environment variable: APIFY_API_TOKEN`
- Diagnosis created with real run evidence
- Improvement proposal was created instead of pretending success

### Existing-Dossier Proof Without Dossier Path

Command used:

```sh
python3 scripts/real-p1-full-proof.py   --base-url http://127.0.0.1:8000   --inputs-json /tmp/p1_existing_inputs.json
```

Observed outcome:

- Run status: `failed`
- Worker: `p1-dossier-reader`
- Explicit error: `missing required input: dossier_source_path`
- Diagnosis created with real run evidence
- No fallback path was used

## Operational Meaning

P1 backend hardening is implemented, tested, and ready to run for real. What remains before claiming a fresh full external proof is not backend code work, but operational configuration:

- set the missing provider credentials
- set the missing sheet and file-system paths
- run the full proof script again with real inputs and approvals enabled where needed

Once those values are configured, the new proof scripts are ready to verify:

- health and runtime capabilities
- full P1 execution path
- approval preview generation
- summary endpoint output
- cache-hit evidence on a second comparable run
- duplicate-skip evidence on repeated approval
