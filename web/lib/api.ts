export type Tool = { tool: string; args: Record<string, unknown>; ok: boolean };
export type Evidence = { id: string; score: number | null; stale: boolean | null };
export type Totals = { latency_ms: number; tokens_in: number; tokens_out: number; cost_usd: number; llm_calls: number; tool_calls: number };
export type PendingAction = { type: "confirm"; tool: string; args: Record<string, unknown>; summary: string };

export type TurnResult = {
  status: "answered" | "needs_confirmation" | "escalated";
  thread_id: string;
  trace_id: string;
  answer: string;
  intent?: string;
  confidence?: number;
  citations: string[];
  grounded?: boolean;
  abstained?: boolean;
  cache_hit?: boolean;
  stale_sources?: string[];
  handoff_ticket?: string | null;
  follow_up?: string | null;
  tools?: Tool[];
  evidence?: Evidence[];
  verifier_problems?: string[];
  scorecard?: Record<string, boolean> | null;
  pii_redacted?: Record<string, number>;
  read_only?: boolean;
  degraded?: boolean;
  pending_action: PendingAction | null;
  totals: Totals;
  mode: string;
};

export type Span = {
  span_id: string;
  parent_id: string | null;
  name: string;
  kind: "node" | "llm" | "tool" | "retrieval" | "guard";
  status: string;
  offset_ms: number;
  duration_ms: number;
  attributes: Record<string, unknown>;
};
export type Trace = { trace_id: string; thread_id: string; user_id: string; query: string; started_at: number; meta: Record<string, unknown>; totals: Totals; spans: Span[] };
export type TraceRow = { trace_id: string; thread_id: string; user_id: string; query: string; started_at: number; intent: string | null; latency_ms: number; cost_usd: number; grounded: number };

// ---------------------------------------------------------------- sessions
// The backend never trusts a user_id in a request body: every call carries a signed session
// token. Demo personas and the ops role sign in through /v1/auth/dev-login (dev only).
type Session = { token: string; role: "member" | "ops"; sub: string };
const sessions = new Map<string, Session>();

export async function signIn(persona: string): Promise<Session> {
  const cached = sessions.get(persona);
  if (cached) return cached;
  const r = await fetch("/api/v1/auth/dev-login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ persona }) });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `${r.status}`);
  const s = (await r.json()) as Session;
  sessions.set(persona, s);
  return s;
}

/** Which identity a call runs as: a member persona id (U1001…) or "ops". */
export type As = string;

async function authed(as: As, path: string, init: RequestInit = {}): Promise<Response> {
  const go = async () => {
    const { token } = await signIn(as);
    return fetch(`/api/${path}`, { ...init, cache: "no-store", headers: { ...(init.headers ?? {}), authorization: `Bearer ${token}` } });
  };
  let r = await go();
  if (r.status === 401) {
    sessions.delete(as); // expired or backend restarted with a new secret: sign in again once
    r = await go();
  }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `${r.status}`);
  return r;
}

export async function getJSON<T>(path: string, as: As = "ops"): Promise<T> {
  return (await authed(as, path)).json();
}

export async function postJSON<T>(path: string, body: unknown, as: As = "ops"): Promise<T> {
  return (await authed(as, path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })).json();
}

export async function delJSON<T>(path: string, as: As): Promise<T> {
  return (await authed(as, path, { method: "DELETE" })).json();
}

export async function publicJSON<T>(path: string): Promise<T> {
  const r = await fetch(`/api/${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

/** POST + parse an SSE stream of node events (chat turns and confirmations). */
async function streamTurn(as: As, path: string, body: unknown, onNode: (node: string) => void): Promise<TurnResult> {
  const r = await authed(as, path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  if (!r.body) throw new Error("no response body");
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let final: TurnResult | null = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const data = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (!data) continue;
      const ev = JSON.parse(data.slice(6));
      if (ev.type === "node") onNode(ev.node);
      if (ev.type === "final") final = ev.result;
    }
  }
  if (!final) throw new Error("stream ended without a result");
  return final;
}

export const streamChat = (as: As, body: { thread_id: string; message: string }, onNode: (n: string) => void) =>
  streamTurn(as, "v1/chat/stream", body, onNode);

export const streamConfirm = (as: As, body: { thread_id: string; approved: boolean }, onNode: (n: string) => void) =>
  streamTurn(as, "v1/chat/confirm/stream", body, onNode);
