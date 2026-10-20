# Competitor Study with REA (passive)

## What was done
- Tool: REA MCP (`inspect_web_page`) over a local headless Chrome DevTools endpoint (loopback only).
- Target: the **public home page** of a leading Indian digital-health platform.
- Mode: passive. No JavaScript evaluation, no clicks, no login, no private API calls, no user data.
- Captured: accessibility tree labels (navigation, service cards, banners).

## Service surface observed (labels, paraphrased)
| Area | Observed capability | Sahay mapping |
|---|---|---|
| Consultation | Online consult 24x7, in-clinic consult at hospitals | `consult_booking` intent, `search_doctor_slots` / `book_consultation` |
| Medicines | Order medicines, ~60-minute express delivery banner | `order_status`, `medicine_delivery` SOP |
| Lab tests | Lab tests & packages, ~2-hour sample pickup banner | `lab_booking`, `lab_tests` SOP |
| Surgery care | Surgery care landing | `surgery_journey` |
| Insurance | Claims (track in real time), cashless at network hospitals, e-cards for family, hospitalization intimation | `claim_status`, `find_network_hospitals`, `insurance_claims` SOP |
| Membership | Paid membership plan | `policy_faq`, `membership_plans` SOP (renamed "Care Plus") |
| Health ID | Create/link ABHA health ID | `membership_plans` SOP section |
| Specialty | Cancer care, dental, corporate plans | Out of scope v1 |

## What we did NOT copy
Brand names, logos, page copy, policies, prices, API shapes. All SOP text, prices, timelines and
seed data in this repo are **written from scratch** and are fictional.

## Takeaway for design
The surface is wide (≈10 service lines) but the *assistant questions* concentrate on four: status
of a thing I bought (order / lab / claim), how to do X (policy), book something, and "what's next"
in a journey. That is exactly the intent taxonomy in `prompts/classify.md`.
