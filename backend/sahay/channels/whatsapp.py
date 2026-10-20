"""WhatsApp channel (Meta WhatsApp Cloud API).

Inbound:  Meta -> POST /v1/channels/whatsapp/webhook (signed with the app secret)
          -> verify X-Hub-Signature-256 -> dedupe message id -> phone -> member
          -> same Agent as the web chat (same graph, guards, verifier, traces).
Outbound: text replies; a write that needs confirmation becomes an interactive message with
          Yes / No buttons, and the button reply resumes the paused graph.

The channel is a thin adapter on purpose: every safety property (emergency triage, scoped
tools, write confirmation, grounding) comes from the agent, so WhatsApp cannot be a weaker
door into the system than the web app.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import Settings
from ..safety.pii import redact
from .outbox import Outbox

log = logging.getLogger("sahay.whatsapp")
GRAPH = "https://graph.facebook.com/v21.0"
YES = {"yes", "y", "haan", "ha", "han", "confirm", "ok", "okay", "go ahead", "confirm_yes"}
NO = {"no", "n", "nahi", "nahin", "cancel", "stop", "don't", "dont", "confirm_no"}
CITE = re.compile(r"\s*\[(?:[a-z_]+#[a-z0-9-]+|tool:[a-z_]+)\]")
MAX_BODY = 4096


@dataclass
class Inbound:
    msg_id: str
    phone: str
    text: str


def verify_signature(app_secret: str, raw_body: bytes, header: str | None) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    want = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header[7:], want)


def parse(payload: dict[str, Any]) -> list[Inbound]:
    """Pull user messages out of a Cloud API webhook body; ignore delivery/read statuses."""
    out: list[Inbound] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            for m in (change.get("value") or {}).get("messages", []) or []:
                t = m.get("type")
                if t == "text":
                    text = (m.get("text") or {}).get("body", "")
                elif t == "interactive":
                    it = m.get("interactive") or {}
                    text = (it.get("button_reply") or it.get("list_reply") or {}).get("id", "")
                elif t == "button":
                    text = (m.get("button") or {}).get("payload", "")
                else:
                    text = ""  # images, voice notes: answered with a fallback below
                out.append(Inbound(msg_id=m.get("id", ""), phone=re.sub(r"\D", "", m.get("from", "")), text=text.strip()))
    return out


def to_whatsapp_text(answer: str) -> str:
    """Citations are for the web UI and the verifier; on a phone they are noise."""
    return CITE.sub("", answer).strip()[:MAX_BODY]


class WhatsAppChannel:
    def __init__(self, settings: Settings, agent: Any, outbox: Outbox, http: httpx.AsyncClient | None = None) -> None:
        self.s, self.agent, self.outbox = settings, agent, outbox
        self.http = http

    def member_for(self, phone: str) -> str | None:
        from ..mcp_servers import servers

        rows = servers.store().q("SELECT user_id FROM users WHERE phone=?", (phone,))
        return rows[0]["user_id"] if rows else None

    async def handle(self, msg: Inbound) -> list[str]:
        """Process one inbound message; returns the outbox ids of the replies."""
        if not msg.msg_id or not self.outbox.first_time(msg.msg_id):
            return []
        user_id = self.member_for(msg.phone)
        if user_id is None:
            return [await self.send_text(msg.phone, None, "This number isn't linked to a Sahay account yet. Please link it from the app under Profile > WhatsApp.", kind="unlinked")]
        if not msg.text:
            return [await self.send_text(msg.phone, user_id, "I can read text messages only for now. Please type your question.", kind="unsupported")]
        thread_id = f"wa-{msg.phone}"
        word = msg.text.lower().strip(" .!")
        cfg = {"configurable": {"thread_id": f"{user_id}:{thread_id}"}}
        if (word in YES or word in NO) and await self.agent._pending(cfg):
            res = await self.agent.run_turn(user_id=user_id, thread_id=thread_id, resume={"approved": word in YES})
        else:
            res = await self.agent.run_turn(user_id=user_id, thread_id=thread_id, message=msg.text)
        if res.get("status") == "needs_confirmation":
            return [await self.send_buttons(msg.phone, user_id, res.get("answer") or "Please confirm.")]
        return [await self.send_text(msg.phone, user_id, to_whatsapp_text(res.get("answer") or ""), kind="reply")]

    # ------------------------------------------------------------------ outbound
    async def send_text(self, to: str, user_id: str | None, body: str, kind: str = "reply") -> str:
        payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body[:MAX_BODY]}}
        return await self._deliver(to, user_id, kind, body, payload)

    async def send_buttons(self, to: str, user_id: str | None, body: str) -> str:
        payload = {
            "messaging_product": "whatsapp", "to": to, "type": "interactive",
            "interactive": {"type": "button", "body": {"text": body[:1024]}, "action": {"buttons": [
                {"type": "reply", "reply": {"id": "confirm_yes", "title": "Yes, go ahead"}},
                {"type": "reply", "reply": {"id": "confirm_no", "title": "No"}},
            ]}},
        }
        return await self._deliver(to, user_id, "confirm", body, payload)

    async def _deliver(self, to: str, user_id: str | None, kind: str, body: str, payload: dict[str, Any]) -> str:
        logged = redact(body).text  # the outbox is a log: same PII rule as traces
        if not (self.s.whatsapp_access_token and self.s.whatsapp_phone_number_id):
            return self.outbox.record(channel="whatsapp", recipient=to, user_id=user_id, kind=kind, body=logged, payload={}, status="simulated")
        try:
            url = f"{GRAPH}/{self.s.whatsapp_phone_number_id}/messages"
            headers = {"Authorization": f"Bearer {self.s.whatsapp_access_token}"}
            if self.http is not None:
                r = await self.http.post(url, json=payload, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=10) as http:
                    r = await http.post(url, json=payload, headers=headers)
            r.raise_for_status()
            return self.outbox.record(channel="whatsapp", recipient=to, user_id=user_id, kind=kind, body=logged, payload={}, status="sent")
        except Exception as e:  # noqa: BLE001 - delivery failure is recorded, never raised into the webhook
            log.warning("whatsapp send failed: %s", e)
            return self.outbox.record(channel="whatsapp", recipient=to, user_id=user_id, kind=kind, body=logged, payload={},
                                      status="failed", error=str(e)[:300])
