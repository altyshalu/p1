# Taskforce Glossary

This document defines the public terminology for ABRT's L2/L3 active inference runtime.

The current product is not a marketplace. It is an active inference protocol and runtime where L2 supervises L3 workers through bounded work orders. The registry layer is called **Taskforce Hub**. A future ecosystem may expose a broader **Taskforce Marketplace**, but that is not the v1 positioning.

## Canonical Terms

| Term | Replaces | Definition |
| --- | --- | --- |
| **Playbook** | Process pack | A versioned process definition that tells L2 what mission is being run, which workers are allowed, which tools may be used, what inputs are required, what evals must pass, and when the run is complete. |
| **Work Order** | Task contract | A bounded instruction from L2 to one L3 worker. It includes the worker, goal, inputs, allowed tools, budget, schemas, eval spec, retry policy, memory policy, and external-action policy. |
| **External Actions** | External actions | Any effect outside the runtime's internal memory and artifacts: posting, sending messages, writing to external services, spending money, mutating third-party data, or calling tools that can change external state. |
| **Taskforce Hub** | Registry Marketplace | The internal registry of approved capabilities: workers, tools, evals, playbooks, and known failure patterns. It is a controlled capability hub, not a public marketplace. |
| **Hub Lookup** | Resolve in marketplace | Runtime lookup of a worker, tool, eval, playbook, or failure pattern from Taskforce Hub before execution. Lookup does not install or invent capabilities. |
| **Runtime** | Execution fabric | The execution layer that validates work orders, runs L3 workers, enforces schemas and external-action policy, records artifacts/evals/events, and returns control to L2. |
| **Incident Brief** | Failure Context | A structured report generated when a work order fails or an eval does not pass. It includes failure type, worker, error, structured error payload, retry budget, matched failure pattern, mitigation, repair guidance, and eval result if relevant. |
| **Worker** | Worker | An L3 execution profile. Workers can be deterministic, agentic, judge, adapter, or human-gate profiles. The term stays **Worker**. |
| **Tool** | Tool | A callable capability that a worker may use only if the worker, playbook, and external-action policy all allow it. |
| **Judge** | Judge worker | A worker that evaluates another worker's output against explicit criteria and emits a score, checks, reasons, and pass/fail result. |
| **Adapter** | Adapter worker | A worker that transforms one valid shape into another valid shape without changing product intent, usually to repair schema mismatches or bridge worker interfaces. |
| **Gate** | Gate | A checkpoint where the runtime pauses for explicit approval before a user-owned or externally visible action continues. |
| **Repair Pass** | Retry/rebrief/reassign | An L2-directed recovery attempt after an Incident Brief. It may retry with changed inputs, rebrief a worker, spawn an adapter, reassign to another worker, or propose a registry change. |
| **Command Layer** | L2 | The supervisory layer. It chooses the next action, creates work orders, interprets Incident Briefs, and decides repair strategy within the playbook. |
| **Execution Layer** | L3 | The worker layer. It performs bounded work orders and returns structured outputs. |
| **Active Inference Runtime** | L2/L3 protocol runtime | The whole system loop: L2 observes state, selects a bounded action, L3 executes, runtime validates/evaluates, and L2 updates its next belief/action from the result. |
| **Execution Mode** | Delivery/factory mode | L2 runs a known Playbook strictly: create Work Orders, validate, route, eval, repair inside rules, and gate external actions. |
| **Design Mode** | Discovery/agent mode | L2 designs a new or changed Playbook proposal when the user explicitly starts a design run. It can propose Hub changes, but cannot apply executable changes without approval. |

## Positioning Rules

- Say **Taskforce Hub** for the current internal registry.
- Do not call the current product a marketplace.
- Say **Playbook** for user-facing process definitions.
- Say **Work Order** for user-facing task contracts.
- Say **External Actions** for user-facing external actions.
- Say **Incident Brief** for user-facing failure context.
- Approval is required for executable behavior changes, external actions, and user-owned product/editorial decisions.
- L2 should not escalate low-level repair mechanics to the user when the repair is safe and inside the playbook.
