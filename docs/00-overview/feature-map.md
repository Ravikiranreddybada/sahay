# Feature Map

Feature inventory came from (a) the Brainwave AI Software Engineering Intern job description and
(b) a passive REA (reverse-engineering agent) inspection of the public home page of a leading Indian
digital-health platform (accessibility tree only; no private APIs, no scraping of user data; see
[../01-research/competitor-study-rea.md](../01-research/competitor-study-rea.md)). Sahay is an
**original** product: no third-party brand, copy, logo or API is reused.

| Domain | User capability | MCP tool(s) | KB doc | Status |
|---|---|---|---|---|
| Medicine orders | Track order, ETA, prescription hold | `get_order_status`, `list_recent_orders` | medicine_delivery | ✅ |
| Medicine orders | Cancel before dispatch (confirmed, idempotent) | `cancel_order` (write) | refund_policy v2 | ✅ |
| Lab tests | Report status, test search, fasting rules | `get_lab_report_status`, `search_lab_tests` | lab_tests | ✅ |
| Consultations | Find slots, book (confirmed, race-safe) | `search_doctor_slots`, `book_consultation` (write) | consultations | ✅ |
| Insurance | Claim status, pending docs, list claims | `get_claim_status`, `list_claims` | insurance_claims | ✅ |
| Insurance | Cashless network hospitals | `find_network_hospitals` | insurance_claims | ✅ |
| Vaccination journey | Next due dose, overdue, same-day doses | `get_vaccination_schedule` | vaccination_guide | ✅ |
| Surgery journey | Stage, next step, pre-op checklist | `get_surgery_journey`, `get_surgery_checklist` | surgery_care | ✅ |
| Refunds | Timelines per product, tracking | — (policy) | refund_policy v2 (v1 superseded) | ✅ |
| Membership / ABHA | Benefits, family cover, ABHA linking | — | membership_plans (STALE flag demo) | ✅ |
| Safety | Emergency red-flag triage (12 categories) | — | emergency_protocol | ✅ |
| Safety | PII redaction (Aadhaar-Verhoeff, PAN, card-Luhn, phone, email, UPI) | — | — | ✅ |
| Safety | Prompt-injection scoring → read-only mode | — | — | ✅ |
| Handoff | Human ticket with context packet | — | — | ✅ |
| Proactive journeys | Reminder 7d/1d before vaccine due (scheduler) | `set_vaccination_reminder`, sweep | vaccination_guide | ✅ |
| Channels | WhatsApp | — | — | ✅ (simulated outbox until a Meta number is set) |
| Channels | Voice input (browser speech-to-text, en-IN / hi-IN) | — | — | ✅ input only; voice replies 🔜 |
| Family health records | Caregiver view of a parent's records under scoped, expiring consent; revoke (confirmed write) | `list_care_members`, `revoke_care_access` | family_health_records | ✅ |
| Family health records | Medicine list resolved to molecules; same molecule from two prescribers; recorded interactions with source | `get_medication_list` | family_health_records | ✅ |
| Family health records | "Can papa take X with his medicines?" — database check incl. recent orders; never "safe" | `check_medication_safety` | family_health_records | ✅ |
| Family health records | Lab trends across labs and units (cited conversions), out-of-range, steady rise | `get_lab_trends` | family_health_records | ✅ |
| Family health records | Visit brief: appointment, flags, labs to discuss, questions worth asking | `get_visit_brief` | family_health_records | ✅ |
| Privacy | DPDP data rights: export my data, erase my conversation history | — (API) | — | ✅ |
