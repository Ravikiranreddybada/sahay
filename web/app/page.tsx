"use client";
import { useEffect, useState } from "react";
import { Channels } from "@/components/Channels";
import { Chat } from "@/components/Chat";
import { Evals } from "@/components/Evals";
import { Health } from "@/components/Health";
import { RxMark } from "@/components/Icons";
import { Knowledge } from "@/components/Knowledge";
import { Traces } from "@/components/Traces";
import { PERSONAS } from "@/lib/personas";
import { publicJSON } from "@/lib/api";

const AREAS = {
  patient: { label: "Patient", tabs: ["Chat", "Health", "WhatsApp"] },
  office: { label: "Office copy", tabs: ["Traces", "Evals", "Knowledge"] },
} as const;
type Area = keyof typeof AREAS;
type Meta = { mode: string; models: { fast: string; smart: string }; prompt_version: string; kb_version: string; tools: string[]; storage?: { checkpoints: string; cache: string } };

export default function Home() {
  const [area, setArea] = useState<Area>("patient");
  const [tab, setTab] = useState<Record<Area, string>>({ patient: "Chat", office: "Traces" });
  const [user, setUser] = useState<string>(PERSONAS[0].id);
  const [meta, setMeta] = useState<Meta | null | undefined>(undefined);
  useEffect(() => { publicJSON<Meta>("v1/meta").then(setMeta).catch(() => setMeta(null)); }, []);
  const current = tab[area];

  return (
    <div className={`shell area-${area}`}>
      <header className="letterhead">
        <div className="lh-band">
          <div className="lh-brand">
            <RxMark size={26} className="lh-rx" />
            <span className="lh-name">Sahay</span>
            <span className="lh-deva" lang="hi">सहाय</span>
            <span className="lh-line">Grounded care assistant · every answer cites its source · emergencies go to a human</span>
          </div>
          <div className="areas" role="tablist" aria-label="Area">
            {(Object.keys(AREAS) as Area[]).map((a) => (
              <button key={a} role="tab" aria-selected={area === a} className="area" onClick={() => setArea(a)}>{AREAS[a].label}</button>
            ))}
          </div>
        </div>
        <div className="lh-sub">
          <nav className="tabs" role="tablist" aria-label={AREAS[area].label}>
            {AREAS[area].tabs.map((t) => (
              <button key={t} role="tab" className="tab" aria-selected={current === t} onClick={() => setTab({ ...tab, [area]: t })}>{t}</button>
            ))}
          </nav>
          <span className="spacer" />
          {area === "patient" ? (
            <label className="who">
              <span className="label">Patient</span>
              <select value={user} onChange={(e) => setUser(e.target.value)} aria-label="Signed in as">
                {PERSONAS.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.id}</option>)}
              </select>
            </label>
          ) : <span className="who"><span className="label">Signed in as</span> ops</span>}
          <span className="engine" title={meta ? `kb ${meta.kb_version}${meta.storage ? ` · ${meta.storage.checkpoints} · ${meta.storage.cache}` : ""}` : undefined}>
            {meta === undefined ? "Connecting…" : meta === null ? <b className="engine-down">Backend offline</b> : (
              <>
                <span className={`engine-dot${meta.mode === "offline" ? " off" : ""}`} />
                {meta.mode === "offline" ? "Offline engine" : `${meta.models.fast} / ${meta.models.smart}`}
                <span className="engine-sep">prompt {meta.prompt_version}</span>
                <span className="engine-sep">{meta.tools.length} tools</span>
              </>
            )}
          </span>
        </div>
      </header>
      <main className="main">
        {/* Chat stays mounted so a conversation survives a look at Health or the office copy. */}
        <div className="keep" hidden={current !== "Chat"}><Chat user={user} /></div>
        {current === "Health" && <Health user={user} />}
        {current === "WhatsApp" && <Channels />}
        {current === "Traces" && <Traces />}
        {current === "Evals" && <Evals />}
        {current === "Knowledge" && <Knowledge />}
      </main>
    </div>
  );
}
