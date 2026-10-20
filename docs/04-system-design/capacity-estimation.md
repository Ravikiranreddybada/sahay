# Capacity Estimation (Back of Envelope)

All numbers are estimates with assumptions stated, so an interviewer can change one and follow the effect.
Exchange rate used: **$1 ≈ ₹85**.

## 1. Traffic
| Assumption | Value | Note |
|---|---|---|
| Daily active users (DAU) | **1,00,000** | design target |
| Conversations / DAU / day | 2 | conservative (support usage is usually ~1) |
| Turns / conversation | 4 | question, follow-up, confirm, thanks |
| **Turns / day** | **8,00,000** | 1e5 × 2 × 4 |
| Average rate | 9.3 turns/s | 8e5 / 86,400 |
| Peak-hour share | 10 % of daily | IST peaks 10:00-13:00, 19:00-22:00 |
| Peak-hour rate | 22 turns/s | 80,000 / 3,600 |
| Peak-minute burst | ×2 → **45 turns/s** | |
| **Design capacity** | **50 turns/s sustained, 150 turns/s burst** | 3× burst headroom |

## 2. Concurrency (Little's law: L = λ × W)
| | λ (turns/s) | W (avg turn latency) | In-flight turns |
|---|---|---|---|
| Sustained | 50 | 2.5 s | **125** |
| Burst | 150 | 2.5 s | **375** |
| Open SSE connections | — | — | ≈ 6-8 % of DAU online at peak → **~8,000** |

## 3. LLM calls and tokens per turn
| Call | Share of turns | Model tier | Input tokens (cached prefix) | Output |
|---|---|---|---|---|
| classify | 100 % | fast | 1,400 (1,000) | 120 |
| plan_tools | 30 % (after deterministic fast-path, see cost-model) | smart | 1,800 (1,200) | 80 |
| answer | 85 % (15 % = cache hit / emergency / abstain-without-LLM) | 50 % fast, 50 % smart | 2,600 (1,200) | 220 |
| regenerate after verify | 5 % | same as answer | 2,800 | 220 |

Per turn ≈ **4.0k input tokens** (≈ 55 % cache-read) and **≈ 330 output tokens**, ≈ **2.2 LLM calls**.

At 50 turns/s sustained:
| Quantity | Value |
|---|---|
| LLM requests | 110 RPS ≈ **6,600 RPM** |
| Input tokens | 200k tok/s ≈ **12M ITPM** (≈ 5.4M uncached) |
| Output tokens | 16.5k tok/s ≈ **1M OTPM** |

→ This is enterprise-tier provider capacity. Plan: two providers (Anthropic API + AWS Bedrock), quota
headroom ≥ 2× sustained; see [llm-capacity-and-rate-limits.md](llm-capacity-and-rate-limits.md).

## 4. Compute (API tier)
- CPU per turn excluding waiting on I/O: ~15 ms (retrieval ≈ 3 ms, verification < 1 ms, JSON/pydantic, SSE).
- 50 turns/s × 15 ms = **0.75 vCPU** — the API tier is **I/O/connection bound, not CPU bound**.
- One pod (1 vCPU / 2 GB, Uvicorn async) holds ~100 in-flight turns comfortably (semaphore = 150).
- Burst 375 in-flight → 4 pods; run **min 6** (2 per AZ × 3 AZ) for HA, autoscale to 40.

## 5. Storage
| Data | Per turn | Per day | Retention | Steady state |
|---|---|---|---|---|
| Checkpoints (`durability="exit"`: ~2 writes × 8 KB) | 16 KB | 12.8 GB | 30 days | **~385 GB** |
| Traces (all spans) | 25 KB | 20 GB | 7 d hot / 90 d S3 | 140 GB hot (10 % sampled to Langfuse) + 1.8 TB S3 |
| Messages (redacted, inside checkpoints) | — | — | — | — |
| Handoff tickets (~8 % of conversations) | 4 KB | 64 MB | 1 year | 23 GB |
| KB vectors (10k chunks × 1024 × 4 B) | — | — | — | **40 MB** (fits in RAM everywhere) |
| Semantic cache (5k entries × 4 KB vector+answer) | — | — | TTL 1 h | 20 MB |

Write rate on Postgres: 50 turns/s × 2 = **100 writes/s** (+ tickets) — a single Aurora writer handles this with large headroom (~10k+ writes/s).

## 6. Tools (MCP)
- ~1 tool call per tool-intent turn; 60 % of turns are tool intents → **~30-45 tool RPS** at sustained peak.
- Read tools 20-80 ms; 2-3 tasks per MCP server is enough, autoscale on p95 latency.

## 7. Bandwidth
- Request ~1 KB, SSE stream ~6 KB per turn → 50 turns/s × 7 KB ≈ **350 KB/s** — negligible.

## Sensitivity
| If this changes… | …then |
|---|---|
| turns/conversation 4 → 8 | double LLM quota + cost; compute still trivial |
| cache hit 15 % → 35 % (FAQ-heavy campaign) | −20 % LLM cost and quota |
| move answer 50 % → 80 % fast tier | −30 % cost; must hold grounded-rate in evals |
| average latency 2.5 s → 5 s (provider slow) | in-flight doubles → pods autoscale on in-flight, not CPU |
