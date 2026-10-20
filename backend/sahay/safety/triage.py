"""Red-flag triage. Runs first, deterministically, before any LLM call.

This is deliberately rule-based: an emergency path must not depend on a model's mood, a
provider outage, or a cache. Recall matters far more than precision here (a false alarm
costs one extra line of text; a miss can cost a life), and the eval suite gates on 100%
recall for the emergency set.

Coverage: English, romanised Hindi ("Hinglish", how most Indian users type) and Devanagari.
INC-009: "my baby is not breathing", "I want to die" and "seene mein dard" all missed the
English-only list, and "not sure but I have chest pain" was suppressed by the negation rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RED_FLAGS: dict[str, list[str]] = {
    "cardiac": [
        r"chest (pain|tightness|pressure)", r"heart attack", r"pain (spreading|radiating|going) (to|into|down) (my |his |her )?(left )?arm",
        r"(seene|sine|chhati|chati) (mein|me|main) (dard|jalan|bhari)", r"dil ka daura", r"सीने में दर्द", r"दिल का दौरा",
    ],
    "breathing": [
        r"(can'?t|cannot|unable to|difficulty|trouble|struggling to|hard to) breath", r"\bnot breathing\b", r"stopped breathing",
        r"breathless(ness)?", r"short(ness)? of breath", r"choking", r"turning (blue|purple)", r"lips? (are |is )?(turning )?blue",
        r"saa?ns (nahi|nahin|nai) (aa|le)", r"saa?ns (lene )?mein (dikkat|taklif|problem)", r"दम घुट", r"सांस (नहीं|लेने में)",
    ],
    "stroke": [r"face (is )?droop", r"slurred speech", r"(sudden )?numb(ness)? (on )?one side", r"\bstroke\b(?! of)", r"can'?t (move|feel) (one|his|her|my) (side|arm|leg)", r"लकवा", r"\blakwa\b"],
    "bleeding": [
        r"(heavy|severe|uncontrolled|won'?t stop|not stopping|lot of) bleed", r"vomiting blood", r"blood in (vomit|stool)", r"coughing (up )?blood",
        r"(bahut|zyada|jyada) (khoon|khun) (nikal|beh|aa)", r"खून (बह|निकल)",
    ],
    "neuro": [
        r"unconscious", r"passed out", r"fainted", r"seizure", r"\bfits\b", r"convulsion", r"(not|isn'?t|is not) (responding|waking up)", r"unresponsive",
        r"collapsed", r"(behosh|behoshi)", r"बेहोश", r"दौरा (पड़|पड)",
    ],
    "self_harm": [
        r"(kill|end|hurt|harm) (myself|my ?self|my life)", r"suicid", r"(don'?t|do not) want to (live|be alive)", r"want to die", r"wish i (was|were) dead",
        r"no (reason|point) (to|in) (live|living)", r"better off dead", r"self[- ]harm", r"overdos",
        r"(marna|mar jana) (chahta|chahti)", r"(khud ?khushi|aatmahatya)", r"जीना नहीं", r"आत्महत्या", r"मरना चाहत",
    ],
    "child_vaccine_reaction": [
        r"(fever|temperature|bukhar).{0,25}(10[4-9]|105)", r"(10[4-9]|105)\s*(°|deg|degree)?\s*f?\s*(fever|temperature|bukhar)",
        r"swelling of (the )?face", r"face (is )?swell", r"crying (non[- ]?stop |continuously )?(for )?(more than )?3 hours",
    ],
    "allergy": [r"anaphyla", r"throat (is )?(closing|swelling)", r"lips? (are |is )?swell", r"tongue (is )?swell", r"swollen (lips|tongue|throat)"],
    "poisoning": [r"(swallowed|drank|ate|took) (a lot of |too many |all )(the |my |his |her )?(pills|tablets|medicine)", r"(drank|swallowed|ate|took|consumed|kha li?y?a?)\b.{0,20}\b(poison|bleach|pesticide|phenyl|acid|rat kill|zeher)", r"zeher (kha|pi)", r"(ज़हर|जहर) (खा|पी)"],
}
_COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in RED_FLAGS.items()}
# A negation only cancels a red flag when it directly governs it: "no chest pain", "without
# chest pain", "don't have chest pain". It must not reach across a clause: "not sure but I
# have chest pain" is an emergency (INC-009), so the window stops at but/and/punctuation.
_NEGATION = re.compile(r"\b(no|not|without|never|denies|don'?t have|doesn'?t have|didn'?t have|nahi|nahin)\b(\s+\w+){0,2}\s*$", re.I)
_CLAUSE_BREAK = re.compile(r"(\bbut\b|\band\b|\bnow\b|[,.;!?])", re.I)
# categories where we never trust a negation: the cost of a miss is too high
_NO_NEGATION = {"self_harm", "poisoning"}


@dataclass
class TriageResult:
    emergency: bool
    category: str | None = None
    matched: str | None = None


def _negated(text: str, start: int) -> bool:
    prefix = text[max(0, start - 40): start]
    parts = _CLAUSE_BREAK.split(prefix)
    return bool(_NEGATION.search(parts[-1] if parts else prefix))


def triage(text: str) -> TriageResult:
    for cat, pats in _COMPILED.items():
        for p in pats:
            for m in p.finditer(text):
                if cat not in _NO_NEGATION and _negated(text, m.start()):
                    continue
                return TriageResult(True, cat, m.group(0))
    return TriageResult(False)


EMERGENCY_MESSAGES = {
    "self_harm": (
        "I'm really sorry you're feeling this way. You don't have to go through this alone. "
        "Please call the Tele-MANAS helpline at 14416 (free, 24x7) or 112 right now, and reach out to someone you trust. "
        "I'm connecting you to a human care agent. "
        "(Tele-MANAS 14416 par abhi call karein — Hindi mein bhi madad milti hai.)"
    ),
    "default": (
        "This could be a medical emergency. Please call 112 or go to the nearest emergency room right now. "
        "Don't wait for an online consultation. I'm alerting a human care agent to help you. "
        "(Yeh emergency ho sakti hai — abhi 112 par call karein ya nazdeeki emergency room jaayein.)"
    ),
}
