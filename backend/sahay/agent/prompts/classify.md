Classify the user's latest message for routing. Use the conversation so far to resolve follow-ups ("and when will it arrive?" continues the previous intent).

Intents:
- order_status: medicine order tracking, delivery, prescription hold
- refund_cancel: cancel something, refund timelines, returns
- lab_booking: lab tests, sample collection, reports, fasting
- consult_booking: find or book a doctor (online or in-clinic)
- claim_status: insurance claims, cashless, reimbursement, e-card, network hospitals
- vaccination_journey: child vaccines, schedule, due doses, reactions logistics
- surgery_journey: planned surgery, pre-op, admission, discharge, recovery
- health_records: the user's or a family member's medicine list, a check of one medicine against current medicines ("can papa take Brufen with his tablets?"), lab results over time, a pre-visit brief, family consent / access
- policy_faq: platform policies, membership, ABHA, general how-it-works
- medical_advice: asks what medicine/dose to take, or to diagnose a symptom
- human_agent: wants a human, or a complaint to escalate
- chitchat: greetings, thanks, small talk

Extract entities exactly as written: order_id (ORD-####), claim_id (CLM-#####), booking_id (LAB-#### or BKG-######), slot_id (S-###), city, specialty, procedure, child_name, member (whose health records: self, father, mother, or a first name), medicine (brand or molecule as written), analyte (hba1c, ldl, fasting_glucose, vitamin_d, creatinine, tsh).
A question that names a medicine and asks if it can be taken *with current medicines* is health_records (a database check), not medical_advice. "Which medicine should I take for fever?" is medical_advice.
search_query: rewrite the message as a standalone search query for the knowledge base (resolve pronouns using the conversation).

needs_live_data: true only if the answer depends on THIS user's own records or asks for an action ("where is my order", "is my report ready", "cancel ORD-1043", "next vaccine for Aarav"). False for how-it-works questions even inside a domain ("how long do refunds take", "what documents does a reimbursement claim need", "will I get a refund if the doctor doesn't join").
