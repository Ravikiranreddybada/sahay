"""Lab values from different labs on one axis.

A value drifting over years, measured at different labs in different units, looks
borderline on every single report and alarming only in sequence (shivama205/parchi).
So each analyte has one canonical unit; every conversion is a fixed, cited factor, and
the converted point keeps the value and unit the report printed.

This module states facts (value, range, direction). It never interprets them clinically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Analyte:
    key: str
    name: str
    unit: str  # canonical
    conversions: dict[str, tuple[Callable[[float], float], str]]  # unit -> (fn to canonical, cited factor)


ANALYTES: dict[str, Analyte] = {a.key: a for a in [
    Analyte("hba1c", "HbA1c", "%", {
        "mmol/mol": (lambda v: 0.09148 * v + 2.152, "NGSP % = 0.09148 x IFCC mmol/mol + 2.152 (IFCC-NGSP master equation)"),
    }),
    Analyte("ldl", "LDL cholesterol", "mg/dL", {
        "mmol/l": (lambda v: v * 38.67, "mg/dL = mmol/L x 38.67 (cholesterol molar mass)"),
    }),
    Analyte("fasting_glucose", "Fasting blood sugar", "mg/dL", {
        "mmol/l": (lambda v: v * 18.016, "mg/dL = mmol/L x 18.016 (glucose molar mass)"),
    }),
    Analyte("vitamin_d", "Vitamin D (25-OH)", "ng/mL", {
        "nmol/l": (lambda v: v * 0.4006, "ng/mL = nmol/L x 0.4006"),
    }),
    Analyte("creatinine", "Serum creatinine", "mg/dL", {
        "umol/l": (lambda v: v / 88.42, "mg/dL = µmol/L / 88.42"),
        "µmol/l": (lambda v: v / 88.42, "mg/dL = µmol/L / 88.42"),
    }),
    Analyte("tsh", "TSH", "mIU/L", {"uiu/ml": (lambda v: v, "1 µIU/mL = 1 mIU/L")}),
]}
ANALYTE_WORDS: dict[str, list[str]] = {
    "hba1c": ["hba1c", "a1c", "glycated", "sugar average"], "ldl": ["ldl", "cholesterol", "lipid"],
    "fasting_glucose": ["fasting sugar", "fasting blood sugar", "fbs", "glucose"], "vitamin_d": ["vitamin d", "vit d", "vitd"],
    "creatinine": ["creatinine", "kidney"], "tsh": ["tsh", "thyroid"],
}


def analyte_from_text(text: str) -> str | None:
    low = text.lower()
    for key, words in ANALYTE_WORDS.items():
        if any(w in low for w in words):
            return key
    return None


def to_canonical(analyte: str, value: float, unit: str) -> tuple[float, str | None]:
    a = ANALYTES[analyte]
    u = unit.strip().lower()
    if u == a.unit.lower():
        return value, None
    if u not in a.conversions:
        raise ValueError(f"no cited conversion from {unit} to {a.unit} for {a.name}")
    fn, cite = a.conversions[u]
    return round(fn(value), 1), cite


def trend(analyte: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """rows: value, unit, lab, collected_on, ref_low, ref_high (range in canonical unit)."""
    a = ANALYTES[analyte]
    pts = []
    for r in sorted(rows, key=lambda r: r["collected_on"]):
        v, cite = to_canonical(analyte, float(r["value"]), r["unit"])
        lo, hi = r.get("ref_low"), r.get("ref_high")
        flag = "high" if hi is not None and v > hi else "low" if lo is not None and v < lo else "in_range"
        p: dict[str, Any] = {"date": r["collected_on"], "value": v, "unit": a.unit, "lab": r["lab"], "flag": flag}
        if cite:
            p["reported_as"] = f"{r['value']:g} {r['unit']}"
            p["conversion"] = cite
        pts.append(p)
    out: dict[str, Any] = {"analyte": a.name, "unit": a.unit, "points": pts,
                           "reference_range": _range(rows[-1] if rows else {}, a.unit)}
    if len(pts) >= 2:
        first, last = pts[0]["value"], pts[-1]["value"]
        rel = (last - first) / first if first else 0.0
        out["direction"] = "rising" if rel > 0.05 else "falling" if rel < -0.05 else "stable"
        out["change"] = f"{first:g} -> {last:g} {a.unit} between {pts[0]['date']} and {pts[-1]['date']}"
        vals = [p["value"] for p in pts]
        # every step up, each one small: the drift no single report shows
        out["steady_rise"] = len(vals) >= 3 and all(b > c for b, c in zip(vals[1:], vals[:-1]))
    out["latest_flag"] = pts[-1]["flag"] if pts else None
    out["labs"] = sorted({p["lab"] for p in pts})
    return out


def _range(r: dict[str, Any], unit: str) -> str | None:
    lo, hi = r.get("ref_low"), r.get("ref_high")
    if lo is None and hi is None:
        return None
    if lo is None:
        return f"below {hi:g} {unit}"
    if hi is None:
        return f"above {lo:g} {unit}"
    return f"{lo:g}-{hi:g} {unit}"
