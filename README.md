# L2/L3 Protocol Runtime

ABRT L2/L3 Protocol is an active-inference runtime where an L2 supervisor coordinates bounded L3 workers through typed Work Orders, registered Playbooks, eval gates, retry policy, Incident Briefs, and a database-backed Taskforce Hub.

The current product is not a marketplace. Taskforce Hub is the internal source of truth for approved workers, tools, evals, playbooks, and failure patterns. Public/community marketplace mechanics are intentionally out of scope for this repository right now.

## Core Ideas

- **L2 supervisor** decides what should happen next inside a Playbook.
- **L3 workers** execute bounded Work Orders and return structured artifacts.
- **Playbooks** define the mission boundary: allowed workers, allowed tools, required inputs, eval gates, completion criteria, and External Action rules.
- **Taskforce Hub** stores approved capabilities in Postgres, seeded from `registries/`.
- **Runtime** enforces schemas, tool policy, External Action policy, eval thresholds, retry budgets, and failure learning.
- **Design Mode** lets L2 propose a new Playbook when the current task is discovery, not delivery.
- **Execution Mode** runs a known Playbook deterministically through registered capabilities.

## Repository Map

```text
src/l2l3_protocol/
  api/                 FastAPI app, run control, Hub API
  core/                Pydantic schemas and terminology
  db/                  SQLAlchemy models, store, migrations
  hub/                 Taskforce Hub registry loading and change policy
  live/                Textual TUI for live run observation
  memory/              memory adapters
  runtime/             L2 supervisor, Design Mode, Runtime, L3 executor, Work Order enforcement
  workers/             built-in worker entrypoints

registries/
  playbooks/           YAML seed Playbooks
  worker-profiles/     YAML seed worker profiles
  tools/               YAML seed tool metadata
  evals/               YAML seed eval specs
  failure-patterns/    YAML seed known failure patterns

docs/                  architecture, setup, glossary, brainstorms, QA notes
alembic/               database migrations
tests/                 unit and integration tests
```

## Prerequisites

- Python `3.13`
- `uv`
- Docker / Docker Compose
- Git
- API keys for the real LLM providers you intend to use

Recommended local provider setup:

- `DEEPSEEK_API_KEY` for Hermes/L2/L3 execution
- `GEMINI_API_KEY` for mem0 embeddings/LLM memory if memory is enabled

Do not commit real secrets. `.env` is ignored by git.

## Environment

Create a local environment file:

```sh
cp .env.example .env
```

Required baseline variables:

```env
ENVIRONMENT=local
LOG_LEVEL=INFO
DATABASE_URL=postgresql+asyncpg://l2l3:l2l3@localhost:5434/l2l3_protocol

AGENTMEMORY_BASE_URL=http://localhost:3111
AGENTMEMORY_SECRET=
AGENTMEMORY_ENABLED=true

MEM0_ENABLED=true
MEM0_QDRANT_HOST=localhost
MEM0_QDRANT_PORT=6333
MEM0_COLLECTION_NAME=l2l3_semantic_memory
MEM0_LLM_PROVIDER=gemini
MEM0_LLM_MODEL=gemini-2.5-flash
MEM0_EMBEDDER_PROVIDER=gemini
MEM0_EMBEDDER_MODEL=models/gemini-embedding-001
MEM0_EMBEDDING_DIMS=768
GEMINI_API_KEY=

HERMES_ENABLED=true
HERMES_MODEL=deepseek-v4-pro
HERMES_MAX_ITERATIONS=20
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com

PROCEDURAL_REGISTRY_PATH=registries
```

Local Postgres is exposed on host port `5434` to avoid common conflicts with other local databases. Inside Docker Compose, services still talk to Postgres on `postgres:5432`.

## Setup

Install dependencies:

```sh
uv sync --all-groups
```

Start infrastructure:

```sh
docker compose up -d postgres qdrant agentmemory
```

Run migrations:

```sh
uv run alembic upgrade head
```

Start the API locally:

```sh
uv run l2l3-protocol
```

In another terminal, seed Taskforce Hub from YAML:

```sh
curl -X POST http://localhost:8080/hub/sync/yaml
```

Check health:

```sh
curl http://localhost:8080/health
```

## Running a Real Pipeline

Start a real Trend Radar run:

```sh
uv run l2l3-live start trend-radar \
  --query "agent memory systems" \
  --provider github \
  --provider arxiv \
  --provider huggingface \
  --channel x
```

Watch an existing run:

```sh
uv run l2l3-live watch <run-id>
```

The TUI shows run status, Work Orders, evals, Incident Briefs, approval prompts, and separate scrollable views for long draft/event content.

## Running P1 Operator Outreach

`p1-operator-outreach` is the migrated ABRT/Limpid operator and angel outreach pipeline. It uses real P1 dossiers or real source providers, creates bounded Work Orders, stores canonical runtime artifacts, evaluates grounded outreach drafts, and stops at approval before external action.

Existing real dossier migration proof:

```sh
uv run python scripts/real-playbook-acceptance.py \
  --api-url http://localhost:8080 \
  --playbook-key p1-operator-outreach \
  --goal "P1 existing dossier migration proof" \
  --inputs-json '{"mode":"existing_dossiers","limit":1,"dossier_source_path":"/root/sovereign-os/OS_Core/Data_Lake/Dossiers","only_awaiting_outreach":true,"allow_google_sheet_write":false,"require_human_approval":true}'
```

Full sourcing proof requires real `EXA_API_KEY`, `APIFY_API_TOKEN`, `GEMINI_API_KEY`, and Google Sheets credentials when sheet sync is enabled. Crunchbase sourcing uses the Apify Store actor `parseforge/crunchbase-scraper` by default; pass `crunchbase_actor_id` only when deliberately switching to another real actor. Missing credentials or actor permissions fail explicitly; the runtime must not substitute demo leads or old scripts.

Latest real proof notes: [docs/p1-l2l3-real-proof-2026-05-29.md](docs/p1-l2l3-real-proof-2026-05-29.md).

## Current Self-Improvement Loop

The current hardened dogfood path is `build-in-public-trend-radar`.

It exercises the L2/L3 protocol against real source APIs:

1. L2 creates bounded Work Orders.
2. L3 workers collect, deduplicate, score, draft, normalize, edit, and evaluate.
3. Runtime stores tasks, artifacts, evals, events, Incident Briefs, and diagnosis.
4. Failed or low-quality runs create evidence-backed improvement proposals.
5. Serious behavior changes require approval.
6. Approved proposals can be implemented through the controlled implementation worker.
7. Before/after proof reruns a comparable real workflow and marks the proposal `proven` only when the original failure signature is absent.

Useful endpoints:

```sh
curl http://localhost:8080/failure-learnings
curl http://localhost:8080/runtime/capabilities
curl http://localhost:8080/improvement-proposals
curl -X POST http://localhost:8080/system-reviews/recent \
  -H 'content-type: application/json' \
  -d '{"limit":20,"playbook_key":"build-in-public-trend-radar"}'
curl -X POST http://localhost:8080/improvement-proposals/<proposal-id>/approve
curl -X POST http://localhost:8080/improvement-proposals/<proposal-id>/implement
```

Real before/after proof:

```sh
uv run python scripts/real-before-after-proof.py \
  --api-url http://localhost:8080 \
  --baseline-run-id <baseline-run-id> \
  --proposal-id <implemented-proposal-id>
```

Known proven milestone:

- Hugging Face provider-no-results in Trend Radar was diagnosed, proposed, approved, implemented, and proven through a real comparable run.

Cross-process real test runbook: `docs/cross-process-testing.md`

## API Basics

Create an Execution Mode run:

```sh
curl -X POST http://localhost:8080/runs \
  -H 'content-type: application/json' \
  -d '{"playbook_key":"build-in-public","l2_mode":"execution","goal":"<real goal>","inputs":{"signals":["<real signal>"],"channels":["x"]}}'
```

Create a Design Mode run:

```sh
curl -X POST http://localhost:8080/runs \
  -H 'content-type: application/json' \
  -d '{"playbook_key":"<new-playbook-key>","l2_mode":"design","goal":"<real design goal>","inputs":{}}'
```

Hub endpoints:

```sh
curl http://localhost:8080/hub/playbook
curl http://localhost:8080/hub/worker
curl http://localhost:8080/hub/tool
curl http://localhost:8080/hub/eval
curl http://localhost:8080/hub/failure-pattern
```

## Tests

Run the full test suite:

```sh
uv run pytest
```

Generate migration SQL without applying it:

```sh
uv run alembic upgrade head --sql
```

Apply migrations to the real local Postgres:

```sh
uv run alembic upgrade head
```

## Safety Rules

This repository has a strict trust boundary:

- No demos unless explicitly requested.
- No fallbacks unless explicitly requested.
- No mocks outside tests.
- No synthetic runtime data presented as real behavior.
- No silent degraded paths.
- No legacy compatibility layers by default.
- If something required is missing, fail explicitly and fix the primary path.

## Key Docs

- [Architecture](docs/architecture.md)
- [Development Guide](docs/development.md)
- [Runtime Setup](docs/runtime-setup.md)
- [Parallel L2/L3 Hardening Plan](docs/plans/2026-05-27-parallel-l2l3-hardening-plan.md)
- [Glossary](docs/glossary.md)
- [L2 Runtime Modes](docs/l2-runtime-modes.md)
- [Build-in-Public System Spec](docs/build-in-public-system-spec-v1.md)
- [L2/L3 Architecture QA](docs/qa-sessions/2026-05-25-l2-l3-architecture-qa.md)

## Contribution Workflow

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a branch or PR.

Short version:

- Do not push directly to `main`.
- Organization members create feature branches.
- External contributors fork first.
- Keep changes small and commit using Conventional Commits.
- Run tests before asking for review.
- Leave the branch/PR for owner review before merge.
