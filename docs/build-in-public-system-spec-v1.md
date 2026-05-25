# ABRT Build-in-Public System Spec v1

**Status:** Deferred until after the first L2 <-> L3 protocol milestone

## Purpose

ABRT should eventually run a build-in-public distribution system that minimizes team time spent on social media while maximizing reach, credibility, feedback, and public proof of work.

This should not be treated as a generic posting bot. It should be treated as a small operational system for distribution, powered by the same architecture principles behind ABRT itself.

## Strategic framing

The strongest version of this system is a dogfooding instance of ABRT's own thesis:

- `L2` acts as the content and distribution manager
- `L3` acts as a set of narrow, channel-specific execution workers

This allows the team to test the same management logic on a real internal workflow while keeping humans focused on review, taste, and higher-level judgment.

## Core architecture

### L2: Distribution Manager

The L2 distribution layer should:

- decide which internal or external signals are worth turning into content
- choose the right channel for each piece
- decide timing and scheduling
- route work to the appropriate L3 worker
- evaluate output quality
- request rewrites or alternate angles
- escalate to human review only for approval, edits, or edge-case judgment

### L3: Channel-Specific Workers

Candidate workers:

- `L3-X-Reply-Worker`
- `L3-X-Post-Worker`
- `L3-LinkedIn-Post-Worker`
- `L3-Weekly-Blog-Worker`
- `L3-GitHub-Log-Worker`

Each worker should be work_order-bound and narrow. It should know only the content task it receives, not the full strategic orchestration context.

## Channel recommendation for v1

Primary channels:

- `X` for realtime discourse, network effects, and technical visibility
- `LinkedIn` for founder/company narrative and legitimacy
- `GitHub` for public proof of work and visible progress
- `Weekly blog or notes` for long-form synthesis

Not core in v1:

- `Reddit`

Reason: Reddit may matter later, but it is lower-confidence, less predictable, and easier to misuse with semi-automation. It should remain manual or opportunistic until the main loop is stable.

## System shape

The build-in-public system should eventually include:

1. `Signal ingestion`
   Internal signals: commits, docs, architecture decisions, demos, bugs, failures, fixes, lessons learned.
   External signals: watchlists, GitHub, HN, papers, launches, discourse.

2. `Narrative engine`
   Convert signals into reusable content atoms:
   build updates, technical insights, founder POV, disagreements, demos, weekly syntheses.

3. `Channel adapters`
   Adapt one source idea into channel-specific outputs for X, LinkedIn, GitHub, and long-form writing.

4. `Approval console`
   Human review surface with fast approve/reject/edit/schedule actions.
   The existing swipe-based mobile review pattern from the X operator system is the preferred UX reference.

5. `Learning loop`
   Learn from edits, rejections, post performance, and feedback so the system improves over time.

## Reuse from the existing X Operator pattern

The existing `x-operator-pipeline` should be the main implementation reference for:

- staged flow: `collect -> synthesize -> approve -> publish -> learn`
- SQLite or equivalent single state layer
- browser-native publishing
- Telegram or Mini App approval loop
- mobile-first swipe review UX
- self-improvement via edit/rejection trajectories

ABRT should not copy it blindly. It should generalize it from a single-channel X operator into a multi-channel distribution operating layer.

## Why defer it

This system is important, but it should come after the first serious L2 <-> L3 protocol work, because:

- the distribution system should reuse the same orchestration ideas
- it is a strong dogfooding environment for the core protocol
- building it too early risks creating a content tool instead of a true ABRT-native management layer

## Return trigger

Return to this spec after:

- the first usable L2 <-> L3 protocol exists
- worker lifecycle and intervention logic are clearer
- the team is ready to dogfood ABRT on an internal operations workflow

## Intended outcome

The end state is not “post more.”

The end state is:

- minimal team time spent on distribution
- maximum leverage from public progress
- human review preserved where taste and judgment matter
- a real internal proving ground for ABRT's management architecture
