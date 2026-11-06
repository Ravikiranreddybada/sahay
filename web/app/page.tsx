"use client";
import { useEffect, useState } from "react";
import { Channels } from "@/components/Channels";
import { Chat } from "@/components/Chat";
import { Evals } from "@/components/Evals";
import { Health } from "@/components/Health";
import { Activity, Book, ChatIcon, Gauge, Heart, Logo, Phone } from "@/components/Icons";
import { Knowledge } from "@/components/Knowledge";
import { Traces } from "@/components/Traces";
import { PERSONAS, persona } from "@/lib/personas";
import { publicJSON } from "@/lib/api";

const AREAS = {
  patient: { label: "Patient", tabs: ["Chat", "Health", "WhatsApp"] },
  office: { label: "Operations", tabs: ["Traces", "Evals", "Knowledge"] },
} as const;
const TAB_ICON: Record<string, (p: { size?: number }) => React.ReactElement> = {
  Chat: ChatIcon, Health: Heart, WhatsApp: Phone, Traces: Activity, Evals: Gauge, Knowledge: Book,
};
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
    <div className={`app area-${area}`}>
      <aside className="side">
        <div className="brand">
          <Logo size={26} className="brand-logo" title="Sahay" />
          <span className="brand-name">Sahay</span>
          <span className="brand-deva" lang="hi">सहाय</span>
        </div>
        <div className="areas" role="tablist" aria-label="Area">
          {(Object.keys(AREAS) as Area[]).map((a) => (
            <button key={a} role="tab" aria-selected={area === a} className="area" onClick={() => setArea(a)}>{AREAS[a].label}</button>
          ))}
        </div>
        <nav className="nav" role="tablist" aria-label={AREAS[area].label}>
          {AREAS[area].tabs.map((t) => {
            const Icon = TAB_ICON[t];
            return (
              <button key={t} role="tab" className="nav-item" aria-selected={current === t} onClick={() => setTab({ ...tab, [area]: t })}>
                <Icon size={17} />{t}
              </button>
            );
          })}
        </nav>
        <div className="side-foot">
          <div className="engine-card" title={meta ? `kb ${meta.kb_version}${meta.storage ? ` · ${meta.storage.checkpoints} · ${meta.storage.cache}` : ""}` : undefined}>
            <span className="label">Engine</span>
            <div className="engine">
              {meta === undefined ? "Connecting…" : meta === null ? <b className="engine-down">Backend offline</b> : (
                <>
                  <span className={`engine-dot${meta.mode === "offline" ? " off" : ""}`} />
                  <span>{meta.mode === "offline" ? "Offline engine" : `${meta.models.fast} / ${meta.models.smart}`}</span>
                  <span className="engine-sep">{meta.tools.length} tools</span>
                </>
              )}
            </div>
          </div>
          <div className="me">
            <span className="avatar" aria-hidden>{area === "patient" ? persona(user).name.split(" ").map((w) => w[0]).join("") : "OP"}</span>
            {area === "patient" ? (
              <label className="who">
                <span className="label">Signed in as</span>
                <select value={user} onChange={(e) => setUser(e.target.value)} aria-label="Signed in as">
                  {PERSONAS.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.id}</option>)}
                </select>
              </label>
            ) : <div className="who"><span className="label">Signed in as</span><span className="who-ops">Operations</span></div>}
          </div>
        </div>
      </aside>
      <main className="main">
        {/* Chat stays mounted so a conversation survives a look at Health or Operations. */}
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
