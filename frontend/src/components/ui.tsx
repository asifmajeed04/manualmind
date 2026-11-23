import type { ReactNode, SVGProps } from "react";

export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <defs>
        <linearGradient id="logo-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#fcd34d" />
          <stop offset="1" stopColor="#f97316" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#logo-g)" />
      <path d="M9 8h9l5 5v11a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z" fill="#0b0f17" />
      <path d="M11.5 15h8M11.5 18.5h8M11.5 22h5" stroke="#fbbf24" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex shrink-0 items-center gap-2.5">
      <Logo />
      <span className={`text-[15px] font-bold tracking-tight text-white ${compact ? "hidden sm:inline" : ""}`}>
        Manual<span className="text-gradient">mind</span>
      </span>
    </div>
  );
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent ${className}`}
      aria-hidden
    />
  );
}

/** Tiny drawn flag (emoji flags don't render on Windows). */
export function FlagMark({ lang }: { lang: "de" | "en" }) {
  return lang === "de" ? (
    <span aria-hidden className="inline-flex h-2.5 w-3.5 flex-col overflow-hidden rounded-[2px] ring-1 ring-white/10">
      <span className="flex-1 bg-black" />
      <span className="flex-1 bg-red-600" />
      <span className="flex-1 bg-amber-400" />
    </span>
  ) : (
    <svg aria-hidden viewBox="0 0 60 30" className="h-2.5 w-3.5 rounded-[2px] ring-1 ring-white/10">
      <rect width="60" height="30" fill="#1e3a8a" />
      <path d="M0 0l60 30M60 0 0 30" stroke="#fff" strokeWidth="6" />
      <path d="M30 0v30M0 15h60" stroke="#fff" strokeWidth="10" />
      <path d="M30 0v30M0 15h60" stroke="#dc2626" strokeWidth="6" />
    </svg>
  );
}

export function Flag({ lang }: { lang: "de" | "en" | null }) {
  if (!lang) return <span className="text-xs text-ink-400">–</span>;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-white/[0.04] px-1.5 py-0.5 font-mono text-[11px] font-semibold text-ink-200">
      <FlagMark lang={lang} />
      {lang.toUpperCase()}
    </span>
  );
}

/** Minimal stroke icon set (Lucide-style paths). */
const paths = {
  upload: "M12 16V4m0 0-4 4m4-4 4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3",
  file: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5zm0 0v5h5",
  chat: "M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z",
  trash: "M4 7h16M10 11v6m4-6v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3",
  send: "M5 12h14m-6-6 6 6-6 6",
  stop: "M7 7h10v10H7z",
  x: "M6 6l12 12M18 6 6 18",
  globe: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zm0 0c2.5-2.5 3.5-5.5 3.5-9S14.5 5.5 12 3m0 18c-2.5-2.5-3.5-5.5-3.5-9S9.5 5.5 12 3M3.5 9h17M3.5 15h17",
  layers: "m12 3 9 5-9 5-9-5 9-5zm-9 9 9 5 9-5m-18 4 9 5 9-5",
  quote: "M7 7h4v4c0 3-1.5 5-4 6m6-10h4v4c0 3-1.5 5-4 6",
  sparkle: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z",
  logout: "M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H3",
  filter: "M4 5h16l-6 8v5l-4 2v-7L4 5z",
  check: "m5 12 5 5L20 7",
  alert: "M12 9v4m0 4h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  search: "m21 21-4.3-4.3M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z",
};

export function Icon({ name, className = "h-4 w-4", ...rest }: { name: keyof typeof paths } & SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden {...rest}>
      <path d={paths[name]} />
    </svg>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded border border-white/10 bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-ink-300">{children}</kbd>
  );
}
