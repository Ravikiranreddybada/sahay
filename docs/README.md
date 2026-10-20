# Sahay — Documentation Index

Sahay is a grounded, multi-agent **care assistant** for a digital-healthcare platform in India:
query resolution (orders, lab reports, claims, refunds), plus personalised **vaccination** and
**surgery** journeys. Built on LangGraph + MCP + hybrid RAG + evals, designed for **1 lakh (100,000)
daily active users**, with a stress design for 1 lakh *concurrent* users.

> Status legend used in every doc
> - ✅ **Built** — code exists in this repo and is covered by tests or evals
> - 🧭 **Designed** — production path specified here (config, interface, IaC) but runs in a dev substitute locally
> - 🔜 **Planned** — on the roadmap, not started

## Map

| Folder | What is inside | Read when |
|---|---|---|
| [00-overview](00-overview/) | Vision, problem, feature map, glossary | First |
| [01-research](01-research/) | GitHub repo research (what we took from each), competitor study with REA | You want the "why this design" |
| [02-tech-stack](02-tech-stack/) | Every technology, why, and what we rejected | Choosing / defending tools |
| [03-architecture](03-architecture/) | Agent graph, RAG, MCP layer, context engineering, safety, data model, API | Building or debugging |
| [04-system-design](04-system-design/) | Capacity math for 1 lakh users, scaling, caching, storage, reliability, security, SLOs, cost, AWS deploy, load tests | System-design interview |
| [05-decisions](05-decisions/) | Architecture Decision Records (ADRs) | "Why not X?" |
| [06-evals](06-evals/) | Eval strategy, metrics, golden set, regression gate | Changing a prompt / model |
| [07-debugging](07-debugging/) | Failure-mode playbook + real incident log | Something is wrong |
| [08-build-plan](08-build-plan/) | Phased roadmap, step-by-step build guide, local runbook | Building it yourself |
| [09-interview](09-interview/) | Resume bullets, talking points, demo script | Interviews |

## One-paragraph architecture

A FastAPI gateway authenticates the user and rate-limits per user. Each turn runs a **LangGraph
state machine**: deterministic guards (PII redaction, prompt-injection scoring, emergency triage) →
intent classification (fast model, schema-forced output) → **least-privilege MCP tool loop** over four
domain MCP servers (orders, care services, claims, care journeys) with human confirmation for
write actions → **hybrid retrieval** (BM25 + vectors + RRF + freshness) over versioned SOPs →
**token-budgeted context assembly** → cited answer (smart model) → **deterministic grounding
verifier** with one regeneration → finalize (cache, memory, metrics). Every node emits a span; every
change is gated by an eval suite in CI.
