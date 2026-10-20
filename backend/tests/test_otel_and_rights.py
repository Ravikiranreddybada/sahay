"""OTLP export shape + privacy allow-list; DPDP data-rights endpoints; new routes are authed."""

import json

from sahay.obs.otel import to_otlp
from tests.test_api import client, login  # noqa: F401 - module fixture reuse


async def test_otlp_uses_genai_conventions_and_drops_payloads(agent):
    r = await agent.run_turn(user_id="U1001", thread_id="o", message="What medicines is papa taking?")
    otlp = to_otlp(agent.deps.traces.get(r["trace_id"]))
    spans = otlp["resourceSpans"][0]["scopeSpans"][0]["spans"]
    keys = {a["key"] for s in spans for a in s["attributes"]}
    assert spans[0]["name"] == "invoke_agent sahay" and "gen_ai.conversation.id" in keys
    assert any(s["name"] == "execute_tool get_medication_list" for s in spans)
    assert any(s["name"].startswith("chat ") for s in spans) and "gen_ai.usage.input_tokens" in keys
    blob = json.dumps(otlp).lower()
    assert "ecosprin" not in blob and "venkat" not in blob  # tool results never exported
    assert all(s["parentSpanId"] for s in spans[1:])


def test_new_routes_require_auth(client):  # noqa: F811
    for path in ["/v1/health/members", "/v1/health/overview", "/v1/me/data"]:
        assert client.get(path).status_code == 401, path
    assert client.delete("/v1/me/history").status_code == 401
    assert client.get("/v1/safety/rules", headers=login(client, "U1001")).status_code == 403
    rules = client.get("/v1/safety/rules", headers=login(client, "ops")).json()
    assert rules["rules"][0]["id"] == "SAHAY-TR-0001"


def test_health_overview_respects_consent(client):  # noqa: F811
    ok = client.get("/v1/health/overview", params={"member": "father"}, headers=login(client, "U1001")).json()
    assert ok["medications"]["member"] == "Venkat" and ok["brief"]["questions"]
    denied = client.get("/v1/health/overview", params={"member": "mother"}, headers=login(client, "U1003")).json()
    assert "expired" in denied["medications"]["error"] and "medications" not in denied["medications"]
    other = client.get("/v1/health/overview", params={"member": "Venkat"}, headers=login(client, "U1002")).json()
    assert "No family member" in other["labs"]["error"]


def test_data_export_and_erasure(client):  # noqa: F811
    h = login(client, "U1002")
    r = client.post("/v1/chat", headers=h, json={"message": "Where is my order ORD-2077?", "thread_id": "erase-me"}).json()
    data = client.get("/v1/me/data", headers=h).json()
    assert data["user_id"] == "U1002" and "erase-me" in data["conversation_threads"]
    assert all(o["order_id"] != "ORD-1042" for o in data["orders"])  # only own records
    gone = client.delete("/v1/me/history", headers=h).json()
    assert gone["traces_erased"] >= 1 and gone["threads_erased"] >= 1
    assert client.get(f"/v1/traces/{r['trace_id']}", headers=h).status_code == 404
    assert client.get("/v1/threads/erase-me", headers=h).json()["messages"] == []
