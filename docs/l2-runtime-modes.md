# L2 Runtime Modes

L2 Runtime has two explicit operating modes.

## Execution Mode

Execution Mode runs a known Playbook. It is the delivery/factory path.

- Requires an active Playbook in Taskforce Hub.
- Creates bounded Work Orders.
- Validates inputs, tools, schemas, evals, and External Actions.
- Routes Work Orders to registered Workers.
- Produces Incident Briefs when work fails.
- Repairs only inside Playbook policy.
- Fails explicitly if the Playbook is missing.

## Design Mode

Design Mode authors a Playbook proposal. It is the discovery/architect path.

- Must be explicitly requested with `l2_mode: "design"`.
- Does not execute a Playbook.
- Reads Taskforce Hub state.
- Proposes a Playbook, required Workers, Tools, Evals, and test plan.
- Stores a `playbook_proposal` artifact.
- Stores registry change candidate artifacts.
- Stops at human approval.

Design Mode never mutates executable Taskforce Hub state directly.

## API Examples

Run a known Playbook:

```sh
curl -X POST http://localhost:8080/runs \
  -H 'content-type: application/json' \
  -d '{"playbook_key":"build-in-public","l2_mode":"execution","goal":"<real goal>","inputs":{"signals":["<real signal>"],"channels":["x"]}}'
```

Design a new Playbook:

```sh
curl -X POST http://localhost:8080/runs \
  -H 'content-type: application/json' \
  -d '{"playbook_key":"<new-playbook-key>","l2_mode":"design","goal":"<real design goal>","inputs":{}}'
```
