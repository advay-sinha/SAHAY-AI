import type { ReactNode, SVGProps } from "react";

const paths: Record<string, ReactNode> = {
  queue: <><path d="M4 6h2v2H4zM9 6h11M4 11h2v2H4zM9 11h11M4 16h2v2H4zM9 16h11" /></>,
  audit: <><path d="M12 3 5 6v5c0 4.6 2.9 8.1 7 10 4.1-1.9 7-5.4 7-10V6l-7-3Z" /><path d="m9 12 2 2 4-4" /></>,
  case: <><path d="M5 3h11l3 3v15H5z" /><path d="M8 9h8M8 13h8M8 17h5" /></>,
  supervisor: <><path d="M12 13a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM5 21v-2a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v2" /><path d="M19 8h3M20.5 6.5v3" /></>,
  shield: <><path d="M12 2 4 5v6c0 5 3.4 9.1 8 11 4.6-1.9 8-6 8-11V5l-8-3Z" /><path d="M9 11h6M9 14h4" /></>,
  alert: <><path d="M12 3 2.5 20h19L12 3Z" /><path d="M12 9v5M12 17h.01" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  lock: <><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3M12 15v2" /></>,
  eye: <><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
  eyeOff: <><path d="m3 3 18 18M10.6 6.2A10.8 10.8 0 0 1 12 6c6.5 0 10 6 10 6a17 17 0 0 1-2.1 2.8M6.7 6.7C3.7 8.4 2 12 2 12s3.5 6 10 6a10.8 10.8 0 0 0 4.3-.9M10 10a3 3 0 0 0 4 4" /></>,
  arrow: <path d="M5 12h14M14 7l5 5-5 5" />,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
  bolt: <path d="m13 2-8 12h7l-1 8 8-12h-7l1-8Z" />,
  logout: <><path d="M10 4H4v16h6M14 8l4 4-4 4M8 12h10" /></>,
  search: <><circle cx="10" cy="10" r="6" /><path d="m15 15 5 5" /></>,
  refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M18 12a6 6 0 0 0-10.5-4M6 12a6 6 0 0 0 10.5 4" /></>,
  radio: <><path d="M5 8a9 9 0 0 1 0 8M9 5a13 13 0 0 1 0 14" /><circle cx="16" cy="12" r="2" /></>,
};

export function ConsoleIcon({ name, ...props }: { name: string } & SVGProps<SVGSVGElement>) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
    strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name] ?? <circle cx="12" cy="12" r="3" />}</svg>;
}

export function SahayMark({ compact = false }: { compact?: boolean }) {
  return <div className="flex items-center gap-2" aria-label="SAHAY-AI Executive Console">
    <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-inverse-surface text-cyan-300"><ConsoleIcon name="shield" className="h-7 w-7" /></span>
    {!compact && <span className="leading-none"><strong className="block font-display text-base tracking-[0.12em] text-white">SAHAY-AI</strong><small className="mt-1 block text-[9px] tracking-[0.2em] text-slate-400">EXECUTIVE CONSOLE</small></span>}
  </div>;
}
