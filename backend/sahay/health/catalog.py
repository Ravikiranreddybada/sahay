"""Medicine catalog and interaction table. The database decides; the model only explains.

Indian prescriptions name brands, not molecules. One molecule reaches a patient through
several products from several prescribers ("Atorva 10" from the cardiologist, "Ecosprin-AV"
from the GP), and fixed-dose combinations hide molecules inside them (Combiflam is
ibuprofen + paracetamol). So every medicine is resolved to molecules first, and the
duplicate / interaction checks run on molecules, deterministically, against this table.

Ideas from shivama205/parchi (brand -> molecule incl. FDCs, duplicate therapy) and
rxcheck ("the database decides whether an interaction exists; the LLM only explains").

The interaction rows are a small curated demo set of well-documented pairs, each with its
source. It is NOT a clinical reference. An empty result means "none recorded here", never
"safe": the tool output and the verifier both enforce that wording.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# brand (lower-case key) -> (display name, molecules, strength)
BRANDS: dict[str, tuple[str, list[str], str]] = {
    "ecosprin 75": ("Ecosprin 75", ["aspirin"], "75 mg"),
    "ecosprin-av 75": ("Ecosprin-AV 75", ["aspirin", "atorvastatin"], "75 mg / 10 mg"),
    "atorva 10": ("Atorva 10", ["atorvastatin"], "10 mg"),
    "clopilet 75": ("Clopilet 75", ["clopidogrel"], "75 mg"),
    "omez 20": ("Omez 20", ["omeprazole"], "20 mg"),
    "pan 40": ("Pan 40", ["pantoprazole"], "40 mg"),
    "pan-d": ("Pan-D", ["pantoprazole", "domperidone"], "40 mg / 30 mg"),
    "glycomet 500": ("Glycomet 500", ["metformin"], "500 mg"),
    "telma 40": ("Telma 40", ["telmisartan"], "40 mg"),
    "thyronorm 50": ("Thyronorm 50", ["levothyroxine"], "50 mcg"),
    "dolo 650": ("Dolo 650", ["paracetamol"], "650 mg"),
    "crocin 650": ("Crocin 650", ["paracetamol"], "650 mg"),
    "combiflam": ("Combiflam", ["ibuprofen", "paracetamol"], "400 mg / 325 mg"),
    "brufen 400": ("Brufen 400", ["ibuprofen"], "400 mg"),
    "claribid 500": ("Claribid 500", ["clarithromycin"], "500 mg"),
    "cetzine 10": ("Cetzine 10", ["cetirizine"], "10 mg"),
    "shelcal 500": ("Shelcal 500", ["calcium carbonate", "cholecalciferol"], "500 mg / 250 IU"),
}
# Short names people actually type ("Brufen", "Dolo", "Ecosprin AV").
ALIASES: dict[str, str] = {
    "ecosprin": "ecosprin 75", "ecosprin av": "ecosprin-av 75", "ecosprin-av": "ecosprin-av 75", "atorva": "atorva 10",
    # no bare "pan": it is also the PAN card every Indian user mentions
    "clopilet": "clopilet 75", "omez": "omez 20", "pan d": "pan-d", "glycomet": "glycomet 500",
    "telma": "telma 40", "thyronorm": "thyronorm 50", "dolo": "dolo 650", "crocin": "crocin 650", "brufen": "brufen 400",
    "claribid": "claribid 500", "cetzine": "cetzine 10", "shelcal": "shelcal 500",
}
MOLECULES = sorted({m for _, ms, _ in BRANDS.values() for m in ms} | {"warfarin"})
MOLECULE_ALIASES = {"acetaminophen": "paracetamol", "asa": "aspirin"}


@dataclass(frozen=True)
class Interaction:
    a: str
    b: str
    severity: str  # major | moderate
    effect: str
    source: str


_PAIRS = [
    Interaction("clopidogrel", "omeprazole", "major",
                "omeprazole can reduce how well clopidogrel prevents clots (CYP2C19 inhibition)",
                "US FDA clopidogrel label, boxed warning section"),
    Interaction("aspirin", "clopidogrel", "moderate",
                "taking both raises bleeding risk; doctors often prescribe this pair on purpose after a heart event",
                "ACC/AHA dual antiplatelet therapy guideline"),
    Interaction("aspirin", "ibuprofen", "moderate",
                "ibuprofen can block low-dose aspirin's heart-protective effect and adds stomach-bleeding risk",
                "US FDA 2006 science paper on ibuprofen and low-dose aspirin"),
    Interaction("clopidogrel", "ibuprofen", "moderate",
                "a painkiller of the NSAID type with an antiplatelet medicine raises bleeding risk",
                "US FDA clopidogrel label, drug interactions section"),
    Interaction("atorvastatin", "clarithromycin", "major",
                "clarithromycin raises atorvastatin levels and the risk of muscle damage (CYP3A4)",
                "US FDA atorvastatin label, drug interactions section"),
    Interaction("ibuprofen", "warfarin", "major",
                "raises bleeding risk", "US FDA warfarin label"),
    Interaction("aspirin", "warfarin", "major",
                "raises bleeding risk", "US FDA warfarin label"),
]
INTERACTIONS: dict[tuple[str, str], Interaction] = {tuple(sorted((i.a, i.b))): i for i in _PAIRS}  # type: ignore[misc]


@dataclass
class Resolved:
    query: str
    brand: str | None
    molecules: list[str]
    strength: str | None
    resolved: bool


def resolve(name: str) -> Resolved:
    """Brand or molecule name -> molecules. Unknown names stay unresolved (never guessed)."""
    key = re.sub(r"\s+", " ", name.strip().lower())
    key = re.sub(r"\b(tablets?|tabs?|capsules?|syrup)\b", "", key).strip()
    key = re.sub(r"\s*x\s*\d+$", "", key).strip()  # order lines: "Paracetamol 650mg x15"
    key = ALIASES.get(key, key)
    if key in BRANDS:
        disp, mols, strength = BRANDS[key]
        return Resolved(name, disp, list(mols), strength, True)
    bare = re.sub(r"\s*\d+(\.\d+)?\s*(mg|mcg|iu|g|ml)\b.*$", "", key).strip()
    bare = MOLECULE_ALIASES.get(bare, bare)
    if bare in MOLECULES:
        return Resolved(name, None, [bare], None, True)
    if bare in ALIASES:
        return resolve(ALIASES[bare])
    return Resolved(name, None, [], None, False)


def find_mentions(text: str) -> list[str]:
    """Catalog brands / molecules mentioned in free text, longest match first."""
    low = text.lower()
    names = sorted(set(BRANDS) | set(ALIASES) | set(MOLECULES) | set(MOLECULE_ALIASES), key=len, reverse=True)
    found: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for n in names:
        for m in re.finditer(rf"(?<![a-z]){re.escape(n)}(?![a-z])", low):
            if any(s <= m.start() < e for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), text[m.start():m.end()]))
    return [t for _, t in sorted(found)]


def interactions_between(molecules: list[str]) -> list[Interaction]:
    ms = sorted(set(molecules))
    out = []
    for i, a in enumerate(ms):
        for b in ms[i + 1:]:
            if (a, b) in INTERACTIONS:
                out.append(INTERACTIONS[(a, b)])
    return out


RELATIONS: dict[str, str] = {
    "papa": "father", "dad": "father", "father": "father", "pitaji": "father", "appa": "father", "nanna": "father", "abbu": "father",
    "mom": "mother", "mother": "mother", "mummy": "mother", "maa": "mother", "amma": "mother", "ammi": "mother",
    "me": "self", "myself": "self", "my own": "self",
}
RELATION_RE = re.compile(r"\b(?:my\s+)?(" + "|".join(k for k in RELATIONS if k not in {"me", "myself", "my own"}) + r")(?:'s|’s|\b)", re.I)
