"use client";
import { useState } from "react";
import { Alert } from "./Icons";
import type { Trace } from "@/lib/api";

const KINDS = ["node", "llm", "tool", "retrieval", "guard"] as const;

export function Waterfall({ trace }: { trace: Trace }) {
  const [sel, setSel] = useState<string | null>(null);
  const spans = [...trace.spans].sort((a, b) => a.offset_ms - b.offset_ms);
  const total = Math.max(1, ...spans.map((s) => s.offset_ms + s.duration_ms));
  const depth = (id: string | null): number => {
    let d = 0;
    let cur = spans.find((s) => s.span_id === id);
    while (cur?.parent_id) {
      d++;
      cur = spans.find((s) => s.span_id === cur!.parent_id);
    }
    return d;
  };
  const picked = spans.find((s) => s.span_id === sel);
  return (
    <div className="waterfall">
      <div className="legend">
        {KINDS.map((k) => <span key={k}><i className={`k-${k}`} />{k}</span>)}
      </div>
      <div className="wf">
        {spans.map((s) => (
          <button key={s.span_id} className="wf-row" aria-pressed={sel === s.span_id} onClick={() => setSel(sel === s.span_id ? null : s.span_id)}>
            <span className="wf-name mono" style={{ paddingLeft: depth(s.span_id) * 10 }} title={s.name}>
              {s.status === "error" && <Alert size={12} className="bad-text" />}{s.name}
            </span>
            <span className="wf-track">
              <span className={`wf-bar k-${s.kind}`} style={{ left: `${(s.offset_ms / total) * 100}%`, width: `${(s.duration_ms / total) * 100}%` }} />
            </span>
            <span className="wf-dur mono">{s.duration_ms.toFixed(1)}</span>
          </button>
        ))}
      </div>
      {picked && <pre className="attrs">{JSON.stringify(picked.attributes, null, 2)}</pre>}
    </div>
  );
}
