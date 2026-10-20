"""Vaccine reminder sweep (the "reminds parents 7 days and 1 day before a dose" promise in
the vaccination SOP, made real).

Runs as a background task in the API (every `reminder_interval_s`) and on demand from the
ops UI. Properties that matter:

* exactly-once per (child, vaccine, due date, offset): the log row is *claimed* with an
  INSERT before sending, so two API replicas sweeping at once cannot both send.
* catch-up: a sweep that missed a day still sends the most urgent reminder that applies,
  but never the 7-day and the 1-day reminder together.
* one message per child per due day ("DTaP 2, IPV 2 and Rotavirus 2 are due"), not three.
* overdue doses get one nudge pointing to a pediatrician catch-up plan; the assistant
  never decides a catch-up schedule itself (SOP: Missed or delayed doses).
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from ..mcp_servers.store import DomainStore
from .outbox import Outbox

OFFSETS = (1, 7)  # most urgent first
OVERDUE = -1


def _key(child_id: str, vaccine: str, due: str, offset: int) -> str:
    return hashlib.sha256(f"{child_id}|{vaccine}|{due}|{offset}".encode()).hexdigest()[:32]


class ReminderService:
    def __init__(self, store: DomainStore, outbox: Outbox, channel: Any | None = None) -> None:
        self.store, self.outbox, self.channel = store, outbox, channel

    def _claim(self, key: str, user_id: str, child_id: str, vaccine: str, due: str, offset: int) -> bool:
        with self.store._lock:
            cur = self.store.db.execute("INSERT OR IGNORE INTO reminder_log VALUES (?,?,?,?,?,?,?)",
                                        (key, user_id, child_id, vaccine, due, offset, datetime.now().isoformat()))
            self.store.db.commit()
        return cur.rowcount == 1

    def due(self, today: date | None = None) -> list[dict[str, Any]]:
        """What a sweep would send now, before claiming anything (used by the ops view)."""
        today = today or date.today()
        rows = self.store.q(
            "SELECT r.user_id, r.channel, c.child_id, c.name AS child, d.vaccine, d.due_date, u.phone "
            "FROM reminders r JOIN children c ON c.child_id=r.child_id JOIN vaccine_doses d ON d.child_id=c.child_id "
            "JOIN users u ON u.user_id=r.user_id WHERE r.active=1 AND d.given_on IS NULL ORDER BY d.due_date")
        sent = {r["key"] for r in self.store.q("SELECT key FROM reminder_log")}
        out = []
        for r in rows:
            days = (date.fromisoformat(r["due_date"]) - today).days
            if days < 0:
                offset = OVERDUE
            else:
                offset = next((o for o in OFFSETS if days <= o), None)
                if offset is None:
                    continue
            # a 1-day reminder supersedes an unsent 7-day one; never send both
            keys = [_key(r["child_id"], r["vaccine"], r["due_date"], o) for o in (offset, *[o for o in OFFSETS if o < offset])]
            if any(k in sent for k in keys):
                continue
            out.append({**r, "days": days, "offset": offset, "key": keys[0]})
        return out

    async def sweep(self, today: date | None = None) -> dict[str, Any]:
        today = today or date.today()
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for r in self.due(today):
            if self._claim(r["key"], r["user_id"], r["child_id"], r["vaccine"], r["due_date"], r["offset"]):
                groups[(r["user_id"], r["child_id"], r["due_date"])].append(r)
        sent: list[str] = []
        for (_user, _child, due), doses in groups.items():
            first = doses[0]
            names = ", ".join(d["vaccine"] for d in doses)
            if first["offset"] == OVERDUE:
                body = (f"{first['child']}'s {names} {'was' if len(doses) == 1 else 'were'} due on {due}. Please don't restart the series — "
                        f"a pediatrician can advise a catch-up plan. Reply 'book pediatrician' and I'll find a slot.")
                kind = "reminder_overdue"
            else:
                when = "tomorrow" if first["days"] == 1 else ("today" if first["days"] == 0 else f"in {first['days']} days")
                body = (f"Reminder: {first['child']}'s {names} {'is' if len(doses) == 1 else 'are'} due {when} ({due}). "
                        f"Keep the vaccination card ready. Reply 'book vaccination' to schedule a home or clinic visit.")
                kind = f"reminder_{first['offset']}d"
            if first["channel"] == "whatsapp" and self.channel is not None:
                sent.append(await self.channel.send_text(first["phone"], first["user_id"], body, kind=kind))
            else:
                sent.append(self.outbox.record(channel=first["channel"], recipient=first["phone"], user_id=first["user_id"],
                                               kind=kind, body=body, payload={}, status="simulated"))
        return {"date": today.isoformat(), "messages": len(sent), "doses": sum(len(v) for v in groups.values()), "outbox_ids": sent}
