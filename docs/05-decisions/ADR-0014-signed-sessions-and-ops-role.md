# ADR-0014: Signed sessions; user identity never comes from the request body

**Context.** v0.1 took `user_id` from the JSON body and left trace, handoff and KB endpoints open (INC-016). Traces contain tool results, so this exposed every user's orders and claims.
**Decision.** Every member route reads the user from a signed bearer token (HMAC-SHA256, expiry). Two roles: `member` (chat, confirm, own threads/traces, feedback) and `ops` (traces, handoffs, KB admin, evals, channels). Dev mints tokens for the seeded personas through `/v1/auth/dev-login`; the app refuses to start outside dev with dev-login on or the default secret.
**Alternatives.** PyJWT (extra dependency for the same 30 lines); cookies + CSRF (the web app is a same-origin proxy, but mobile and WhatsApp clients are not browsers).
**Consequences.** + IDOR at the HTTP layer is closed the same way ADR-0007 closed it at the tool layer. + Swapping to the platform's OIDC provider changes one module (`sahay/auth.py`). − Tokens are not revocable before expiry (12 h); prod uses short-lived tokens from the IdP.
