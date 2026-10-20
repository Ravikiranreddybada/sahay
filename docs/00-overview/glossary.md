# Glossary

| Term | Meaning here |
|---|---|
| Turn | One user message and the assistant's reply (one graph run) |
| Thread | A conversation; LangGraph checkpoint key |
| Node | One step in the LangGraph state machine (guard_in, classify, plan_tools …) |
| MCP | Model Context Protocol: standard client/server protocol for tools and resources |
| MCP hub | Our client-side gateway to all MCP servers (scoping, authz, timeouts, tracing) |
| Injected param | Tool argument filled by the server side (`user_id`, `idempotency_key`), hidden from the LLM |
| Write tool | Tool with side effects; needs human confirmation (LangGraph `interrupt`) |
| Evidence | A KB chunk passed to the model, with id like `refund_policy#lab-tests` |
| RRF | Reciprocal Rank Fusion: combine rankings by 1/(k + rank) |
| Stale chunk | Chunk whose document is past its `review_by` date |
| Superseded | Older version of a logical doc (same `doc_id`, lower `version`) — never indexed |
| Grounded | Draft passes the verifier: real citations, no invented numbers/ids, uses tool data |
| Abstain | The assistant says it does not know and offers a human/next step |
| Containment | Conversation resolved without a human |
| Lakh | 1,00,000 (100k) |
| DPDP | India's Digital Personal Data Protection Act, 2023 |
| ABHA | Ayushman Bharat Health Account (national health ID) |
