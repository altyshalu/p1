---
date: 2026-05-24
topic: l2-l3-communication
status: draft
---

# L2-L3 Communication Protocol Brainstorm

## What We're Building

The core system architecture should center around `L2 <-> L3` communication.

The goal is not to build "one very smart autonomous agent." The goal is to build a system where humans specify `what`, while the system increasingly owns `how`.

In this model:

- `L2` is the management and control layer
- `L3` is the execution layer

`L2` should decompose high-level goals, select the right workers, supervise quality, decide retries or replans, and convert experience into reusable machinery. `L3` should perform bounded, detailed, trackable work under explicit work_orders.

The desired end state is that a human can hand the system a meaningful global task and get back a validated result without manually steering execution at the implementation level.

## Core Philosophy

The central idea is:

`L2-L3 Communication Protocol = manager agent + typed work_orders + isolated workers + evaluator loop + curated memory + evolving registry`

Not:

`Protocol = one powerful autonomous agent`

This is the key philosophical distinction. The value of the system should come from disciplined coordination, verification, memory curation, and iterative improvement, not from relying on one giant prompt or one endlessly-general worker.

## Why This Direction

This direction fits both the project thesis and the practical lessons emerging from current agent systems:

- orchestrator-worker systems outperform monolithic agents on many open-ended tasks
- isolated subagents reduce context pollution and path dependency
- eval-driven iteration is more robust than intuition-driven prompt tweaking
- memory must be curated, layered, and strategically retrieved rather than dumped into context
- stable interfaces matter more than clever internal loops

Hermes looks like a strong base for `L2` because it already provides:

- an agent loop
- delegation
- memory
- skills
- cron
- session storage
- tooling and runtime abstractions

But Hermes alone is not the architecture. The missing layer is the explicit `L2/L3` protocol and the runtime structures around it.

## Role Of L2

`L2` should be a disciplined manager and control plane, not the main hands-on worker.

Its job is to:

1. accept a high-level goal
2. determine what type of task it is
3. decompose it into typed executable units
4. choose the correct `L3` workers
5. monitor progress and artifacts
6. evaluate outputs and decide whether they pass
7. retry, rebrief, reassign, replan, or escalate if necessary
8. consolidate useful outcomes into memory, work_orders, and skills

`L2` should not become a giant do-everything worker. Its intelligence matters, but its main virtue should be discipline.

## Role Of L3

`L3` should not be treated as "some agents and some scripts." It should be treated as a unified execution layer with multiple worker types behind a common work_order interface.

Useful worker classes:

- `deterministic workers` — scripts, pipelines, linters, extractors, test runners, deployers
- `agentic workers` — subagents for open-ended bounded reasoning tasks
- `judge workers` — critics, evaluators, verifiers
- `adapter workers` — formatters, publishers, translators, delivery surfaces

This allows the protocol to route work based on execution shape rather than ideology about whether "agents" or "scripts" are better.

## The Most Important Primitive: Task Contracts

The core object of the system should be a `Task Contract`.

`L2` should not delegate work as plain natural-language prompts whenever that can be avoided. It should delegate through structured work_orders.

A work_order should define at least:

- `task_type`
- `goal`
- `inputs_schema`
- `output_schema`
- `allowed_tools`
- `budget`
- `stop_conditions`
- `grader_spec`
- `retry_policy`
- `memory_policy`
- `external_action_policy`

This is what turns delegation into a protocol instead of improvised management.

Natural language remains useful, but it should live inside a typed envelope.

## Memory Architecture

Memory should be layered. A useful model is:

- `working memory` — live state for the current task
- `episodic memory` — traces, failures, retries, outcomes
- `semantic memory` — stable project knowledge, conventions, architecture facts
- `procedural memory` — skills, runbooks, work_orders, policies

Important principle:

`L3 should not own memory truth`

`L3` should produce observations and artifacts.

`L2` should decide what becomes durable memory.

This keeps shared memory cleaner and reduces runaway contamination from noisy leaf workers. It also means retrieval can stay selective and strategic.

## Registry-Centric Design

The protocol should likely grow around several explicit registries:

- `Contract Registry`
- `Worker Registry`
- `Eval Registry`
- `Skill Registry`
- `Failure Pattern Registry`
- `Artifact Type Registry`

This makes the system legible and improveable. Instead of "the agent got smarter somehow," we can point to the exact artifact that evolved:

- a better work_order
- a new worker type
- a stronger grader
- a refined skill
- a stored failure pattern

## The Execution Loop

The `L2 <-> L3` interaction should probably follow a loop like this:

1. goal intake
2. task typing
3. work_order generation
4. worker selection
5. execution
6. artifact collection
7. evaluation
8. repair or acceptance
9. memory consolidation
10. registry evolution

This is the actual source of "automatic interaction." The system works because the loop is explicit, not because the prompt is magical.

## Self-Improvement Philosophy

Self-improvement should not begin with "let the agent rewrite itself."

It should begin with a safer ladder:

1. improve task briefs
2. improve work_orders
3. improve evals and graders
4. improve skills and tool descriptions
5. improve prompts
6. only then consider code evolution

This is the safer and more operational path because:

- work_orders and evals are more stable than prompts
- skills are easier to inspect than emergent runtime behavior
- code changes without strong evals are too dangerous

The target is not "self-improving agent" in the abstract.

The target is a self-improving execution fabric.

## Human Role

Humans should increasingly answer:

- what outcome matters
- what constraints matter
- what tradeoffs are acceptable

Humans should not need to micromanage:

- decomposition
- retries
- prompt rewrites
- subtask routing
- implementation-level steering

That is precisely the management labor `L2` is meant to absorb.

## Important Constraints

Several practical warnings matter early:

- do not start with deep recursive agent hierarchies
- do not let all workers write into shared memory
- do not trust raw worker output without evals
- do not confuse transcripts with knowledge
- do not overfit to one framework abstraction

The first useful version should likely be:

- one `L2`
- many `L3` leaf workers
- explicit work_orders
- explicit evals
- curated memory
- minimal nesting

## Working Thesis

The strongest concise thesis from this discussion is:

`L2 should not be the smartest part of the system.`

`L2 should be the most disciplined part of the system.`

Its value is not brilliance alone. Its value is in:

- decomposition
- routing
- evaluation
- stopping bad branches
- repairing failed branches
- turning experience into reusable machinery

## Open Questions

- What is the minimal viable `Task Contract` schema for the protocol v1?
- What should live in `agentmemory` versus local project artifacts versus Hermes-native memory?
- Should `L2` itself be a single long-lived Hermes agent, or a narrower orchestrator wrapper around Hermes primitives?
- Which `L3` tasks should stay deterministic first, and which justify agentic workers from day one?
- What is the first `Eval Registry` shape that is useful without being too expensive?
- How should failure analysis be represented so that retries become informed rather than repetitive?

## Next Direction

The next productive design fronts are:

1. define the `Task Contract`
2. define the memory model between `L2` and `L3`
3. define the self-improvement loop and its guardrails

Those three pieces appear to be the foundation for making the architecture operational rather than merely conceptual.
