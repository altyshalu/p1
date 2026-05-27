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
    "playbook_key": "build-in-public",
    "l2_mode": "execution",
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

The live dashboard syncs the YAML registry into the database, creates a `build-in-public-trend-radar` run, and opens a full-screen terminal UI with a compact main dashboard. Heavy content such as drafts and event payloads opens in separate scrollable Markdown windows. It does not mutate runtime logic; it only watches and sends explicit user replies or approval commands.

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

## Diagnosis And Self-Improvement

Fetch a completed, failed, or blocked run:

```sh
curl http://localhost:8080/runs/<run_id>
```

The run payload includes diagnosis, improvement proposals, and failure learnings when available.

List active lessons from real work:

```sh
curl http://localhost:8080/failure-learnings
```

Review recent real runs:

```sh
curl -X POST http://localhost:8080/system-reviews/recent \
  -H 'content-type: application/json' \
  -d '{"limit":20,"playbook_key":"build-in-public-trend-radar"}'
```

Approve and implement a supported proposal:

```sh
curl -X POST http://localhost:8080/improvement-proposals/<proposal-id>/approve
curl -X POST http://localhost:8080/improvement-proposals/<proposal-id>/implement
```

Run real before/after proof:

```sh
uv run python scripts/real-before-after-proof.py \
  --api-url http://localhost:8080 \
  --baseline-run-id <baseline-run-id> \
  --proposal-id <implemented-proposal-id>
```

This proof path must use real services. If Postgres, Hermes/model credentials, source APIs, or required registry data are missing, the proof should fail explicitly.

## Taskforce Hub

The Runtime uses the database-backed Taskforce Hub as the source of truth. `registries/` is only explicit seed data for setup.

Seed the database-backed Hub from YAML:

```sh
curl -X POST http://localhost:8080/hub/sync/yaml
```

Inspect Hub entries:

```sh
curl http://localhost:8080/hub/worker
curl http://localhost:8080/hub/eval/build-in-public-draft-quality
curl http://localhost:8080/hub/playbook/build-in-public-trend-radar
```

Supported Hub kinds are:

- `tool`
- `worker`
- `eval`
- `playbook`
- `failure_pattern`

Hub changes that alter executable behavior stay approval-gated. Safe metadata/stat updates can auto-apply; worker/tool installs, entrypoints, external-action policies, Playbook behavior, and eval threshold loosening require explicit approval through the change-candidate API.

The Runtime never reads YAML as an alternate source after startup. If Hub data is missing, the Runtime fails explicitly; run the sync command or fix the Hub state.
