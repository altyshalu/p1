# Overall System Improvement Plan

This is a living list of system improvements proposed during product and engineering discussions.

The list is not ordered by priority. Each item captures the idea, why it matters, how we improve the system, and what we expect to change.

## #1 Improvement: Self-Expanding Diagnosis Categories

### Problem

The current diagnosis engine is strongest when an error matches a known category. This is useful for common failures, but weak for new or unusual failures. Unknown errors still get recorded, but the system does not yet learn a better category by itself.

### Improvement

Allow the system to create new diagnosis categories automatically when a real run produces an error that does not fit the existing taxonomy.

The system should:

- inspect the real run evidence;
- compare the failure against existing categories;
- reuse an existing category when the match is clear;
- create a new category when no existing category fits;
- attach evidence such as run id, worker, task, raw error, events, artifacts, and eval results;
- group future similar failures under the new category.

### Approval Boundary

Creating diagnosis categories does not require human approval because it does not change runtime behavior.

Approval is still required for behavior changes such as worker logic, playbooks, policies, eval thresholds, tool registry changes, implementation workers, or external actions.

### Expected Result

The system becomes better at naming and grouping real failures over time.

New failures should stop disappearing into vague buckets like `unknown_error`. Instead, they should become reusable failure signatures that can later produce stronger learnings, proposals, and regression checks.

### Success Criteria

- Unknown real failures create evidence-backed diagnosis categories.
- Similar future failures are grouped under the created category.
- Category creation is visible in run diagnosis or learning reports.
- No behavior-changing runtime action happens without approval.
- No category is created without real run evidence.

## #2 Improvement: Autonomous Codex Implementation Worker With Independent Review

### Problem

The current improvement loop still asks for too much human attention after the system already knows what needs to be fixed. This slows down self-improvement and makes the process depend on a developer manually turning every approved idea into code.

### Improvement

Turn the implementation worker into an autonomous coding loop powered by Codex through ACP or another structured agent-control interface.

The system should:

- create a bounded implementation task from an improvement proposal;
- define allowed files, forbidden files, success criteria, and required proof commands;
- start a Codex implementer in an isolated branch or worktree;
- let Codex make the fix and open a PR;
- start a separate independent Codex reviewer;
- have the reviewer check scope, diff, tests, proof, and whether the implementer stayed inside bounds;
- send factual review feedback back to the implementer when changes are needed;
- retry the implement-review loop up to a fixed limit, for example 3 iterations;
- merge automatically when the reviewer approves and all required real checks pass.

### Approval Boundary

The final result does not require manual approval when the task stays inside the predefined safe bounds and all required proof passes.

The system must fail closed when:

- the implementer changes files outside bounds;
- required real tests fail;
- proof commands are missing or weak;
- the reviewer finds a real blocking issue;
- the retry limit is exhausted.

### Reviewer Behavior

The reviewer should be factual, practical, and not overly strict.

It should not reject work for style preferences or theoretical concerns. It should reject only when there is a concrete correctness, scope, safety, proof, or maintainability issue.

### Expected Result

The system can fix small and medium improvements without constant human babysitting.

Humans should mostly see final proof, merged changes, and clear logs. Human attention should be reserved for strategy, high-risk behavior changes, external actions, or cases where the autonomous loop cannot prove success.

### Success Criteria

- Each autonomous fix has a proposal id, branch, PR, implementer log, reviewer log, test log, and proof result.
- The implementer cannot silently change files outside the declared bounds.
- The reviewer runs independently from the implementer.
- Failed reviews produce actionable feedback and another implementation iteration.
- The loop stops after the configured retry limit.
- Successful bounded fixes merge automatically only after real checks pass.
