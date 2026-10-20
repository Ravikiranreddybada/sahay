# Eval Strategy

> Goal: know whether a prompt, model, KB or code change **helped**, before it ships.

## Three layers
| Layer | What | When | Cost |
|---|---|---|---|
| Unit tests | Chunker, retrieval cases, PII, triage, verifier, breaker, idempotency | every commit | seconds |
| **Golden-set eval (end-to-end through the real graph)** | `evals/golden.yaml` → metrics → gate vs `evals/baseline.json` | every PR (offline engine) + nightly (real model) | seconds offline / ~₹50 nightly |
| **Counterfactual invariance** | `evals/counterfactual.yaml`: same request, one irrelevant detail changed (gender, age, name, locality, language) → identical decision; hard gate | every PR, after the golden set, on fresh data | seconds offline |
| Rule-pack tests | every threat rule's `match` / `no_match` example | every commit | ms |
| Production signals | grounded %, abstain %, 👎 rate, escalations, canary deltas | continuous | — |

## Golden set design (`backend/evals/golden.yaml`)
Files: `golden.yaml` (78 cases, gated), `heldout.yaml` (24 cases, reported only) and `counterfactual.yaml` (15 cases, 141 variant runs, hard gate). Each case is an assertion bundle (promptfoo-style), e.g.:
```yaml
- id: order-status-explicit
  user: U1001
  turns: ["Where is my order ORD-1042?"]
  expect:
    intent: order_status
    tools: [get_order_status]
    tool_args: {get_order_status: {order_id: ORD-1042}}
    must_contain: ["out for delivery"]
    grounded: true
```
Categories and why each exists:
| Category | Count | Catches |
|---|---|---|
| Tool status (orders, labs, claims, journeys) | ~14 | wrong tool / wrong args / ignored live data |
| Policy FAQ (refunds, fasting, claims docs, vaccination, surgery) | ~12 | bad chunking, wrong top-k, stale version |
| Version / freshness | 2 | v1 policy served after v2 exists; stale warning missing |
| Multi-turn follow-ups | 3 | context loss, entity carry-over, context bleed |
| Writes + confirmation | 3 | write without confirmation, double execution |
| Safety: emergency | 6 | missed red flags (hard gate) and false alarms on negations |
| Safety: injection / cross-user | 4 | IDOR, capability escalation (hard gate) |
| Medical boundary | 2 | dosing advice |
| Out-of-KB | 2 | hallucination instead of abstain |
| Handoff / smalltalk | 2 | routing |
| Family health records | 12 | model-made "safe" verdicts, missed duplicate molecules, unit-blind lab trends, consent bypass, member carried into a self question |
| Injection (Hinglish) | 1 | English-only defences (INC-017) |

## Rules
- A bug found in production becomes a golden case **before** the fix (red → green).
- Baseline is updated only by an explicit `--update-baseline` in a reviewed PR.
- Nightly real-model run also computes an **LLM-judge faithfulness** score (fast tier, rubric prompt) — tracked, not gated (judge drift).

## Current results (offline engine, 2026-10-18)
| Set | Cases | Pass | Intent | Tool recall | Recall@5 | MRR | Grounded | Emergency recall | Cross-user leak |
|---|---|---|---|---|---|---|---|---|---|
| golden | 78 | 100 % | 100 % | 100 % | 100 % | 1.00 | 100 % | 100 % | 0 |
| held-out | 24 | 100 % | 100 % | 100 % | 100 % | 1.00 | 100 % | 100 % | 0 |
| counterfactual | 15 cases / 141 runs | consistency 100 % | | | | | | | |

History on the golden set: first run 46/54 (85 %) → fixes INC-004…007 → 54/54 → INC-008 found by tests → 55/55 → October audit added 10 cases that each failed on v0.1 (INC-009, -010, profile city, reminders) → 65/65.
v0.3 added 13 golden cases for health records + Hinglish injection; the first run failed 4 (INC-017, INC-018, INC-019, a KB section that did not answer "how") → 78/78. The 4 new held-out cases passed on first run.
Gate check: forcing `top_k=1, budget=150` drops pass rate to 92.7 % and the gate **fails** as designed. A deliberately biased triage (ignore red flags if the message says "woman") drops counterfactual consistency to 73 % and the gate **fails**.

**Caveats (read before quoting these numbers).**
- The offline engine was tuned on the golden set; treat golden = training accuracy.
- The held-out set was written after tuning and never used to tune, but by the same author who knows the system and on a small KB (9 docs, 35 chunks). It is a sanity check, not proof of generalisation.
- Real-model (Claude) numbers are **not measured yet** (no API key in the build environment). The nightly CI job runs the same gate when `ANTHROPIC_API_KEY` is set.
- Next step for honest numbers: 100+ cases written by CS agents from real (redacted) conversations.
