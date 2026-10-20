# ADR-0005: Model tiers per node + router

**Context.** Cost and latency at 8 lakh turns/day; provider incidents.
**Decision.** Fast tier (Haiku) for classify/verify/smalltalk; smart tier (Sonnet) for planning and synthesis; `ModelRouter` with retries (jittered), per-model circuit breaker, fallback model, per-call cost spans. Second provider (Bedrock) in prod.
**Alternatives.** One large model everywhere (+38 % cost, +latency); provider SDK retries (no cross-model fallback, double retries).
**Consequences.** + Cost ₹2.3/conversation; graceful under brownouts. − Two prompts styles to keep compatible across tiers (eval-gated).
