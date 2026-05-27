# Development Guide

This guide is for developers joining the repository.

## First-Time Setup

Clone:

```sh
git clone git@github.com:ABRTAI-C/l2l3-protocol.git
cd l2l3-protocol
```

Install dependencies:

```sh
uv sync --all-groups
```

Create `.env`:

```sh
cp .env.example .env
```

Fill real provider keys in `.env`:

- `DEEPSEEK_API_KEY`
- `GEMINI_API_KEY` if memory is enabled

Start dependencies:

```sh
docker compose up -d postgres qdrant agentmemory
```

Run migrations:

```sh
uv run alembic upgrade head
```

Start API:

```sh
uv run l2l3-protocol
```

Seed Taskforce Hub:

```sh
curl -X POST http://localhost:8080/hub/sync/yaml
```

## Full Docker Run

Build and start all services:

```sh
docker compose up -d --build
```

The API is exposed at:

```text
http://localhost:8080
```

Postgres is exposed on:

```text
localhost:5434
```

Inside Docker, services use:

```text
postgres:5432
qdrant:6333
agentmemory:3111
```

## Common Commands

Run tests:

```sh
uv run pytest
```

Run one test file:

```sh
uv run pytest tests/test_process_runtime.py
```

Generate migration SQL:

```sh
uv run alembic upgrade head --sql
```

Apply migrations:

```sh
uv run alembic upgrade head
```

Inspect Docker services:

```sh
docker compose ps
```

Follow API logs:

```sh
docker compose logs -f app
```

## Adding A Worker

1. Add or update a worker implementation in `src/l2l3_protocol/workers/`.
2. Add a worker profile YAML file in `registries/worker-profiles/`.
3. Define input and output schemas.
4. Define retry policy.
5. Define External Action policy.
6. Add compatible tool ids.
7. Add tests for the worker path.
8. Sync Hub from YAML in local runtime:

```sh
curl -X POST http://localhost:8080/hub/sync/yaml
```

## Adding A Tool

1. Add tool metadata in `registries/tools/`.
2. Set `external_action_class`.
3. Set auth requirements.
4. Set toolset name.
5. Add the tool id to compatible workers.
6. Add the tool id to allowed Playbooks.
7. Add tests for allowed and denied tool usage.

## Adding A Playbook

1. Create `registries/playbooks/<playbook-key>/playbook.yaml`.
2. Define allowed workers and tools.
3. Define required inputs.
4. Define completion criteria.
5. Define required eval keys if quality gates are needed.
6. Add or update integration tests.
7. Document the intended run path.

## Adding An Eval

1. Add eval YAML in `registries/evals/`.
2. Set `eval_type`: `unit`, `outcome`, or `drift`.
3. Set `minimum_score` or `pass_threshold`.
4. Add checks and expected payload fields.
5. Wire the eval through a worker `grader_spec`.
6. Test that Runtime enforces the Hub threshold.

## Database Rules

Use Alembic migrations for structural changes.

Do not avoid migrations by hiding production state in generic JSON fields.

After changing models:

```sh
uv run alembic upgrade head --sql
uv run alembic upgrade head
uv run pytest
```

## Runtime Honesty Rules

If a real dependency is missing, fail explicitly.

Do not add:

- fallback behavior
- fake runtime data
- demo-only flows
- hidden alternate tools
- synthetic success responses
- compatibility layers that keep old names alive

Tests may use fixtures and fakes only when they are clearly test-only.

## Self-Improvement Proof Rules

Run diagnosis and improvement proposals are production behavior, not demo output.

Fast unit tests may cover the analyzer and API contracts, but release proof for these features must use a real end-to-end run:

```sh
docker compose up -d postgres qdrant agentmemory
uv run alembic upgrade head
uv run l2l3-protocol
curl -X POST http://localhost:8080/hub/sync/yaml
uv run l2l3-live start trend-radar \
  --query "AI agent evals runtime observability memory" \
  --provider github \
  --provider arxiv \
  --provider huggingface \
  --channel x
```

The proof is valid only when the run uses real Postgres, real Hermes/model credentials, real source APIs, and real runtime workers. If any required service or credential is missing, the proof must fail explicitly. Do not replace it with mocks, fakes, simulations, embedded example responses, or synthetic provider data.
