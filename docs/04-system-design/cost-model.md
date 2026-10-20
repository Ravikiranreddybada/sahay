# Cost Model

Prices: list prices per 1M tokens (input / output): fast tier **$1 / $5**, smart tier **$3 / $15**,
cache reads at **10 %** of input price. $1 ≈ ₹85. Token shapes from [capacity-estimation.md](capacity-estimation.md).

## Per-call cost
| Call | Uncached in | Cached in | Out | Cost |
|---|---|---|---|---|
| classify (fast) | 400 | 1,000 | 120 | $0.00110 |
| plan (smart) | 600 | 1,200 | 80 | $0.00336 |
| answer (smart) | 1,400 | 1,200 | 220 | $0.00786 |
| answer (fast) | 1,400 | 1,200 | 220 | $0.00262 |

## Per turn
| Design | classify | plan | answer | regen | **$/turn** | ₹/conversation (4 turns) |
|---|---|---|---|---|---|---|
| Naive (all smart, LLM planner always on 80 %, no fast-path) | 0.0011 | 0.0027 | 0.0067 | 0.0004 | **$0.0109** | ₹3.7 |
| **Sahay** (fast-path → planner on 30 %, answer 50 % fast tier) | 0.0011 | 0.0010 | 0.0045 | 0.0003 | **$0.0068** | **₹2.3** |
| + campaign/FAQ cache 35 % | | | | | ~$0.0055 | ₹1.9 |

## Monthly (8 lakh turns/day)
| Item | Naive | Sahay |
|---|---|---|
| LLM | ~$262k | **~$163k** (−38 %) |
| AWS infra (ECS ~22 tasks, Aurora 2× r7g.large, Redis 2× r7g.large, ALB, NAT, Kinesis/S3, CloudWatch) | ~$3k | ~$3k |
| **Total** | ~$265k | **~$166k ≈ ₹1.4 Cr** |

LLM is ~98 % of cost → optimisation effort goes to **calls avoided** (fast-path, cache, abstain-without-LLM)
and **tier routing**, not to infra.

## Levers ranked by ₹ saved per unit of quality risk
1. Deterministic tool fast-path (no quality risk; exact id → exact tool).
2. Abstain without LLM when nothing retrieved (improves quality).
3. Prompt caching (no risk).
4. Fast-tier answers for templated tool intents (eval-gated).
5. Semantic cache for FAQs (threshold-gated, version-keyed).
6. Shorter outputs (2-4 sentences rule) — output tokens are 5× the input price.
