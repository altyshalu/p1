# 2026-05-28 Cross-Process Coupling Inventory

This inventory tracks every place where the runtime was still biased toward one process instead of treating Playbooks generically.

## Current Couplings Found

1. `scripts/real-trend-radar-acceptance.py` was the only real acceptance entrypoint.
It encoded one Playbook, one input shape, and one success path.

2. `l2l3-live review recent` defaulted to `build-in-public-trend-radar`.
This made the CLI convenient for one process but misleading for others.

3. `reports/system-learning` had no scope controls.
It mixed all evidence-backed learnings together and made daily or per-Playbook review awkward.

4. `regression-cases` listing had no process filter.
The catalog itself was generic, but operators could not easily isolate one Playbook from another.

5. Runtime readiness was implicit.
There was no honest API surface that said whether Hermes-backed workers were actually runnable in the live environment.

6. Proven proposal resolution matched active learnings only by `failure_signature` and `target_component`.
Across multiple Playbooks this risks resolving the wrong learning family.

## Required Fix Direction

1. Add a generic real readiness script driven by live Hub registry data.
2. Add a generic real acceptance runner for any Playbook with explicit JSON inputs.
3. Add scope controls for recent review and learning reports.
4. Add filtered regression catalog access by Playbook.
5. Expose runtime capabilities without leaking secrets.
6. Resolve proven failure learnings with Playbook awareness.

## Non-Fixes

1. Do not fake a second process.
Use a real seeded Playbook if one exists; otherwise fail honestly.

2. Do not add fallback success paths.
A real run must either finish in an allowed terminal state or fail loudly with evidence.
