import { useEffect } from "react";
import type { Citation } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { renderCodes } from "./AnswerText";
import { Icon } from "./ui";

export function CitationPanel({ citation, onClose }: { citation: Citation; onClose: () => void }) {
  const { t } = useI18n();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <>
      {/* backdrop on mobile */}
      <button aria-label={t.close} onClick={onClose} className="fixed inset-0 z-20 bg-black/50 backdrop-blur-sm lg:hidden" />
      <aside
        key={citation.chunk_id}
        className="fixed inset-x-0 bottom-0 z-30 max-h-[75dvh] animate-fade-up md:inset-x-auto md:left-1/2 md:w-[560px] md:-translate-x-1/2 overflow-y-auto rounded-t-2xl border-t border-white/10 bg-ink-850 p-5 shadow-2xl lg:static lg:left-auto lg:translate-x-0 lg:z-auto lg:max-h-none lg:w-[400px] lg:shrink-0 lg:rounded-none lg:border-l lg:border-t-0 lg:bg-ink-900/60 lg:backdrop-blur-xl"
      >
        <div aria-hidden className="mx-auto -mt-2 mb-3 h-1 w-10 rounded-full bg-white/20 lg:hidden" />
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-widest text-amber-300">
              <span className="flex h-[18px] min-w-[18px] items-center justify-center rounded-md bg-amber-400 px-1 text-[10.5px] text-ink-950">
                {citation.index}
              </span>
              {t.source}
            </p>
            <h2 className="mt-2 break-words text-base font-semibold leading-snug text-white">{citation.document_name}</h2>
          </div>
          <button onClick={onClose} aria-label={t.close} className="btn-ghost h-10 w-10 shrink-0 !p-0 lg:h-auto lg:w-auto lg:!p-1.5">
            <Icon name="x" />
          </button>
        </div>

        {/* "paper" page */}
        <div className="relative mt-5 rounded-xl bg-[#f6f3ec] p-5 pb-10 text-[13.5px] leading-relaxed text-stone-800 shadow-[0_20px_50px_-20px_rgb(0_0_0/0.8)]">
          <div className="absolute inset-x-0 top-0 h-1 rounded-t-xl bg-gradient-to-r from-amber-400 to-orange-500" />
          <p className="mb-3 text-[10px] font-semibold uppercase tracking-widest text-stone-500">{t.passage}</p>
          <blockquote className="whitespace-pre-wrap border-l-2 border-amber-500 pl-3 [&_.code-tag]:border-amber-600/30 [&_.code-tag]:bg-amber-500/15 [&_.code-tag]:text-amber-900">
            {renderCodes(citation.snippet)}
          </blockquote>
          <span className="absolute bottom-3 right-4 font-mono text-[11px] text-stone-500">
            {t.page} {citation.page}
          </span>
        </div>
      </aside>
    </>
  );
}
