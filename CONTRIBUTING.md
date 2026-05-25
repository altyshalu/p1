# Contributing

This project is experimental, but the engineering bar is strict. The runtime must be honest: no fake success, no hidden alternate paths, and no silent degraded behavior.

## Branch Policy

Do not push directly to `main`.

Organization members:

```sh
git checkout -b feat/short-description
```

External contributors:

1. Fork the repository.
2. Create a feature branch in the fork.
3. Open a pull request back to this repository.

Every change should stay on a branch until Nikita reviews it.

## Commit Policy

Use Conventional Commits:

```text
feat(runtime): add design mode proposal artifacts
fix(db): correct work order migration
docs(readme): clarify local setup
test(runtime): cover eval failure repair path
```

Make small logical commits. Do not bundle unrelated refactors, docs, and behavior changes unless they are part of one coherent change.

## Pull Request Checklist

Before requesting review:

- The branch is up to date with `main`.
- The change has a clear purpose.
- Runtime behavior is real, not simulated.
- Required migrations are included.
- New behavior has tests.
- `uv run pytest` passes.
- `.env` and secrets are not committed.
- Docs are updated when terminology, setup, API, or workflow changes.

## No Fallbacks, No Demos, No Mocks

Do not add:

- fallback execution paths
- demo flows
- fake/example runtime data
- synthetic worker outputs
- hidden alternate tools
- silent empty defaults for required config
- mocks outside tests
- legacy compatibility layers unless explicitly approved

Tests can use fixtures and test doubles only when they are clearly test-only and do not present mocked behavior as real runtime behavior.

If a required dependency is missing, the correct behavior is to fail explicitly with a useful error.

## Schema And Migration Rules

Use migrations when the concept requires database structure.

Do not hide production state in run payloads, events, or loose JSON just to avoid a migration.

When renaming concepts:

- rename code symbols
- rename persisted fields
- add migrations for existing data
- update docs
- update tests

## Local Verification

Minimum verification before review:

```sh
uv run pytest
uv run alembic upgrade head --sql
```

When touching migrations or DB config, also verify against local Postgres:

```sh
docker compose up -d postgres
uv run alembic upgrade head
```

When touching API or TUI:

```sh
uv run l2l3-protocol
curl http://localhost:8080/health
curl -X POST http://localhost:8080/hub/sync/yaml
```

## Review Expectations

PR descriptions are part of the work. A reviewer should be able to understand the change without asking for a private walkthrough.

Every PR must include:

- What changed
- Why it changed
- Why this approach was chosen
- What alternatives were considered or rejected
- How the implementation works
- How it was tested
- Proof for bug fixes, such as logs, stack traces, failing test output, screenshots, or reproduction steps
- Evidence for improvements, such as before/after behavior, benchmark output, UX screenshots, run traces, or architectural reasoning
- Any migration or operational impact
- Any explicit risks or follow-up work

Keep PRs focused. If a change starts growing across unrelated areas, split it.

## PR Description Template

Use this structure unless the change is truly tiny.

````md
## Summary

What changed in one or two paragraphs.

## Problem

What was broken, missing, confusing, slow, unsafe, or incomplete.

## Why Now

Why this matters now and what happens if we do not change it.

## Approach

How the solution works. Include the main design decisions, tradeoffs, and rejected alternatives.

## Implementation Notes

Important files, data model changes, API changes, migrations, worker/tool/eval changes, or runtime behavior changes.

## Proof

For bugs:
- reproduction steps
- failing logs, stack traces, screenshots, or test output before the fix
- passing logs or test output after the fix

For improvements:
- before/after behavior
- run traces, screenshots, benchmark output, or concrete reasoning
- why this is better than the previous behavior

## Tests

Commands run and their output summary.

Example:

```sh
uv run pytest
uv run alembic upgrade head --sql
```

## Risk

Known risks, edge cases, migration impact, operational impact, or rollback concerns.

## Follow-ups

Anything intentionally left out.
````

Bad PR descriptions:

- "fix bug"
- "updates"
- "refactor"
- "works now"

Good PR descriptions explain the reasoning path. The reviewer should see what the author believed, what evidence changed that belief, and why the final implementation is the right move.
