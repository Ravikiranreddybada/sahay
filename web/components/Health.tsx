"use client";
import { useEffect, useState } from "react";
import { Download, Erase } from "./Icons";
import { Stamp } from "./Stamp";
import { delJSON, getJSON } from "@/lib/api";
import { persona } from "@/lib/personas";

type Member = { member: string; relation: string; consent?: "active" | "expired" | "none"; consent_scopes?: string[]; consent_expires?: string };
type Med = { name: string; molecules: string[]; strength: string | null; instructions: string; prescriber: string; specialty: string; started_on: string; resolved: boolean };
type Dup = { molecule: string; products: string[]; prescribers: string[] };
type Inter = { between: string[]; products: string[]; severity: "major" | "moderate"; effect: string; source: string };
type Point = { date: string; value: number; unit: string; lab: string; flag: string; reported_as?: string; conversion?: string };
type Trend = { analyte: string; unit: string; points: Point[]; reference_range: string | null; direction?: string; change?: string; steady_rise?: boolean; latest_flag: string | null; labs: string[] };
type Err = { error: string };
type Overview = {
  medications: ({ member: string; medications: Med[]; stopped: string[]; duplicates: Dup[]; interactions: Inter[]; note: string } | Err);
  labs: ({ trends: Trend[]; note?: string } | Err);
  brief: ({ appointment: { doctor: string; specialty: string; time: string; mode: string } | null; questions: string[] } | Err);
};

const isErr = (x: unknown): x is Err => !!x && typeof x === "object" && "error" in x;
const FLAG: Record<string, string> = { high: "H", low: "L" };
const fmtDate = (d: string) => new Date(d).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

export function Health({ user }: { user: string }) {
  const [members, setMembers] = useState<Member[]>([]);
  const [member, setMember] = useState<string>("self");
  const [data, setData] = useState<Overview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [rights, setRights] = useState<string | null>(null);
  const [confirmErase, setConfirmErase] = useState(false);

  useEffect(() => {
    setMember("self");
    setRights(null);
    setErr(null);
    setConfirmErase(false);
    getJSON<{ members: Member[] }>("v1/health/members", user).then((r) => setMembers(r.members)).catch((e) => setErr(String(e.message)));
  }, [user]);
  useEffect(() => {
    setData(null);
    const q = member === "self" ? "" : `?member=${encodeURIComponent(member)}`;
    getJSON<Overview>(`v1/health/overview${q}`, user).then(setData).catch((e) => setErr(String(e.message)));
  }, [user, member]);

  async function exportData() {
    const d = await getJSON<Record<string, unknown>>("v1/me/data", user);
    const url = URL.createObjectURL(new Blob([JSON.stringify(d, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `sahay-my-data-${user}.json`;
    a.click();
    URL.revokeObjectURL(url);
    setRights("Downloaded everything Sahay holds about you (right of access).");
  }
  async function erase() {
    const r = await delJSON<{ threads_erased: number; traces_erased: number }>("v1/me/history", user);
    setConfirmErase(false);
    setRights(`Erased ${r.threads_erased} conversation thread(s) and ${r.traces_erased} trace(s). Orders, claims and medical records stay (legal retention).`);
  }

  const meds = data && !isErr(data.medications) ? data.medications : null;
  const labs = data && !isErr(data.labs) ? data.labs : null;
  const brief = data && !isErr(data.brief) ? data.brief : null;
  const blocked = data && isErr(data.medications) ? data.medications.error : null;
  const sel = members.find((m) => (m.relation === "self" ? "self" : m.relation) === member);
  const me = persona(user);
  // The one big number: the latest value that is out of range, else the one rising on every report.
  const lead = labs?.trends.find((t) => t.latest_flag && t.latest_flag !== "in_range") ?? labs?.trends.find((t) => t.steady_rise);
  const leadPt = lead?.points.at(-1);
  const footnotes = labs?.trends.flatMap((t) => t.points.filter((p) => p.reported_as).map((p) => ({ t, p }))) ?? [];

  return (
    <div className="page report">
      <div className="report-sheet">
        <header className="report-head">
          <div>
            <h2>Family health record</h2>
            <p className="sub">Brands resolved to molecules. Duplicates and interactions come from the medicine database, never from the model. Lab values from different labs are put on one unit, with the conversion shown.</p>
          </div>
          <div className="report-actions">
            <button className="btn ghost" onClick={exportData}><Download size={16} />Download my data</button>
            {confirmErase ? (
              <span className="row">
                <button className="btn danger" onClick={erase}>Erase chat history</button>
                <button className="btn ghost" onClick={() => setConfirmErase(false)}>Keep it</button>
              </span>
            ) : <button className="btn ghost" onClick={() => setConfirmErase(true)}><Erase size={16} />Erase chat history</button>}
          </div>
        </header>

        <dl className="patient-block">
          <div><dt>Requested by</dt><dd>{me.name} <span className="mono muted">{me.id}</span></dd></div>
          <div>
            <dt>Records of</dt>
            <dd>
              <span className="tabs inline" role="tablist" aria-label="Whose records">
                {members.map((m) => {
                  const key = m.relation === "self" ? "self" : m.relation;
                  return (
                    <button key={key} role="tab" className="tab" aria-selected={member === key} onClick={() => setMember(key)}>
                      {m.relation === "self" ? "Me" : `${m.member} · ${m.relation}`}
                    </button>
                  );
                })}
              </span>
            </dd>
          </div>
          <div>
            <dt>Consent</dt>
            <dd>
              {!sel || sel.relation === "self" ? <span className="muted">Own record</span>
                : sel.consent === "active" ? <span>Active until {fmtDate(sel.consent_expires!)} · <span className="muted">{sel.consent_scopes?.join(", ")}</span></span>
                : <Stamp tone="alarm" sub={sel.consent_expires ? `on ${fmtDate(sel.consent_expires)}` : undefined}>Consent {sel.consent}</Stamp>}
            </dd>
          </div>
        </dl>

        {rights && <p className="notice" role="status">{rights}</p>}
        {err && <div className="err" role="alert">{err}</div>}
        {!data && !err && <p className="muted loading">Opening records…</p>}
        {blocked && (
          <section className="closed" role="alert">
            <Stamp tone="alarm">Access closed</Stamp>
            <p>{blocked}</p>
          </section>
        )}

        {lead && leadPt && (
          <section className="lead">
            <span className="label">Worth discussing first</span>
            <p className="lead-value">
              <span className="lead-name">{lead.analyte}</span>
              <span className="big">{leadPt.value}<small>{leadPt.unit}</small></span>
              {FLAG[leadPt.flag] && <span className="flag-letter">{FLAG[leadPt.flag]}</span>}
            </p>
            <p className="lead-note">{lead.steady_rise ? "Higher on every report. " : ""}{lead.change}. Reference range {lead.reference_range}.</p>
          </section>
        )}

        {meds && (
          <section className="block">
            <h3 className="section-head">Current medicines</h3>
            <table className="table">
              <thead><tr><th>Product</th><th>Contains</th><th>How to take</th><th>Prescribed by</th></tr></thead>
              <tbody>
                {meds.medications.map((m) => (
                  <tr key={m.name}>
                    <td><b>{m.name}</b><span className="cell-sub mono">{m.strength}</span></td>
                    <td>{m.molecules.length ? m.molecules.map((x) => {
                      const dup = meds.duplicates.some((d) => d.molecule === x);
                      return <span key={x} className={`mol${dup ? " dup" : ""}`} title={dup ? "Also in another product on this list" : undefined}>{x}{dup && <sup>2×</sup>}</span>;
                    }) : <span className="warn">not in database</span>}</td>
                    <td>{m.instructions}</td>
                    <td>{m.prescriber}<span className="cell-sub">{m.specialty}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!!meds.stopped.length && <p className="muted small">Stopped: {meds.stopped.join(", ")}</p>}
          </section>
        )}

        {meds && (
          <section className="block">
            <h3 className="section-head">Flags from the medicine database</h3>
            {!meds.duplicates.length && !meds.interactions.length && <p className="muted">None recorded. That is not a safety verdict.</p>}
            <ul className="flags">
              {meds.interactions.map((i) => (
                <li key={i.between.join()} className={`flagrow ${i.severity}`}>
                  <span className="flag-kind">{i.severity} interaction</span>
                  <div>
                    <p><b>{i.products[0]} + {i.products[1]}</b>: {i.effect}.</p>
                    <p className="muted small">Source: {i.source}</p>
                  </div>
                </li>
              ))}
              {meds.duplicates.map((d) => (
                <li key={d.molecule} className="flagrow dup">
                  <span className="flag-kind">same medicine twice</span>
                  <div><p><b>{d.molecule}</b> is in {d.products.join(" and ")}, from {d.prescribers.join(" and ")}.</p></div>
                </li>
              ))}
            </ul>
            <p className="fineprint">{meds.note}</p>
          </section>
        )}

        {labs && (
          <section className="block">
            <h3 className="section-head">Lab results over time</h3>
            {labs.note && <p className="muted">{labs.note}</p>}
            {!!labs.trends.length && (
              <table className="table labs">
                <thead><tr><th>Test</th><th className="num">Latest</th><th>Flag</th><th>Reference</th><th>Trend</th><th>Reported by</th></tr></thead>
                <tbody>
                  {labs.trends.map((t) => {
                    const last = t.points.at(-1)!;
                    return (
                      <tr key={t.analyte}>
                        <td><b>{t.analyte}</b><span className="cell-sub">{t.direction}{t.steady_rise ? " on every report" : ""}</span></td>
                        <td className="num"><b className={FLAG[last.flag] ? "out" : ""}>{last.value}</b> <span className="muted">{t.unit}</span></td>
                        <td>{FLAG[last.flag] ? <span className="flag-letter">{FLAG[last.flag]}</span> : <span className="muted">—</span>}</td>
                        <td className="mono small">{t.reference_range ?? "n/a"}</td>
                        <td><Spark t={t} /></td>
                        <td className="small">{t.labs.join(", ")}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
            {!!footnotes.length && (
              <ol className="footnotes">
                {footnotes.map(({ t, p }) => (
                  <li key={t.analyte + p.date}><b>{t.analyte}</b>, {fmtDate(p.date)}, {p.lab}: reported as <span className="mono">{p.reported_as}</span>, shown as <span className="mono">{p.value} {p.unit}</span>. <span className="muted">{p.conversion}</span></li>
                ))}
              </ol>
            )}
          </section>
        )}

        {brief && (
          <section className="block brief">
            <h3 className="section-head">Visit brief</h3>
            {brief.appointment
              ? <p className="appt"><b>{brief.appointment.doctor}</b>, {brief.appointment.specialty} · {brief.appointment.time} · {brief.appointment.mode.replace("_", " ")}</p>
              : <p className="muted">No upcoming appointment on record.</p>}
            {brief.questions.length ? (
              <>
                <p className="muted small">Questions worth asking</p>
                <ol className="questions">{brief.questions.map((q) => <li key={q}>{q}</li>)}</ol>
              </>
            ) : <p className="muted">Nothing in the records needs flagging.</p>}
          </section>
        )}
        <p className="fineprint report-foot">Demo records (synthetic). A family member&apos;s records open only under their unexpired, scoped consent, checked inside the MCP server — the same path the chat uses.</p>
      </div>
    </div>
  );
}

/** Small trend line with the reference band behind it. Out-of-range points are filled red; converted points are ringed. */
function Spark({ t }: { t: Trend }) {
  const W = 168, H = 44, P = 6;
  const vals = t.points.map((p) => p.value);
  const range = t.reference_range?.match(/[\d.]+/g)?.map(Number) ?? [];
  const lo = t.reference_range?.startsWith("below") ? null : range[0] ?? null;
  const hi = t.reference_range?.startsWith("below") ? range[0] : t.reference_range?.startsWith("above") ? null : range[1] ?? null;
  const all = [...vals, ...(lo != null ? [lo] : []), ...(hi != null ? [hi] : [])];
  const min = Math.min(...all) * 0.96, max = Math.max(...all) * 1.04;
  const x = (i: number) => P + (vals.length === 1 ? (W - 2 * P) / 2 : (i * (W - 2 * P)) / (vals.length - 1));
  const y = (v: number) => H - P - ((v - min) / (max - min || 1)) * (H - 2 * P);
  const bandTop = y(hi ?? max), bandBot = y(lo ?? min);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="spark" role="img" aria-label={`${t.analyte}: ${t.change ?? ""}`}>
      <rect x={P} y={bandTop} width={W - 2 * P} height={Math.max(0, bandBot - bandTop)} className="band" />
      <polyline points={vals.map((v, i) => `${x(i)},${y(v)}`).join(" ")} className="line" />
      {t.points.map((p, i) => (
        <circle key={p.date} cx={x(i)} cy={y(p.value)} r={3.5} className={`pt${FLAG[p.flag] ? " out" : ""}${p.reported_as ? " converted" : ""}`}>
          <title>{`${p.value} ${p.unit} · ${p.date} · ${p.lab}${p.reported_as ? ` · reported as ${p.reported_as}` : ""}`}</title>
        </circle>
      ))}
    </svg>
  );
}
