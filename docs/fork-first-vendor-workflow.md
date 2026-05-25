# Fork-First Vendor Workflow

Use this workflow whenever we need to fix, extend, or stabilize a third-party tool that we depend on, such as Hermes Desktop, Claw3D / Hermes Office, or similar agent infrastructure.

## Principle

Do not rely on one-off edits inside an installed app or a local runtime directory as the source of truth.

If the change matters, make it reproducible in source control:

1. Fork the upstream repository under our GitHub account or team account.
2. Create a focused branch for the fix or integration.
3. Make the smallest source change that solves the issue.
4. Add tests, smoke checks, or a clear manual verification note.
5. Commit and push the branch to our fork.
6. Use that fork branch for our local build or installation.
7. Optionally open a PR upstream if the change is generally useful.

This gives us two paths at the same time: we can use our own working version immediately, and we can upstream the improvement later.

## When To Fork

Fork when:

- We need to patch bugs in Hermes Desktop, Claw3D, Hermes Office, or another external tool.
- We need deeper integration than configuration alone can provide.
- The local installed version was manually patched and the fix must be preserved.
- Another team member should be able to reproduce the exact behavior on a new machine.
- We may want to send the change back as an upstream PR.

Do not fork for temporary experiments, throwaway debugging, or changes that can be handled through documented configuration.

## Branch Naming

Use short, descriptive branches:

```text
fix/ssh-kanban-argument-quoting
feat/hermes-profile-agents
docs/fork-first-workflow
```

Prefer one issue or integration per branch. Avoid mixing unrelated local convenience changes with upstreamable fixes.

## Commit Standards

Each commit should explain why the change exists, not only what changed.

Include:

- The user-visible problem.
- The source-level fix.
- The constraint that shaped the approach.
- What was tested.
- What was not tested, if anything.

Example:

```text
feat(hermes): expose profiles as Claw3D agents

Hermes profiles are available through the Hermes CLI rather than the HTTP API,
so the adapter discovers them with `profile list` and maps each profile to a
stable Claw3D agent id.

Constraint: Hermes profile metadata is not exposed through the HTTP API yet.
Tested: WebSocket connect and agents.list returned all Hermes profile agents.
```

## Verification

Before calling a fork branch usable, capture evidence.

Good verification examples:

- Unit tests for parser, quoting, routing, or adapter logic.
- Typecheck or build command.
- Smoke test that exercises the actual UI/gateway path.
- Manual command output showing the expected state.
- Screenshot or short note when the fix is visual.

For desktop or agent tools, prefer at least one real end-to-end check. A unit test alone is often not enough.

## Syncing With Upstream

Keep the fork updateable.

Recommended setup:

```bash
git remote -v
git remote add upstream https://github.com/<upstream-owner>/<repo>.git
git fetch upstream
```

Update our main branch from upstream:

```bash
git checkout main
git fetch upstream
git merge upstream/main
git push origin main
```

Rebase a working branch when needed:

```bash
git checkout <branch>
git fetch upstream
git rebase upstream/main
```

If rebase becomes risky or conflict-heavy, use a merge commit instead and document why.

## Local Installation From Fork

A new team member should be able to reproduce our version by following the fork branch, not by copying patched app files.

Document these details near the project:

- Fork URL.
- Branch name.
- Commit hash used locally.
- Build/install command.
- Runtime configuration needed.
- Smoke test command.
- Known limitations.

For installed desktop apps, keep a backup of the original app before replacing it, but treat the fork branch as the real source of truth.

## Upstream PR Criteria

Open an upstream PR when:

- The fix is generic and not tied to our private infrastructure.
- It does not include secrets, local paths, private domains, or team-only assumptions.
- Tests or reproduction steps are included.
- The implementation follows upstream style and avoids unnecessary product opinion.

Keep private deployment details in our docs, not in the upstream PR.

## Current Forks

### Hermes Desktop

- Upstream: `fathah/hermes-desktop`
- Fork: `nik1t7n/hermes-desktop`
- Branch: `fix/ssh-kanban-argument-quoting`
- Purpose: preserve remote Hermes SSH argument quoting so Kanban actions work through SSH tunnel mode.

### Claw3D / Hermes Office

- Upstream: `fathah/hermes-office`
- Fork: `nik1t7n/hermes-office`
- Branch: `feat/hermes-profile-agents`
- Purpose: expose Hermes profiles as Claw3D agents and route profile-specific chat through the matching Hermes profile.

## Rule Of Thumb

If we would be annoyed to rediscover or reapply the fix on another laptop, it belongs in a fork branch and a short runbook.
