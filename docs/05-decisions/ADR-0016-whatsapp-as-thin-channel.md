# ADR-0016: WhatsApp is a thin channel over the same agent

**Context.** Most Indian users prefer WhatsApp. A second "WhatsApp bot" with its own logic would be a weaker door into the same data.
**Decision.** The WhatsApp Cloud API webhook maps the sender's phone to a member and calls the *same* `Agent` (same triage, scoped tools, confirmations, verifier, traces). Writes become interactive Yes/No button messages; the button reply resumes the paused graph. Inbound message ids are deduplicated (Meta retries webhooks); signatures are verified with the app secret; the webhook acknowledges at once and answers in the background. Without a Meta token, outbound messages are recorded in an outbox as `simulated`.
**Alternatives.** A separate bot framework (Rasa, Twilio Studio): duplicates safety logic. Long-polling a BSP: higher latency, same parsing.
**Consequences.** + One place to fix a safety bug. + The full channel flow is testable offline (`/v1/channels/whatsapp/simulate`, `test_api.py`). − Citations are stripped for WhatsApp; the web trace view is still the audit trail.
