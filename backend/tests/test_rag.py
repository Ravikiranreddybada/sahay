from pathlib import Path

import pytest

from sahay.rag.chunker import chunk_document
from sahay.rag.embed import stem
from sahay.rag.index import HybridIndex

KB = Path(__file__).resolve().parent.parent / "data" / "kb"


@pytest.fixture(scope="module")
def index():
    ix = HybridIndex()
    ix.load_dir(KB)
    return ix


@pytest.mark.parametrize("query,intent,expected", [
    ("how long does refund take for cancelled medicine order", "refund_cancel", "refund_policy#medicine-orders"),
    ("my kid has fever after jab", "vaccination_journey", "vaccination_guide#after-the-vaccine"),
    ("do I need to fast for HbA1c", "lab_booking", "lab_tests#fasting-instructions"),
    ("what documents for reimbursement", "claim_status", "insurance_claims#reimbursement-claims"),
    ("family members in care plus", "policy_faq", "membership_plans#family-cover"),  # INC-001
    ("can I cancel lab test", "refund_cancel", "refund_policy#lab-tests"),
])
def test_top1(index, query, intent, expected):
    assert index.search(query, top_k=3, intent=intent)[0].chunk.id == expected


def test_superseded_version_never_indexed(index):
    texts = " ".join(c.text for c in index.chunks if c.doc_id == "refund_policy")
    assert "10-14" not in texts and "5-7 working days" in texts
    assert {c.doc_version for c in index.chunks if c.doc_id == "refund_policy"} == {"2"}


def test_stale_doc_flagged(index):
    assert all(c.is_stale() for c in index.chunks if c.doc_id == "membership_plans")


def test_lists_not_split():
    raw = (KB / "insurance_claims.md").read_text()
    reimb = [c for c in chunk_document("insurance_claims", raw) if "reimbursement" in c.id]
    assert any("Discharge summary" in c.text and "Cancelled cheque" in c.text for c in reimb)


def test_incremental_reembed(index):
    stats = index.build(list(index.chunks))
    assert stats["re_embedded"] == 0


@pytest.mark.parametrize("a,b", [("take", "takes"), ("change", "changes"), ("fasting", "fast"), ("refunds", "refund")])
def test_stemmer_consistent(a, b):  # INC-007
    assert stem(a) == stem(b)
