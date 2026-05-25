# Next Week Plan

**Timeframe:** Friday, May 22, 2026 to Friday, May 29, 2026

## Main Goal

Over the next week, our focus is to push Hermes forward on two fronts at the same time:

1. Stabilize and adapt the Claw 3D work so it fits naturally into the Hermes Agent ecosystem.
2. Design and prototype the L2-to-L3 operating model so agent layers can manage real work without a human sitting in the loop for hours.

Everything we do this week should also feed our build-in-public effort across Twitter/X, LinkedIn, Reddit, GitHub, and the broader English-speaking AI community.

## Saturday: Claw 3D + Build in Public Foundation

### 1. Claw 3D Experimentation and Integration

On Saturday, we will experiment with Claw 3D in practice and use the day to discover what already works and what still needs attention. If needed, we will fix, polish, adapt, and integrate the system more tightly with Hermes Agent.

Key outcomes for the day:

- Validate the current Claw 3D workflow.
- Fix obvious issues, friction points, or broken behavior.
- Adapt the setup so it is more compatible with Hermes Agent.
- Identify what should remain experimental versus what should become part of the stable Hermes path.

### 2. Build in Public Strategy, Plan, and Tooling

On the same day, we will define how we want to build in public as a startup. The goal is not just to post updates, but to create a repeatable distribution system that brings feedback, attention, credibility, and community.

We want to build in public in the English-speaking AI ecosystem through:

- Twitter/X
- LinkedIn
- Reddit
- GitHub
- Other relevant online communities

Key outcomes for the day:

- Define our build-in-public narrative.
- Decide what kinds of updates we want to share.
- Decide how often we want to post.
- Decide which channels are best for technical updates, founder narrative, demos, and progress logs.
- Create a lightweight tooling and workflow stack for writing, posting, saving, and reusing content.
- Make GitHub a visible public log of progress, experiments, and technical evolution.

## Sunday to Friday: L2 and L3 Agent Protocol

For the rest of the week, our main mission is to invent, design, and build the working relationship between the L2 and L3 layers inside Hermes.

## Problem We Are Solving

Previously, a human had to sit with an agent for hours: prompting it, fixing it, debugging it, improving it, retrying tasks, and manually steering the process until something useful happened.

We want to replace that human-in-the-loop function with an L2 agent layer.

In this model:

- **L3** is the execution layer: AI workers, subagents, scripts, or other task-doing units.
- **L2** is the management layer: it supervises, improves, redirects, retries, spawns, upgrades, and removes L3 workers as needed.

The long-term goal is simple but difficult: any pipeline or task should be handed to an L2 + L3 system, and the system should drive itself toward completion with minimal or no human intervention.

## Weekly Focus for L2/L3

From Sunday through next Friday, we will work on the core protocol that defines how L2 and L3 cooperate inside Hermes.

Core areas of work:

- Define the communication protocol between L2 and L3.
- Define the lifecycle of an L3 worker: spawn, brief, execute, report, retry, improve, replace, and terminate.
- Define how L2 evaluates whether an L3 worker is doing useful work or wasting cycles.
- Define how L2 decides when to rewrite prompts, split tasks, escalate, or reassign work.
- Define how L2 keeps task state, context, memory, and progress consistent across multiple workers.
- Define how this system can support any pipeline, not just one narrow use case.
- Explore whether this should become a Hermes-native plugin, subsystem, or equivalent control layer.

## General Focus for the Rest of the Week

For the rest of the week, we will stay focused on turning the L2/L3 concept into a real operating model inside Hermes.

This means we will:

- clarify the L2/L3 problem and document the biggest failure modes in human-managed agent workflows,
- design the first version of the communication protocol between L2 and L3,
- define the full lifecycle of L3 workers inside a managed system,
- design the intervention logic for when L2 should retry, re-prompt, split work, replace workers, or stop a failing branch,
- turn the protocol into something operational inside Hermes, potentially through a plugin, control layer, or similar native mechanism,
- and finish the week with a concrete, testable first version of the L2-to-L3 protocol that can serve as the foundation for future pipelines.

## Deliverables by Next Friday

By next Friday, we want to have:

- A validated Claw 3D experiment with fixes and Hermes alignment where needed.
- A clear build-in-public strategy and working content/tooling process.
- A documented L2-to-L3 protocol for Hermes.
- A first working implementation direction for making L2 manage L3 workers in practice.
- A clearer decision on whether this should live as a Hermes plugin or a similar internal subsystem.
- Public build-in-public updates that show real progress during the week.

## Build in Public as a Weekly Layer

Build in public is not a side activity this week. It is part of the system.

That means we should continuously capture:

- experiments
- failures
- fixes
- architecture decisions
- lessons learned
- demos
- progress screenshots or clips
- GitHub-visible technical milestones

The public story should show that we are not just building another agent wrapper. We are trying to solve a hard systems problem: how to replace the human manager in agent workflows with a reliable L2 layer that can operate L3 workers at scale.

## Success Definition

This week is successful if, by next Friday, we have:

- moved Claw 3D closer to practical Hermes use,
- created a real build-in-public operating rhythm,
- and produced a working first protocol for L2 managing L3 inside Hermes.

That protocol does not need to be perfect yet, but it must be real enough that we can start using it as the foundation for future pipelines.
