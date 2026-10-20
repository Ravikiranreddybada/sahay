"""Embedders.

`HashingEmbedder` is a dependency-free, deterministic embedder (word uni/bi-grams + char
trigrams, signed feature hashing, L2-normalised) with a domain synonym layer. It is the
offline/CI default. In production swap in a hosted model (Voyage / Cohere / OpenAI / bge-m3)
by implementing `Embedder` — the index records `embedder.id` per vector, so a model change
forces a full re-embed instead of silently mixing two vector spaces (a classic source of
"stale embeddings" that look fine but retrieve garbage).
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

import numpy as np

SYNONYMS: dict[str, str] = {
    "jab": "vaccine", "shot": "vaccine", "shots": "vaccine", "immunisation": "vaccine", "immunization": "vaccine",
    "vaccination": "vaccine", "vaccines": "vaccine", "operation": "surgery", "op": "surgery",
    "meds": "medicine", "medicines": "medicine", "tablets": "medicine", "pharmacy": "medicine",
    "money": "refund", "reimburse": "reimbursement", "cashback": "refund",
    "doc": "doctor", "physician": "doctor", "consultation": "consult", "teleconsult": "consult",
    "bloodwork": "lab", "pathology": "lab", "test": "lab", "tests": "lab",
    "insurer": "insurance", "tpa": "insurance", "mediclaim": "insurance",
    "kid": "child", "baby": "child", "infant": "child", "son": "child", "daughter": "child",
    "cancelled": "cancel", "cancellation": "cancel", "canceled": "cancel",
}
_WORD = re.compile(r"[a-z0-9]+")


def stem(w: str) -> str:
    """Tiny, *consistent* suffix stripper: the same rule must map query and document forms
    to one stem (take/takes/taking -> tak, change/changes -> chang). INC-007 was a version
    of this that stripped "es" from "takes" but left "take" alone, so they never matched."""
    if len(w) <= 3 or not w.isalpha():
        return w
    if w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith("sses"):
        w = w[:-2]
    elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        w = w[:-1]
    for suf in ("ing", "ed"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            if len(w) > 2 and w[-1] == w[-2] and w[-1] not in "lsz":
                w = w[:-1]  # stopped -> stop
            break
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]
    return w


def normalize_terms(text: str) -> list[str]:
    out = []
    for w in _WORD.findall(text.lower()):
        w = SYNONYMS.get(w, w)
        out.append(SYNONYMS.get(stem(w), stem(w)))
    return out


class Embedder(Protocol):
    id: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbedder:
    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim
        self.id = f"hashing-v2-{dim}"

    def _features(self, text: str) -> list[tuple[str, float]]:
        words = normalize_terms(text)
        feats: list[tuple[str, float]] = [(f"w:{w}", 1.0) for w in words]
        feats += [(f"b:{a}_{b}", 1.3) for a, b in zip(words, words[1:])]
        for w in words:
            if len(w) > 4:
                padded = f"#{w}#"
                feats += [(f"c:{padded[i:i+3]}", 0.25) for i in range(len(padded) - 2)]
        return feats

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, t in enumerate(texts):
            for feat, w in self._features(t):
                h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "little")
                out[row, h % self.dim] += w if (h >> 63) & 1 else -w
            n = np.linalg.norm(out[row])
            if n:
                out[row] /= n
        return out
