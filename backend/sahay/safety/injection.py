"""Prompt-injection defence in two places, driven by one versioned rule pack
(`rules/threat_rules.yaml`, ATR-style: stable ids, OWASP category, executable examples):

1. User input: summed rule weights. High score -> the turn is still answered, but tool
   access is restricted to read-only tools and the event is traced with the rule ids.
   (Blocking outright frustrates real users who paste odd text; restricting capability is
   the safer trade.)
2. Tool / retrieval output (indirect injection): content coming back from MCP servers or the
   KB is wrapped in data delimiters, and lines that match a `data` rule are replaced before
   the model sees them. A doctor's note saying "ignore previous instructions" is data, not a
   command.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

RULES_FILE = Path(__file__).parent / "rules" / "threat_rules.yaml"


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    owasp: str
    surfaces: tuple[str, ...]
    weight: float
    patterns: tuple[re.Pattern[str], ...]
    examples: dict[str, list[str]]


@functools.cache
def load_rules(path: Path = RULES_FILE) -> tuple[str, tuple[Rule, ...]]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules = []
    for r in doc["rules"]:
        rules.append(Rule(
            id=r["id"], title=r["title"], owasp=r["owasp"], surfaces=tuple(r["surfaces"]), weight=float(r["weight"]),
            patterns=tuple(re.compile(p, re.I | re.M) for p in r["patterns"]), examples=r.get("examples", {}),
        ))
    ids = [r.id for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate threat rule id")
    return str(doc["version"]), tuple(rules)


def scan(text: str, surface: str = "user") -> list[Rule]:
    return [r for r in load_rules()[1] if surface in r.surfaces and any(p.search(text) for p in r.patterns)]


def injection_score(text: str) -> tuple[float, list[str]]:
    hits = scan(text, "user")
    return min(1.0, round(sum(r.weight for r in hits), 2)), [r.id for r in hits]


def rules_catalog() -> dict[str, Any]:
    version, rules = load_rules()
    return {"version": version, "rules": [{"id": r.id, "title": r.title, "owasp": r.owasp, "surfaces": list(r.surfaces),
                                           "weight": r.weight, "examples": r.examples} for r in rules]}


def sanitize_untrusted(text: str, source: str) -> tuple[str, list[str]]:
    """Returns the wrapped text and the ids of the data rules that fired."""
    fired: set[str] = set()
    data_rules = [r for r in load_rules()[1] if "data" in r.surfaces and r.weight >= 0.4]
    out = []
    for line in text.split("\n"):
        hit = [r for r in data_rules if any(p.search(line) for p in r.patterns)]
        if hit:
            fired.update(r.id for r in hit)
            out.append(f"[removed: instruction-like text in data ({', '.join(sorted(r.id for r in hit))})]")
        else:
            out.append(line)
    return f'<data source="{source}">\n' + "\n".join(out) + "\n</data>", sorted(fired)
