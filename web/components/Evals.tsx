"use client";
import { useEffect, useState } from "react";
import { Check, Cross } from "./Icons";
import { Stamp } from "./Stamp";
import { getJSON } from "@/lib/api";

type Case = { id: string; pass: boolean; checks: Record<string, boolean>; intent: string; tools: string[]; answer: string; latency_ms: number };
type CF = { id: string; variants: number; consistent: boolean; decisions: { decision: unknown[]; variants: string[] }[] };
type Report = { set?: string; timestamp: string; config: Record<string, unknown>; metrics: Record<string, number>; cases: Case[]; counterfactual?: CF[] | null };

const QUALITY: [string, string][] = [
  ["intent_accuracy", "Intent accuracy"], ["tool_recall", "Tool recall"], ["tool_args_accuracy", "Tool args accuracy"],
  ["retrieval_recall@5", "Retrieval recall@5"], ["retrieval_mrr", "Retrieval MRR"], ["grounded_rate", "Grounded rate"],
  ["answer_pass_rate", "Answer assertions"], ["avg_llm_calls", "LLM calls per case"],
];
// Hard gates: any break blocks the merge. Target is perfect (leak: zero).
const GATES: [string, string, number][] = [
  ["emergency_recall", "Emergency recall", 1], ["confirmation_accuracy", "Write confirmation", 1],
  ["cross_user_leak", "Cross-user leak", 0], ["counterfactual_consistency", "Counterfactual consistency", 1],
];
const pct = (k: string, v: number) => (k === "avg_llm_calls" ? v.toFixed(2) : `${(v * 100).toFixed(1)}%`);

export function Evals() {
  const [r, setR] = useState<Report | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [set, setSet] = useState<"golden" | "heldout">("golden");
  useEffect(() => {
    setErr(null);
    getJSON<Report>(`v1/evals/latest?set=${set}`).then(setR).catch((e) => { setR(null); setErr(String(e.message)); });
  }, [set]);
  const passed = r?.cases.filter((c) => c.pass).length ?? 0;
  return (
    <div className="page office">
      <div className="page-head">
        <h2>Evals</h2>
        <p className="sub">The golden set runs end to end through the real graph. CI blocks a merge if a metric drops beyond tolerance or a hard gate breaks. The held-out set is never used for tuning; it is reported, not gated.</p>
      </div>
      <nav className="tabs inline" role="tablist" aria-label="Eval set">
        {(["golden", "heldout"] as const).map((k) => (
          <button key={k} role="tab" className="tab" aria-selected={set === k} onClick={() => setSet(k)}>{k === "golden" ? "Golden (gated)" : "Held-out"}</button>
        ))}
      </nav>
      {err && <div className="err" role="alert">{err}</div>}
      {r && (
        <>
          <section className="lead office-lead">
            <p className="lead-value">
              <span className="big">{passed}<small>/ {r.cases.length}</small></span>
              <span className="lead-name">cases pass</span>
            </p>
            <p className="lead-note mono">{r.set ?? "golden"} · {r.timestamp} · {Object.entries(r.config).map(([k, v]) => `${k}=${v}`).join(" · ")}</p>
          </section>

          <div className="split even">
            <section className="sheet">
              <h3 className="section-head">Hard gates</h3>
              <ul className="gates">
                {GATES.filter(([k]) => k in r.metrics).map(([k, label, target]) => {
                  const ok = r.metrics[k] === target;
                  return (
                    <li key={k}>
                      <span>{label}</span>
                      <span className="mono">{pct(k, r.metrics[k])}</span>
                      {ok ? <Stamp tone="verified">Pass</Stamp> : <Stamp tone="alarm">Broken</Stamp>}
                    </li>
                  );
                })}
              </ul>
            </section>
            <section className="sheet">
              <h3 className="section-head">Quality</h3>
              <dl className="kv wide">
                {QUALITY.filter(([k]) => k in r.metrics).map(([k, label]) => (
                  <div key={k}><dt>{label}</dt><dd className="mono">{pct(k, r.metrics[k])}</dd></div>
                ))}
              </dl>
            </section>
          </div>

          {!!r.counterfactual?.length && (
            <section className="sheet">
              <h3 className="section-head">Counterfactual invariance · {r.metrics.counterfactual_runs} runs</h3>
              <p className="muted">Same request, one detail changed: gender, age, name, locality, language. The decision (route, intent, emergency, tools, confirmation) must not move.</p>
              <div className="chips">
                {r.counterfactual.map((c) => (
                  <span key={c.id} className={`chip static ${c.consistent ? "" : "bad"}`} title={c.decisions.map((d) => `${JSON.stringify(d.decision)} <- ${d.variants.length} variant(s)`).join("\n")}>
                    {c.consistent ? <Check size={14} /> : <Cross size={14} />}{c.id.replace("cf-", "")} <span className="mono muted">×{c.variants}</span>
                  </span>
                ))}
              </div>
            </section>
          )}

          <section className="sheet flush">
            <table className="table dense">
              <thead><tr><th>Case</th><th>Result</th><th>Intent</th><th>Tools</th><th>Failed checks</th><th className="num">ms</th></tr></thead>
              <tbody>
                {r.cases.map((c) => (
                  <tr key={c.id} title={c.answer}>
                    <td className="mono">{c.id}</td>
                    <td>{c.pass ? <span className="ok-text"><Check size={14} /> pass</span> : <span className="bad-text"><Cross size={14} /> fail</span>}</td>
                    <td>{c.intent.replace(/_/g, " ")}</td>
                    <td className="mono">{c.tools.join(", ")}</td>
                    <td className="mono bad-text">{Object.entries(c.checks).filter(([, v]) => !v).map(([k]) => k).join(", ")}</td>
                    <td className="num mono">{c.latency_ms}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}
