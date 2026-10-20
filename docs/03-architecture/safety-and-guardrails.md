# Safety and Guardrails

| Layer | Where | Mechanism | Test |
|---|---|---|---|
| Emergency triage | `guard_in` (first) | Regex red flags in 8 categories with negation handling ("no chest pain" ≠ emergency); bypasses LLM | eval gate: emergency recall = 100% |
| Self-harm | `guard_in` | Tele-MANAS 14416 + 112 message; negation never suppresses this category | tests |
| PII redaction | `guard_in` | Aadhaar (Verhoeff checksum), card (Luhn), PAN, phone, email, UPI → typed placeholders | unit tests |
| Prompt injection (direct) | `guard_in` | Weighted signal score; ≥ 0.5 → **read-only mode** (write tools removed) | eval cases |
| Prompt injection (indirect) | context assembly | `<data>` wrapping + instruction-line scrub on tool/KB text | unit tests |
| Authorisation | MCP hub | Injected `user_id`; ownership checks in every tool | tests: other user's order → not found |
| Medical boundary | prompt + verifier | Rule 4 + dosing-language detector in verifier | eval cases |
| Grounding | verifier | Fabricated citation / invented numbers & ids / ignored tool data | eval: grounded rate |
| Write safety | `confirm` node | `interrupt()` + explicit approval + idempotency | tests |
| Abuse | API | Per-user token bucket; WAF at edge 🧭 | tests |

## Why rules, not a model, for triage
Recall must be 100% and must not depend on provider uptime. A false positive costs one line of
text; a false negative can cost a life. A model-based triage can be *added* as a second net
(🔜) but never replace the deterministic first net.

## Compliance notes (India) 🧭
- DPDP Act 2023: purpose limitation (we only process what the support task needs), redaction before
  third-party processing (LLM provider), retention limits (checkpoints 30 days, traces 7 days hot).
- Data residency: run LLM via AWS Bedrock in ap-south-1 (Mumbai) where available for PHI-bearing flows.
- Audit: every write tool call is a span with user, args, idempotency key and result.
