"""Typed contracts between graph nodes. Enums + bounds make a bad model output a
validation error (caught, repaired, traced) instead of a silent downstream bug."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Intent = Literal[
    "order_status", "refund_cancel", "lab_booking", "consult_booking", "claim_status",
    "vaccination_journey", "surgery_journey", "health_records", "policy_faq", "medical_advice", "human_agent", "chitchat",
]


class Entities(BaseModel):
    order_id: str | None = Field(None, pattern=r"^ORD-\d{4,8}$")
    claim_id: str | None = Field(None, pattern=r"^CLM-\d{4,8}$")
    booking_id: str | None = Field(None, pattern=r"^(LAB|BKG)-\d{4,8}$")
    slot_id: str | None = Field(None, pattern=r"^S-\d{1,5}$")
    city: str | None = None
    specialty: str | None = None
    procedure: str | None = None
    child_name: str | None = None
    pincode: str | None = None
    member: str | None = Field(None, description="whose records: 'self', a relation (father, mother) or a family member's first name")
    medicine: str | None = Field(None, description="a medicine brand or molecule exactly as written, e.g. 'Brufen', 'Combiflam'")
    analyte: str | None = Field(None, description="a lab test: hba1c, ldl, fasting_glucose, vitamin_d, creatinine, tsh")

    @field_validator("order_id", "claim_id", "booking_id", "slot_id", mode="before")
    @classmethod
    def _norm_id(cls, v: object) -> object:
        # models write "ord1043", "Ord-1043", "ORD 1043"; normalise before the pattern check
        # instead of burning a repair round-trip on a cosmetic difference
        if isinstance(v, str) and (m := re.fullmatch(r"\s*([A-Za-z]+)[\s-]?(\d+)\s*", v)):
            return f"{m.group(1).upper()}-{m.group(2)}"
        return v


class IntentResult(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0, le=1)
    entities: Entities = Field(default_factory=Entities)
    needs_retrieval: bool = True
    needs_live_data: bool = Field(True, description="True if the answer depends on this user's own records (order, claim, report, journey) or an action; False for how-it-works / policy questions.")
    search_query: str = Field(min_length=1, max_length=400)


class AnswerOut(BaseModel):
    answer: str = Field(min_length=1, max_length=1500)
    citations: list[str] = Field(default_factory=list, max_length=12)
    abstained: bool = False
    follow_up: str | None = None
