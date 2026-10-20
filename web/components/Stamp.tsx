/**
 * A rubber stamp: the product's mark for a decided state (verified, abstained, emergency, handed off).
 * `land` plays the one authored motion in the app — the stamp coming down — and only on a fresh answer.
 */
export type StampTone = "verified" | "warn" | "alarm" | "sign" | "ink";

export function Stamp({ tone, children, land, sub }: { tone: StampTone; children: React.ReactNode; land?: boolean; sub?: React.ReactNode }) {
  return (
    <span className={`stamp stamp-${tone}${land ? " land" : ""}`}>
      <span className="stamp-main">{children}</span>
      {sub && <span className="stamp-sub">{sub}</span>}
    </span>
  );
}
