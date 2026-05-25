# L2/L3 Architecture Q&A Session

Date: 2026-05-25

Purpose: explain the current ABRT L2/L3 runtime architecture in simple language for team sharing.

---

## 1. What is a Playbook?

A `Playbook` is the description of a pipeline or process.

It tells L2:

- what kind of task this is
- which workers are allowed
- which tools are allowed
- which inputs are required
- what counts as completion
- which memory and External Action rules apply

Example: the `build-in-public` Playbook describes how to turn progress signals into public draft posts.

---

## 2. Why does L2 load the Playbook and allowed workers from Taskforce Hub?

So L2 does not improvise.

The Playbook defines the rules of the process:

- which workers can be used
- which tools can be used
- which inputs are required
- which completion criteria apply
- which External Actions are allowed or forbidden

L2 loads this from the registry to know:

> “For this process, I may only use these workers and follow these rules.”

Without this, L2 could start inventing workers, tools, and steps during Execution Mode. That would break the discipline of the protocol.

---

## 3. Does L2 decide what it needs and load tool/worker implementations from Taskforce Hub?

Almost, but with an important constraint.

L2 does **not** load arbitrary implementations by itself.

How it works:

1. A human starts a Playbook, for example `build-in-public`.
2. Runtime loads the Playbook.
3. The Playbook already defines which workers and tools are allowed.
4. L2 chooses from that allowed set.
5. Runtime validates L2's choice.
6. Runtime runs the worker through its registered entrypoint.

So L2 does not say:

> “I will find anything I want in Taskforce Hub.”

It says:

> “For this process, I am allowed to choose from these workers. I will pick the right one.”

Taskforce Hub is the source of registered capabilities. L2 operates inside the Playbook boundaries.

---

## 4. What are External Actions?

`External Actions` are actions that change the outside world instead of only returning a result.

Examples:

- publish a post
- send an email
- write a file
- call an external API
- create a task
- modify the registry
- write to memory
- deploy something

In this protocol, External Actions must be explicitly allowed.

Example: a worker may generate a draft, but it cannot publish the draft unless publishing is explicitly allowed.

---

## 5. When L2 chooses the next action, does it create a Work Order in working memory?

Yes.

If L2 chooses an action like:

> “Run `quality-judge`.”

Then runtime creates a `WorkOrder` and stores it in Postgres.

The Work Order includes:

- task id
- run id
- worker profile
- goal
- inputs
- output schema
- allowed tools
- budget
- policies
- status

So yes: it is a state/log record in Postgres that makes the whole process trackable.

---

## 6. How does Work Order validation work?

Before running a worker, runtime checks the Work Order.

It validates:

- required inputs exist
- input types are correct
- requested tools are allowed
- the worker does not violate External Action policy
- the expected output schema is defined

Example:

If a worker requires `signals`, but L2 passes `{}`, the task does not run. It fails explicitly.

---

## 7. What does Hub Lookup mean?

`Hub Lookup` means taking keys from the Work Order and finding the real registered specs.

Example:

The Work Order says:

```text
worker_profile = quality-judge
```

Runtime goes to Taskforce Hub and loads the `quality-judge` worker spec:

- entrypoint
- worker type
- input schema
- output schema
- compatible tools
- External Action policy

If the Work Order asks for a tool like `x-publisher`, runtime checks:

- does this tool exist in Taskforce Hub?
- is it compatible with this worker?
- is it allowed by this Playbook?
- what toolset does it map to?
- what External Actions does it have?

If everything is valid, runtime runs the worker.

If not, runtime fails explicitly.

---

## 8. What happens if the Work Order is invalid?

The worker does **not** run.

Runtime does this:

1. Marks the task as `failed`.
2. Writes a `work_order_validation_failed` event.
3. Writes a `task_failed` event.
4. Creates an `incident_brief` for L2.

The Incident Brief includes:

- which worker failed
- failure type
- what exactly broke
- whether retry is possible
- whether a known failure pattern exists

Then control returns to L2.

L2 can decide to:

- rebuild the Work Order
- ask the user for missing data
- choose another worker
- fail the process

---

## 9. What does `grader_spec exists` mean?

It means the task or worker has a rule saying:

> “This result must be evaluated.”

Example:

```yaml
grader_spec:
  eval_key: build-in-public-draft-quality
```

This tells runtime:

> “After this worker runs, load the eval spec `build-in-public-draft-quality` and check the result.”

If there is no `grader_spec`, the result is saved as an artifact without a separate eval check.

---

## 10. How does the eval loop work?

The eval loop works like this:

1. Worker returns a result.
2. Runtime validates the output schema.
3. Runtime sees `grader_spec`.
4. Runtime gets `eval_key` from `grader_spec`.
5. Runtime loads the eval spec from Taskforce Hub.
6. Runtime reads the threshold, for example `minimum_score: 0.75`.
7. Runtime reads the score from the worker result.
8. Runtime compares score against threshold.
9. Runtime writes an `EvalResult` to Postgres.
10. If score is below threshold, the task fails.
11. Runtime creates an `incident_brief` and gives it back to L2.

The important point:

The eval loop does not only record the worker's opinion. It applies an independent rule from the registry.

---

## 11. What does it mean to match a failure pattern after eval failure?

It means runtime checks whether this failure looks like a known problem.

Example failure:

- worker: `quality-judge`
- failure type: `eval_failed`
- reason: score is below threshold

Runtime checks the `failure_pattern` registry for something like:

```json
{
  "worker_id": "quality-judge",
  "failure_type": "eval_failed",
  "root_cause": "drafts too short",
  "mitigation": "ask L2 to regenerate drafts with stronger evidence"
}
```

If it finds a match, runtime adds that information to the Incident Brief.

Then L2 receives more than:

> “Something failed.”

It receives:

- what failed
- whether this happened before
- likely root cause
- recommended mitigation

This makes retry smarter. It avoids repeating the same mistake.

---

## Core Summary

The system is built around disciplined orchestration:

- Human defines the goal.
- Playbook defines the allowed process boundaries.
- L2 chooses actions inside those boundaries.
- Runtime creates typed Work Orders.
- Work Order validator blocks invalid work before execution.
- Taskforce Hub resolves registered workers, tools, policies, and evals.
- L3 workers execute bounded tasks.
- Eval loop checks results against registry-defined standards.
- Incident Brief gives L2 structured information for repair or retry.

The goal is not one giant smart agent.

The goal is a controlled Runtime where every Work Order is explicit, validated, trackable, and repairable.
