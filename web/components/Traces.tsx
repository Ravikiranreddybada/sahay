"use client";
import { useEffect, useState } from "react";
import { Alert } from "./Icons";
import { Waterfall } from "./Waterfall";
import { getJSON, type Trace, type TraceRow } from "@/lib/api";

export function Traces() {
  const [rows, setRows] = useState<TraceRow[]>([]);
  const [sel, setSel] = useState<Trace | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { getJSON<TraceRow[]>("v1/traces?limit=100").then(setRows).catch((e) => setErr(String(e.message))); }, []);
  const open = (id: string) => getJSON<Trace>(`v1/traces/${id}`).then(setSel).catch((e) => setErr(String(e.message)));
  return (
    <div className="page office">
      <div className="page-head">
        <h2>Traces</h2>
        <p className="sub">Every turn is a trace; every node, LLM call, tool call and retrieval is a span. Start debugging here, not in the prompt.</p>
      </div>
      {err && <div className="err" role="alert">{err}</div>}
      <div className="split wide">
        <section className="sheet flush">
          <table className="table dense">
            <thead><tr><th>Query</th><th>Intent</th><th className="num">ms</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.trace_id} className="click" aria-selected={sel?.trace_id === r.trace_id} tabIndex={0}
                  onClick={() => open(r.trace_id)} onKeyDown={(e) => { if (e.key === "Enter") open(r.trace_id); }}>
                  <td>{r.query}<span className="cell-sub mono">{r.user_id} · {new Date(r.started_at * 1000).toLocaleTimeString("en-IN")}</span></td>
                  <td>{r.intent?.replace(/_/g, " ")}{!r.grounded && <span className="warn" title="Not grounded"> <Alert size={14} /></span>}</td>
                  <td className="num mono">{r.latency_ms.toFixed(0)}</td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={3} className="muted">No traces yet. Ask something in Patient → Chat.</td></tr>}
            </tbody>
          </table>
        </section>
        <section className="sheet">
          {sel ? (
            <>
              <h3 className="trace-title">{sel.query}</h3>
              <dl className="totals">
                <div><dt>Trace</dt><dd className="mono">{sel.trace_id.slice(0, 12)}</dd></div>
                <div><dt>Latency</dt><dd className="mono">{sel.totals.latency_ms.toFixed(1)} ms</dd></div>
                <div><dt>LLM calls</dt><dd className="mono">{sel.totals.llm_calls}</dd></div>
                <div><dt>Tool calls</dt><dd className="mono">{sel.totals.tool_calls}</dd></div>
                <div><dt>Tokens</dt><dd className="mono">{sel.totals.tokens_in} / {sel.totals.tokens_out}</dd></div>
                <div><dt>Cost</dt><dd className="mono">${sel.totals.cost_usd.toFixed(5)}</dd></div>
              </dl>
              <Waterfall trace={sel} />
            </>
          ) : <p className="muted">Select a trace. Click any span to see its attributes: retrieved chunk ranks, tool args, verifier problems, tokens.</p>}
        </section>
      </div>
    </div>
  );
}
