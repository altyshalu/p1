# ABRT Agent Instructions

## No Fallbacks

This project has a strict no-fallback policy.

Do not add fallback behavior, silent degradation, synthetic substitute data, alternate hidden execution paths, or "best effort" behavior that masks a broken primary path.

Required behavior:

- If required data, registry entries, tools, workers, eval specs, credentials, schemas, or services are missing, fail explicitly.
- Surface the exact missing dependency or invalid state.
- Fix the primary path instead of adding a secondary path.
- Tests should assert explicit failure, not fallback success.

Allowed:

- Explicit bootstrap/import commands, such as syncing YAML registry seed data into the database-backed marketplace.
- Explicit user-approved migrations or one-time setup flows.

Not allowed:

- Runtime fallback from the marketplace to YAML.
- Synthetic worker outputs when inputs are missing.
- Default alternate tools when requested tools are unavailable.
- Silent empty objects/lists when required configuration files are missing or invalid.

## Commit Discipline

After every logical change or small coherent block of work, create a separate git commit using Conventional Commits.

Do this unless the user explicitly says not to commit.
