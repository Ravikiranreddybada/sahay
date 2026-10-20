# LLM Capacity and Rate Limits

## Demand (from capacity-estimation)
Sustained peak: **~6.6k RPM, ~12M input TPM (≈5.4M uncached), ~1M output TPM**. Burst 3×.

## Supply plan
1. **Two providers, same model family**: Anthropic API + AWS Bedrock (ap-south-1 where available).
   Different quota pools; router treats them as one tier with weighted routing (e.g., 60/40).
2. **Quota headroom ≥ 2× sustained** on each tier; provisioned throughput for the fast tier
   (classification is every turn, so it is the steadiest load).
3. **Per-tenant budgets**: internal tools (eval runs, re-embeds) use a separate key and are scheduled off-peak.

## Admission control (protect the provider budget)
```
per-user token bucket (30 turns/min, burst 10)            -> 429 Retry-After
per-pod in-flight semaphore (150)                          -> 503 Retry-After (shed)
global token-rate governor (Redis sliding window of TPM)   -> trigger degradation L1/L2 before 429s start
```
Shedding order when over budget: background jobs → FAQ turns go cache-or-fast-tier → tool turns keep smart tier → emergency path never shed.

## Why the token governor matters
Provider 429s arrive *after* you exceed quota; by then retries amplify load ("retry storm"). The
governor watches our own TPM and steps down the ladder at 80 % of quota, so retries never storm.
Retries use full jitter and a retry budget (≤ 10 % of requests may be retries per minute).
