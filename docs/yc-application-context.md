# YC Application Q&A

## How long have the founders known one another and how did you meet? Have any of the founders not met in person?

We have known each other for three months. We met through a startup development program run by the Kyrgyz Republic for startups going to Silicon Valley (Dive into Silicon Valley). Both of our previous startups won spots in the program, and we spent a month together in the US. During that trip we realized we wanted to build together and started working on this new product along with ABRT AI Lab. All founders have met in person.

## Who writes code, or does other technical work on your product? Was any of it done by a non-founder? Please explain.

All technical work is done exclusively by the founders. Nikita is our lead engineer -- he builds the core L2/L3 protocol, implements the agent architecture, and handles all production code. Altynai is our AI research engineer and Head of AI Memory, focused on agent memory systems, including knowledge graphs, cross-session recall, and competitive technical analysis. She also designed our proprietary CLARK semantic memory algorithm for durable project knowledge, tool memory, and rule-based cross-session retrieval. No non-founders touch the codebase.

## Are you looking for a cofounder?

No

## Company name*

Taskforce

## Describe what your company does in 50 characters or less.*

It helps companies manage teams of AI workers.

## Company URL, if any

taskforcehub.dev

## Please provide a link to the product, if any.



## Please provide a link to the product, if any.



## What is your company going to make? Please describe your product and what it does or will do.

Taskforce is a coordination runtime for AI taskforces. It lets a high-level AI supervisor manage specialized AI workers through typed Work Orders, approved tools, eval gates, retry policies, memory rules, and human approval gates for external actions.

Today, running multi-step agent work is still too manual: a human has to prompt, re-prompt, inspect failures, decide what to retry, and prevent the agent from silently doing unsafe things. We are building the layer that turns that messy process into a reliable operating system for AI workers. The first use case is automating real operational workflows for AI-native companies and VC workflows: sourcing, research, diligence, founder support, reporting, and distribution.

## Where do you live now, and where would the company be based after YC?

Bishkek, Kyrgyz Republic / Palo Alto, USA

## Explain your decision regarding location.



## How far along are you?

Working prototype. We have built the core orchestration runtime: a supervisor layer that creates bounded Work Orders, a worker execution layer, a Taskforce Hub for approved workers/tools/evals/playbooks, eval gates, retry/repair loops, Incident Briefs, and explicit approval gates for external actions. We also have the real partners to work with, starting with ABRT AI Lab/ABRT VC workflows.

## How long have each of you been working on this? How much of that has been full-time? Please explain.

We have both been working on this full-time for the past 3 months. In that time, we have built the core product ourselves end-to-end -- from protocol architecture and agent systems to AI memory research, implementation, and product design. All technical work has been done directly by the two founders.

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

We picked this idea because we hit the problem ourselves. With current AI tools, a capable founder can get a lot done, but only by acting as the manager: breaking work into tasks, supervising agents, checking outputs, retrying failures, preserving context, and stopping unsafe external actions. That human management (and micro-management) layer is the bottleneck.

Our domain expertise comes from building agentic systems directly and from working with ABRT AI Lab/ABRT VC on real VC operating workflows. ABRT's venture background gives us access to concrete, high-value workflows: startup sourcing, diligence, founder support, investor matching, portfolio operations, and reporting. These are not toy automations; they are messy, judgment-heavy, multi-step processes where reliability matters.

We know people need this because the same pattern appears in every serious AI workflow we see: companies do not just need another chatbot or single-purpose agent. They need a way to coordinate many AI workers, enforce boundaries, evaluate work, learn from failures, and keep humans in the loop only when judgment or external action is required.

## Who are your competitors? What do you understand about your business that they don't?

We do not think there is a perfect direct competitor yet. The closest products are Stilla, Rodin, Copyl, Blue Prism WorkHQ, RunState Workforce, and Paperclip. They overlap with us because they all treat AI as workers/teammates or try to coordinate agentic work.

The difference is that most of them sell agents, AI teammates, enterprise automation, or a managed workspace. We are building the underlying coordination runtime: a command layer that decides which worker should do what, validates Work Orders, controls tools, checks outputs with evals, handles retries/repairs, keeps memory clean, and gates external actions.

Our bet is that once companies depend on AI workers, the bottleneck is not making another worker. The bottleneck is managing many workers reliably. The durable product is the operating layer that makes AI labor inspectable, bounded, and safe enough for real business operations.

## How do or will you make money? How much could you make?

We will make money as B2B software for companies that run high-value recurring workflows with AI workers. The initial model is a subscription for the coordination runtime plus usage-based pricing for worker execution and managed enterprise deployments.

Early pricing: $1k-$5k/month for small teams running a few critical workflows; $25k-$100k/year for larger companies or funds that need custom playbooks, private deployment, governance, and integrations. For VC/fund operations, one customer can justify this if we save even one analyst hire or materially improve sourcing and diligence throughput.

If we become the operating layer for AI taskforces inside 10,000 companies at an average $25k/year, that is $250M ARR. The larger opportunity is that every company that hires people for repeatable knowledge work will eventually also manage AI workers, and that requires infrastructure.

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

Nikita Nosov, CEO: 47%
Altynai, CTO: 33%
ABRT-related strategic partner: 20%

We expect founder equity to vest on a standard schedule, and we will finalize the ABRT-related economics in legal docs before incorporation.

## What convinced you to apply to Y Combinator? Did someone encourage you to apply? Have you been to any YC events?

YC partners' videos on Instagram pushed us to apply. The main reason is that YC is unusually direct about what matters: build something people want, talk to users, move fast, and be honest about progress. That is the environment we want around us while we turn Taskforce from a working prototype into a company. We have not attended YC events yet.

## How did you hear about Y Combinator?

We first heard about YC through the startup ecosystem and later followed YC partners' videos on Instagram, which encouraged us to apply now instead of waiting until the product looked more polished.
