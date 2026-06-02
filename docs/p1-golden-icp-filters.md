# P1 Golden ICP Filters

## Purpose

This document is the canonical qualification policy for ABRT/Limpid P1: finding and preparing high-quality angels/operators for outreach.

It merges:

- The old server implementation criteria from the Sovereign OS P1 scripts and gateway documents.
- The Google Sheet `01 ICP Definition` criteria.
- Current lead-scoring practice: keep fit, evidence, and readiness separate instead of letting one generic score hide weak qualification.

The goal is not to collect more leads. The goal is to identify the small number of people who are truly worth outreach: product-led B2C operators who have built at scale and who are personally active as angel investors.

## One-Sentence Definition

A qualified P1 lead is a senior B2C or product-led operator who has personally built or scaled consumer-facing product mechanics, has verified angel/check-writing activity, has enough current bandwidth to engage, and has clean evidence proving identity, role, investment activity, and fit.

## Golden ICP

The Golden ICP is a rare hybrid:

- Seasoned Product Leader or Product Founder.
- Consumer, mobile, marketplace, gaming, fintech, social, or product-led growth background.
- Personally experienced scaling a product to a large user base.
- Actively deploys personal capital as an angel investor or syndicate lead.
- Thinks in a systematic, data-driven, product-led way.
- Is reachable and likely to have enough attention for a high-context expert/investor conversation.

The best lead is not a traditional corporate manager and not a generic VC. The best lead is a hands-on product builder from an elite tech ecosystem who also writes checks.

## Best-Fit Persona

### Ideal Current or Past Roles

Strong positive roles:

- Chief Product Officer.
- VP Product.
- Head of Product.
- Lead Product Manager.
- Product Founder.
- Co-Founder with clear product ownership.
- Former product leader at a scaled consumer or product-led company.
- Fractional CPO.
- Independent product advisor with clear angel activity.
- Angel investor with strong product-operator history.
- Syndicate lead with consumer/product portfolio.

Secondary roles:

- CEO or founder with strong product evidence.
- Growth leader with direct product/growth mechanics ownership.
- Marketplace, monetization, or product analytics leader.
- Consumer fintech or gaming operator with direct scale responsibility.

Weak roles unless supported by strong evidence:

- Generic founder without product responsibility.
- Generic operator without consumer/product-led history.
- Advisor without personal investing proof.
- Mentor, accelerator judge, or ecosystem connector without check-writing proof.
- Corporate strategy, business development, or investor relations profile.

## Core Qualification Logic

Every qualified lead must pass three layers:

1. Hard gates.
2. Quality score.
3. Final gateway evaluation.

If a lead fails a hard gate, it should not be rescued by a high score in another category. For example, a current VP at a large company with no bandwidth should not pass just because they have great historical product experience.

## Hard Gates

### Gate 1: Identity Integrity

Identity must be verified before any scoring result is trusted.

Pass requirements:

- The person found by live research must match the provided name and historical anchors.
- LinkedIn, personal site, Crunchbase, AngelList, Dealroom, NfX Signal, company bio, or similar evidence must converge on the same person.
- Identity confidence should be at least 90 percent before outreach.
- Same-name collisions must be treated as failure unless resolved by evidence.

Reject or manual review:

- Different person with same name.
- Conflicting current role/history.
- No reliable source tying the person to the expected companies.
- LinkedIn URL slug or profile evidence does not match the person and cannot be resolved.

### Gate 2: B2C or Product-Led Product Experience

The lead must have evidence of building, scaling, or leading a consumer-facing or product-led product.

Pass examples:

- Consumer internet.
- Mobile apps.
- Social networks.
- Gaming.
- Consumer fintech.
- Marketplaces.
- Creator/community products.
- Digital health/lifestyle products, not biotech.
- Product-led SaaS with bottom-up user adoption.
- PLG tools with strong consumer-like adoption dynamics.

Strong proof points:

- Millions of MAUs.
- Millions of downloads.
- Global marketplace scale.
- Hyper-growth product.
- Viral loops.
- User acquisition and retention mechanics.
- Monetization.
- Product analytics.
- Growth hacking.
- Consumer scaling.
- Community-driven growth.

Reject:

- Enterprise-only B2B SaaS without PLG.
- IBM/Oracle/SAP-style enterprise background only.
- Corporate finance.
- Defense or military.
- Biotech.
- Heavy industry.
- Legal-only background.
- Academic-only background.

### Gate 3: Product Leadership

The lead must have had real product ownership, not only general management.

Pass:

- CPO, VP Product, Head of Product, Lead PM.
- Founder/co-founder where product ownership is explicit.
- Growth/product leader responsible for product mechanics.
- Marketplace/product analytics/monetization leader with clear product influence.

Secondary:

- CEO/founder without explicit product title, but with strong evidence they built the product.

Reject or down-rank:

- CEO/founder with no product evidence.
- Corporate manager with no direct product responsibility.
- Investor-only profile with no operator background.

### Gate 4: Verified Angel or Check-Writer Activity

The lead must have evidence of personally deploying capital.

Pass evidence:

- AngelList investor profile.
- Crunchbase personal investor profile.
- Dealroom investor evidence.
- PitchBook evidence.
- NfX Signal profile.
- Public portfolio page.
- Syndicate lead profile.
- Micro-fund or specialized fund founded by the person.
- Publicly listed angel investments.
- Founder/operator with clear personal portfolio.

Strong investor patterns:

- Direct angel investing.
- Syndicate participation.
- Syndicate leadership.
- Consumer tech portfolio.
- Gaming portfolio.
- Consumer fintech portfolio.
- E-commerce infrastructure investments.
- Product-led or AI/product tooling investments.

Reject:

- Investor relations.
- Mentor only.
- Advisor only.
- Accelerator judge only.
- Corporate VC partner without personal portfolio.
- Traditional VC partner where personal check-writing is not visible.
- "Investor" title with no portfolio evidence.

### Gate 5: Bandwidth

The lead must plausibly have enough current attention for outreach.

High bandwidth:

- Fractional CPO.
- Independent advisor.
- Angel investor.
- Solo founder.
- Building in stealth.
- On sabbatical.
- Recently exited operator.
- Former executive now investing/advising.

Low bandwidth:

- Current C-suite role at an operating company.
- Current VP role at an operating company.
- Current Director role at an operating company.
- Current GP or Partner at an active fund.
- Current CEO/founder of a scaling venture-backed startup with employees.
- Active role at a company with more than 50 employees.
- Recent full-time role start in 2025 or 2026 that suggests new operational commitment.

Important exception:

- "Founder" is not automatically bad. Solo, independent, stealth, or fractional founder profiles can be high bandwidth.
- "Advisor" is not automatically good. Advisor-only profiles still need investor and product proof.

### Gate 6: Geographic and Language Fit

Priority hubs:

- Silicon Valley.
- Palo Alto.
- San Francisco.
- Stanford ecosystem.
- Miami.
- London.
- Vienna.
- Amsterdam.
- Stockholm.

Server-side historical node cities also included:

- Cyprus.
- Luxembourg.

Hard exclusions from the Google Sheet ICP:

- India.
- LATAM.
- Non-English profiles.

These exclusions should be treated as current P1 policy unless the owner explicitly changes the target geography.

### Gate 7: No Duplicates

The same person must not be processed or published repeatedly.

Requirements:

- Deduplicate by normalized full name.
- Deduplicate by LinkedIn URL.
- Deduplicate by investor profile URL when available.
- Deduplicate before API calls when possible.
- If two records may be the same person but identity is uncertain, hold for manual review instead of merging silently.

## Quality Score

The old server triage used a 100-point score:

- B2C and PLG DNA: 0-45 points.
- Investor priority: 0-35 points.
- Systematic investing signal: 0-20 points.

That score is useful, but the updated ICP is stricter. The merged production score should separate the strongest business requirements more clearly.

### Recommended Production Score

Total: 100 points.

#### 1. B2C / PLG Product DNA: 0-30 points

30 points:

- Scaled mass-market consumer, mobile, social, gaming, marketplace, consumer fintech, or viral product.
- Clear evidence of growth, monetization, retention, marketplace dynamics, or user-scale product mechanics.

20-25 points:

- Strong PLG or bottom-up product-led background with consumer-like adoption.
- Examples: Notion, Figma, Slack, Dropbox, Wise, Trello, Superhuman, Box-like product-led companies.

10-15 points:

- Mixed product background with some consumer or PLG evidence, but not the core career story.

0-5 points:

- Enterprise-only, corporate, consulting, finance, heavy industry, legal, biotech, or unclear product DNA.

#### 2. Product Leadership: 0-20 points

20 points:

- CPO, VP Product, Head of Product, Lead PM, or product-owning founder at a scaled relevant company.

15 points:

- Senior PM, growth/product lead, marketplace/product analytics lead, or monetization lead with clear ownership.

10 points:

- Founder/CEO with some product evidence but no explicit product title.

0-5 points:

- General business, strategy, investing, finance, or advisory role without product ownership.

#### 3. Verified Angel / Check-Writer Activity: 0-25 points

25 points:

- Public personal portfolio, AngelList/Crunchbase/Dealroom/PitchBook/NfX Signal evidence, syndicate lead profile, or micro-fund founder evidence.

15-20 points:

- Strong public angel/investor claims with some portfolio evidence, but not fully complete.

5-10 points:

- Investing interest, advisory activity, or ecosystem participation without clear check-writing proof.

0 points:

- No personal investing evidence.
- Corporate VC only.
- Investor relations only.
- Mentor/advisor only.

#### 4. Liquidity / Elite Ecosystem Signal: 0-10 points

10 points:

- Major exit, unicorn equity path, or senior role at elite scaled company.
- Examples: Amazon, ByteDance/TikTok, Binance, Uber, Tesla, Yahoo, Yandex, Meta, Airbnb, Stripe, Revolut, Wise, Carta, AngelList.

5 points:

- Strong high-growth startup or known ecosystem, but no clear liquidity event.

0 points:

- No evidence of liquidity or elite ecosystem access.

#### 5. Systematic Product / Investing Fit: 0-10 points

10 points:

- Explicit data-driven, algorithmic, quant, ML, analytics, thesis-driven, signal-based, metrics-based, evidence-based, or framework-based language.

5 points:

- Background implies strong structured thinking: analytics leader, data scientist, product ops, growth analytics, investment/product infrastructure.

0 points:

- Purely qualitative profile with no systematic signal.

#### 6. Geography and Language Fit: 0-5 points

5 points:

- Priority hub and English-language profile.

3 points:

- English-language profile outside priority hubs but still reachable/relevant.

0 points:

- Excluded geography or non-English profile.

## Score Interpretation

Scoring only applies after hard gates are checked.

### 85-100: Gold

Meaning:

- Strong Golden ICP.
- Ready for final gateway and likely outreach.

Required action:

- Publish only if identity, bandwidth, and evidence are clean.

### 70-84: Strong

Meaning:

- Likely good, but one area needs better evidence or manual judgment.

Required action:

- Hold for intelligence enrichment or gateway review.
- Do not outreach until the missing evidence is resolved.

### 50-69: Data Lake Only

Meaning:

- Interesting but not outreach-ready.
- May become useful later, but not current priority.

Required action:

- Save dossier if evidence is real.
- Do not publish as a winner.

### Below 50: Reject

Meaning:

- Not a meaningful P1 fit.

Required action:

- Reject with explicit reason.
- Do not spend further provider calls unless the owner requests re-check.

## Final Gateway

The final gateway decides whether a lead can move to outreach.

Required final signals:

- Identity confidence: at least 90 percent.
- Bandwidth: HIGH.
- Liquidity: YES or strong enough ecosystem/liquidity evidence.
- Product/B2C fit: PASS.
- Verified investor/check-writer evidence: PASS.
- Exclusion check: PASS.
- Evidence sufficiency: PASS.

The old server gateway treated identity, liquidity, and bandwidth as the core "Ultimate Trifecta." The updated P1 gateway should expand this into:

- Identity integrity.
- Product-led B2C fit.
- Verified check-writer activity.
- Bandwidth.
- Liquidity/ecosystem signal.
- Systematic alignment.
- Evidence sufficiency.

## Decision Statuses

Use explicit statuses. Do not hide weak evidence under generic "qualified" language.

### Awaiting Outreach

Use when:

- Hard gates pass.
- Score is Gold or strong enough after manual review.
- Final gateway passes.
- Outreach angle is clear.

### Qualified - Needs Enrichment

Use when:

- Person looks promising.
- One evidence area is missing or incomplete.
- More Exa/LinkedIn/Crunchbase/AngelList/Dealroom/PitchBook/NfX Signal research is needed.

### Manual Review Required

Use when:

- Identity is plausible but not certain.
- Bandwidth is unclear.
- Investor evidence is ambiguous.
- The person is a founder/executive and the current commitment level is unclear.

### Data Lake Only

Use when:

- Lead is interesting but not outreach-ready.
- Score is 50-69.
- Missing investor proof or bandwidth clarity prevents action.

### Bypass

Use when:

- Identity is valid, but the person is currently too busy.
- Liquidity is missing.
- Investor proof is missing.
- Profile is adjacent but not a strong P1 fit.

### Reject

Use when:

- Hard exclusion applies.
- Product DNA is absent.
- Investor evidence is absent and profile is not strategically useful.
- Profile is non-English or excluded geography under current policy.
- Enterprise/corporate/defense/biotech/heavy industry/legal-only profile.

### Identity Mismatch

Use when:

- Live evidence points to a different person.
- Same-name collision is unresolved.
- Historical anchors do not match current evidence.

## Positive Signal Library

### Company and Ecosystem Signals

Strong positive ecosystems:

- Amazon.
- ByteDance / TikTok.
- Binance.
- Uber.
- Tesla.
- Yahoo.
- Yandex.
- Meta.
- Airbnb.
- Stripe.
- Revolut.
- Wise.
- Carta.
- AngelList.
- Notion.
- Figma.
- Slack.
- Dropbox.
- Trello.
- Superhuman.
- Box.

These companies are not automatic pass signals. They only matter when tied to product leadership, consumer/product-led scale, liquidity, or investment activity.

### Product and Growth Keywords

Strong positive keywords:

- CPO.
- VP Product.
- Head of Product.
- Lead PM.
- Product founder.
- Consumer scaling.
- Viral loops.
- Growth hacking.
- Monetization.
- Product analytics.
- Retention.
- Activation.
- Marketplace.
- Millions of MAUs.
- Millions of downloads.
- Hyper-growth.
- Global marketplace.
- Community-driven growth.
- PLG.
- Bottom-up adoption.

### Investor Keywords

Strong positive keywords:

- Angel investor.
- Active angel.
- Syndicate lead.
- Personal portfolio.
- Micro-fund founder.
- Venture lab founder.
- Direct investments.
- Check writer.
- Deal flow.
- NfX Signal.
- AngelList.
- Dealroom.
- PitchBook.
- Crunchbase investor profile.

### Systematic Fit Keywords

Strong positive keywords:

- Data-driven.
- Quant.
- Algorithmic.
- AI-scored.
- Machine learning.
- Product analytics.
- Metrics-based.
- Evidence-based.
- Thesis-driven.
- Signal-based.
- Framework.
- Risk-adjusted.
- Hypothesis.
- Allocation.
- Investment infrastructure.
- Product infrastructure.

## Negative Signal Library

### Excluded Industries and Backgrounds

Reject or heavily down-rank:

- B2B enterprise-only SaaS.
- Oracle/Salesforce/SAP/IBM-style enterprise background without PLG.
- Corporate finance.
- Investor relations.
- Defense.
- Military.
- Biotech.
- Heavy industry.
- Legal.
- Academic-only.
- Consulting-only.
- Corporate banking.

### Excluded or Weak Investor Profiles

Reject or down-rank:

- Traditional VC partner without personal portfolio evidence.
- Corporate VC without personal check-writing evidence.
- Mentor only.
- Advisor only.
- Accelerator judge only.
- Board member only.
- "Investor" keyword without portfolio proof.

### Bandwidth Red Flags

Reject from current outreach or mark Bypass:

- Current C-suite at active company.
- Current VP at active company.
- Current Director at active company.
- Current GP or Partner at active fund.
- Current CEO/founder of scaling company with employees.
- Recent 2025/2026 full-time executive hire.
- Large operational team commitment.

## Evidence Requirements

Each lead dossier should preserve evidence, not just conclusions.

Minimum evidence fields:

- Full name.
- LinkedIn URL or strongest identity URL.
- Current role.
- Current company.
- Current role source URL.
- Historical product/operator anchors.
- Product leadership evidence.
- B2C/PLG scale evidence.
- Investor/check-writer evidence.
- Portfolio evidence URL if available.
- Liquidity/ecosystem evidence.
- Systematic alignment evidence.
- Geography/language evidence.
- Bandwidth evidence.
- Exclusion check result.
- Gateway decision.
- Reasoning summary.

Evidence should include source URLs wherever possible.

If evidence is missing, the system must say what is missing. It must not infer a pass from vibes.

## Search and Research Rules

### Source Priority

Preferred sources:

- LinkedIn.
- Personal website.
- Crunchbase.
- AngelList.
- Dealroom.
- PitchBook.
- NfX Signal.
- Company bio.
- Fund/syndicate page.
- Public portfolio page.
- Recent interviews, podcasts, or posts.
- Exa search results with URLs.
- Apify/Crunchbase actor results when available.

### LinkedIn Block Handling

If LinkedIn is blocked or unavailable, do not fail silently and do not invent identity.

Use omni-channel search:

- Name + company + LinkedIn.
- Name + company + Twitter/X.
- Name + company + personal website.
- Name + company + read.cv.
- Name + company + Crunchbase.
- Name + company + AngelList.
- Name + company + portfolio.

### Career Pivot Handling

Do not treat every career pivot as an identity mismatch.

Example logic:

- Former Airbnb VP now independent writer/advisor can still be identity match.
- Former product leader now angel investor can be ideal.
- Former operator now active Apple Director may be identity match but low bandwidth.

The system must separate:

- Is this the same person?
- Is this person currently a good outreach target?

## Runtime Implications

### Watchtower

Watchtower should search for leads that match the Golden ICP, not broad "investor" or broad "operator" lists.

Watchtower should prioritize:

- Product leadership plus angel keywords.
- Consumer/PLG scale keywords.
- Public investor portfolio signals.
- Priority hubs.

### Triage Agent

Triage should:

- Apply hard exclusions early.
- Score fit with the production score.
- Save only evidence-backed dossiers.
- Reject explicitly when required evidence is absent.

### Data Lake

The Data Lake should store all real evidence and decisions.

It should not store vague summaries as substitutes for source-backed facts.

### Intelligence Gatherer

The Intelligence Gatherer should fill the missing evidence fields:

- Current role.
- Bandwidth.
- Investor proof.
- Product scale proof.
- Identity convergence.
- Geography/language.

### Gateway Evaluator

Gateway should be strict and cynical.

It should not optimize for passing leads. It should optimize for preventing weak leads from reaching outreach.

### Registry Publisher

Publisher should only sync winners that pass final gateway.

It should publish to a dedicated new-leads tab when requested, so fresh P1 output does not mix with old records.

### Outreach Architect

Outreach should only draft for leads in `Awaiting Outreach`.

Drafts must reference real evidence:

- Product/operator history.
- Investor portfolio.
- Why Limpid/ABRT is specifically relevant.
- A concrete outreach angle.

## Acceptance Criteria

The P1 lead filter is implemented correctly when:

- Every outreach-ready lead has verified identity.
- Every outreach-ready lead has B2C/PLG product evidence.
- Every outreach-ready lead has product leadership evidence.
- Every outreach-ready lead has verified angel/check-writer evidence.
- Every outreach-ready lead has a bandwidth decision.
- Every rejected or bypassed lead has a specific reason.
- No enterprise-only, defense, military, biotech, heavy industry, legal, non-English, India, or LATAM profile reaches outreach under current policy.
- No mentor/advisor/corporate VC profile reaches outreach without personal check-writing proof.
- No active busy executive reaches outreach without explicit owner approval.
- Every score is backed by preserved evidence.
- Missing evidence produces `Qualified - Needs Enrichment`, `Manual Review Required`, `Data Lake Only`, or `Reject`, not a fake pass.

## External Practice Notes

Current lead-scoring practice generally supports the same structure used here: define ICP fit, score explicit profile attributes, preserve qualification evidence, and separate qualified leads from weak leads before sales/outreach handoff.

Useful references:

- [TechTarget lead scoring best practices](https://www.techtarget.com/searchcustomerexperience/tip/10-lead-scoring-best-practices-to-improve-sales-efficiency)
- [Apollo high-value lead criteria](https://www.apollo.io/insights/what-criteria-should-i-use-to-find-high-value-b2b-leads)
- [UpLead lead scoring guide](https://www.uplead.com/lead-scoring/)

These references are not the source of the P1 ICP. The source of the P1 ICP is the ABRT/Limpid server history plus the Google Sheet definition. The external references only confirm the structure: hard fit criteria, evidence-backed scoring, and clear qualification handoff.
