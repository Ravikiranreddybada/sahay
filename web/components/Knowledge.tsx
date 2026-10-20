"use client";
import { useEffect, useState } from "react";
import { Refresh } from "./Icons";
import { getJSON, postJSON } from "@/lib/api";

type Doc = { doc_id: string; title: string; version: string; review_by: string | null; stale: boolean; chunks: number; sections: string[] };
type KB = { kb_version: string; embedder: string; files: string[]; indexed_docs: Doc[]; scheduled?: string[] };
type Ticket = { ticket_id: string; user_id: string; priority: string; reason: string; status: string; created_at: number; packet: Record<string, unknown> };

export function Knowledge() {
  const [kb, setKb] = useState<KB | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => {
    getJSON<KB>("v1/kb").then(setKb).catch((e) => setMsg(String(e.message)));
    getJSON<Ticket[]>("v1/handoffs").then(setTickets).catch(() => undefined);
  };
  useEffect(load, []);
  const reindex = async () => {
    setBusy(true);
    try {
      const r = await postJSON<{ chunks: number; re_embedded: number; kb_version: string }>("v1/kb/reindex", {});
      setMsg(`Re-indexed: ${r.chunks} chunks, ${r.re_embedded} re-embedded (content-hash diff), kb_version ${r.kb_version}.`);
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const resolve = async (id: string) => {
    await postJSON(`v1/handoffs/${id}/resolve`, { note: "resolved from ops console" }).catch((e) => setMsg(String(e.message)));
    load();
  };
  const open = tickets.filter((t) => t.status === "open").length;
  return (
    <div className="page office">
      <div className="page-head">
        <h2>Knowledge &amp; handoffs</h2>
        <p className="sub">Only the latest version of each SOP is indexed. Docs past their review date are served with a warning, never silently.</p>
      </div>
      {msg && <p className="notice" role="status">{msg}</p>}
      {kb && (
        <section className="sheet flush">
          <div className="sheet-head padded">
            <h3 className="label">Knowledge base</h3>
            <span className="mono muted">kb {kb.kb_version} · {kb.embedder} · {kb.files.length} files → {kb.indexed_docs.length} indexed</span>
            <span className="spacer" />
            <button className="btn ghost" onClick={reindex} disabled={busy}><Refresh size={16} />{busy ? "Re-indexing…" : "Re-index"}</button>
          </div>
          <table className="table dense">
            <thead><tr><th>Document</th><th>Version</th><th>Review by</th><th>Status</th><th className="num">Chunks</th><th>Sections</th></tr></thead>
            <tbody>
              {kb.indexed_docs.map((d) => (
                <tr key={d.doc_id}>
                  <td><b>{d.title}</b><span className="cell-sub mono">{d.doc_id}</span></td>
                  <td className="mono">v{d.version}</td>
                  <td className="mono">{d.review_by}</td>
                  <td>{d.stale ? <span className="warn">stale</span> : <span className="muted">fresh</span>}</td>
                  <td className="num mono">{d.chunks}</td>
                  <td className="small">{d.sections.join(" · ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="fineprint padded">Files on disk: <span className="mono">{kb.files.join(", ")}</span>. Superseded versions (e.g. refund_policy_v1) are never indexed.
            {!!kb.scheduled?.length && <> Scheduled, not yet in force: <span className="mono">{kb.scheduled.join(", ")}</span>.</>}</p>
        </section>
      )}
      <section className="sheet flush">
        <div className="sheet-head padded"><h3 className="label">Handoff queue</h3><span className="muted small">{open} open</span></div>
        <table className="table dense">
          <thead><tr><th>Ticket</th><th>Priority</th><th>Reason</th><th>Member</th><th>Context packet for the human agent</th><th>Status</th></tr></thead>
          <tbody>
            {tickets.map((t) => (
              <tr key={t.ticket_id}>
                <td className="mono">{t.ticket_id}</td>
                <td>{t.priority === "P1" ? <b className="bad-text">P1</b> : t.priority}</td>
                <td>{t.reason}</td>
                <td className="mono">{t.user_id}</td>
                <td><details><summary className="mono">{JSON.stringify(t.packet).slice(0, 90)}…</summary><pre className="attrs">{JSON.stringify(t.packet, null, 2)}</pre></details></td>
                <td>{t.status === "open" ? <button className="btn ghost" onClick={() => resolve(t.ticket_id)}>Resolve</button> : <span className="muted">resolved</span>}</td>
              </tr>
            ))}
            {!tickets.length && <tr><td colSpan={6} className="muted">No handoffs yet.</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  );
}
