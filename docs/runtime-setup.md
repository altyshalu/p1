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

## Live run dashboard

Run the API server first:

```sh
uv run l2l3-protocol
```

In another terminal, start a real trend-radar run. Source collection is the first L3 task inside the pipeline:

```sh
uv run l2l3-live start trend-radar \
  --query "agent evaluation runtime" \
  --provider github \
  --provider arxiv \
  --provider huggingface \
  --channel x
```

The live CLI does not ship embedded source data. It passes the real query/providers into the run; L2 must create a `trend-source-collector` task, and that worker calls the allowed read-only tools for GitHub, arXiv, and Hugging Face. If a provider request fails or returns no usable results, the task fails explicitly.

The live dashboard syncs the YAML registry into the database, creates a `build-in-public-trend-radar` run, and opens a full-screen terminal UI with scrollable pipeline, draft, eval, event, and user-input panes. It does not mutate runtime logic; it only watches and sends explicit user replies or approval commands.

Watch an existing run:

```sh
uv run l2l3-live watch <run_id>
```

Controls:

- `f`: toggle compact/full event payloads.
- `F2`: open the current L2 prompt or approval gate in a large scrollable Markdown window.
- `F3`: open drafts in a large scrollable Markdown window.
- `F4`: open events in a large scrollable Markdown window.
- `r`: force refresh.
- `q`: quit the watcher only; the run keeps its current backend state.
- When `waiting_user`: type the L2 answer in the input bar and press Enter.
- When `waiting_approval`: type `approve`, `reject <reason>`, or `edit <message>`.

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
