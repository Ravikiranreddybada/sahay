"""Family health records: molecule resolution, cited unit conversion, consent scoping,
and the rule that a database miss is never reported as 'safe'."""

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from sahay.agent.verify import verify_draft
from sahay.health import catalog, labs
from sahay.mcp_servers import servers


def test_brand_resolves_to_molecules_including_fdc():
    assert catalog.resolve("Combiflam").molecules == ["ibuprofen", "paracetamol"]
    assert catalog.resolve("Ecosprin AV").molecules == ["aspirin", "atorvastatin"]
    assert catalog.resolve("Paracetamol 650mg x15").molecules == ["paracetamol"]
    unknown = catalog.resolve("Zxyprol 20")
    assert not unknown.resolved and unknown.molecules == []  # never guessed


def test_pan_card_is_not_a_medicine():
    assert catalog.find_mentions("please update my PAN card") == []


def test_unit_conversion_is_cited_and_keeps_reported_value():
    t = labs.trend("hba1c", [
        {"value": 6.6, "unit": "%", "lab": "A", "collected_on": "2025-01-01", "ref_low": 4.0, "ref_high": 5.6},
        {"value": 52, "unit": "mmol/mol", "lab": "B", "collected_on": "2025-06-01", "ref_low": 4.0, "ref_high": 5.6},
        {"value": 7.4, "unit": "%", "lab": "A", "collected_on": "2026-01-01", "ref_low": 4.0, "ref_high": 5.6},
    ])
    mid = t["points"][1]
    assert mid["value"] == 6.9 and mid["reported_as"] == "52 mmol/mol" and "IFCC" in mid["conversion"]
    assert t["direction"] == "rising" and t["steady_rise"] and t["latest_flag"] == "high"


def test_unknown_unit_raises_instead_of_guessing():
    with pytest.raises(ValueError):
        labs.to_canonical("hba1c", 6.0, "mg/dL")


async def test_duplicate_molecule_across_prescribers(agent):
    r = servers.get_medication_list("U1001", "father")
    dups = {d["molecule"]: d for d in r["duplicates"]}
    assert set(dups) == {"aspirin", "atorvastatin"} and len(dups["aspirin"]["prescribers"]) == 2
    assert r["interactions"][0]["severity"] == "major"  # major first
    assert "Telma 40" in r["stopped"]


async def test_consent_expired_and_missing_member(agent):
    with pytest.raises(ToolError, match="expired"):
        servers.get_lab_trends("U1003", None, "mother")
    with pytest.raises(ToolError, match="No family member"):
        servers.get_medication_list("U1002", "Venkat")  # another account's member, by name


async def test_revoked_consent_closes_access(agent):
    r = await agent.deps.hub.call("revoke_care_access", {"member": "father"}, user_id="U1001", thread_id="rv")
    assert r.result["status"] == "access_revoked"
    tr = await agent.deps.hub.call("get_medication_list", {"member": "father"}, user_id="U1001", thread_id="rv")
    assert tr.result is None and "consent" in tr.error


async def test_member_id_cannot_be_injected_through_args(agent):
    # the hub strips scope params; a member_id for another account still resolves inside *this* account only
    tr = await agent.deps.hub.call("get_medication_list", {"member": "M-3001"}, user_id="U1001", thread_id="x")
    assert tr.result is None and "No family member" in tr.error


def test_verifier_blocks_safety_verdict_and_ungrounded_interaction():
    v = verify_draft({"answer": "Yes, Brufen is safe with Ecosprin. [kb#a]", "citations": ["kb#a"]}, "", ["kb#a"], False)
    assert not v["ok"] and v["scorecard"]["no_safety_verdict"] is False
    v = verify_draft({"answer": "Brufen interacts with Ecosprin. [kb#a]", "citations": ["kb#a"]}, "", ["kb#a"], False)
    assert v["scorecard"]["interactions_from_database"] is False
    ok = verify_draft({"answer": "No interaction or duplicate is recorded in our database. [tool:check_medication_safety]"},
                      "", ["tool:check_medication_safety"], True)
    assert ok["ok"] and ok["score"] == 1.0


async def test_medicine_question_routes_to_database_check(agent):
    r = await agent.run_turn(user_id="U1001", thread_id="m", message="Can papa take Brufen with his medicines?")
    assert r["intent"] == "health_records" and [t["tool"] for t in r["tools"]] == ["check_medication_safety"]
    assert r["grounded"] and r["scorecard"]["no_safety_verdict"] and "is safe" not in r["answer"].lower()


async def test_carried_member_does_not_leak_into_self_question(agent):
    await agent.run_turn(user_id="U1001", thread_id="sw", message="What medicines is papa taking?")
    r = await agent.run_turn(user_id="U1001", thread_id="sw", message="and what are my medicines?")
    assert "Shelcal" in r["answer"] and "Ecosprin" not in r["answer"]
