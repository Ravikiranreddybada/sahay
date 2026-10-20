# Data Model

## Domain (behind MCP servers) — `sahay/mcp_servers/store.py`
```mermaid
erDiagram
  users ||--o{ orders : places
  users ||--o{ lab_bookings : books
  users ||--o{ consults : books
  users ||--o{ claims : files
  users ||--o{ children : has
  children ||--o{ vaccine_doses : schedule
  users ||--o{ surgeries : journey
  slots ||--o| consults : "booked as"
  users { text user_id PK  text name  text city  text plan }
  orders { text order_id PK  text user_id FK  json items  text status  real amount  text eta }
  lab_bookings { text booking_id PK  text user_id FK  text test  text status  text report_eta }
  slots { text slot_id PK  text doctor  text specialty  text city  text time  int fee  text booked_by }
  claims { text claim_id PK  text user_id FK  text status  real claimed  real approved  text pending_docs }
  children { text child_id PK  text user_id FK  text name  date dob }
  vaccine_doses { text child_id FK  text vaccine  date due_date  date given_on }
  surgeries { text user_id FK  text procedure  text stage  text next_step  date admission_date }
  idempotency { text key PK  json result  ts created_at }
```

## Agent-side stores
| Store | Key | Content | Retention |
|---|---|---|---|
| Checkpoints | `thread_id` + checkpoint id | Graph state (redacted messages, entities, summary) | 30 days |
| Traces | `trace_id` | Spans with attributes (tokens, cost, hits, tool args) | 7 days hot, 90 days cold (S3) |
| Feedback | `trace_id` | thumbs up/down + comment | 1 year (eval mining) |
| Handoffs | `ticket_id` | Context packet, priority, status | Per CS policy |
| Semantic cache | (intent, prompt_version, kb_version) + vector | Non-personal answers | TTL 1 h |

## Seed users (dev)
| User | Persona | Demo flows |
|---|---|---|
| U1001 Ananya (Bangalore, Care Plus) | Parent of Aarav (≈2.5 months) | order ORD-1042 out for delivery, ORD-1043 cancellable, LAB-7781, claim CLM-55020 partial, vaccine due in 3 days |
| U1002 Rahul (Mumbai) | Cataract surgery journey | ORD-2077 prescription hold, CLM-55012 documents pending, LAB-7790 ready |
| U1003 Fatima (Hyderabad, Care Plus) | Parent of Zoya (overdue MMR) | CLM-55031 under review, LAB-7795 culture processing |
