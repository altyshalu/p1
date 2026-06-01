# Altynai Task Plan: P1 Reproducible Quality Audit Pack

**Owner:** Altynai

**Branch:** `feat/p1-quality-audit-pack`

**Priority:** Current number one priority from the production readiness sequence.

**Merge owner:** Nikita

## Purpose

Your task is to make P1 quality review reproducible.

Nikita will review the current P1 output from the human/business side. Your work should support that by making the system produce a clear audit pack from real P1 runs: what was collected, what passed, what failed, what evidence exists, where quality looks weak, and what should be manually reviewed.

This is not about improving P1 yet. This is about making the current quality visible and measurable so the team can improve it intelligently.

The question you are answering is:

Can we inspect a real P1 run and automatically surface the quality signals that matter?

## Why This Runs in Parallel With Nikita's Task

Nikita's task is qualitative: decide what good means and judge whether the current output is production-worthy.

Your task is reproducibility: make sure the same type of review can be repeated on future real runs without manually digging through artifacts every time.

These two tasks are parallel because they touch different layers:

- Nikita owns the human quality bar and business judgment.
- You own the audit pack that extracts and summarizes real quality signals.

This lets both branches merge cleanly if file ownership stays separate.

## Scope

You own the read-only quality audit layer.

The audit pack should inspect real P1 run data and summarize quality signals. It should not fake data, create demo runs, silently skip missing dependencies, or write to production systems.

The output should help the team understand:

- how many leads were collected,
- how many were normalized,
- how many passed triage,
- how many passed gateway evaluation,
- how many final dossiers exist,
- how many outreach drafts exist,
- how many external write outputs exist,
- which required fields are missing,
- where evidence is thin,
- where candidates look duplicated,
- where outreach looks generic,
- where claims may be unsupported,
- and which records need human review.

## Files You Should Own

Recommended files:

- `scripts/real-p1-quality-audit.py`
- `docs/reports/p1-quality-audit-pack.md`
- optional: `tests/test_real_p1_quality_audit.py`

Avoid touching:

- Nikita's rubric/report files,
- UI files,
- broad runtime architecture,
- unrelated process contracts,
- unrelated registries,
- external publishing behavior.

The audit should be read-only unless Nikita explicitly approves a behavior change.

## Step 1: Identify the Real P1 Data Sources

Start by identifying where the real P1 run data lives today.

The audit pack should read from the same real execution sources the system already uses: run records, tasks, artifacts, evals, events, and proof outputs.

Do not add a new fake data path. Do not create embedded sample payloads. Do not make the script pass when the real run does not exist.

If a required run, artifact, database, credential, or service is missing, the audit should fail clearly and say what is missing.

This step is successful when you can describe exactly where the audit reads data from and how another developer can point it at a real run.

You can move on when there is no ambiguity about the source of truth.

## Step 2: Build the Read-Only Audit Command

Create a command that runs against a real P1 run and produces a quality audit summary.

The command should be explicit. It should require a real run identifier or a clearly documented real input. It should not silently choose an example run. It should not generate fake outputs if the run is missing.

The command should produce both:

- a machine-readable output, preferably JSON,
- and a human-readable Markdown summary.

The Markdown summary should be easy for Nikita to use in his quality review.

This step is successful when the command can be run locally against a real P1 run and produce a clear audit result.

You can move on when the command either succeeds with real data or fails with a precise missing-dependency message.

## Step 3: Add Basic Funnel Integrity Checks

The first audit layer should check whether the P1 funnel is structurally coherent.

It should summarize:

- raw leads count,
- normalized leads count,
- triage count,
- gateway-approved count,
- dossier count,
- draft count,
- sheet/output count where available,
- and outreach master count where available.

It should flag suspicious cases:

- zero outputs after non-zero inputs,
- mismatched final counts,
- missing final artifacts,
- duplicate candidate identities,
- missing LinkedIn URLs,
- missing evidence URLs,
- missing outreach drafts,
- or missing external write summaries.

This step comes before deeper subjective quality checks because structural integrity is the fastest way to catch broken runs.

This step is successful when the audit can quickly say whether a real run has a coherent funnel.

You can move on when the funnel counts and missing-output warnings are reliable.

## Step 4: Add Evidence and Grounding Signals

After funnel integrity, inspect evidence quality.

The audit should not try to replace human judgment. It should surface signals that help humans judge faster.

Useful signals include:

- number of evidence links per approved lead,
- source diversity,
- missing source URLs,
- claims with no supporting link,
- stale or unclear evidence,
- weak identity evidence,
- and records where the evidence does not obviously support the approval.

The audit should mark these as review signals, not final truth.

This step is successful when the audit makes weak evidence easy to find.

You can move on when Nikita can use the audit output to prioritize which leads need manual review.

## Step 5: Add Outreach Quality Signals

Next, inspect outreach draft quality.

Again, this should not pretend to be a perfect judge. It should catch obvious issues and surface review candidates.

Useful signals include:

- missing personalization,
- overly generic wording,
- missing connection to ABRT/Limpid,
- unsupported claims,
- too-short or too-long drafts,
- missing recipient name,
- missing evidence-backed hook,
- repeated templates across multiple people,
- and drafts that look unsafe to send without heavy editing.

The audit should help the team find weak drafts quickly.

This step is successful when the audit can separate likely-good drafts from drafts that clearly require human review.

You can move on when the outreach section gives Nikita useful review targets.

## Step 6: Add Quality Risk Summary

After collecting structural, evidence, and outreach signals, produce a final quality risk summary.

The summary should classify the run into a simple state:

- looks healthy,
- needs review,
- blocked by missing data,
- blocked by weak output,
- or failed audit.

This is not the final production decision. Nikita owns the human baseline decision. Your audit should provide input into that decision.

The summary should include:

- top risks,
- affected leads,
- missing artifacts,
- suspicious counts,
- weak evidence areas,
- weak outreach areas,
- and recommended human review focus.

This step is successful when the audit output tells the team where to look first.

You can move on when the summary is concise and actionable.

## Step 7: Document the Audit Pack

Write a short document explaining:

- what the audit checks,
- what it does not check,
- how to run it,
- what real dependencies are required,
- how to interpret the result,
- and what counts as a failure.

The document should be honest about limits. If the audit cannot determine subjective quality, say that clearly. If a human review is required, say so.

This step is successful when another developer can run the audit without asking you how it works.

You can move on when the command and docs are understandable from a fresh checkout.

## Step 8: Run a Real Smoke Check

Run the audit against a real P1 run.

Do not use fake data. Do not add fallback data. Do not make the proof pass if the real run is missing.

If the real infrastructure is unavailable, the result should be an explicit failure that says what is missing.

The smoke check should confirm:

- the audit can load the real run,
- the counts are extracted,
- missing fields are flagged,
- evidence signals are produced,
- outreach signals are produced,
- and the final risk summary is generated.

This step is successful when the audit produces a real report or fails for a concrete real reason.

## Success Criteria

Your task is successful when the branch contains:

- a real read-only P1 quality audit command,
- a human-readable audit report format,
- basic funnel integrity checks,
- evidence quality signals,
- outreach quality signals,
- a quality risk summary,
- documentation,
- and a real smoke-check result.

The work is not successful if it only works on fake payloads.

The work is not successful if it silently ignores missing artifacts.

The work is not successful if it writes to external systems or changes runtime behavior without approval.

## Handoff to Nikita

Your handoff should include:

- the branch name,
- the command to run,
- the real run ID used for smoke check,
- the produced audit report path,
- the top quality risks found,
- and any fields/artifacts that were hard to inspect.

Nikita will use this to complete the human baseline decision and merge the work.

## Merge Guidance

Nikita is the merge owner.

Keep your branch focused and easy to review. Avoid touching files outside the audit scope unless absolutely required.

Recommended merge flow:

1. Push `feat/p1-quality-audit-pack`.
2. Send Nikita the smoke-check result and report path.
3. Nikita reviews and merges your branch first if it is clean.
4. Nikita then updates his quality baseline report with any useful audit findings.

## Done Means

Done means the team can run one command against a real P1 run and get a useful quality audit pack.

The audit does not need to decide all subjective quality questions. It needs to make real quality review faster, repeatable, and harder to fake.
