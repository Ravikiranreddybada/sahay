"use client";
import { useEffect, useState } from "react";
import { Phone, Refresh, Send } from "./Icons";
import { getJSON, postJSON } from "@/lib/api";

type Out = { id: string; channel: string; recipient: string; user_id: string | null; kind: string; body: string; status: string; error: string | null; created_at: number };
type Due = { user_id: string; channel: string; child: string; vaccine: string; due_date: string; days: number; offset: number };

const PHONES = [
  { phone: "919800000001", who: "Ananya (U1001)" },
  { phone: "919800000002", who: "Rahul (U1002)" },
  { phone: "919800000003", who: "Fatima (U1003)" },
  { phone: "911111111111", who: "Unlinked number" },
];
const QUICK = ["Where is my order ORD-1042?", "Cancel order ORD-1043", "YES", "NO", "remind me about Aarav's vaccines on whatsapp", "seene mein dard ho raha hai"];
const time = (s: number) => new Date(s * 1000).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });

export function Channels() {
  const [phone, setPhone] = useState(PHONES[0].phone);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [outbox, setOutbox] = useState<Out[]>([]);
  const [due, setDue] = useState<Due[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [sent, setSent] = useState<{ phone: string; text: string; at: number }[]>([]);

  const load = () => {
    getJSON<Out[]>("v1/channels/outbox?limit=60").then(setOutbox).catch((e) => setMsg(String(e.message)));
    getJSON<Due[]>("v1/reminders/due").then(setDue).catch(() => undefined);
  };
  useEffect(load, []);

  async function send(t: string) {
    if (!t.trim() || busy) return;
    setBusy(true);
    setMsg(null);
    try {
      setSent((s) => [...s, { phone, text: t, at: Date.now() / 1000 }]);
      await postJSON("v1/channels/whatsapp/simulate", { phone, text: t });
      setText("");
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function sweep() {
    setBusy(true);
    try {
      const r = await postJSON<{ messages: number; doses: number; date: string }>("v1/reminders/run", {});
      setMsg(`Reminder sweep for ${r.date}: ${r.messages} message(s) covering ${r.doses} dose(s). Run it again and it sends 0, because each reminder goes out exactly once.`);
      load();
    } finally {
      setBusy(false);
    }
  }

  // Interleave what was typed here (this session) with Sahay's replies from the outbox.
  const thread = [
    ...sent.filter((s) => s.phone === phone).map((s) => ({ id: `in-${s.at}`, at: s.at, mine: true, body: s.text, kind: "" })),
    ...outbox.filter((o) => o.recipient === phone).map((o) => ({ id: o.id, at: o.created_at, mine: false, body: o.body, kind: o.kind })),
  ].sort((a, b) => a.at - b.at);

  return (
    <div className="page">
      <div className="page-head">
        <h2>WhatsApp</h2>
        <p className="sub">WhatsApp runs through the same agent as the web chat: same triage, scoped tools, confirmations and verifier. Without a Meta token, replies go to the outbox as <span className="mono">simulated</span>. Nothing leaves this machine.</p>
      </div>
      {msg && <p className="notice" role="status">{msg}</p>}
      <div className="split">
        <section className="sheet wa">
          <div className="sheet-head">
            <Phone size={16} />
            <h3 className="label">Simulator</h3>
            <span className="spacer" />
            <select value={phone} onChange={(e) => setPhone(e.target.value)} className="select" aria-label="From number">
              {PHONES.map((p) => <option key={p.phone} value={p.phone}>+{p.phone} · {p.who}</option>)}
            </select>
          </div>
          <div className="wa-thread" aria-live="polite">
            {!thread.length && <p className="muted">No messages with this number yet. Send one below.</p>}
            {thread.map((o) => (
              <div key={o.id} className={`wa-msg${o.mine ? " mine" : ""}${o.kind === "confirm" ? " confirm" : ""}`}>
                {!o.mine && o.kind && <span className="wa-kind">{o.kind}</span>}
                <p>{o.body}</p>
                <span className="wa-time mono">{time(o.at)}</span>
                {o.kind === "confirm" && (
                  <div className="row">
                    <button className="btn primary" disabled={busy} onClick={() => send("YES")}>Yes, go ahead</button>
                    <button className="btn" disabled={busy} onClick={() => send("NO")}>No</button>
                  </div>
                )}
              </div>
            ))}
          </div>
          <form onSubmit={(e) => { e.preventDefault(); send(text); }} className="composer slim">
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a WhatsApp message…" aria-label="WhatsApp message" maxLength={2000} />
            <button className="btn primary" disabled={busy || !text.trim()}><Send size={16} />Send</button>
          </form>
          <div className="chips">
            {QUICK.map((q) => <button key={q} className="chip" disabled={busy} onClick={() => send(q)}>{q}</button>)}
          </div>
        </section>

        <div className="stack">
          <section className="sheet">
            <div className="sheet-head">
              <h3 className="label">Vaccine reminders due</h3>
              <span className="spacer" />
              <button className="btn ghost" disabled={busy} onClick={sweep}><Refresh size={16} />Run reminder sweep</button>
            </div>
            <table className="table">
              <thead><tr><th>Child</th><th>Vaccine</th><th>Due</th><th>Reminder</th><th>Channel</th></tr></thead>
              <tbody>
                {due.map((d, i) => (
                  <tr key={i}>
                    <td>{d.child} <span className="mono muted">{d.user_id}</span></td>
                    <td>{d.vaccine}</td>
                    <td className="mono">{d.due_date}</td>
                    <td>{d.offset === -1 ? <span className="bad-text">overdue nudge</span> : `${d.offset} days before`}</td>
                    <td>{d.channel}</td>
                  </tr>
                ))}
                {!due.length && <tr><td colSpan={5} className="muted">Nothing due. Turn reminders on from chat: “remind me about Aarav&apos;s vaccines on whatsapp”.</td></tr>}
              </tbody>
            </table>
          </section>
          <section className="sheet">
            <div className="sheet-head"><h3 className="label">Outbox</h3><span className="spacer" /><span className="muted small">{outbox.length} message(s)</span></div>
            <table className="table">
              <thead><tr><th>Time</th><th>To</th><th>Kind</th><th>Message</th><th>Status</th></tr></thead>
              <tbody>
                {outbox.map((o) => (
                  <tr key={o.id}>
                    <td className="mono">{time(o.created_at)}</td>
                    <td className="mono">{o.recipient}</td>
                    <td>{o.kind}</td>
                    <td className="msg-cell">{o.body}</td>
                    <td>{o.status === "failed" ? <span className="bad-text" title={o.error ?? ""}>failed</span> : <span className="muted">{o.status}</span>}</td>
                  </tr>
                ))}
                {!outbox.length && <tr><td colSpan={5} className="muted">The outbox is empty.</td></tr>}
              </tbody>
            </table>
          </section>
        </div>
      </div>
    </div>
  );
}
