# Nikita Task Plan: P1 Human Quality Baseline

**Owner:** Nikita

**Branch:** `feat/p1-quality-baseline-review`

**Priority:** Current number one priority from the production readiness sequence.

**Merge owner:** Nikita

## Purpose

Your task is to define whether P1 output is actually good enough to trust.

This is deliberately not a code-first task. The point is to look at the real outputs from the current P1 process and decide what quality means before the team improves, stabilizes, scales, or builds UI around the system.

P1 is currently our strongest real workflow proof. If P1 quality is weak, scaling the protocol to more ABRT processes will only spread weak assumptions. So the first move is to create a clear human/business quality baseline.

The question you are answering is:

Would we be comfortable using the current P1 output in a real ABRT founder/operator workflow?

## Why This Comes First

This task comes before runtime hardening, observability, UI, and multi-process scaling because none of those matter if the output itself is not good.

A system can be stable and still produce mediocre results. A dashboard can be beautiful and still show weak leads. A generalized process engine can scale and still multiply low-quality work.

So your job is to define the production-quality bar from the business side:

- what a good lead looks like,
- what a weak lead looks like,
- what evidence is strong enough,
- what outreach is usable,
- what output would embarrass us,
- and what must be fixed before we call P1 production-ready.

## Scope

You own the qualitative review layer.

You should focus on:

- final approved P1 leads,
- rejected or filtered leads where available,
- dossiers,
- live intelligence evidence,
- gateway evaluation reasoning,
- final Google Sheet-style output,
- outreach drafts,
- and the overall founder/operator usefulness of the results.

You should not focus on implementation details unless they directly affect quality. You do not need to change runtime code in this branch.

## Files You Should Own

Create and edit only planning/reporting files unless you intentionally decide otherwise.

Recommended files:

- `docs/quality/p1-quality-baseline-rubric.md`
- `docs/reports/p1-quality-baseline-review-2026-06-01.md`

Avoid touching:

- runtime code,
- worker code,
- scripts owned by Altynai's audit branch,
- API code,
- UI code,
- registry files,
- tests.

This keeps your branch easy to merge with Altynai's parallel work.

## Step 1: Collect the Real P1 Output Set

Start by identifying the real P1 run or runs that represent the current system.

Use existing proof documentation and real artifacts. Do not invent example candidates. Do not review hypothetical output. Do not fill gaps with fake data.

The review set should include the actual current P1 outputs:

- raw lead source summary,
- normalized leads,
- triage results,
- dossiers,
- intelligence/evidence,
- gateway-approved leads,
- final publish-ready records,
- outreach drafts,
- and any recorded quality eval results.

The output of this step should be a short section in your review report that says exactly which real run or artifact set you reviewed.

You can move on when the reviewed source set is explicit enough that someone else can find the same outputs and reproduce the review.

## Step 2: Define the Quality Rubric

Before judging the outputs, define the rubric.

The rubric should be practical, not academic. It should describe what makes a P1 result usable for ABRT.

Suggested dimensions:

- **Lead relevance:** Is this person actually relevant for ABRT/Limpid/operator outreach?
- **Identity confidence:** Do we know who this person is, or is the record ambiguous?
- **Operator/investor fit:** Does the person have meaningful startup, operator, investor, PLG, B2C, AI, or systems relevance?
- **Evidence strength:** Are claims backed by real sources?
- **Context freshness:** Is the information recent enough to matter?
- **Decision reasoning:** Is the approval/rejection logic understandable?
- **Outreach usefulness:** Would we send or lightly edit this outreach draft?
- **Personalization quality:** Does the outreach reference specific, true context?
- **Risk:** Is there anything that would make this output unsafe, embarrassing, spammy, or misleading?

The rubric should classify output into clear levels:

- production-ready,
- usable with light human edit,
- needs significant improvement,
- reject.

You can move on when the rubric is clear enough that another reviewer could use it and reach roughly the same judgment.

## Step 3: Review the Final Approved Leads

Review every final approved P1 lead in the chosen proof set.

For each lead, write a concise judgment:

- why the lead is relevant,
- what evidence supports the decision,
- what feels weak or missing,
- whether the lead should stay approved,
- whether the outreach is usable,
- and whether the record is production-ready.

Do not only look for failures. Also identify what is already strong, because that tells the team what to preserve.

The output of this step should be a table or structured section in the review report. It does not need to be beautiful, but it must be specific.

You can move on when every final approved lead has a clear human-quality judgment.

## Step 4: Review the Output as a System, Not Just Individual Leads

After reviewing individual leads, step back and judge P1 as a full process.

Look for patterns:

- Are too many candidates similar?
- Are the scores too generous?
- Are weak leads slipping through?
- Are strong leads being missed?
- Is the outreach too generic?
- Does evidence actually support the claims?
- Are the final outputs easy for an operator to use?
- Would this save time in a real workflow?
- Would this be safe to show to founders?

The goal is to identify systemic quality problems, not just one-off examples.

You can move on when the report clearly separates individual lead issues from process-level quality issues.

## Step 5: Define Production Blockers

Now convert observations into blockers.

Use three levels:

- **Must fix before production:** These issues make P1 unsafe, low-trust, or not useful enough.
- **Should fix soon:** These issues reduce quality but do not block controlled usage.
- **Can defer:** These are polish or second-order improvements.

Be strict. If something would cause a founder or operator to lose trust in the system, it is a production blocker.

You can move on when the team can look at the report and immediately understand the top quality risks.

## Step 6: Write the Baseline Decision

End the report with a direct decision.

Choose one:

- P1 is production-ready for controlled internal usage.
- P1 is close, but blocked by specific quality issues.
- P1 is not production-ready yet.

Do not soften the answer. The point of the baseline is to create clarity.

The decision should include:

- what is already good,
- what must improve,
- what should be tested next,
- and what Altynai's audit tooling should help measure repeatedly.

## Success Criteria

Your task is successful when the branch contains:

- a clear P1 quality rubric,
- a real-output review report,
- quality judgments for the final approved leads,
- process-level quality issues,
- production blockers,
- and a direct baseline decision.

The work is not successful if it only says "looks good" or "needs improvement" without evidence.

The work is also not successful if it reviews fake examples, synthetic data, or imagined outputs.

## Handoff to Altynai

Altynai's parallel branch will focus on making quality review reproducible through real audit tooling.

Your handoff to her should be:

- the dimensions that matter most,
- the quality issues that should become measurable signals,
- any artifact fields that were hard to inspect manually,
- and any outputs that need better structure for future UI/observability.

## Merge Guidance

You are the merge owner.

Recommended merge order:

1. Merge Altynai's audit branch first if it lands cleanly and produces useful audit output.
2. Rebase or update your review branch if you want to reference her audit outputs.
3. Merge your quality baseline report after the final decision is written.

This keeps the final main branch containing both:

- the human quality baseline,
- and the reproducible audit mechanism.

## Done Means

Done means the team can say:

We know the current real quality of P1. We know what production-ready means. We know which quality issues matter most. We know whether P1 can move forward or must be improved first.
