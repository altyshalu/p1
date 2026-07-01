# P1 Team Runbook

This is the shared operating path for finding suitable angel investors with the real P1 pipeline. Everyone should run P1 through the same playbook, the same proof scripts, and the same input JSON shape.

## Runtime Owner

The main runtime is the FastAPI process started by `uv run l2l3-protocol` or by the `app` service in `docker-compose.yml`.

P1 is not a standalone scraper. The API creates a `p1-operator-outreach` run, `ProcessRuntime` executes the P1 worker sequence, and the workers write artifacts back to the run store. Scripts under `scripts/real-p1-*.py` are the operator controls around that runtime.

## Standard Server Start

Start the shared runtime:

```sh
docker compose up --build
```

The API listens on `http://127.0.0.1:8080`.

For a local non-Docker run, start dependencies first, then run:

```sh
uv sync
uv run l2l3-protocol
```

Check that the runtime is alive:

```sh
curl http://127.0.0.1:8080/health
```

## Required Environment

Copy `.env.example` to `.env` and fill the real keys needed for the mode you run.

For source-only angel discovery:

- `GEMINI_API_KEY`
- `EXA_API_KEY` when `sources` contains `exa`
- `APIFY_API_TOKEN` when `sources` contains any `apify_*` source

For full outreach and external writes:

- all source-only keys
- `GOOGLE_SA_PATH` and `P1_GOOGLE_SHEET_ID` for Google Sheets
- `P1_OUTREACH_MASTER_PATH` for outreach-master sync
- `P1_DOSSIER_OUTPUT_PATH` for data-lake dossier sync

The readiness script fails if required keys, paths, or provider permissions are missing. Do not bypass readiness.

## Canonical Commands

Run a preflight:

```sh
uv run python scripts/run-p1-team.py preflight \
  --inputs-json examples/p1-europe-angel-search.source-only.json
```

Find and score Europe-only angels without external writes:

```sh
uv run python scripts/run-p1-team.py source-only \
  --inputs-json examples/p1-europe-angel-search.source-only.json
```

Run the full approval-gated outreach pipeline:

```sh
uv run python scripts/run-p1-team.py full \
  --inputs-json examples/p1-europe-angel-search.full.json
```

Approve writes only after reviewing the P1 external action preview:

```sh
uv run python scripts/run-p1-team.py full \
  --inputs-json examples/p1-europe-angel-search.full.json \
  --approve
```

## Angel Search Policy

Use `source_only` first when the goal is to find suitable angels. It runs:

1. source collection per provider,
2. source merge and dedupe,
3. lead normalization,
4. P1 triage scoring,
5. dossier writing,
6. metrics summary.

Use `full_pipeline` only when you also need live intelligence, gateway evaluation, outreach drafts, quality judging, and approval-gated sync.

For Europe searches, keep the query explicit about Europe and exclude Cyprus in the query when Cyprus must not be included. Keep `use_provider_cache=true` so repeated team runs reuse provider responses instead of spending credits unnecessarily. Set `force_rerun=true` only when you intentionally want fresh provider calls.

## Output Review

Every run exposes a compact summary:

```sh
curl http://127.0.0.1:8080/runs/<run-id>/summary
```

For full runs, P1 writes a preview artifact before external writes. Review that preview first, then approve through the API or the team wrapper with `--approve`.

## Do Not

- Do not paste manually found leads into production sheets and call it P1.
- Do not skip `scripts/real-p1-readiness.py`.
- Do not write to Google Sheets without approval preview.
- Do not run different private payload shapes for the same team workflow.
