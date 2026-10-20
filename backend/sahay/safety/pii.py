"""PII redaction for Indian identifiers, applied *before* text reaches the LLM, logs or traces.

Health data is sensitive personal data under India's DPDP Act 2023. The model never needs a
user's Aadhaar or card number to answer a support question, so we replace them with typed
placeholders (<AADHAAR_1>) and keep the mapping only in request memory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


# Verhoeff tables for Aadhaar checksum (cuts false positives on random 12-digit numbers).
_D = [[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],
      [5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]]
_P = [[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],
      [4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]]


def _verhoeff_ok(num: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


PATTERNS: list[tuple[str, re.Pattern[str], object]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), None),
    ("AADHAAR", re.compile(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b"), lambda m: _verhoeff_ok(re.sub(r"\D", "", m))),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b"), lambda m: _luhn_ok(re.sub(r"\D", "", m))),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), None),
    ("PHONE", re.compile(r"(?<!\d)(?:\+91[ -]?|0)?[6-9]\d{9}(?!\d)"), None),
    ("UPI", re.compile(r"\b[\w.-]{2,}@(?:ok\w+|ybl|paytm|upi|apl|ibl|axl)\b"), None),
]


@dataclass
class Redaction:
    text: str
    found: dict[str, int] = field(default_factory=dict)
    mapping: dict[str, str] = field(default_factory=dict)


def redact(text: str) -> Redaction:
    out = Redaction(text=text)
    counters: dict[str, int] = {}
    for label, pat, check in PATTERNS:
        def sub(m: re.Match[str]) -> str:
            raw = m.group(0)
            if check is not None and not check(raw):  # type: ignore[operator]
                return raw
            counters[label] = counters.get(label, 0) + 1
            token = f"<{label}_{counters[label]}>"
            out.mapping[token] = raw
            return token

        out.text = pat.sub(sub, out.text)
    out.found = counters
    return out
