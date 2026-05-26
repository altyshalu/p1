# YC Application Q&A

## How long have the founders known one another and how did you meet? Have any of the founders not met in person?

We have known each other for three months, but it has been an intense three months. We met through a Kyrgyz Republic startup program that sent both of our previous startups to Silicon Valley. Both teams won spots, and we spent a month together in the US living and working around the same startup house/community.

That month was a real stress test: new country, long days, pitching, feedback, pressure, and constant plan changes. We saw how each other thinks, reacts under stress, handles feedback, and keeps working when things are messy. After that trip we decided to build together and started Taskforce with ABRT AI Lab. All founders have met in person.

## Who writes code, or does other technical work on your product? Was any of it done by a non-founder? Please explain.

All technical work is done exclusively by the founders. Nikita is our lead engineer — he builds the core L2/L3 protocol, implements the agent architecture, and handles all production code. Altynai is our AI research engineer and Head of AI Memory, focused on agent memory systems, including knowledge graphs, cross-session recall, and competitive technical analysis. She also designed our proprietary CLARK semantic memory algorithm for durable project knowledge, tool memory, and rule-based cross-session retrieval. No non-founders touch the codebase.

## Are you looking for a cofounder?

No

## Company name*

Taskforce

## Describe what your company does in 50 characters or less.*

Coordination layer for AI agent teams

## Company URL, if any

taskforcehub.dev

## Please provide a link to the product, if any.



## Please provide a link to the product, if any.



## What is your company going to make? Please describe your product and what it does or will do.

Every serious AI workflow has the same bottleneck: a human stuck in the middle, checking outputs, fixing failures, and babysitting agents. Taskforce is the coordination layer that removes that human from the middle safely.

A team gives Taskforce a workflow, and Taskforce breaks it into jobs, assigns each job to the right AI worker, checks the output, retries or repairs failures, preserves memory, and stops for human approval only when something important is about to happen in the real world.

The first use case is VC and company operations: sourcing startups, researching markets, doing diligence, preparing reports, supporting founders, and running internal workflows. We are building the coordination protocol that makes AI agents useful as a reliable workforce, not just as one-off chatbots.

## Where do you live now, and where would the company be based after YC?

Bishkek, Kyrgyz Republic / Palo Alto, USA

## Explain your decision regarding location.



## How far along are you?

Working prototype. We are using Taskforce with ABRT AI Lab on real VC workflows, including startup sourcing, market research, diligence, reporting, founder support, and host/candidate discovery.

One concrete workflow is a multi-agent host-finding pipeline: Taskforce researches candidates, verifies identity, checks relevance, deduplicates profiles, and prepares outreach context. The goal is to turn work that normally takes days of analyst time into a supervised AI workflow that runs in hours, with humans only reviewing edge cases and approvals.

Under the hood, Taskforce breaks a workflow into bounded jobs, assigns each job to the right AI worker, checks outputs, retries or repairs failures, stores run state and memory, and requires human approval before external actions (e.g. outreach)

## How long have each of you been working on this? How much of that has been full-time? Please explain.

We have both worked on this full-time for the past 3 months, usually 12-15 hours a day. The first month overlapped with the Silicon Valley startup program, where we lived and worked around the same startup house and tested whether we could handle pressure together. Since then we have been building Taskforce every day.

In that time we built the core product ourselves end-to-end: protocol architecture, agent runtime, memory research, implementation, and product design. The time frame is short, but the working relationship has been intense: we have already made technical decisions quickly, handled ambiguity, disagreed and resolved it, and kept shipping under pressure.

## What tech stack are you using, or planning to use, to build this product? Include AI models and AI coding tools you use.

Backend: Python 3.13, FastAPI, Pydantic, SQLAlchemy, Alembic, Postgres/asyncpg, Docker Compose, Textual TUI, structlog, pytest. Registry/playbooks/workers/evals are defined as YAML seeds and synced into a database-backed Taskforce Hub. Memory layer: AgentMemory plugin + Custom CLARK algorithm for semantic memory + Qdrant. Frontend/landing: React, TypeScript, Vite/TanStack Router, Tailwind-style CSS, shadcn components, Cloudflare/Vercel/Railway deployment targets.

AI models: frontier GPT, Gemini, and DeepSeek models, chosen by task complexity, cost, and required reasoning/reliability. AI coding tools: Hermes agent harness, Codex, and OpenCode depending on the task.

## How many active users or customers do you have? How many are paying? Who is paying you the most, and how much do they pay you?

We are pre-revenue but have real design partners/users. ABRT AI Lab is our main design partner; we are building toward an AI-native VC fund operating system with them, starting from sourcing, diligence, research, and portfolio-support workflows. We are also in conversations/pilots with companies in Kyrgyzstan, including Red Petroleum-type operational businesses, where the pain is repetitive research, analysis, internal operations, and workflow execution.

0 paying customers today. We are intentionally not counting design partners as revenue until commercial terms are signed.

## If you are applying with the same idea as a previous batch, did anything change? If you applied with a different idea, why did you pivot and what did you learn from the last idea?

We have not applied to YC before.

## If you have already participated or committed to participate in an incubator, "accelerator" or "pre-accelerator" program, please tell us about it.

We have not participated in or committed to any incubator, accelerator, or pre-accelerator program.

## Why did you pick this idea to work on? Do you have domain expertise in this area? How do you know people need what you're making?

We picked this idea because we felt the problem ourselves. AI tools can make a founder much faster, but only if the founder keeps managing the agents: breaking work into steps, checking outputs, fixing failures, preserving context, and stopping unsafe actions. That is the dirty work in the middle of every AI workflow.

Companies are racing to become AI-native, but the foundation is missing. Without a coordination layer, they do not get autonomous operations; they get AI-assisted chaos with humans babysitting agents.

Our domain expertise comes from building agentic systems directly and from working with ABRT AI Lab/ABRT VC on real VC operating workflows. These workflows are perfect early examples: sourcing, diligence, research, founder support, investor matching, reporting, and portfolio operations are repetitive, high-value, multi-step, and require reliability.

We know people need this because every serious AI workflow we see has the same bottleneck: the human is still stuck in the loop doing operational cleanup. Taskforce moves humans back to strategy, judgment, and edge cases instead of keeping them in the middle of every task.

## Who are your competitors? What do you understand about your business that they don't?

We do not think there is a perfect direct competitor yet. The closest products are Stilla, Rodin, Copyl, and Paperclip. They overlap with us because they also treat AI as workers, teammates, or managed automation.

The architectural mistake we think most of the market is making is starting from the worker. They try to make better agents, more agents, or usual harness of agents. But in real company workflows, the hard part is not creating another agent. The hard part is coordinating many imperfect agents so they can do useful work without a human babysitting every step.

Without a coordination layer, adding more agents creates more failure modes: duplicated work, lost context, unchecked outputs, unclear ownership, and unsafe external actions. Taskforce starts from the management layer: assigning work, checking outputs, repairing failures, preserving memory, and escalating only the decisions that actually need a human (and further trying to minimize human interaction after gathering feedback).

## How do or will you make money? How much could you make?

We will make money as B2B software for companies that run recurring work through AI agents. The initial model is a subscription for the coordination runtime, plus usage-based pricing for agent execution and managed enterprise deployments.

Early pricing will be $1k-$5k/month for startups and small teams running a few important workflows, and $25k-$250k/year for larger companies, funds, and operations-heavy businesses that need custom playbooks, private deployment, governance, integrations, and approval controls.

The market is much larger than the current "AI agents" software category. Salesforce is a $41B+ revenue company for managing customer workflows, ServiceNow is a $12B+ subscription revenue company for managing enterprise workflows, and Workday is a $9B+ revenue company for managing people and finance workflows. If AI workers become a new labor layer inside companies, they will need their own operating layer.

A realistic path to $1B ARR is 20,000 companies paying an average of $50k/year, or 5,000 larger customers paying $200k/year. If Taskforce becomes the coordination layer for AI-native work, the upside is multi-billion ARR.

## If you had any other ideas you considered applying with, please list them. One may be something we've been waiting for. Often when we fund people it's to do something they list here and not in the main application.

AI agent workers marketplace
A marketplace where companies can discover, deploy, and manage specialized AI agents as digital workers. Instead of hiring for every narrow task, teams can plug in curated agent roles for research, operations, analysis, support, growth, and execution.

AI-native VC fund
A venture fund built around AI as its operating system. Instead of using AI as a side tool, the fund uses agentic workflows, memory systems, and automated intelligence across sourcing, diligence, founder support, investor matching, and portfolio operations.

AI operations copilot for traditional companies
A system that watches repetitive back-office work inside companies, turns it into approved playbooks, and routes recurring tasks to AI workers with human approval gates. Initial markets could be fuel, logistics, retail, finance, and other operationally complex local businesses.

Agent reliability/eval infrastructure
A developer platform focused only on testing, evaluating, and repairing agent workflows before they are trusted in production.

## If you have not formed the company yet, describe the planned equity ownership breakdown among the founders, employees and any other proposed stockholders. If there are multiple founders, be sure to give the proposed equity ownership of each founder and founder title (e.g. CEO). (This question is as much for you as us.)

Planned ownership before incorporation:

Nikita Nosov, CEO: 45%
Altynai, CTO: 30%
ABRT-related strategic partner: 25%

Nikita has the largest share because he is the original founder, primary product lead, and primary builder of the core runtime and company direction. He leads product, engineering execution, fundraising, customer development, and go-to-market.

Altynai has a major founder share because she is a technical cofounder building full-time with Nikita. She writes code, leads AI architecture and memory systems, and contributes directly to the core product, including agent memory, knowledge graphs, cross-session recall, and technical research.

The ABRT-related strategic partner share reflects the incubation period, early product and workflow access, AI Lab/VC domain contribution, and their role as our first design partner for real VC workflows. This structure is still subject to final legal documentation before incorporation. We expect founder equity to vest on a standard 4-year schedule with a 1-year cliff, and we plan to create an employee option pool at the first priced round.

## What convinced you to apply to Y Combinator? Did someone encourage you to apply? Have you been to any YC events?

We chose YC specifically because Taskforce needs exactly what YC is best at: turning a working prototype into a company by forcing us to talk to users, narrow the wedge, and move much faster.

We studied YC companies like Zapier and Retool. Zapier showed that workflow automation can become a huge company by starting with a painful coordination problem. Retool showed that companies will adopt new internal infrastructure when it helps them run operations faster without replacing their whole stack. We think AI-native companies need the next version of that: infrastructure for coordinating AI workers.

YC would help us most with three things: getting our first US customers beyond ABRT, pressure-testing the wedge with founders and operators who are already trying to run AI-native companies, and relocating/building from the Bay Area where the AI startup ecosystem is concentrated.

We are not applying to accelerators generally. We are applying to YC because it is the place where the density of AI founders, early adopters, and blunt feedback is highest.

## How did you hear about Y Combinator?

We first heard about YC through the startup ecosystem and later followed YC partners' videos on Instagram, which encouraged us to apply now instead of waiting until the product looked more polished.
