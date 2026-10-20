# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Two audiences, equal weight:

- **Members and caregivers in India.** Adults who handle health admin for themselves and their family: a parent tracking a child's vaccines, an adult child managing an elderly father's medicines and lab reports, a patient before cataract surgery. They write in English, Hinglish or Devanagari, and some use voice. They come with a concrete job: where is my order, is this refund coming, is papa's HbA1c going up, can he take this with his other medicines.
- **Reviewers of the system.** Engineers, interviewers and ops staff who want to see how an answer was made: which graph nodes ran, which MCP tools were called, what was retrieved, what the verifier checked, how the eval gates hold.

## Product Purpose

Sahay is a grounded care assistant: query resolution for orders, lab reports, claims and refunds, plus personalised vaccination and surgery journeys and family health records. Its purpose is to be reliably right instead of confidently wrong. Success means a member gets a correct, cited answer or an honest "I don't know / here is a human", and a reviewer can trace exactly why.

## Positioning

The model never decides facts. Live data comes from scoped MCP tools, policy from versioned SOPs, medicine interactions from a database; the model only explains. A deterministic verifier scores every answer against tool data and evidence, emergencies bypass the model entirely, and every write waits for the member's explicit Yes.

## Operating Context

- Patient side: Chat (with live pipeline, confirm cards, citations, grounding scorecard, voice en-IN / hi-IN), Health (family switcher, consent state, medicines resolved to molecules, interaction and duplicate flags, lab trends with reference bands, visit brief, DPDP data rights), WhatsApp simulator and vaccine reminders.
- Ops side ("under the hood"): trace waterfall, eval dashboard (golden / held-out / counterfactual, hard gates), knowledge base freshness, handoff queue.
- The two sides are separate areas of one product: patient experience first, a clear switch into the ops console. Same brand; ops is denser.
- Demo personas: Ananya Rao (U1001, Bangalore, parent of Aarav, caregiver for father Venkat), Rahul Mehta (U1002, Mumbai, cataract surgery), Fatima Shaikh (U1003, Hyderabad, parent of Zoya, mother's consent expired). Ops role signs in separately.
- Desktop-first; phone width must work but is secondary.

## Capabilities and Constraints

- Next.js 16 + React 19, no UI library; plain CSS in `web/app/globals.css`. Backend at `/api/*` via proxy route.
- Offline engine runs without an API key; the UI must show engine mode honestly (offline / model names).
- Statuses the UI must express: answered, needs_confirmation, escalated, grounded, abstained, cache hit, stale source, read-only mode, degraded, PII redacted, emergency.
- Medicine interaction table is a small curated demo set, not a clinical reference.

## Brand Commitments

- Name: Sahay (Hindi: help, support).
- The user explicitly forbids an "AI-generated" look: no stock AI palettes (purple/blue gradients, neon glow, glassmorphism), no template feel.

## Evidence on Hand

- Real eval results from the backend (`v1/evals/latest`), real traces, real KB docs. Demo personas and records are synthetic and must stay labeled as demo data.
- No real users, testimonials, hospitals or partners exist. Do not invent any.

## Product Principles

1. Show the source. Every fact on screen points to where it came from.
2. Honest states over smooth ones: abstained, stale, degraded and blocked are shown plainly, never hidden.
3. Ask before acting. Any write is a visible, explicit confirmation.
4. Emergencies are loud and immediate; everything else is calm.
5. The machinery is inspectable, but never in the member's way.

## Accessibility & Inclusion

- Mixed scripts: Latin and Devanagari must render well side by side.
- Older caregivers: readable sizes, strong contrast, clear status words (not color alone).
