# System Design — 1 Lakh Users

| Doc | Question it answers |
|---|---|
| [capacity-estimation.md](capacity-estimation.md) | How much traffic, tokens, storage? (back-of-envelope with every assumption written down) |
| [high-level-design.md](high-level-design.md) | What runs where, and how a request flows |
| [scaling-strategy.md](scaling-strategy.md) | How each tier scales horizontally; autoscaling signals |
| [caching-strategy.md](caching-strategy.md) | 5 cache layers, what is never cached |
| [storage-and-data.md](storage-and-data.md) | Postgres, Redis, pgvector, S3: schema, partitioning, retention |
| [reliability-and-degradation.md](reliability-and-degradation.md) | Failure modes, breakers, load shedding, the 5-level degradation ladder, DR |
| [llm-capacity-and-rate-limits.md](llm-capacity-and-rate-limits.md) | Provider TPM/RPM planning, multi-provider, admission control |
| [stress-1-lakh-concurrent.md](stress-1-lakh-concurrent.md) | The campaign spike: 1 lakh users online at once |
| [security-and-compliance.md](security-and-compliance.md) | AuthN/Z, DPDP, PHI handling, secrets |
| [observability-and-slos.md](observability-and-slos.md) | SLIs/SLOs, dashboards, alerts, trace sampling |
| [cost-model.md](cost-model.md) | ₹ per conversation and the levers |
| [deployment-aws.md](deployment-aws.md) | AWS topology, CI/CD, canary for prompts |
| [load-testing.md](load-testing.md) | k6/Locust plan and pass criteria |
