# High-Level Design

```mermaid
flowchart TB
  U[Users: web / app / WhatsApp later] --> CF[CloudFront + AWS WAF<br/>bot rules, geo, rate rules]
  CF --> ALB[Public ALB]
  ALB --> API1[API pod] & API2[API pod] & APIn[API pod ×N]
  subgraph VPC["VPC ap-south-1 (3 AZ)"]
    API1 & API2 & APIn --> IALB[Internal ALB]
    IALB --> MO[MCP orders ×2-6]
    IALB --> MC[MCP care_services ×2-6]
    IALB --> ML[MCP claims ×2-6]
    IALB --> MJ[MCP care_journeys ×2-6]
    API1 & API2 & APIn --> RC[(ElastiCache Redis<br/>rate limit, semantic cache, hot session)]
    API1 & API2 & APIn --> AU[(Aurora PostgreSQL<br/>checkpoints, tickets, feedback, pgvector)]
    API1 & API2 & APIn --> GW[LLM gateway layer<br/>in-process router]
    WK[Worker service] --> AU
    SQS[[SQS queues]] --> WK
    EB[EventBridge Scheduler] --> SQS
    API1 & API2 & APIn --> KF[Kinesis Firehose] --> S3[(S3 trace lake)]
  end
  GW --> ANT[Anthropic API]
  GW --> BR[AWS Bedrock Claude<br/>same models, separate quota]
  MO & MC & ML & MJ --> DOM[(Domain systems:<br/>OMS, LIS, HIS, TPA)]
```

## Request path and latency budget (tool turn, p50)
| Step | Budget |
|---|---|
| Edge + ALB + auth + rate limit | 15 ms |
| Load checkpoint (Aurora, by PK) | 5 ms |
| guard_in | 2 ms |
| classify (fast model) | 350 ms |
| plan (fast-path: 0 ms; LLM: 600 ms) | 0-600 ms |
| MCP tool call | 60 ms |
| retrieve (embed 40 ms + search 3 ms) | 45 ms |
| answer (smart model, ~220 output tokens) | 1,200 ms |
| verify + finalize + checkpoint write | 15 ms |
| **Total** | **~1.7 s (fast-path) / ~2.3 s (LLM plan)**; p95 target ≤ 4 s |

## Key design decisions (details in [../05-decisions](../05-decisions/))
1. Stateless API, state in Postgres checkpoints (ADR-0003).
2. MCP servers as separately-scaled services per domain (ADR-0002).
3. Two LLM providers behind one router, model tiers per node (ADR-0005).
4. Deterministic safety outside the model (ADR-0006).
5. Eval gate in CI for every prompt/model/KB change (ADR-0008).
