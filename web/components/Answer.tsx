"use client";

/** Renders inline [source-id] markers as stamped reference codes. */
export function Answer({ text, onCite }: { text: string; onCite?: (id: string) => void }) {
  const parts = text.split(/(\[[a-z_]+#[a-z0-9-]+\]|\[tool:[a-z_]+\])/g);
  return (
    <p className="answer">
      {parts.map((p, i) => {
        const m = p.match(/^\[(.+)\]$/);
        if (!m) return <span key={i}>{p}</span>;
        const id = m[1];
        const isTool = id.startsWith("tool:");
        return (
          <button key={i} className={`cite${isTool ? " tool" : ""}`} title={isTool ? `Live data from ${id.slice(5)}` : `Policy: ${id}`} onClick={(e) => { e.stopPropagation(); onCite?.(id); }}>
            {isTool ? <><span className="cite-kind">live</span>{id.slice(5).replace(/_/g, " ")}</> : <><span className="cite-kind">ref</span>{id.split("#")[0].replace(/_/g, " ")}</>}
          </button>
        );
      })}
    </p>
  );
}
