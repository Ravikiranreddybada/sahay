# Local Runbook

```bash
cd ~/Documents/S-Prep/Projects/sahay
python3 -m venv .venv && .venv/bin/pip install -e "backend[dev]"

# optional: real model (otherwise deterministic offline engine)
export ANTHROPIC_API_KEY=sk-ant-...

# API
cd backend && ../.venv/bin/uvicorn sahay.main:app --reload --port 8000

# Web (new terminal)
cd web && npm install && npm run dev   # http://localhost:3000

# Tests + eval gate
cd backend && ../.venv/bin/pytest -q && ../.venv/bin/python -m evals.run_evals
```

## Try it
```bash
TOKEN=$(curl -s localhost:8000/v1/auth/dev-login -H 'content-type: application/json' -d '{"persona":"U1001"}' | jq -r .token)
AUTH="authorization: Bearer $TOKEN"

curl -s localhost:8000/v1/chat -H "$AUTH" -H 'content-type: application/json' \
  -d '{"message":"Where is my order ORD-1042?"}' | jq .answer

# write flow: needs confirmation
curl -s localhost:8000/v1/chat -H "$AUTH" -H 'content-type: application/json' \
  -d '{"thread_id":"demo-1","message":"Cancel order ORD-1043"}' | jq '.status, .pending_action'
curl -s localhost:8000/v1/chat/confirm -H "$AUTH" -H 'content-type: application/json' \
  -d '{"thread_id":"demo-1","approved":true}' | jq .answer

# WhatsApp + reminders (ops)
OPS=$(curl -s localhost:8000/v1/auth/dev-login -H 'content-type: application/json' -d '{"persona":"ops"}' | jq -r .token)
curl -s localhost:8000/v1/channels/whatsapp/simulate -H "authorization: Bearer $OPS" -H 'content-type: application/json' \
  -d '{"phone":"919800000001","text":"Where is my order ORD-1042?"}' | jq '.replies[0].body'
curl -s -XPOST localhost:8000/v1/reminders/run -H "authorization: Bearer $OPS" | jq
```

## Production storage locally
```bash
# Postgres checkpoints (any local Postgres 14+)
export SAHAY_DATABASE_URL=postgresql://sahay@127.0.0.1:5432/sahay
# Redis limiter + semantic cache + turn locks
export SAHAY_REDIS_URL=redis://127.0.0.1:6379/0
cd backend && ../.venv/bin/uvicorn sahay.main:app --port 8000      # /v1/meta shows "postgres · redis"
SAHAY_TEST_PG_URL=$SAHAY_DATABASE_URL ../.venv/bin/pytest -q tests/test_storage.py
```

## Reset demo data
`rm -rf backend/var` (domain DB, traces and checkpoints are recreated and re-seeded on start).
