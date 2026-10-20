"""Domain data store behind the MCP servers (stands in for the booking / order / claims
microservices). SQLite in dev; each server would own its own Postgres schema in prod."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, name TEXT, city TEXT, plan TEXT, phone TEXT, language TEXT);
CREATE TABLE IF NOT EXISTS children (child_id TEXT PRIMARY KEY, user_id TEXT, name TEXT, dob TEXT);
CREATE TABLE IF NOT EXISTS vaccine_doses (child_id TEXT, vaccine TEXT, due_date TEXT, given_on TEXT);
CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, user_id TEXT, items TEXT, status TEXT, amount REAL, placed_at TEXT, eta TEXT);
CREATE TABLE IF NOT EXISTS lab_bookings (booking_id TEXT PRIMARY KEY, user_id TEXT, test TEXT, status TEXT, collected_at TEXT, report_eta TEXT);
CREATE TABLE IF NOT EXISTS lab_catalog (code TEXT PRIMARY KEY, name TEXT, price INTEGER, fasting INTEGER, tat_hours INTEGER);
CREATE TABLE IF NOT EXISTS slots (slot_id TEXT PRIMARY KEY, doctor TEXT, specialty TEXT, city TEXT, time TEXT, fee INTEGER, mode TEXT, booked_by TEXT);
CREATE TABLE IF NOT EXISTS consults (booking_id TEXT PRIMARY KEY, user_id TEXT, slot_id TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS claims (claim_id TEXT PRIMARY KEY, user_id TEXT, hospital TEXT, status TEXT, claimed REAL, approved REAL, pending_docs TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS hospitals (name TEXT, city TEXT, specialties TEXT, cashless INTEGER);
CREATE TABLE IF NOT EXISTS surgeries (user_id TEXT, procedure TEXT, hospital TEXT, stage TEXT, next_step TEXT, admission_date TEXT);
CREATE TABLE IF NOT EXISTS idempotency (key TEXT PRIMARY KEY, result TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS reminders (reminder_id TEXT PRIMARY KEY, user_id TEXT, child_id TEXT, channel TEXT, active INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS reminder_log (key TEXT PRIMARY KEY, user_id TEXT, child_id TEXT, vaccine TEXT, due_date TEXT, offset_days INTEGER, sent_at TEXT);
-- health records: an account holds members (self + people the account holder cares for);
-- a non-self member's records are readable only under an unexpired consent with that scope
CREATE TABLE IF NOT EXISTS members (member_id TEXT PRIMARY KEY, account_user_id TEXT, name TEXT, relation TEXT, dob TEXT);
CREATE TABLE IF NOT EXISTS consents (consent_id TEXT PRIMARY KEY, member_id TEXT, grantee_user_id TEXT, scopes TEXT, granted_at TEXT, expires_at TEXT, revoked INTEGER);
CREATE TABLE IF NOT EXISTS medications (med_id TEXT PRIMARY KEY, member_id TEXT, name TEXT, instructions TEXT, prescriber TEXT, specialty TEXT, started_on TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS lab_results (member_id TEXT, analyte TEXT, value REAL, unit TEXT, lab TEXT, collected_on TEXT, ref_low REAL, ref_high REAL);
CREATE TABLE IF NOT EXISTS appointments (appointment_id TEXT PRIMARY KEY, member_id TEXT, doctor TEXT, specialty TEXT, time TEXT, mode TEXT);
"""
# Bump when the schema or seed shape changes; a dev DB from an older shape is rebuilt.
SCHEMA_VERSION = "5"


class DomainStore:
    def __init__(self, path: Path, *, reseed_stale: bool = True) -> None:
        self._lock = threading.Lock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        # Seed dates are relative to the seed day ("ETA today", "vaccine due in 3 days"). A dev DB
        # kept for a week silently turns "due in 3 days" into "overdue" and the demo lies
        # (INC-012), so demo data older than today, or from an older schema, is rebuilt.
        meta = {r["key"]: r["value"] for r in self.q("SELECT key, value FROM meta")}
        stale = meta.get("schema") != SCHEMA_VERSION or (reseed_stale and meta.get("seed_date") != date.today().isoformat())
        if stale or not self.db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            self._reset()
            self.seed()

    def _reset(self) -> None:
        with self._lock:
            tables = [r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for t in tables:
                self.db.execute(f"DROP TABLE IF EXISTS {t}")
            self.db.executescript(SCHEMA)

    def q(self, sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def x(self, sql: str, args: tuple[Any, ...] = ()) -> None:
        with self._lock:
            self.db.execute(sql, args)
            self.db.commit()

    # Idempotency: a retried write (network blip, user double-tap, LLM re-plans the same call)
    # returns the first result instead of booking twice.
    def idem_get(self, key: str) -> dict[str, Any] | None:
        rows = self.q("SELECT result FROM idempotency WHERE key=?", (key,))
        return json.loads(rows[0]["result"]) if rows else None

    def idem_put(self, key: str, result: dict[str, Any]) -> None:
        self.x("INSERT OR IGNORE INTO idempotency VALUES (?,?,?)", (key, json.dumps(result), datetime.now().isoformat()))

    def seed(self) -> None:
        today = date.today()
        d = lambda n: (today + timedelta(days=n)).isoformat()  # noqa: E731
        users = [("U1001", "Ananya Rao", "bangalore", "care_plus", "919800000001", "en"), ("U1002", "Rahul Mehta", "mumbai", "basic", "919800000002", "en"),
                 ("U1003", "Fatima Shaikh", "hyderabad", "care_plus", "919800000003", "hi")]
        children = [("C501", "U1001", "Aarav", d(-75)), ("C502", "U1003", "Zoya", d(-300))]
        doses = [
            ("C501", "BCG", d(-75), d(-75)), ("C501", "Hepatitis B - dose 1", d(-75), d(-75)), ("C501", "OPV - dose 0", d(-75), d(-75)),
            ("C501", "DTwP/DTaP - dose 1", d(-33), d(-32)), ("C501", "IPV - dose 1", d(-33), d(-32)), ("C501", "Rotavirus - dose 1", d(-33), d(-32)),
            ("C501", "DTwP/DTaP - dose 2", d(3), None), ("C501", "IPV - dose 2", d(3), None), ("C501", "Rotavirus - dose 2", d(3), None),
            ("C501", "DTwP/DTaP - dose 3", d(31), None),
            ("C502", "MMR - dose 1", d(-30), None), ("C502", "Typhoid conjugate", d(-30), None),
        ]
        orders = [
            ("ORD-1042", "U1001", json.dumps(["Metformin 500mg x30", "Vitamin D3 60K x4"]), "out_for_delivery", 412.0, d(-1), d(0)),
            ("ORD-1043", "U1001", json.dumps(["Paracetamol 650mg x15"]), "packed", 48.0, d(0), d(1)),
            ("ORD-2077", "U1002", json.dumps(["Insulin Glargine 100IU"]), "prescription_hold", 1250.0, d(-1), None),
            ("ORD-1044", "U1001", json.dumps(["Dolo 650 x10"]), "delivered", 32.0, d(-3), d(-2)),
            ("ORD-3001", "U1003", json.dumps(["Cetirizine 10mg x10"]), "delivered", 35.0, d(-6), d(-5)),
        ]
        labs = [
            ("LAB-7781", "U1001", "HbA1c + Lipid Profile", "sample_collected", d(0), d(1)),
            ("LAB-7790", "U1002", "Thyroid Profile (T3,T4,TSH)", "report_ready", d(-2), d(-1)),
            ("LAB-7795", "U1003", "Urine Culture", "processing", d(-1), d(3)),
        ]
        catalog = [
            ("HBA1C", "HbA1c (Glycated Haemoglobin)", 450, 0, 24), ("LIPID", "Lipid Profile", 600, 1, 24),
            ("TFT", "Thyroid Profile (T3,T4,TSH)", 550, 0, 24), ("CBC", "Complete Blood Count", 300, 0, 12),
            ("FBS", "Fasting Blood Sugar", 150, 1, 12), ("FULLBODY", "Full Body Checkup (72 tests)", 1999, 1, 48),
            ("VITD", "Vitamin D (25-OH)", 1100, 0, 24), ("UCULT", "Urine Culture", 700, 0, 96),
        ]
        slots = []
        docs = [("Dr. Kavya Iyer", "dermatologist"), ("Dr. Arjun Nair", "cardiologist"), ("Dr. Meera Pillai", "pediatrician"),
                ("Dr. Sanjay Gupta", "general physician"), ("Dr. Priya Reddy", "gynecologist"), ("Dr. Vikram Shah", "orthopedic")]
        n = 1
        for city in ["bangalore", "mumbai", "hyderabad", "delhi"]:
            for doc, spec in docs:
                for h in (10, 15, 18):
                    slots.append((f"S-{n:03d}", doc, spec, city, f"{d(1)} {h}:00", 500 if spec == "general physician" else 800, "video" if h != 15 else "in_clinic", None))
                    n += 1
        claims = [
            ("CLM-55012", "U1002", "Lakeside Eye Hospital, Mumbai", "documents_pending", 48000, 0, "Final bill with itemised break-up; Lens invoice", d(-2)),
            ("CLM-55020", "U1001", "Greenfield Multispeciality, Bangalore", "partially_approved", 62000, 54500, "", d(-8)),
            ("CLM-55031", "U1003", "Charminar Care Hospital, Hyderabad", "under_review", 23000, 0, "", d(-1)),
        ]
        hospitals = [
            ("Greenfield Multispeciality", "bangalore", "cardiology,orthopedics,general surgery", 1),
            ("Indiranagar Eye Institute", "bangalore", "ophthalmology", 1),
            ("Whitefield Women & Child", "bangalore", "obstetrics,pediatrics", 1),
            ("Lakeside Eye Hospital", "mumbai", "ophthalmology", 1), ("Harbour Heart Centre", "mumbai", "cardiology", 1),
            ("Charminar Care Hospital", "hyderabad", "general surgery,orthopedics", 1), ("Capital City Hospital", "delhi", "multispeciality", 1),
            ("Koramangala Clinic", "bangalore", "general medicine", 0),
        ]
        surgeries = [("U1002", "cataract", "Lakeside Eye Hospital, Mumbai", "insurance_preauth", "Upload the final cost estimate so the hospital can raise pre-authorisation", d(6))]
        # Ananya coordinates care for her father Venkat (68): two prescribers who never spoke,
        # one molecule through two products, an interacting pair, and an HbA1c that rose
        # across three reports from two labs in two units.
        members = [("U1001", "U1001", "Ananya Rao", "self", d(-365 * 34)), ("M-2001", "U1001", "Venkat Rao", "father", d(-365 * 68)),
                   ("U1002", "U1002", "Rahul Mehta", "self", d(-365 * 41)), ("U1003", "U1003", "Fatima Shaikh", "self", d(-365 * 31)),
                   ("M-3001", "U1003", "Shabana Shaikh", "mother", d(-365 * 59))]
        consents = [("CNS-2001", "M-2001", "U1001", "medications,labs,appointments", d(-60), d(305), 0),
                    ("CNS-3001", "M-3001", "U1003", "medications,labs", d(-400), d(-35), 0)]  # expired
        card, gp = ("Dr. Arjun Nair", "cardiologist"), ("Dr. Sanjay Gupta", "general physician")
        meds = [
            ("RX-01", "M-2001", "Ecosprin 75", "1 tablet after lunch", *card, d(-400), "active"),
            ("RX-02", "M-2001", "Clopilet 75", "1 tablet after breakfast", *card, d(-400), "active"),
            ("RX-03", "M-2001", "Atorva 10", "1 tablet at night", *card, d(-400), "active"),
            ("RX-04", "M-2001", "Ecosprin-AV 75", "1 capsule at night", *gp, d(-90), "active"),
            ("RX-05", "M-2001", "Omez 20", "1 capsule before breakfast", *gp, d(-60), "active"),
            ("RX-06", "M-2001", "Glycomet 500", "1 tablet twice a day after meals", *gp, d(-300), "active"),
            ("RX-07", "M-2001", "Telma 40", "1 tablet in the morning", *gp, d(-500), "stopped"),
            ("RX-11", "U1001", "Glycomet 500", "1 tablet after dinner", *gp, d(-200), "active"),
            ("RX-12", "U1001", "Shelcal 500", "1 tablet after lunch", *gp, d(-200), "active"),
            ("RX-21", "U1003", "Thyronorm 50", "1 tablet on an empty stomach", "Dr. Priya Reddy", "gynecologist", d(-150), "active"),
            ("RX-31", "M-3001", "Telma 40", "1 tablet in the morning", *gp, d(-700), "active"),
        ]
        labs_hist = [
            ("M-2001", "hba1c", 6.6, "%", "Sahay Labs Bangalore", d(-370), 4.0, 5.6),
            ("M-2001", "hba1c", 52, "mmol/mol", "Metro Diagnostics", d(-190), 4.0, 5.6),
            ("M-2001", "hba1c", 7.4, "%", "Sahay Labs Bangalore", d(-12), 4.0, 5.6),
            ("M-2001", "ldl", 3.1, "mmol/L", "Metro Diagnostics", d(-190), None, 100),
            ("M-2001", "ldl", 96, "mg/dL", "Sahay Labs Bangalore", d(-12), None, 100),
            ("M-2001", "creatinine", 1.0, "mg/dL", "Sahay Labs Bangalore", d(-370), 0.7, 1.3),
            ("M-2001", "creatinine", 97, "µmol/L", "Metro Diagnostics", d(-190), 0.7, 1.3),
            ("M-2001", "creatinine", 1.2, "mg/dL", "Sahay Labs Bangalore", d(-12), 0.7, 1.3),
            ("U1001", "vitamin_d", 18, "ng/mL", "Sahay Labs Bangalore", d(-200), 30, 100),
            ("U1001", "vitamin_d", 75, "nmol/L", "Metro Diagnostics", d(-20), 30, 100),
            ("U1001", "hba1c", 5.9, "%", "Sahay Labs Bangalore", d(-200), 4.0, 5.6),
            ("U1001", "hba1c", 6.1, "%", "Sahay Labs Bangalore", d(-20), 4.0, 5.6),
            ("U1003", "tsh", 5.8, "mIU/L", "Charminar Diagnostics", d(-150), 0.4, 4.5),
            ("U1003", "tsh", 4.1, "uIU/mL", "Sahay Labs Hyderabad", d(-10), 0.4, 4.5),
            ("M-3001", "hba1c", 7.9, "%", "Charminar Diagnostics", d(-100), 4.0, 5.6),
        ]
        appts = [("APT-9001", "M-2001", "Dr. Arjun Nair", "cardiologist", f"{d(4)} 11:00", "in_clinic")]
        with self._lock:
            c = self.db
            c.executemany("INSERT INTO users VALUES (?,?,?,?,?,?)", users)
            c.executemany("INSERT INTO children VALUES (?,?,?,?)", children)
            c.executemany("INSERT INTO vaccine_doses VALUES (?,?,?,?)", doses)
            c.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", orders)
            c.executemany("INSERT INTO lab_bookings VALUES (?,?,?,?,?,?)", labs)
            c.executemany("INSERT INTO lab_catalog VALUES (?,?,?,?,?)", catalog)
            c.executemany("INSERT INTO slots VALUES (?,?,?,?,?,?,?,?)", slots)
            c.executemany("INSERT INTO claims VALUES (?,?,?,?,?,?,?,?)", claims)
            c.executemany("INSERT INTO hospitals VALUES (?,?,?,?)", hospitals)
            c.executemany("INSERT INTO surgeries VALUES (?,?,?,?,?,?)", surgeries)
            c.executemany("INSERT INTO members VALUES (?,?,?,?,?)", members)
            c.executemany("INSERT INTO consents VALUES (?,?,?,?,?,?,?)", consents)
            c.executemany("INSERT INTO medications VALUES (?,?,?,?,?,?,?,?)", meds)
            c.executemany("INSERT INTO lab_results VALUES (?,?,?,?,?,?,?,?)", labs_hist)
            c.executemany("INSERT INTO appointments VALUES (?,?,?,?,?,?)", appts)
            # Fatima already opted in to WhatsApp reminders for Zoya (who has overdue doses)
            c.execute("INSERT INTO reminders VALUES (?,?,?,?,1,?)", ("REM-SEED01", "U1003", "C502", "whatsapp", today.isoformat()))
            c.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", [("schema", SCHEMA_VERSION), ("seed_date", today.isoformat())])
            c.commit()
