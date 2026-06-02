# Next Week Plan

**Timeframe:** Monday, June 1 to Friday, June 5, 2026

## Main Direction

This week, the main focus is to move ABRT from a working technical proof into an investor-demo-ready, reliable, understandable operating system for real business processes.

Last week, we proved that the L2/L3 protocol can run a real process through P1. This week, we need to make it feel less like an engineering experiment and more like a system that founders, operators, and future users can actually trust.

There is now a second constraint on top of the production-readiness work: the June 27 investor demo. By June 25, we need a narrow but strong demo path where P1 can be shown live with confidence. That means this week should not spread the team across too many future processes. The highest-leverage move is to make one process, P1, feel real, high-quality, observable, and controllable.

The priorities are:

1. Improve quality.
2. Improve stability.
3. Make the system easier to observe and operate.
4. Prepare the first investor-demo surfaces: Telegram bot as the control panel and dashboard as the live stage.
5. Prepare the system for production-level usage.
6. Keep scaling beyond P1 as an architectural direction, but do not let it distract from making P1 demo-grade this week.

## Demo Deadline Overlay

The investor demo target is June 27. The internal build target is June 25.

The demo should show one clear story:

ABRT can take a real operator/angel-search goal, coordinate AI workers through the process, stop for human approval before important actions, and turn the result into a useful follow-up workflow.

The demo should have two surfaces:

- **Telegram bot as the control panel.** A user can start a goal, check progress, approve or reject outputs, and leave structured feedback from a phone.
- **Dashboard as the stage.** A larger screen shows the live process: what agents are doing, what passed quality checks, what is waiting for approval, and what changed as a result of human feedback.

The bot is the minimum viable demo surface because it makes the system feel controllable. The dashboard is the visual proof surface because it makes the coordination visible.

Both surfaces should use the same real backend state and the same real run events. They should not be separate demos.

## Critical Path for This Week

The first unlock is a verified real P1 proof pack.

Before investing too much in UI polish or future process expansion, the server-side P1 path must be able to pass a real proof pack with the required provider and output configuration in place.

The critical configuration and proof path includes:

- Apify access,
- Exa access,
- Google service account access,
- the real P1 Google Sheet target,
- the real outreach master target,
- the real dossier output path,
- the real dossier source path,
- and a passing real P1 proof pack with verification enabled.

This matters because the bot and dashboard are wrappers around the real process. If the real process is not verified, the surfaces only make uncertainty more visible.

By the end of the week, we expect the first verified P1 run to be the anchor for quality review, observability, bot integration, and dashboard integration.

## External Direction Signals

Current production-agent guidance continues to point in the same direction:

- Agent systems need traceability across model calls, tool calls, handoffs, guardrails, and custom events.
- Guardrails should validate inputs and outputs instead of letting weak results silently pass.
- Observability should help humans understand complex agent behavior quickly, not just store logs.
- Human approval and feedback are part of the operating system, not an afterthought.

References:

- OpenTelemetry GenAI semantic conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- OpenAI Agents SDK tracing: https://openai.github.io/openai-agents-python/tracing/
- OpenAI Agents SDK guardrails: https://openai.github.io/openai-agents-js/guides/guardrails
- LangSmith observability concepts: https://docs.langchain.com/langsmith/observability-concepts

## 1. Quality First

The system should not merely "complete runs." It should produce outputs that are actually useful, accurate, and reliable.

This week, we need to raise the bar for quality across the full process:

- better inputs,
- better filtering,
- better reasoning,
- better outputs,
- better evaluation,
- better final artifacts.

The goal is that when the system produces a result, we can confidently show it to a founder, investor, customer, or internal operator without needing to manually explain away obvious weaknesses.

By the end of the week, we expect to see:

- cleaner outputs,
- fewer low-quality results,
- stronger quality checks,
- clearer reasons why something passed or failed,
- and a higher confidence that successful runs are genuinely good, not just technically completed.

## 2. Stability and Production Readiness

The system needs to become harder to break.

Right now, the priority is not adding more flashy functionality. The priority is making sure real workflows can run consistently, recover from problems, and fail clearly when something is wrong.

This means improving the overall reliability of the runtime, workers, process flow, approvals, retries, and proof paths.

By the end of the week, we expect to see:

- fewer random failures,
- clearer failure reasons,
- better recovery from interrupted runs,
- stronger proof that successful runs can be repeated,
- and a system that feels much closer to production readiness.

The standard is simple:

If something works once, it should work again.

If something fails, we should know exactly why.

If something is not safe to continue, the system should stop clearly instead of pretending.

## 3. Observability and Trust

A real operator should be able to understand what the system is doing without reading code or digging through raw logs.

This week, we need to make the system more transparent.

The user should be able to see:

- what is running,
- what already happened,
- what failed,
- what is waiting for approval,
- what the system learned,
- what changed between runs,
- and whether the final result is trustworthy.

By the end of the week, we expect to have a clearer operating view of the system: not necessarily a final polished product UI, but a real way to inspect progress, status, quality, and outcomes.

The goal is to reduce the feeling of a black box.

For the June demo, observability also has a presentation role. The dashboard should make the system feel alive: the audience should see agents coordinating work, passing data forward, hitting quality gates, pausing for approval, and logging the human decision back into the system.

This does not mean building a fake visual show. It means exposing the real run state in a way a human can understand quickly.

## 4. User-Friendly Experience

The system should become easier to use.

Not just easier for engineers, but easier for a normal operator who wants to run a process, track progress, approve actions, and inspect results.

This week, we should define and start building the first useful interfaces around the protocol.

It does not need to be the final UI. It does need to be practical and demo-useful.

The user-facing experience should split into two complementary surfaces:

- **Telegram bot:** the phone-based control panel.
- **Dashboard:** the larger visual operating view.

Together, they should help the user:

- start or inspect a run,
- see progress,
- understand the current state,
- review outputs,
- approve or reject important actions,
- leave structured feedback,
- and see what needs attention.

By the end of the week, we expect to have a clearer user experience direction and early working surfaces connected to real system data.

The bot is the floor. Without it, the user cannot feel direct control. The dashboard is the ceiling. It creates the visual story for the investor demo.

## 5. Scaling Beyond P1

P1 proved the first serious real workflow.

Now the bigger question is whether the same system can scale to other ABRT processes without becoming messy, custom, and fragile.

This week, we should start turning P1 from a one-off success into a reusable pattern, but we should not fully build a second process before the demo path is strong.

The system should become more general:

- same core logic,
- same operating model,
- same quality loop,
- same approval philosophy,
- same observability layer,
- but different business processes.

By the end of the week, we expect to have a clearer path for applying the protocol to another ABRT process, not a fully productionized P2.

The target is not to fully perfect every process immediately. The target is to prove that the architecture can expand cleanly while keeping engineering focus on P1.

For the investor demo timeline, scaling beyond P1 should be shown as architecture and roadmap, not as the main development target.

## 6. Self-Improvement With Control

The system should continue becoming smarter from real work, but without becoming chaotic.

This means it should keep learning from:

- failed runs,
- weak outputs,
- repeated mistakes,
- human interventions,
- low-quality results,
- missing tools,
- and broken process steps.

But the system should not silently change important behavior on its own.

By the end of the week, we expect the self-improvement loop to feel more practical:

- the system sees real problems,
- explains them clearly,
- suggests improvements,
- shows evidence,
- and waits for approval before anything important changes.

This is the core philosophy:

The system should learn aggressively, but change carefully.

## 7. Production Quality Bar

This week should raise the overall standard.

We should stop thinking only in terms of "does it run?" and start thinking in terms of "is it production-worthy?"

A production-worthy process should be:

- reliable,
- observable,
- repeatable,
- recoverable,
- understandable,
- high-quality,
- approval-safe,
- and usable by someone other than the developer who built it.

By Friday, the system should feel meaningfully closer to that bar.

## What We Do Not Do Before the Demo

To protect focus, we should not spend this week building broad secondary directions that do not directly improve the June demo path.

Before the investor demo, we should not prioritize:

- fully building P2 or other ABRT processes,
- worker A/B competitions,
- automatic worker retirement,
- real-time auto-training,
- memory migration to Mem0,
- a complex four-part VC score,
- or UI polish that is disconnected from real P1 state.

These ideas may still matter, but they belong in roadmap, architecture notes, or future planning. The demo path needs one strong pipeline, not five half-ready directions.

## Demo Success Shape

The target demo should be simple and strong.

A user enters a real goal through the Telegram bot. The dashboard shows the system receiving the goal, coordinating work, moving through quality gates, and preparing outputs. The bot asks for approval before important actions. The user approves or rejects from the phone. The dashboard reflects the decision, and the result is logged back into the system as part of the improvement loop.

The message should be:

ABRT is not just running agents. ABRT is coordinating an AI-native workflow where the human sets goals and approves important actions, while the system does the operational work and learns from the result.

There must also be a replay backup for the demo. Live execution is the ideal path, but the event must not depend on external services behaving perfectly on stage.

## Expected End-of-Week Outcome

By the end of the week, we want to be able to say:

ABRT now has a real working P1 process engine, not just a prototype.

P1 is more stable, more observable, and closer to production quality.

The system can show what it is doing, explain what happened, and make its outputs easier to trust.

There is a clear first direction for the two demo surfaces: Telegram bot as the control panel and dashboard as the live operating view.

The architecture is beginning to show how it can scale beyond P1, but the actual build focus remains on making P1 strong enough for the June demo.

The quality bar is higher: successful runs should not only finish, they should produce results we are comfortable showing and using.

## Success Definition

This week is successful if, by Friday, we have:

- a more reliable P1 process,
- visibly better output quality,
- clearer run visibility,
- fewer black-box failures,
- a verified real P1 proof-pack path or a precise blocker list if infrastructure is missing,
- a practical first Telegram bot direction,
- a practical first dashboard direction,
- a concrete architecture path to support more ABRT processes after the demo,
- and stronger confidence that the system is moving toward production readiness.

The short version:

This week is about turning "P1 works" into "we can trust P1, operate it, show it live, and use it as the foundation for the rest of ABRT."
