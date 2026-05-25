# L2-L3 Protocol Runtime Setup

This runtime keeps protocol memory outside Hermes built-in memory:

- working memory: Postgres
- episodic memory: agentmemory REST sidecar
- semantic memory: Mem0 library with local Qdrant
- procedural memory: Git-backed `registries/`

## Local setup

1. Create `.env` from `.env.example` and fill local secrets.
2. Start the self-hosted stack:

```sh
docker compose up --build
```

3. Create a generic run through the API:

```sh
curl -X POST http://localhost:8080/runs \
  -H 'content-type: application/json' \
  -d '{
    "process_key": "build-in-public",
    "goal": "Turn today protocol implementation progress into build-in-public drafts.",
    "inputs": {
      "signals": [
        "Created Postgres working-memory state store",
        "Added agentmemory episodic adapter",
        "Added Mem0 semantic adapter backed by Qdrant"
      ],
      "channels": ["x", "linkedin", "github"]
    },
    "require_human_approval": true
  }'
```

Logs are written as JSONL under `logs/`.

## Registry marketplace

The runtime uses the database-backed marketplace as the source of truth. `registries/` is only explicit seed data for setup.

Seed the database-backed registry from YAML:

```sh
curl -X POST http://localhost:8080/registry/sync/yaml
```

Inspect marketplace entries:

```sh
curl http://localhost:8080/registry/worker
curl http://localhost:8080/registry/eval/build-in-public-draft-quality
```

Supported registry kinds are:

- `tool`
- `worker`
- `eval`
- `process_pack`
- `failure_pattern`

Registry changes that alter executable behavior stay approval-gated. Safe metadata/stat updates can auto-apply; worker/tool installs, entrypoints, side-effect policies, process behavior, and eval threshold loosening require explicit approval through the change-candidate API.

There is no runtime fallback from the marketplace to YAML. If registry data is missing, the runtime fails explicitly; run the sync command or fix the registry state.
