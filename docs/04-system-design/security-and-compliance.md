# Security and Compliance

| Area | Control |
|---|---|
| AuthN | OIDC/JWT from the platform's identity service; API never trusts a `user_id` in the body in prod (dev accepts it for the demo) |
| AuthZ (data) | MCP hub injects the authenticated `user_id`; every tool filters by it (row-level ownership) |
| AuthZ (actions) | Per-intent tool allow-list; write tools need explicit confirmation; read-only mode on injection suspicion |
| PII | Redaction at ingress (Aadhaar-Verhoeff, PAN, card-Luhn, phone, email, UPI); raw text never stored |
| PHI to LLM provider | Minimum necessary: redacted query + only this user's tool fields needed; zero-retention agreements; Bedrock in-region option |
| Secrets | AWS Secrets Manager; rotated; never in env files in prod |
| Transport | TLS 1.2+ at ALB; mTLS/SG-restricted internal ALB for MCP servers |
| Network | Private subnets for all services; egress only via NAT to provider endpoints (allow-list) |
| Abuse | WAF rate rules, per-user token bucket, request size limits (message ≤ 2,000 chars) |
| Prompt injection | Direct: scoring + capability reduction; indirect: data tags + scrub |
| Audit | Every write tool call traced with user, args, idempotency key, result; 1-year retention |
| DPDP Act 2023 | Purpose limitation, consent at signup, data-principal deletion (delete thread checkpoints + traces by user), breach runbook |
| Supply chain | Pinned deps, `pip-audit` + Dependabot in CI, image scanning (ECR) |
