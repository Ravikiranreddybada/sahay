"""HTTP-level tests: auth on every route (INC-016), WhatsApp webhook, reminders."""

import hashlib
import hmac
import json
import tempfile

import pytest
from fastapi.testclient import TestClient

from sahay import auth
from sahay.config import get_settings


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()
    mp.setenv("SAHAY_DATA_DIR", tempfile.mkdtemp(prefix="sahay-api-"))
    mp.setenv("SAHAY_REMINDER_INTERVAL_S", "0")
    mp.setenv("SAHAY_WHATSAPP_APP_SECRET", "test-app-secret")
    get_settings.cache_clear()
    from sahay.main import app

    with TestClient(app) as c:
        yield c
    mp.undo()
    get_settings.cache_clear()


_tokens: dict[str, dict[str, str]] = {}


def login(client, persona):
    if persona not in _tokens:  # dev-login is itself rate limited per IP
        r = client.post("/v1/auth/dev-login", json={"persona": persona})
        assert r.status_code == 200
        _tokens[persona] = {"Authorization": f"Bearer {r.json()['token']}"}
    return _tokens[persona]


def test_chat_requires_session(client):
    assert client.post("/v1/chat", json={"message": "hi"}).status_code == 401


def test_user_id_in_body_is_ignored(client):
    h = login(client, "U1001")
    r = client.post("/v1/chat", headers=h, json={"user_id": "U1002", "message": "Where is my order ORD-2077?", "thread_id": "a1"})
    assert r.status_code == 200 and "no order ord-2077 found" in r.json()["answer"].lower()  # ran as U1001


def test_tampered_or_expired_token_rejected(client):
    s = get_settings()
    good = auth.issue(s.auth_secret, "U1001", "member", 60)
    body, sig = good.split(".")
    forged = auth._b64(json.dumps({"sub": "U1002", "role": "member", "exp": 9999999999}).encode()) + "." + sig
    assert client.post("/v1/chat", headers={"Authorization": f"Bearer {forged}"}, json={"message": "hi"}).status_code == 401
    expired = auth.issue(s.auth_secret, "U1001", "member", -5)
    assert client.post("/v1/chat", headers={"Authorization": f"Bearer {expired}"}, json={"message": "hi"}).status_code == 401


def test_ops_endpoints_closed_to_members(client):
    h = login(client, "U1001")
    for path in ["/v1/traces", "/v1/handoffs", "/v1/kb", "/v1/channels/outbox", "/v1/reminders/due"]:
        assert client.get(path).status_code == 401, path
        assert client.get(path, headers=h).status_code == 403, path
    assert client.post("/v1/kb/reindex", headers=h).status_code == 403
    assert client.get("/v1/traces", headers=login(client, "ops")).status_code == 200


def test_member_sees_only_own_trace_and_thread(client):
    a, b = login(client, "U1001"), login(client, "U1002")
    r = client.post("/v1/chat", headers=a, json={"message": "Where is my order ORD-1042?", "thread_id": "own"}).json()
    assert client.get(f"/v1/traces/{r['trace_id']}", headers=a).status_code == 200
    assert client.get(f"/v1/traces/{r['trace_id']}", headers=b).status_code == 404
    assert client.get("/v1/threads/own", headers=b).json()["messages"] == []
    assert client.post("/v1/feedback", headers=b, json={"trace_id": r["trace_id"], "rating": -1}).status_code == 404


def test_streamed_confirm_flow(client):
    h = login(client, "U1001")
    r = client.post("/v1/chat", headers=h, json={"message": "Cancel order ORD-1043", "thread_id": "cf"}).json()
    assert r["status"] == "needs_confirmation"
    with client.stream("POST", "/v1/chat/confirm/stream", headers=h, json={"thread_id": "cf", "approved": True}) as s:
        events = [json.loads(line[6:]) for line in s.iter_lines() if line.startswith("data: ")]
    assert events[-1]["type"] == "final" and "cancelled" in events[-1]["result"]["answer"]
    assert client.post("/v1/chat/confirm", headers=h, json={"thread_id": "cf", "approved": True}).status_code == 409


def _signed(payload: dict) -> tuple[bytes, dict]:
    raw = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(b"test-app-secret", raw, hashlib.sha256).hexdigest()
    return raw, {"x-hub-signature-256": sig, "content-type": "application/json"}


def _wa(msg_id: str, phone: str, text: str | None = None, button: str | None = None) -> dict:
    m = {"id": msg_id, "from": phone, "type": "text", "text": {"body": text}} if text else \
        {"id": msg_id, "from": phone, "type": "interactive", "interactive": {"type": "button_reply", "button_reply": {"id": button, "title": "x"}}}
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": [m]}}]}]}


def test_whatsapp_webhook_signature_and_flow(client):
    ops = login(client, "ops")
    raw, _ = _signed(_wa("wamid.1", "919800000001", "Where is my order ORD-1042?"))
    assert client.post("/v1/channels/whatsapp/webhook", content=raw, headers={"x-hub-signature-256": "sha256=bad"}).status_code == 401

    raw, hdr = _signed(_wa("wamid.2", "919800000001", "Cancel order ORD-1043"))
    assert client.post("/v1/channels/whatsapp/webhook", content=raw, headers=hdr).status_code == 200
    client.post("/v1/channels/whatsapp/webhook", content=raw, headers=hdr)  # Meta retry: same message id
    out = client.get("/v1/channels/outbox", headers=ops).json()
    confirms = [o for o in out if o["recipient"] == "919800000001" and o["kind"] == "confirm"]
    assert len(confirms) == 1  # deduped

    raw, hdr = _signed(_wa("wamid.3", "919800000001", button="confirm_yes"))
    client.post("/v1/channels/whatsapp/webhook", content=raw, headers=hdr)
    reply = client.get("/v1/channels/outbox", headers=ops).json()[0]
    assert reply["kind"] == "reply" and "cancelled" in reply["body"] and "[tool:" not in reply["body"]


def test_whatsapp_unknown_number_gets_no_agent(client):
    r = client.post("/v1/channels/whatsapp/simulate", headers=login(client, "ops"), json={"phone": "911111111111", "text": "where is ORD-1042"})
    assert r.json()["replies"][0]["kind"] == "unlinked"


def test_whatsapp_verify_handshake(client):
    s = get_settings()
    r = client.get("/v1/channels/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": s.whatsapp_verify_token, "hub.challenge": "42"})
    assert r.text == "42"
    assert client.get("/v1/channels/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "x"}).status_code == 403


def test_reminder_sweep_is_exactly_once(client):
    ops = login(client, "ops")
    due = client.get("/v1/reminders/due", headers=ops).json()
    assert any(d["child"] == "Zoya" and d["offset"] == -1 for d in due)  # seeded opt-in, overdue doses
    first = client.post("/v1/reminders/run", headers=ops).json()
    assert first["messages"] >= 1 and first["doses"] == 2  # MMR + Typhoid grouped into one message
    again = client.post("/v1/reminders/run", headers=ops).json()
    assert again["messages"] == 0
    body = client.get("/v1/channels/outbox", headers=ops).json()[0]["body"]
    assert "Zoya" in body and "pediatrician" in body


def test_handoff_resolve(client):
    h, ops = login(client, "U1003"), login(client, "ops")
    r = client.post("/v1/chat", headers=h, json={"message": "I want to talk to a human", "thread_id": "hf"}).json()
    t = r["handoff_ticket"]
    assert client.post(f"/v1/handoffs/{t}/resolve", headers=ops, json={"note": "called back"}).status_code == 200
    assert client.post(f"/v1/handoffs/{t}/resolve", headers=ops, json={}).status_code == 404
