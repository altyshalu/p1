# Cross-Process Real Testing

Use these commands when validating that the runtime is ready for more than one Playbook.

## Baseline Infra

```sh
uv run pytest -q
docker compose up -d postgres qdrant agentmemory
uv run alembic upgrade head
uv run l2l3-protocol
curl -X POST http://localhost:8080/hub/sync/yaml
curl http://localhost:8080/health
curl http://localhost:8080/runtime/capabilities
```

## Readiness

Trend radar:

```sh
uv run python scripts/real-playbook-readiness.py   --api-url http://localhost:8080   --playbook-key build-in-public-trend-radar   --inputs-json '{"query":"agent runtime eval memory","providers":["github","arxiv","huggingface"],"channels":["x"],"max_results":2}'
```

Manual build-in-public:

```sh
uv run python scripts/real-playbook-readiness.py   --api-url http://localhost:8080   --playbook-key build-in-public   --inputs-json '{"signals":["Implemented evidence-backed review CLI","Added regression catalog rerun command"],"channels":["x"]}'
```

## Acceptance

Trend radar:

```sh
uv run python scripts/real-playbook-acceptance.py   --api-url http://localhost:8080   --playbook-key build-in-public-trend-radar   --goal 'Real acceptance for trend-radar cross-process readiness'   --inputs-json '{"query":"agent runtime eval memory","providers":["github","arxiv","huggingface"],"channels":["x"],"max_results":2}'
```

Manual build-in-public:

```sh
uv run python scripts/real-playbook-acceptance.py   --api-url http://localhost:8080   --playbook-key build-in-public   --goal 'Real acceptance for build-in-public cross-process readiness'   --inputs-json '{"signals":["Implemented evidence-backed review CLI","Added regression catalog rerun command"],"channels":["x"]}'
```

## Review And Reporting

```sh
uv run python scripts/real-system-review.py recent --api-url http://localhost:8080 --since-hours 24 --format markdown
uv run python scripts/real-system-review.py learned --api-url http://localhost:8080 --since-hours 24 --format markdown
uv run python scripts/real-system-review.py regressions --api-url http://localhost:8080 --playbook-key build-in-public-trend-radar
```

## Regression Replay

```sh
uv run python scripts/real-regression-cases.py list --api-url http://localhost:8080
uv run python scripts/real-regression-cases.py rerun --api-url http://localhost:8080 --limit 5
```

## Rules

1. No mocks for operational proof.
2. No fallback success path.
3. If the second Playbook is missing or broken, record the exact blocker instead of pretending readiness.
