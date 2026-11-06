/**
 * Status badge for a decided state (verified, abstained, emergency, handed off).
 * Name kept from the earlier design; it now renders a quiet pill with a status dot.
 */
export type StampTone = "verified" | "warn" | "alarm" | "sign" | "ink";

export function Stamp({ tone, children, sub }: { tone: StampTone; children: React.ReactNode; land?: boolean; sub?: React.ReactNode }) {
  return (
    <span className={`badge badge-${tone}`}>
      <i className="badge-dot" aria-hidden />
      <span className="badge-main">{children}</span>
      {sub && <span className="badge-sub">{sub}</span>}
    </span>
  );
}
