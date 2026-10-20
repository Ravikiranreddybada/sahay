"""Session tokens and roles.

INC-016: the API used to take `user_id` from the request body, and the trace, handoff and KB
endpoints had no auth at all, so anyone who could reach the API could read any user's
conversation and every trace (which carry tool results with order and claim data). Now:

* member tokens carry `sub` = user id. Chat, confirm, threads and feedback use *only* that.
* ops tokens (role "ops") gate traces, handoffs, KB admin, evals and channel tooling.
* tokens are HMAC-SHA256 signed (stdlib, JWT-shaped: header-free `payload.sig`), with expiry.

Prod swaps the issuer for the platform's identity provider (OIDC); the dependency
functions below are the only thing the routes see, so that swap touches one file.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request

from .config import Settings

ROLES = {"member", "ops"}


@dataclass(frozen=True)
class Principal:
    sub: str
    role: str


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue(secret: str, sub: str, role: str, ttl_s: int) -> str:
    if role not in ROLES:
        raise ValueError(role)
    body = _b64(json.dumps({"sub": sub, "role": role, "exp": int(time.time()) + ttl_s}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify(secret: str, token: str) -> Principal:
    try:
        body, sig = token.split(".", 1)
        want = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, want):
            raise ValueError("bad signature")
        claims = json.loads(_unb64(body))
        if claims["exp"] < time.time():
            raise ValueError("expired")
        if claims["role"] not in ROLES:
            raise ValueError("bad role")
        return Principal(sub=str(claims["sub"]), role=claims["role"])
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        raise HTTPException(401, f"Invalid session: {e}", headers={"WWW-Authenticate": "Bearer"}) from e


def _settings(req: Request) -> Settings:
    return req.app.state.settings


def _bearer(req: Request) -> str | None:
    h = req.headers.get("authorization", "")
    return h[7:].strip() if h.lower().startswith("bearer ") else None


def member(req: Request) -> Principal:
    tok = _bearer(req)
    if not tok:
        raise HTTPException(401, "Sign in required.", headers={"WWW-Authenticate": "Bearer"})
    p = verify(_settings(req).auth_secret, tok)
    if p.role != "member":
        raise HTTPException(403, "A member session is required for chat.")
    return p


def ops(req: Request) -> Principal:
    s = _settings(req)
    key = req.headers.get("x-ops-key")
    if s.ops_key and key and hmac.compare_digest(key, s.ops_key):
        return Principal(sub="ops-key", role="ops")
    tok = _bearer(req)
    if not tok:
        raise HTTPException(401, "Ops sign-in required.", headers={"WWW-Authenticate": "Bearer"})
    p = verify(s.auth_secret, tok)
    if p.role != "ops":
        raise HTTPException(403, "This page is for the care-operations team.")
    return p
