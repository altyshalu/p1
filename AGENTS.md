# ABRT Agent Instructions

## No Fallbacks

This project has a strict no-fallback policy.

Do not add fallback behavior, demo commands, mocks, fake/example data, silent degradation, synthetic substitute data, alternate hidden execution paths, or "best effort" behavior that masks a broken primary path unless the user explicitly asks for them.

This is a trust boundary. Demo/fallback/mock behavior can make the system look operational when only a substitute path is working.

Required behavior:

- If required data, registry entries, tools, workers, eval specs, credentials, schemas, or services are missing, fail explicitly.
- Surface the exact missing dependency or invalid state.
- Fix the primary path instead of adding a secondary path.
- Require real inputs for runtime commands.
- Tests should assert explicit failure, not fallback success.

Allowed:

- Explicit bootstrap/import commands, such as syncing YAML registry seed data into the database-backed marketplace.
- Explicit user-approved migrations or one-time setup flows.

Not allowed:

- Runtime fallback from the marketplace to YAML.
- Synthetic worker outputs when inputs are missing.
- Default alternate tools when requested tools are unavailable.
- Silent empty objects/lists when required configuration files are missing or invalid.
- CLI demo flows that create runs from embedded fake/example data.
- Mocks or test doubles outside tests, or tests that present mocked behavior as real runtime behavior.

## Commit Discipline

After every logical change or small coherent block of work, create a separate git commit using Conventional Commits.

Do this unless the user explicitly says not to commit.
