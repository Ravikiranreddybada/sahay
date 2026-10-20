# Problem Statement

Customer support in digital healthcare has four properties that break naive chatbots:

1. **Answers are per-user.** "Where is my order" has no answer in any document. A RAG-only bot
   answers with the delivery *policy* — technically relevant, practically useless.
2. **Policies change and old versions linger.** Refund windows, fees and claim SLAs are revised. If
   v1 and v2 of a policy both sit in the vector store, retrieval picks whichever embeds closer —
   the bot is "confidently wrong" with a real citation.
3. **Actions have consequences.** Cancelling an order or booking a slot must be idempotent,
   confirmed, and authorised for *this* user only.
4. **Some messages are emergencies.** A chest-pain message must never wait for a model, a cache or a
   retry loop.

And at **1 lakh users** three more appear:

5. Provider rate limits and latency spikes become daily events, not edge cases.
6. Token cost becomes a P&L line; every unnecessary smart-model call is money.
7. You cannot debug by reading chats; you need traces and an eval set.

## What "done" looks like
- A user question is routed, grounded, cited, verified and answered in one turn.
- Every failure mode above has a mechanism in the code **and** a test/eval that proves it.
- The system design shows how each component scales to 1 lakh DAU, with numbers.
