/** One drawn icon set: 20px grid, 1.6 stroke, round caps. No emoji, no unicode stand-ins. */
type P = { size?: number; className?: string; title?: string };

function Svg({ size = 18, className, title, children }: P & { children: React.ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6}
      strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden={title ? undefined : true} role={title ? "img" : undefined}>
      {title && <title>{title}</title>}
      {children}
    </svg>
  );
}

/** The prescription mark: an R whose leg is crossed. */
export const RxMark = (p: P) => <Svg {...p}><path d="M5 17V3h5a3.5 3.5 0 0 1 0 7H5" /><path d="M8.5 10l7.5 8" /><path d="M11.5 17.5l4.5-4.5" /></Svg>;
export const Mic = (p: P) => <Svg {...p}><rect x="7.5" y="2.5" width="5" height="9" rx="2.5" /><path d="M4.5 9.5a5.5 5.5 0 0 0 11 0" /><path d="M10 15v2.5" /></Svg>;
export const Stop = (p: P) => <Svg {...p}><rect x="5" y="5" width="10" height="10" rx="1.5" /></Svg>;
export const Send = (p: P) => <Svg {...p}><path d="M3.5 10h12" /><path d="M11 5.5 15.5 10 11 14.5" /></Svg>;
export const Check = (p: P) => <Svg {...p}><path d="m4 10.5 4 4 8-9" /></Svg>;
export const Cross = (p: P) => <Svg {...p}><path d="m5 5 10 10M15 5 5 15" /></Svg>;
export const Alert = (p: P) => <Svg {...p}><path d="M10 2.8 18 17H2z" /><path d="M10 8v4" /><path d="M10 14.6v.1" /></Svg>;
export const Download = (p: P) => <Svg {...p}><path d="M10 3v10" /><path d="m5.5 8.5 4.5 4.5 4.5-4.5" /><path d="M3.5 16.5h13" /></Svg>;
export const Erase = (p: P) => <Svg {...p}><path d="M3.5 5.5h13" /><path d="M8 5.5V3.5h4v2" /><path d="M5 5.5 6 17h8l1-11.5" /></Svg>;
export const Refresh = (p: P) => <Svg {...p}><path d="M16 10a6 6 0 1 1-1.8-4.3" /><path d="M16 3.5v3.5h-3.5" /></Svg>;
export const ThumbUp = (p: P) => <Svg {...p}><path d="M6.5 9 9.5 3c1.2 0 2 .9 2 2v3h4a1.5 1.5 0 0 1 1.5 1.8l-1.2 6A1.5 1.5 0 0 1 14.3 17H6.5z" /><path d="M3 9h3.5v8H3z" /></Svg>;
export const ThumbDown = (p: P) => <Svg {...p}><path d="M13.5 11 10.5 17c-1.2 0-2-.9-2-2v-3h-4A1.5 1.5 0 0 1 3 10.2l1.2-6A1.5 1.5 0 0 1 5.7 3h7.8z" /><path d="M17 11h-3.5V3H17z" /></Svg>;
export const Sheet = (p: P) => <Svg {...p}><path d="M5 2.5h7l3 3v12H5z" /><path d="M12 2.5v3h3" /><path d="M7.5 9.5h5M7.5 12.5h5" /></Svg>;
export const Phone = (p: P) => <Svg {...p}><rect x="5.5" y="2" width="9" height="16" rx="2" /><path d="M9 15h2" /></Svg>;
export const Panel = (p: P) => <Svg {...p}><rect x="3" y="3.5" width="14" height="13" rx="1.5" /><path d="M12 3.5v13" /></Svg>;
