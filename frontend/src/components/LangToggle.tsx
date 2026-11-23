import { useI18n, type Lang } from "../lib/i18n";

export function LangToggle() {
  const { lang, setLang } = useI18n();
  return (
    <div className="flex rounded-lg border border-white/10 bg-white/[0.03] p-0.5 text-[11px] font-semibold" role="group" aria-label="Language">
      {(["de", "en"] as Lang[]).map((l) => (
        <button
          key={l}
          onClick={() => setLang(l)}
          aria-pressed={lang === l}
          className={`rounded-md px-3 py-2.5 transition sm:px-2 sm:py-1 ${lang === l ? "bg-white/10 text-white" : "text-ink-400 hover:text-ink-200"}`}
        >
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
