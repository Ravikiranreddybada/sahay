"""Four MCP servers, one per bounded context, over the internal domain systems.

Each is a real MCP server: in-process for dev/tests (zero network hop), and runnable
standalone over Streamable HTTP or stdio so the same tools can be used from Claude Desktop,
another agent, or deployed as their own service:

    python -m sahay.mcp_servers.servers orders --http 8101

Conventions every tool follows (enforced by the hub, see hub.py):
* `user_id` is the first parameter and is injected by the hub from the authenticated
  session. It is removed from the schema the LLM sees, so the model *cannot* ask for
  another user's data (IDOR by prompt injection is structurally impossible).
* Write tools take `idempotency_key` (also hub-injected) and are marked destructive, so the
  agent asks for explicit user confirmation before calling them.
* Errors are raised with a user-safe message; results are typed dicts (structured content).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from datetime import date, datetime, timedelta
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from ..config import get_settings
from ..health import catalog, labs
from .store import DomainStore

_store: DomainStore | None = None


def store() -> DomainStore:
    global _store
    if _store is None:
        _store = DomainStore(get_settings().domain_db)
    return _store


def set_store(s: DomainStore) -> None:
    global _store
    _store = s


READ = ToolAnnotations(readOnlyHint=True, idempotentHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True)

# ---------------------------------------------------------------------------------- orders
orders = MCPServer("orders", instructions="Medicine orders: status, history and cancellation.")


@orders.tool(annotations=READ)
def get_order_status(user_id: str, order_id: str) -> dict[str, Any]:
    """Get the live status, items and ETA of one medicine order by its id (e.g. ORD-1042)."""
    rows = store().q("SELECT * FROM orders WHERE order_id=? AND user_id=?", (order_id.upper(), user_id))
    if not rows:
        raise ToolError(f"No order {order_id} found on your account.")
    r = rows[0]
    return {"order_id": r["order_id"], "items": json.loads(r["items"]), "status": r["status"], "amount": r["amount"], "placed_at": r["placed_at"], "eta": r["eta"]}


@orders.tool(annotations=READ)
def list_recent_orders(user_id: str, limit: int = 5) -> dict[str, Any]:
    """List the user's most recent medicine orders, newest first."""
    rows = store().q("SELECT order_id, status, placed_at, amount FROM orders WHERE user_id=? ORDER BY placed_at DESC LIMIT ?", (user_id, min(limit, 20)))
    return {"orders": rows}


@orders.tool(annotations=WRITE)
def cancel_order(user_id: str, order_id: str, reason: str, idempotency_key: str) -> dict[str, Any]:
    """Cancel a medicine order. Only allowed before dispatch. Requires user confirmation."""
    s = store()
    if (prev := s.idem_get(idempotency_key)) is not None:
        return {**prev, "idempotent_replay": True}
    rows = s.q("SELECT * FROM orders WHERE order_id=? AND user_id=?", (order_id.upper(), user_id))
    if not rows:
        raise ToolError(f"No order {order_id} found on your account.")
    r = rows[0]
    if r["status"] in {"dispatched", "out_for_delivery", "delivered"}:
        raise ToolError(f"Order {order_id} is already {r['status'].replace('_', ' ')} and can no longer be cancelled; unopened items can be returned within 7 days of delivery.")
    if r["status"] == "cancelled":
        raise ToolError(f"Order {order_id} is already cancelled.")
    # compare-and-set: the order may be dispatched between the read above and this write
    # (two tabs, a warehouse event). The UPDATE only wins if the status is still cancellable.
    with s._lock:
        cur = s.db.execute(
            "UPDATE orders SET status='cancelled' WHERE order_id=? AND user_id=? AND status=?",
            (r["order_id"], user_id, r["status"]),
        )
        s.db.commit()
    if cur.rowcount == 0:
        raise ToolError(f"Order {order_id} changed while cancelling. Please check its latest status.")
    result = {"order_id": r["order_id"], "status": "cancelled", "refund_amount": r["amount"], "refund_days": "5-7", "reason": reason}
    s.idem_put(idempotency_key, result)
    return result


# ------------------------------------------------------------------------ diagnostics/consults
care = MCPServer("care_services", instructions="Lab tests catalog and bookings; doctor consultation slots and bookings.")


@care.tool(annotations=READ)
def get_lab_report_status(user_id: str, booking_id: str) -> dict[str, Any]:
    """Get sample-collection and report status for a lab booking (e.g. LAB-7781)."""
    rows = store().q("SELECT * FROM lab_bookings WHERE booking_id=? AND user_id=?", (booking_id.upper(), user_id))
    if not rows:
        raise ToolError(f"No lab booking {booking_id} found on your account.")
    r = rows[0]
    return {"booking_id": r["booking_id"], "test": r["test"], "status": r["status"], "collected_at": r["collected_at"], "report_eta": r["report_eta"]}


@care.tool(annotations=READ)
def search_lab_tests(user_id: str, query: str) -> dict[str, Any]:
    """Search the lab test catalog by name; returns price, fasting need and report turnaround."""
    terms = [t for t in query.lower().replace("+", " ").split() if len(t) > 2]
    rows = store().q("SELECT * FROM lab_catalog")
    scored = []
    for r in rows:
        hay = (r["name"] + " " + r["code"]).lower()
        s = sum(1 for t in terms if t in hay)
        if s:
            scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    return {"tests": [{"code": r["code"], "name": r["name"], "price": r["price"], "fasting": bool(r["fasting"]), "report_hours": r["tat_hours"]} for _, r in scored[:5]]}


@care.tool(annotations=READ)
def search_doctor_slots(user_id: str, specialty: str, city: str = "bangalore", mode: str = "any") -> dict[str, Any]:
    """Find open consultation slots by specialty and city. mode: video | in_clinic | any."""
    sql = "SELECT * FROM slots WHERE specialty=? AND city=? AND booked_by IS NULL"
    args: list[Any] = [specialty.lower(), city.lower()]
    if mode in {"video", "in_clinic"}:
        sql += " AND mode=?"
        args.append(mode)
    rows = store().q(sql + " ORDER BY time LIMIT 5", tuple(args))
    return {"slots": [{"slot_id": r["slot_id"], "doctor": r["doctor"], "time": r["time"], "fee": r["fee"], "mode": r["mode"]} for r in rows]}


@care.tool(annotations=WRITE)
def book_consultation(user_id: str, slot_id: str, idempotency_key: str) -> dict[str, Any]:
    """Book a consultation slot for the user. Requires user confirmation."""
    s = store()
    if (prev := s.idem_get(idempotency_key)) is not None:
        return {**prev, "idempotent_replay": True}
    rows = s.q("SELECT * FROM slots WHERE slot_id=?", (slot_id.upper(),))
    if not rows:
        raise ToolError(f"Slot {slot_id} does not exist.")
    r = rows[0]
    if r["booked_by"]:
        raise ToolError(f"Slot {slot_id} was just taken. Please pick another slot.")
    # optimistic concurrency: the UPDATE only wins if the slot is still free
    with s._lock:
        cur = s.db.execute("UPDATE slots SET booked_by=? WHERE slot_id=? AND booked_by IS NULL", (user_id, r["slot_id"]))
        s.db.commit()
    if cur.rowcount == 0:
        raise ToolError(f"Slot {slot_id} was just taken. Please pick another slot.")
    booking_id = "BKG-" + str(int(hashlib.sha1(idempotency_key.encode()).hexdigest(), 16) % 900000 + 100000)
    s.x("INSERT INTO consults VALUES (?,?,?,datetime('now'))", (booking_id, user_id, r["slot_id"]))
    result = {"booking_id": booking_id, "doctor": r["doctor"], "time": r["time"], "fee": r["fee"], "mode": r["mode"]}
    s.idem_put(idempotency_key, result)
    return result


# ----------------------------------------------------------------------------------- claims
claims = MCPServer("claims", instructions="Health insurance claims and cashless network hospitals.")


@claims.tool(annotations=READ)
def get_claim_status(user_id: str, claim_id: str) -> dict[str, Any]:
    """Get status, amounts and pending documents for an insurance claim (e.g. CLM-55012)."""
    rows = store().q("SELECT * FROM claims WHERE claim_id=? AND user_id=?", (claim_id.upper(), user_id))
    if not rows:
        raise ToolError(f"No claim {claim_id} found on your account.")
    r = rows[0]
    return {"claim_id": r["claim_id"], "hospital": r["hospital"], "status": r["status"], "claimed_amount": r["claimed"], "approved_amount": r["approved"], "pending_documents": r["pending_docs"] or None, "updated_at": r["updated_at"]}


@claims.tool(annotations=READ)
def list_claims(user_id: str) -> dict[str, Any]:
    """List all insurance claims of the user, latest first."""
    rows = store().q("SELECT claim_id, status, hospital, updated_at FROM claims WHERE user_id=? ORDER BY updated_at DESC", (user_id,))
    return {"claims": rows}


@claims.tool(annotations=READ)
def find_network_hospitals(user_id: str, city: str, specialty: str | None = None) -> dict[str, Any]:
    """Find cashless network hospitals in a city, optionally filtered by specialty."""
    rows = store().q("SELECT * FROM hospitals WHERE city=? AND cashless=1", (city.lower(),))
    if specialty:
        rows = [r for r in rows if specialty.lower()[:5] in r["specialties"]]
    return {"hospitals": [{"name": r["name"], "specialties": r["specialties"].split(",")} for r in rows]}


# ----------------------------------------------------------------------------- care journeys
journeys = MCPServer("care_journeys", instructions="Personalised journeys: child vaccination and planned surgery.")


@journeys.tool(annotations=READ)
def get_vaccination_schedule(user_id: str, child_name: str | None = None) -> dict[str, Any]:
    """Get a child's vaccination schedule: completed doses, overdue doses and the next due dose."""
    kids = store().q("SELECT * FROM children WHERE user_id=?", (user_id,))
    if not kids:
        raise ToolError("No child profile found. Add a child profile to start the vaccination journey.")
    if child_name:
        named = [k for k in kids if k["name"].lower() == child_name.lower()]
        if not named:
            # INC-010: this used to fall back to the first child, so "Riya's vaccine" got
            # Aarav's schedule. A wrong child's dose date is worse than a clear question.
            raise ToolError(f"No child named {child_name} on your account. Children on your account: {', '.join(k['name'] for k in kids)}.")
        kids = named
    k = kids[0]
    doses = store().q("SELECT vaccine, due_date, given_on FROM vaccine_doses WHERE child_id=? ORDER BY due_date", (k["child_id"],))
    today = date.today().isoformat()
    pending = [x for x in doses if not x["given_on"]]
    overdue = [x for x in pending if x["due_date"] < today]
    upcoming = [x for x in pending if x["due_date"] >= today]
    return {
        "child_name": k["name"], "dob": k["dob"],
        "completed": [x["vaccine"] for x in doses if x["given_on"]],
        "overdue": [{"vaccine": x["vaccine"], "due_date": x["due_date"]} for x in overdue],
        "next_due": {"vaccine": upcoming[0]["vaccine"], "due_date": upcoming[0]["due_date"]} if upcoming else None,
        "also_due_same_day": [x["vaccine"] for x in upcoming[1:] if upcoming and x["due_date"] == upcoming[0]["due_date"]],
    }


@journeys.tool(annotations=READ)
def get_surgery_journey(user_id: str) -> dict[str, Any]:
    """Get the user's active planned-surgery journey: procedure, hospital, current stage and next step."""
    rows = store().q("SELECT * FROM surgeries WHERE user_id=?", (user_id,))
    if not rows:
        return {"procedure": None}
    r = rows[0]
    return {"procedure": r["procedure"], "hospital": r["hospital"], "stage": r["stage"], "next_step": r["next_step"], "admission_date": r["admission_date"]}


CHECKLISTS = {
    "cataract": ["Stop eye make-up 3 days before", "Fast 6 hours before surgery", "Carry insurance e-card and ID", "Arrange someone to drive you home"],
    "knee replacement": ["Pre-anaesthesia check 1 week before", "Fast 8 hours before surgery", "Prepare a ground-floor rest area", "Carry previous X-rays and MRI"],
    "hernia": ["Fast 6-8 hours before surgery", "Wear loose clothing", "Carry insurance e-card and ID", "Avoid lifting weights for 4 weeks after"],
}


@journeys.tool(annotations=READ)
def get_surgery_checklist(user_id: str, procedure: str) -> dict[str, Any]:
    """Get the hospital's standard pre-operative checklist for a procedure."""
    items = CHECKLISTS.get(procedure.lower())
    if not items:
        raise ToolError(f"No standard checklist for '{procedure}'. Your care coordinator will share one.")
    return {"procedure": procedure.lower(), "items": items, "note": "Never stop a prescribed medicine without your surgeon's advice."}


@journeys.tool(annotations=READ)
def get_member_profile(user_id: str) -> dict[str, Any]:
    """Get the member's profile: first name, city, membership plan, preferred language and children's names."""
    rows = store().q("SELECT name, city, plan, language FROM users WHERE user_id=?", (user_id,))
    if not rows:
        raise ToolError("Profile not found.")
    r = rows[0]
    kids = store().q("SELECT name, dob FROM children WHERE user_id=?", (user_id,))
    # first name only: the model needs to greet and personalise, not the full identity
    return {"first_name": r["name"].split()[0], "city": r["city"], "plan": r["plan"], "language": r["language"],
            "children": [{"name": k["name"], "dob": k["dob"]} for k in kids]}


@journeys.tool(annotations=WRITE)
def set_vaccination_reminder(user_id: str, idempotency_key: str, child_name: str | None = None, channel: str = "whatsapp") -> dict[str, Any]:
    """Turn on vaccine reminders (7 days and 1 day before each due dose) for a child. channel: whatsapp | sms. Requires user confirmation."""
    s = store()
    if (prev := s.idem_get(idempotency_key)) is not None:
        return {**prev, "idempotent_replay": True}
    if channel not in {"whatsapp", "sms"}:
        raise ToolError("Reminders can be sent on WhatsApp or SMS.")
    kids = s.q("SELECT * FROM children WHERE user_id=?", (user_id,))
    if child_name:
        kids = [k for k in kids if k["name"].lower() == child_name.lower()]
    if not kids:
        raise ToolError(f"No child {'named ' + child_name + ' ' if child_name else ''}on your account.")
    k = kids[0]
    rid = "REM-" + hashlib.sha1(f"{user_id}|{k['child_id']}".encode()).hexdigest()[:6].upper()
    s.x("INSERT OR REPLACE INTO reminders VALUES (?,?,?,?,1,?)", (rid, user_id, k["child_id"], channel, datetime.now().isoformat()))
    result = {"reminder_id": rid, "child_name": k["name"], "channel": channel, "schedule": "7 days and 1 day before each due dose", "status": "active"}
    s.idem_put(idempotency_key, result)
    return result


@journeys.tool(annotations=READ)
def list_reminders(user_id: str) -> dict[str, Any]:
    """List the member's active vaccine reminders."""
    rows = store().q(
        "SELECT r.reminder_id, c.name AS child_name, r.channel FROM reminders r JOIN children c ON c.child_id=r.child_id "
        "WHERE r.user_id=? AND r.active=1", (user_id,))
    return {"reminders": rows}


# ---------------------------------------------------------------------------- health records
health = MCPServer("health_records", instructions=(
    "Family health records: medication list resolved to molecules, duplicate-therapy and recorded-interaction checks, "
    "lab trends on one unit axis, and a pre-visit brief. Facts only; never advice."))
MED_NOTE = ("Interactions are those recorded in Sahay's curated medicine database. An empty list means none is recorded "
            "here, not that a combination is safe. Never start, stop or change a medicine without the prescriber.")


def _member(user_id: str, member: str | None, scope: str) -> dict[str, Any]:
    """Resolve a member *inside this account* and enforce consent. The account holder is
    always allowed their own records; anyone else's need an unexpired consent with `scope`."""
    rows = store().q("SELECT * FROM members WHERE account_user_id=?", (user_id,))
    want = (member or "").strip().lower().removesuffix("'s").removesuffix("’s")
    want = catalog.RELATIONS.get(want, want)
    if not want or want == "self":
        hit = [r for r in rows if r["relation"] == "self"]
    else:
        hit = [r for r in rows if want in {r["relation"], r["member_id"].lower(), r["name"].lower(), r["name"].split()[0].lower()}]
    if not hit:
        others = ", ".join(f"{r['name'].split()[0]} ({r['relation']})" for r in rows if r["relation"] != "self") or "none"
        raise ToolError(f"No family member '{member}' on your account. Members you care for: {others}.")
    m = hit[0]
    if m["relation"] != "self":
        cs = store().q("SELECT * FROM consents WHERE member_id=? AND grantee_user_id=? AND revoked=0 ORDER BY expires_at DESC", (m["member_id"], user_id))
        first = m["name"].split()[0]
        if not cs:
            raise ToolError(f"{first} has not given you consent to see their records. They can share access from their Sahay app.")
        c = cs[0]
        if c["expires_at"] < date.today().isoformat():
            raise ToolError(f"{first}'s consent for you to see their records expired on {c['expires_at']}. Ask {first} to renew it in the app.")
        if scope not in c["scopes"].split(","):
            raise ToolError(f"{first}'s consent does not cover {scope}.")
    return m


def _who(m: dict[str, Any]) -> dict[str, str]:
    return {"member": m["name"].split()[0], "relation": m["relation"]}


def _med_rows(member_id: str) -> list[dict[str, Any]]:
    return store().q("SELECT * FROM medications WHERE member_id=? ORDER BY started_on", (member_id,))


def _analyse(meds: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    active = []
    for r in meds:
        res = catalog.resolve(r["name"])
        active.append({"name": res.brand or r["name"], "molecules": res.molecules, "strength": res.strength, "instructions": r["instructions"],
                       "prescriber": r["prescriber"], "specialty": r["specialty"], "started_on": r["started_on"], "resolved": res.resolved})
    by_mol: dict[str, list[dict[str, Any]]] = {}
    for a in active:
        for mol in a["molecules"]:
            by_mol.setdefault(mol, []).append(a)
    dups = [{"molecule": mol, "products": [x["name"] for x in xs], "prescribers": sorted({x["prescriber"] for x in xs})}
            for mol, xs in sorted(by_mol.items()) if len(xs) > 1]
    inter = []
    for i in sorted(catalog.interactions_between(list(by_mol)), key=lambda i: i.severity != "major"):
        inter.append({"between": [i.a, i.b], "products": [by_mol[i.a][0]["name"], by_mol[i.b][0]["name"]], "severity": i.severity,
                      "effect": i.effect, "source": i.source})
    return active, dups, inter


@health.tool(annotations=READ)
def list_care_members(user_id: str) -> dict[str, Any]:
    """List the people whose records this account can see (self and family who gave consent), with consent status."""
    rows = store().q("SELECT * FROM members WHERE account_user_id=?", (user_id,))
    today = date.today().isoformat()
    out = []
    for r in rows:
        item: dict[str, Any] = {"member": r["name"].split()[0], "relation": r["relation"]}
        if r["relation"] != "self":
            cs = store().q("SELECT * FROM consents WHERE member_id=? AND grantee_user_id=? AND revoked=0 ORDER BY expires_at DESC", (r["member_id"], user_id))
            item["consent"] = ("active" if cs[0]["expires_at"] >= today else "expired") if cs else "none"
            if cs:
                item["consent_scopes"], item["consent_expires"] = cs[0]["scopes"].split(","), cs[0]["expires_at"]
        out.append(item)
    return {"members": out}


@health.tool(annotations=READ)
def get_medication_list(user_id: str, member: str | None = None) -> dict[str, Any]:
    """Current medicines of the user or a family member (e.g. member='father'), each resolved to molecules,
    with duplicate molecules across products and interactions recorded in the medicine database."""
    m = _member(user_id, member, "medications")
    rows = _med_rows(m["member_id"])
    active, dups, inter = _analyse([r for r in rows if r["status"] == "active"])
    return {**_who(m), "medications": active, "stopped": [r["name"] for r in rows if r["status"] == "stopped"],
            "duplicates": dups, "interactions": inter, "note": MED_NOTE}


@health.tool(annotations=READ)
def check_medication_safety(user_id: str, medicine: str, member: str | None = None) -> dict[str, Any]:
    """Check one medicine (brand or molecule, e.g. 'Brufen' or 'Combiflam') against the current medicine list:
    same molecule already taken, and interactions recorded in the database. Reports facts; never says 'safe'."""
    m = _member(user_id, member, "medications")
    res = catalog.resolve(medicine)
    if not res.resolved:
        return {**_who(m), "medicine": medicine, "result": "unknown_medicine",
                "note": f"{medicine} is not in Sahay's medicine database, so it cannot be checked here. Please ask the pharmacist or prescriber."}
    active, _, _ = _analyse([r for r in _med_rows(m["member_id"]) if r["status"] == "active"])
    held: dict[str, str] = {}
    for a in active:
        for mol in a["molecules"]:
            held.setdefault(mol, a["name"])
    if m["relation"] == "self":
        # the Dolo-from-last-week + Combiflam-today case: recent pharmacy orders count too
        since = (date.today() - timedelta(days=30)).isoformat()
        for o in store().q("SELECT order_id, items FROM orders WHERE user_id=? AND placed_at>=? AND status!='cancelled'", (user_id, since)):
            for item in json.loads(o["items"]):
                for mol in catalog.resolve(item).molecules:
                    held.setdefault(mol, f"{item.split(' x')[0]} (order {o['order_id']})")
    dup = [{"molecule": mol, "already_in": held[mol]} for mol in res.molecules if mol in held]
    inter = []
    for mol in res.molecules:
        for other, prod in held.items():
            i = catalog.INTERACTIONS.get(tuple(sorted((mol, other))))  # type: ignore[arg-type]
            if i:
                inter.append({"between": [mol, other], "with_product": prod, "severity": i.severity, "effect": i.effect, "source": i.source})
    return {**_who(m), "medicine": res.brand or medicine, "molecules": res.molecules,
            "result": "flags_found" if dup or inter else "none_recorded", "duplicates_with": dup, "interactions": inter, "note": MED_NOTE}


@health.tool(annotations=READ)
def get_lab_trends(user_id: str, analyte: str | None = None, member: str | None = None) -> dict[str, Any]:
    """Lab results over time for the user or a family member, converted to one unit per test with the
    conversion cited, flagged against the reference range, with direction of change. analyte: hba1c, ldl,
    fasting_glucose, vitamin_d, creatinine, tsh (or omit for all)."""
    m = _member(user_id, member, "labs")
    key = labs.analyte_from_text(analyte) if analyte and analyte not in labs.ANALYTES else analyte
    rows = store().q("SELECT * FROM lab_results WHERE member_id=?", (m["member_id"],))
    keys = [key] if key else sorted({r["analyte"] for r in rows})
    trends = [labs.trend(k, [r for r in rows if r["analyte"] == k]) for k in keys if any(r["analyte"] == k for r in rows)]
    out: dict[str, Any] = {**_who(m), "trends": trends}
    if not trends:
        out["note"] = f"No {labs.ANALYTES[key].name if key in labs.ANALYTES else 'lab'} results on record."
    return out


@health.tool(annotations=READ)
def get_visit_brief(user_id: str, member: str | None = None) -> dict[str, Any]:
    """A one-page brief for the next doctor visit: the appointment, current medicines, flags from the medicine
    database, lab values outside range or steadily rising, and the questions worth asking."""
    m = _member(user_id, member, "medications")
    first = m["name"].split()[0] if m["relation"] != "self" else "you"
    appt = store().q("SELECT doctor, specialty, time, mode FROM appointments WHERE member_id=? AND time >= ? ORDER BY time LIMIT 1",
                     (m["member_id"], date.today().isoformat()))
    active, dups, inter = _analyse([r for r in _med_rows(m["member_id"]) if r["status"] == "active"])
    try:
        trends = get_lab_trends(user_id, None, member)["trends"]
    except ToolError:
        trends = []  # consent covers medicines but not labs
    attention = sorted([t for t in trends if t.get("latest_flag") != "in_range" or t.get("steady_rise")], key=lambda t: t.get("latest_flag") == "in_range")
    qs = []
    gets = "You get" if first == "you" else f"{first} gets"
    for d_ in dups:
        qs.append(f"{gets} {d_['molecule']} from both {' and '.join(d_['products'])} ({', '.join(d_['prescribers'])}). Should both continue?")
    for i in inter:
        qs.append(f"Sahay's medicine database records an interaction between {i['products'][0]} and {i['products'][1]} ({i['severity']}: {i['effect']}). Is this combination intended?")
    for t in attention:
        why = "is above the reference range" if t["latest_flag"] == "high" else "is below the reference range" if t["latest_flag"] == "low" else "has risen on every report while staying in range"
        qs.append(f"{t['analyte']} {why} ({t.get('change') or str(t['points'][-1]['value']) + ' ' + t['unit']}). What should we watch?")
    return {**_who(m), "appointment": appt[0] if appt else None, "medications": [f"{a['name']} - {a['instructions']}" for a in active],
            "duplicates": dups, "interactions": inter, "labs_to_discuss": attention, "questions": qs[:6], "note": MED_NOTE}


@health.tool(annotations=WRITE)
def revoke_care_access(user_id: str, member: str, idempotency_key: str) -> dict[str, Any]:
    """Stop seeing a family member's records (revokes this account's consent for that member). Requires user confirmation."""
    s = store()
    if (prev := s.idem_get(idempotency_key)) is not None:
        return {**prev, "idempotent_replay": True}
    rows = s.q("SELECT * FROM members WHERE account_user_id=? AND relation != 'self'", (user_id,))
    want = catalog.RELATIONS.get(member.strip().lower(), member.strip().lower())
    hit = [r for r in rows if want in {r["relation"], r["name"].lower(), r["name"].split()[0].lower()}]
    if not hit:
        raise ToolError(f"No family member '{member}' on your account.")
    s.x("UPDATE consents SET revoked=1 WHERE member_id=? AND grantee_user_id=?", (hit[0]["member_id"], user_id))
    result = {"member": hit[0]["name"].split()[0], "status": "access_revoked", "effective": date.today().isoformat()}
    s.idem_put(idempotency_key, result)
    return result


SERVERS: dict[str, MCPServer] = {"orders": orders, "care_services": care, "claims": claims, "care_journeys": journeys, "health_records": health}


class BearerAuth:
    """ASGI middleware for a standalone MCP server. The hub injects `user_id`, so a server
    reachable without auth would let anyone on the network read any user's data by sending a
    different `user_id` (INC-011). Service-to-service auth closes that: only callers holding
    SAHAY_MCP_TOKEN (the hub) get through. Pure ASGI, so SSE streaming is untouched."""

    def __init__(self, app: Any, token: str) -> None:
        self.app, self.token = app, token.encode()

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            got = headers.get(b"authorization", b"")
            if not hmac.compare_digest(got, b"Bearer " + self.token):
                body = b'{"error":"unauthorized"}'
                await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run one Sahay MCP server standalone")
    ap.add_argument("server", choices=sorted(SERVERS))
    ap.add_argument("--http", type=int, help="serve Streamable HTTP on this port (default: stdio)")
    ap.add_argument("--host", default="127.0.0.1", help="bind address (0.0.0.0 in containers)")
    a = ap.parse_args()
    srv = SERVERS[a.server]
    if a.http:
        import uvicorn

        # stateless: any replica can serve any request behind a load balancer
        app: Any = srv.streamable_http_app(stateless_http=True, host=a.host)
        token = os.environ.get("SAHAY_MCP_TOKEN")
        if token:
            app = BearerAuth(app, token)
        elif a.host not in {"127.0.0.1", "localhost"}:
            raise SystemExit("Refusing to serve on a non-local address without SAHAY_MCP_TOKEN (user_id is caller-supplied).")
        uvicorn.run(app, host=a.host, port=a.http, log_level="warning")
    else:
        srv.run()


if __name__ == "__main__":
    main()
