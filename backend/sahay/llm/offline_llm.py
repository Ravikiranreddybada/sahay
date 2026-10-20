"""Deterministic offline engine.

It implements the same `LLM` contract as the Anthropic adapter so the whole graph, the MCP
tool loop, the verifier and the eval suite run with no API key and no network (CI, laptops,
interview demos). It is *not* a toy echo: it does intent scoring, entity extraction, tool
planning and extractive, cited answer synthesis — a strong, explainable baseline that the
real model must beat on the eval set to justify its latency and cost.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from ..health import catalog, labs
from .base import LLMResponse, ToolCall, ToolSpec

INTENT_LEXICON: dict[str, list[str]] = {
    "order_status": ["order", "medicine", "delivery", "delivered", "dispatch", "shipped", "pharmacy", "tablets", "where is my", "track"],
    "lab_booking": ["lab", "blood test", "test report", "report", "sample", "pathology", "thyroid", "lipid", "hba1c", "cbc", "fasting", "health checkup", "full body"],
    "consult_booking": ["doctor", "consult", "appointment", "dermatologist", "cardiologist", "pediatrician", "gynecologist", "slot", "video call", "in-clinic", "specialist", "book a doctor"],
    "claim_status": ["claim", "insurance", "cashless", "reimbursement", "tpa", "policy number", "network hospital", "e-card", "ecard", "pre-auth", "preauth"],
    "refund_cancel": ["refund", "cancel", "cancellation", "money back", "return"],
    "surgery_journey": ["surgery", "operation", "cataract", "knee replacement", "hernia", "admission", "pre-op", "post-op", "discharge", "anaesthesia", "anesthesia", "procedure"],
    "vaccination_journey": ["vaccine", "vaccination", "vaccinated", "immunization", "immunisation", "jab", "shot", "booster", "mmr", "bcg", "hepatitis b", "polio", "dpt", "hpv", "flu shot", "teeka", "tika", "reminder", "remind me"],
    "health_records": ["medicines is", "medicines does", "medicines are", "his medicines", "her medicines", "my medicines", "medicine list",
                       "list of medicines", "medication", "prescriptions", "interaction", "interact", "duplicate", "trend", "over time",
                       "going up", "rising", "lab history", "lab results", "visit brief", "brief for", "questions to ask", "prepare for",
                       "before the appointment", "before his appointment", "before her appointment", "consent", "access to",
                       "papa", "father", "mother", "mom ", "dad ", "amma", "appa", "pitaji", "mummy"],
    # policy_faq is the fallback intent; generic question words ("what is", "how does") are
    # NOT evidence for it (INC-005) — only platform-policy vocabulary is.
    "policy_faq": ["policy", "gold", "membership", "care plus", "abha", "health id", "benefit", "charges"],
    "medical_advice": ["should i take", "dose", "dosage", "diagnose", "is it normal", "what medicine", "which medicine", "symptom", "can i take", "side effect", "mg"],
    "human_agent": ["human", "real person", "agent", "talk to someone", "customer care", "executive", "complaint", "escalate", "speak to"],
    "chitchat": ["hello", "hi ", "thanks", "thank you", "good morning", "who are you"],
}

# Ties are broken toward *transactional* intents: a user who mentions an order id and
# the word "policy" almost always wants the order, not the policy page.
INTENT_PRIORITY = [
    "human_agent", "medical_advice", "refund_cancel", "claim_status", "order_status", "health_records", "lab_booking",
    "vaccination_journey", "surgery_journey", "consult_booking", "policy_faq", "chitchat",
]

ENTITY_PATTERNS: dict[str, str] = {
    "order_id": r"\b(ORD-?\d{4,8})\b",
    "claim_id": r"\b(CLM-?\d{4,8})\b",
    "booking_id": r"\b((?:BKG|LAB)-?\d{4,8})\b",
    "pincode": r"\b([1-9]\d{5})\b",
}
CITIES = ["bangalore", "bengaluru", "mumbai", "delhi", "hyderabad", "chennai", "pune", "kolkata", "gurgaon", "noida"]
SPECIALTIES = ["dermatologist", "cardiologist", "pediatrician", "gynecologist", "orthopedic", "general physician", "ent", "psychiatrist", "dentist"]
PROCEDURES = ["cataract", "knee replacement", "hernia", "gallbladder", "piles", "lasik"]
# "Aarav's next vaccine" -> child_name=Aarav. Capitalised possessives that are not names:
NOT_NAMES = {"My", "Your", "Our", "His", "Her", "Their", "Today", "Tomorrow", "It", "That", "This", "What", "Who", "Child", "Baby",
             "Son", "Daughter", "Kid", "Doctor", "Hospital", "Order", "Lab", "Claim", "Everyone", "Somebody", "Someone", "Mother", "Father", "Care", "Gold", "Plus", "Sahay", "Dr"}
WORD = re.compile(r"[a-z0-9]+")
STOP = set("a an the is are was were be to of in on for and or my me i you it this that with at by from what when how do does can will please".split())


def _norm_id(raw: str) -> str:
    m = re.match(r"([A-Z]+)-?(\d+)", raw.upper())
    return f"{m.group(1)}-{m.group(2)}" if m else raw.upper()


def extract_entities(text: str) -> dict[str, str]:
    ents: dict[str, str] = {}
    for key, pat in ENTITY_PATTERNS.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            ents[key] = _norm_id(m.group(1)) if key != "pincode" else m.group(1)
    low = text.lower()
    for c in CITIES:
        if c in low:
            ents["city"] = "bangalore" if c == "bengaluru" else c
    for s in SPECIALTIES:
        if re.search(rf"\b{s}\b", low):  # word match: "appointment" contains "ent"
            ents["specialty"] = s
    for p in PROCEDURES:
        if p in low:
            ents["procedure"] = p
    m = re.search(r"\bslot\s*#?\s*(S-?\d+)\b", text, re.IGNORECASE)
    if m:
        ents["slot_id"] = _norm_id(m.group(1))
    if m := catalog.RELATION_RE.search(text):
        ents["member"] = catalog.RELATIONS[m.group(1).lower()]
    elif HEALTH_TOPIC.search(low) and re.search(r"\b(my|i|me|mine)\b", low):
        ents["member"] = "self"  # "my medicines" after talking about papa means me, not papa
    if meds := catalog.find_mentions(text):
        ents["medicine"] = meds[0]
    if a := labs.analyte_from_text(text):
        ents["analyte"] = a
    m = re.search(r"\b([A-Z][a-z]{2,})(?:'s|’s)\b", text) or re.search(r"\b(?:for|of|remind me about)\s+([A-Z][a-z]{2,})\b", text)
    if m and m.group(1) not in NOT_NAMES and m.group(1).lower() not in CITIES:
        ents["child_name"] = m.group(1)
    return ents


LIVE_CUES = [
    r"\bmy(\s+\w+){0,2}\s+(order|orders|claim|claims|report|reports|lab|booking|surgery|operation|medicine|medicines|delivery|child|baby|son|daughter|kid|journey)\b",
    r"\bwhere is\b", r"\btrack\b", r"\bstatus\b", r"\bshow my\b", r"\blist\b", r"\bbook\b", r"\bcancel\b",
    r"\bnext (step|vaccine|dose|jab)\b", r"\bdue\b", r"\bup to date\b", r"\bready\b", r"\bpending\b",
    r"\bwhy (is|was)\b.*\b(ORD|CLM|LAB)-?\d", r"\b(hospitals? in|near me)\b", r"\bremind", r"\b(find|need|show)\b.{0,20}\b(doctor|slot|dermatologist|cardiologist|pediatrician|gynecologist|orthopedic|physician)",
]


INTERACTION_CUE = re.compile(r"\b(with|together|along|alongside|interact\w*|mix|combine|plus|and)\b")
HEALTH_TOPIC = re.compile(r"\b(medicines?|medications?|tablets|prescriptions?|hba1c|ldl|cholesterol|sugar|creatinine|vitamin d|tsh|reports?|results?|appointment|visit|brief|consent|access)\b")


def plan_health(query: str, e: dict[str, str]) -> list[tuple[str, dict[str, Any]]]:
    """One deterministic choice of health-record tool (fast path and offline planner)."""
    low = query.lower()
    who = e.get("member") or e.get("child_name")
    m = {"member": who} if who and who != "self" else {}
    if re.search(r"\b(revoke|remove|stop (seeing|sharing))\b", low):
        return [("revoke_care_access", {"member": who or ""})] if who else [("list_care_members", {})]
    if re.search(r"\b(brief|prepare|questions|before (the|his|her|my) (appointment|visit)|visit)\b", low):
        return [("get_visit_brief", m)]
    named = catalog.find_mentions(query)  # this turn only: a carried medicine is not a new question
    if named and INTERACTION_CUE.search(low):
        return [("check_medication_safety", {"medicine": named[0], **m})]
    if e.get("analyte") or re.search(r"\b(trend|over time|going up|rising|lab history|lab results|reports over)\b", low):
        return [("get_lab_trends", {**({"analyte": e["analyte"]} if e.get("analyte") else {}), **m})]
    if re.search(r"\b(consent|access|who can|family members?)\b", low):
        return [("list_care_members", {})]
    return [("get_medication_list", m)]


def needs_live_data(text: str, ents: dict[str, str]) -> bool:
    """Personal-record question vs. how-it-works question (INC-004)."""
    if any(k in ents for k in ("order_id", "claim_id", "booking_id", "slot_id")):
        return True
    return any(re.search(p, text, re.IGNORECASE) for p in LIVE_CUES)


def score_intents(text: str) -> dict[str, float]:
    low = f" {text.lower()} "
    scores: dict[str, float] = {}
    for intent, kws in INTENT_LEXICON.items():
        s = 0.0
        for kw in kws:
            # keyword must start a word: "hi " must not fire inside Hinglish "sabhi ", "lab" not in "collaborate"
            if re.search(r"(?<![a-z])" + re.escape(kw), low):
                s += 1.0 + 0.15 * kw.count(" ")  # multi-word phrases are stronger evidence
        if s:
            scores[intent] = s
    ents = extract_entities(text)
    if "order_id" in ents:
        scores["order_status"] = scores.get("order_status", 0) + 2
    if "claim_id" in ents:
        scores["claim_status"] = scores.get("claim_status", 0) + 2
    if "booking_id" in ents:
        scores["lab_booking"] = scores.get("lab_booking", 0) + 1.5
    if "refund_cancel" in scores and ("order_id" in ents):
        scores["refund_cancel"] += 1.5
    if catalog.find_mentions(text) and INTERACTION_CUE.search(low):
        # "can papa take Brufen with his medicines?": a check against the record, not advice
        scores["health_records"] = scores.get("health_records", 0) + 2.5
    if "health_records" in scores and ("member" in ents or HEALTH_TOPIC.search(low)):
        scores["health_records"] += 1.0  # relation + records topic beats a lone "report"/"medicine"
    if re.search(r"\bcancel\b", low) and ("order_id" in ents or "booking_id" in ents):
        scores["refund_cancel"] = scores.get("refund_cancel", 0) + 2.0  # an action verb + an id = an action request
    return scores


def tokens(text: str) -> list[str]:
    from ..rag.embed import normalize_terms  # same stemming + synonyms as retrieval

    return [w for w in normalize_terms(text) if w not in STOP and len(w) > 1]


def money(x: Any) -> str:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    return f"{int(f):,}" if f.is_integer() else f"{f:,.2f}"


def approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class OfflineLLM:
    name = "offline"

    async def generate(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int = 1024,
        task: str = "chat",
        hints: dict[str, Any] | None = None,
    ) -> LLMResponse:
        hints = hints or {}
        prompt_text = system + json.dumps(messages, default=str)
        handler = getattr(self, f"_task_{task}", self._task_chat)
        out: LLMResponse = handler(messages, tools or [], hints)
        out.model = "offline"
        out.tokens_in = approx_tokens(prompt_text)
        out.tokens_out = approx_tokens(out.text + json.dumps([c.args for c in out.tool_calls]))
        return out

    # --- tasks -----------------------------------------------------------------------------

    def _task_classify(self, messages, tools, hints) -> LLMResponse:
        text = hints.get("query") or _last_user_text(messages)
        history = hints.get("history_text", "")
        scores = score_intents(text)
        if not scores and history:
            # Follow-ups like "and when will it arrive?" inherit the previous intent.
            prev = hints.get("previous_intent")
            if prev:
                scores = {prev: 0.6}
        if not scores:
            intent, conf = "policy_faq", 0.35
        else:
            best = max(scores.values())
            top = [i for i, s in scores.items() if s == best]
            intent = sorted(top, key=INTENT_PRIORITY.index)[0]
            total = sum(scores.values())
            conf = round(min(0.98, 0.45 + 0.5 * best / total), 2)
        own = extract_entities(text)
        carried = hints.get("carried_entities", {})
        ents = {**carried, **own}
        # INC-008: a carried id only makes this turn "live" for a real follow-up ("when will it arrive?")
        follow_up = intent == hints.get("previous_intent") and bool(re.search(r"\b(it|its|that|this|they|them)\b", text, re.I))
        live = needs_live_data(text, own) or (follow_up and any(k in carried for k in ("order_id", "claim_id", "booking_id")))
        if intent == "health_records":
            # personal records unless it is a how-does-it-work question ("how does Sahay check interactions?")
            live = not re.search(r"^\s*(how|what) (does|do|is) (sahay|the app|it)\b", text, re.I)
        payload = {
            "intent": intent,
            "confidence": conf,
            "entities": ents,
            "needs_retrieval": intent not in {"chitchat", "human_agent"},
            "needs_live_data": live,
            "search_query": text,
        }
        return LLMResponse(tool_calls=[ToolCall(id=_id(), name="emit_classify", args=payload)], stop_reason="tool_use")

    def _task_plan_tools(self, messages, tools, hints) -> LLMResponse:
        intent: str = hints.get("intent", "")
        e: dict[str, str] = hints.get("entities", {})
        done: set[str] = set(hints.get("called_tools", []))
        query = hints.get("query", "").lower()
        city = e.get("city") or (hints.get("profile") or {}).get("city") or "bangalore"
        names = {t.name for t in tools}
        plan: list[tuple[str, dict[str, Any]]] = []

        if intent == "order_status":
            plan.append(("get_order_status", {"order_id": e["order_id"]}) if "order_id" in e else ("list_recent_orders", {}))
        elif intent == "refund_cancel":
            if "order_id" in e and "cancel" in query:
                plan.append(("cancel_order", {"order_id": e["order_id"], "reason": "customer_request"}))
            elif "order_id" in e:
                plan.append(("get_order_status", {"order_id": e["order_id"]}))
        elif intent == "lab_booking":
            if "booking_id" in e:
                plan.append(("get_lab_report_status", {"booking_id": e["booking_id"]}))
            else:
                plan.append(("search_lab_tests", {"query": hints.get("query", "")}))
        elif intent == "consult_booking":
            if "slot_id" in e and any(w in query for w in ["book", "confirm", "yes"]):
                plan.append(("book_consultation", {"slot_id": e["slot_id"]}))
            else:
                plan.append(("search_doctor_slots", {"specialty": e.get("specialty", "general physician"), "city": city}))
        elif intent == "claim_status":
            if any(w in query for w in ["network hospital", "cashless hospital", "hospital near", "hospitals in"]):
                plan.append(("find_network_hospitals", {"city": city}))
            elif "claim_id" in e:
                plan.append(("get_claim_status", {"claim_id": e["claim_id"]}))
            else:
                plan.append(("list_claims", {}))
        elif intent == "vaccination_journey":
            if re.search(r"\b(my|active|list|show)\b.{0,15}\breminders\b", query):
                plan.append(("list_reminders", {}))
            elif "remind" in query:
                plan.append(("set_vaccination_reminder", {**({"child_name": e["child_name"]} if e.get("child_name") else {}),
                                                          "channel": "sms" if "sms" in query else "whatsapp"}))
            else:
                plan.append(("get_vaccination_schedule", {"child_name": e["child_name"]} if e.get("child_name") else {}))
        elif intent == "health_records":
            plan += plan_health(hints.get("query", ""), e)
        elif intent == "surgery_journey":
            plan.append(("get_surgery_journey", {}))
            if e.get("procedure"):
                plan.append(("get_surgery_checklist", {"procedure": e["procedure"]}))

        for name, args in plan:
            if name in names and name not in done:
                return LLMResponse(tool_calls=[ToolCall(id=_id(), name=name, args=args)], stop_reason="tool_use")
        return LLMResponse(text="DONE", stop_reason="end_turn")

    def _task_answer(self, messages, tools, hints) -> LLMResponse:
        query = hints.get("query", "")
        intent = hints.get("intent", "")
        evidence: list[dict[str, Any]] = hints.get("evidence", [])
        tool_results: list[dict[str, Any]] = hints.get("tool_results", [])
        parts: list[str] = []
        used: list[str] = []

        for tr in tool_results:
            line = _render_tool_result(tr)
            if line:
                parts.append(f"{line} [{tr['ref']}]")
                used.append(tr["ref"])

        for ev in evidence:
            if ev.get("pinned"):  # governing rule for this intent (INC-006): always stated
                first = " ".join(re.split(r"(?<=[.!?])\s+", ev["text"])[:2])
                parts.append(f"{first} [{ev['id']}]")
                used.append(ev["id"])
        q = set(tokens(query))
        scored: list[tuple[float, str, str]] = []
        for ev in evidence:
            for sent in re.split(r"(?<=[.!?])\s+|\n+", ev["text"]):
                sent = sent.strip().lstrip("-* ").strip()
                st = set(tokens(sent))
                shared = q & st
                if len(st) < 4 or len(shared) < 2:
                    continue
                score = len(shared) / (len(q) ** 0.5 * len(st) ** 0.5 + 1e-9)
                scored.append((score, sent, ev["id"]))
        scored.sort(key=lambda x: -x[0])
        # with live data, policy text is supporting context only: fewer and stricter
        max_sents, floor = (2, 0.3) if tool_results else (2, 0.2)
        seen: set[str] = set()
        for score, sent, cid in scored:
            if score < floor or sent in seen:
                continue
            seen.add(sent)
            parts.append(f"{sent} [{cid}]")
            used.append(cid)
            if len(seen) >= max_sents:
                break

        if hints.get("read_only"):
            # suspected injection: refuse the action, do not decorate it with loosely related policy text
            parts = [p for p in parts if "[tool:" in p]
            used = [u for u in used if u.startswith("tool:")]
            parts.insert(0, "I can only help with your own account here, and I can't take actions on that request.")
            return LLMResponse(text=json.dumps({"answer": " ".join(parts), "citations": sorted(set(used)), "abstained": not used}))
        if not parts:
            text = (
                "I could not find this in our verified care guidelines, so I won't guess. "
                "I can connect you to a care specialist who can confirm."
            )
            return LLMResponse(text=json.dumps({"answer": text, "citations": [], "abstained": True}))
        if intent == "medical_advice":
            parts.insert(0, "I can't advise on medicines or doses for you personally — a doctor needs to assess that, and I can book a consultation for you.")
        return LLMResponse(text=json.dumps({"answer": " ".join(parts), "citations": sorted(set(used)), "abstained": False}))

    def _task_chat(self, messages, tools, hints) -> LLMResponse:
        return LLMResponse(text="Hi! I'm Sahay. I can track orders, lab reports and claims, book consults and guide you through vaccination and surgery journeys.")


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c
            return " ".join(b.get("text", "") for b in c if isinstance(b, dict))
    return ""


def _id() -> str:
    return "toolu_" + uuid.uuid4().hex[:12]


def _render_tool_result(tr: dict[str, Any]) -> str:
    """Template the structured MCP result into one plain sentence."""
    name, r = tr["tool"], tr.get("result") or {}
    if tr.get("error"):
        return f"I couldn't complete that: {tr['error']}"
    if r.get("status") == "not_performed":
        return "Okay, I have not made any change."
    if name == "get_order_status":
        eta = f", expected by {r['eta']}" if r.get("eta") else ""
        return f"Order {r['order_id']} ({', '.join(r.get('items', []))}) is {r['status'].replace('_', ' ')}{eta}."
    if name == "list_recent_orders":
        if not r.get("orders"):
            return "You have no recent orders."
        o = r["orders"][0]
        return f"Your latest order {o['order_id']} is {o['status'].replace('_', ' ')}."
    if name == "cancel_order":
        return f"Order {r['order_id']} is {r['status']}; refund of ₹{money(r.get('refund_amount', 0))} will reach the original payment method in {r.get('refund_days', '5-7')} working days."
    if name == "get_lab_report_status":
        return f"Lab booking {r['booking_id']} ({r['test']}): {r['status'].replace('_', ' ')}" + (f", report expected {r['report_eta']}." if r.get("report_eta") else ".")
    if name == "search_lab_tests":
        tests = r.get("tests", [])[:3]
        return "Matching tests: " + "; ".join(f"{t['name']} ₹{t['price']} ({'fasting' if t['fasting'] else 'no fasting'})" for t in tests) + "." if tests else "No matching lab tests found."
    if name == "search_doctor_slots":
        s = r.get("slots", [])[:3]
        return "Available slots: " + "; ".join(f"{x['slot_id']} {x['doctor']} {x['time']} ₹{x['fee']}" for x in s) + ". Reply with a slot id to book." if s else "No slots available right now."
    if name == "book_consultation":
        return f"Booked: {r['doctor']} at {r['time']}, booking {r['booking_id']}."
    if name == "get_claim_status":
        return f"Claim {r['claim_id']} is {r['status'].replace('_', ' ')}; approved ₹{money(r.get('approved_amount', 0))} of ₹{money(r.get('claimed_amount', 0))}" + (f". Pending: {r['pending_documents']}" if r.get("pending_documents") else "") + "."
    if name == "list_claims":
        c = r.get("claims", [])
        return f"You have {len(c)} claim(s); latest {c[0]['claim_id']} is {c[0]['status'].replace('_', ' ')}." if c else "You have no claims on record."
    if name == "find_network_hospitals":
        h = r.get("hospitals", [])[:3]
        return "Cashless network hospitals: " + "; ".join(x["name"] for x in h) + "." if h else "No network hospitals found for that city."
    if name == "get_vaccination_schedule":
        due = r.get("next_due")
        return f"{r['child_name']}'s next vaccine: {due['vaccine']} due on {due['due_date']}." if due else f"{r.get('child_name', 'Your child')} is up to date."
    if name == "set_vaccination_reminder":
        return f"Reminders are on for {r['child_name']} on {r['channel'].upper() if r['channel'] == 'sms' else 'WhatsApp'}: {r['schedule']}."
    if name == "list_reminders":
        rs = r.get("reminders", [])
        return "Active reminders: " + "; ".join(f"{x['child_name']} on {x['channel']}" for x in rs) + "." if rs else "You have no active vaccine reminders."
    if name == "get_surgery_journey":
        return f"Your {r['procedure']} is at stage '{r['stage'].replace('_', ' ')}'; next step: {r['next_step']}." if r.get("procedure") else "No active surgery journey."
    if name in HEALTH_RENDER:
        return HEALTH_RENDER[name](r)
    if name == "get_surgery_checklist":
        return f"Pre-op checklist for {r['procedure']}: " + "; ".join(r.get("items", [])[:4]) + "."
    return ""


def _whose(r: dict[str, Any]) -> str:
    return "Your" if r.get("relation") == "self" else f"{r.get('member', 'Their')}'s"


def _r_meds(r: dict[str, Any]) -> str:
    meds = "; ".join(f"{m['name']} ({' + '.join(m['molecules']) or 'not in database'}) - {m['instructions']}, from {m['prescriber']}" for m in r.get("medications", []))
    out = f"{_whose(r)} current medicines: {meds}." if meds else f"{_whose(r)} medicine list is empty."
    for d in r.get("duplicates", []):
        out += f" The same molecule, {d['molecule']}, comes from both {' and '.join(d['products'])}."
    for i in r.get("interactions", []):
        out += f" Sahay's medicine database records a {i['severity']} interaction between {i['products'][0]} and {i['products'][1]}: {i['effect']}."
    if r.get("duplicates") or r.get("interactions"):
        out += " Please show this to the prescriber; don't stop or change any medicine on your own."
    return out


def _r_check(r: dict[str, Any]) -> str:
    if r.get("result") == "unknown_medicine":
        return r["note"]
    head = f"I checked {r['medicine']} ({' + '.join(r.get('molecules', []))}) against {"your" if r.get("relation") == "self" else _whose(r)} current medicines in Sahay's medicine database."
    parts = [f"It contains {d['molecule']}, which is already in {d['already_in']}: taking both doubles that molecule." for d in r.get("duplicates_with", [])]
    parts += [f"A {i['severity']} interaction is recorded between {i['between'][0]} and {i['between'][1]} ({i['with_product']}): {i['effect']}." for i in r.get("interactions", [])]
    if not parts:
        parts = ["No interaction or duplicate is recorded in our database. That is not a safety verdict for this person."]
    return head + " " + " ".join(parts) + " Please confirm with the prescriber or pharmacist before taking it."


def _r_trends(r: dict[str, Any]) -> str:
    if not r.get("trends"):
        return r.get("note", "No lab results on record.")
    out = []
    for t in r["trends"][:3]:
        pts = " -> ".join(f"{p['value']:g} {t['unit']} on {p['date']} ({p['lab']}" + (f", reported as {p['reported_as']}" if p.get("reported_as") else "") + ")" for p in t["points"])
        line = f"{_whose(r)} {t['analyte']}: {pts}."
        if t.get("direction"):
            line += f" Direction: {t['direction']}."
        if t.get("latest_flag") and t["latest_flag"] != "in_range" and t.get("reference_range"):
            line += f" The latest value is {t['latest_flag']} against the lab range {t['reference_range']}."
        elif t.get("steady_rise"):
            line += " Each value is within range, but it has risen on every report."
        out.append(line)
    return " ".join(out) + " Values from different labs are shown in one unit; your doctor can explain what they mean."


def _r_brief(r: dict[str, Any]) -> str:
    a = r.get("appointment")
    head = f"Visit brief: {a['doctor']} ({a['specialty']}) on {a['time']}." if a else "Visit brief (no upcoming appointment on record)."
    qs = " ".join(f"({n}) {q}" for n, q in enumerate(r.get("questions", [])[:4], 1))
    return f"{head} Questions worth asking: {qs}" if qs else f"{head} Nothing in the records needs flagging."


def _r_members(r: dict[str, Any]) -> str:
    ms = [m for m in r.get("members", []) if m["relation"] != "self"]
    if not ms:
        return "Only your own records are on this account."
    return "Family on your account: " + "; ".join(f"{m['member']} ({m['relation']}), consent {m.get('consent')}" + (f" until {m['consent_expires']}" if m.get("consent") == "active" else "") for m in ms) + "."


HEALTH_RENDER = {
    "get_medication_list": _r_meds, "check_medication_safety": _r_check, "get_lab_trends": _r_trends, "get_visit_brief": _r_brief,
    "list_care_members": _r_members,
    "revoke_care_access": lambda r: f"Access to {r['member']}'s records is revoked from {r['effective']}.",
}
