# Stress Scenario: 1 Lakh Users Online at Once

**Scenario**: a national vaccination-drive push notification goes to 10 lakh parents; 1 lakh open
the app within ~10 minutes and ask variants of "is my child's vaccine due / where / how to book".

## Load
| Quantity | Value |
|---|---|
| Concurrent sessions | 1,00,000 |
| Think time between turns | ~30 s |
| Turn rate | 1e5 / 30 ≈ **3,333 turns/s** (≈ 67× normal sustained) |
| Naive LLM demand | 3,333 × 2.2 ≈ 7.3k LLM RPS (≈ 440k RPM) — **not buyable on short notice** |

## Strategy: make most turns not need the smart model
1. **Pre-warm** (campaign is scheduled): precompute answers for the top 50 campaign FAQ phrasings into the
   semantic cache before the push; expected FAQ hit rate 50-60 %.
2. **Personal turns are tool turns**: "is Aarav's vaccine due" → deterministic fast-path
   (`get_vaccination_schedule`) + **templated answer** (fast tier or offline template). No smart call.
3. **Staggered push**: notification fan-out via SQS in 10 waves over 30 min → peak divides ~3-5×.
4. **Degradation L1-L2** pre-enabled for the campaign window (eval-validated quality).
5. **Capacity**: API pods scale on in-flight: 3,333/s × 1.0 s ≈ 3.3k in-flight → ~35 pods (pre-scaled).
   MCP `care_journeys` pre-scaled to 20 tasks with read cache 30 s.
6. **Queue booking writes**: `book_vaccination` requests enqueue to SQS with idempotency keys; user gets
   "request received, confirming in a minute" + push on confirmation (protects the clinic slot DB).

## Resulting demand (estimate)
| | Turns/s | Smart LLM RPS | Fast LLM RPS |
|---|---|---|---|
| Cache hits (55 %) | 1,833 | 0 | 0 |
| Fast-path tool turns (35 %) | 1,167 | 0 | 1,167 (classify) + templated answer |
| Other (10 %) | 333 | 333 | 333 |
| With staggered push (÷3) | ~1,100 | ~110 | ~500 |

→ Smart-tier demand back near normal sustained levels; fast tier at ~4× normal (pre-provisioned).
