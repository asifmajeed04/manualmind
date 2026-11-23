import { useEffect, useRef, useState, type DragEvent } from "react";
import { api, type DocumentRow } from "../lib/api";
import { errorText, useI18n } from "../lib/i18n";
import { Flag, Icon, Spinner } from "./ui";

const MAX_BYTES = 20 * 1024 * 1024;
const POLL_MS = 2000;

type Props = {
  docs: DocumentRow[];
  setDocs: (fn: (d: DocumentRow[]) => DocumentRow[]) => void;
  loadError: string | null;
  onOpenChat: () => void;
};

export function DocumentsPage({ docs, setDocs, loadError, onOpenChat }: Props) {
  const { t, lang } = useI18n();
  const [uploading, setUploading] = useState<string[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Poll every processing document until it's ready/failed.
  const processingIds = docs.filter((d) => d.status === "processing").map((d) => d.id).join(",");
  useEffect(() => {
    if (!processingIds) return;
    const timer = setInterval(async () => {
      for (const id of processingIds.split(",")) {
        try {
          const fresh = await api.getDocument(id);
          setDocs((ds) => ds.map((d) => (d.id === id ? fresh : d)));
        } catch {
          /* try again next tick */
        }
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [processingIds, setDocs]);

  async function handleFiles(files: FileList | null) {
    if (!files?.length) return;
    const errs: string[] = [];
    const valid: File[] = [];
    for (const f of Array.from(files)) {
      if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) errs.push(t.notPdf(f.name));
      else if (f.size > MAX_BYTES) errs.push(t.tooLarge(f.name));
      else valid.push(f);
    }
    setErrors(errs);
    for (const f of valid) {
      setUploading((u) => [...u, f.name]);
      try {
        const doc = await api.uploadDocument(f);
        setDocs((ds) => [doc, ...ds]);
      } catch (err) {
        setErrors((e) => [...e, `${f.name}: ${errorText(t, err)}`]);
      } finally {
        setUploading((u) => u.filter((n) => n !== f.name));
      }
    }
  }

  async function remove(doc: DocumentRow) {
    if (!window.confirm(t.confirmDelete(doc.name))) return;
    try {
      await api.deleteDocument(doc.id);
      setDocs((ds) => ds.filter((d) => d.id !== doc.id));
    } catch (err) {
      setErrors([errorText(t, err)]);
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    handleFiles(e.dataTransfer.files);
  };

  const ready = docs.filter((d) => d.status === "ready");
  const pages = ready.reduce((s, d) => s + (d.page_count ?? 0), 0);
  const fmtDate = (iso: string) =>
    new Date(iso).toLocaleDateString(lang === "de" ? "de-DE" : "en-GB", { day: "2-digit", month: "short", year: "numeric" });

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">{t.docsTitle}</h1>
          <p className="mt-1 text-sm text-ink-400">{t.docsSubtitle}</p>
        </div>
        {ready.length > 0 && (
          <div className="flex items-center gap-3">
            <Stat value={ready.length} label={t.ready} />
            <Stat value={pages} label={t.pages} />
            <button onClick={onOpenChat} className="btn-primary">
              <Icon name="chat" /> {t.chat}
            </button>
          </div>
        )}
      </div>

      {/* Drop zone */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={`group relative mt-6 cursor-pointer overflow-hidden rounded-2xl border border-dashed px-6 py-7 text-center transition-all sm:py-10 ${
          dragOver
            ? "scale-[1.01] border-amber-400 bg-amber-400/[0.07] shadow-[0_0_60px_-10px_rgb(251_191_36/0.5)]"
            : "border-white/15 bg-white/[0.02] hover:border-amber-400/50 hover:bg-white/[0.035]"
        }`}
      >
        <div
          className={`mx-auto flex h-12 w-12 items-center justify-center rounded-xl border transition ${
            dragOver ? "border-amber-400/50 bg-amber-400/20 text-amber-200" : "border-white/10 bg-white/5 text-amber-300 group-hover:-translate-y-0.5"
          }`}
        >
          <Icon name="upload" className="h-5 w-5" />
        </div>
        <p className="mt-3 font-semibold text-white">
          <span className="pointer-coarse:hidden">{dragOver ? t.dropActive : t.dropTitle}</span>
          <span className="hidden pointer-coarse:inline">{t.tapTitle}</span>
        </p>
        <p className="mt-1 text-sm text-ink-400">
          <span className="pointer-coarse:hidden">{t.dropHint}</span>
          <span className="hidden pointer-coarse:inline">{t.tapHint}</span>
        </p>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          hidden
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {uploading.map((n) => (
        <div key={n} className="glass relative mt-3 overflow-hidden rounded-xl px-4 py-3">
          <div className="shimmer absolute inset-0" />
          <p className="relative flex items-center gap-2 text-sm text-ink-200">
            <Spinner className="text-amber-300" /> {t.uploading}: <span className="truncate font-medium text-white">{n}</span>
          </p>
        </div>
      ))}
      {[...(loadError ? [loadError] : []), ...errors].map((e, i) => (
        <p key={i} className="mt-3 flex items-start gap-2 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-2.5 text-sm text-red-300">
          <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
          {e}
        </p>
      ))}

      {/* Library */}
      {docs.length === 0 ? (
        <div className="mt-10 text-center">
          <p className="mx-auto max-w-sm text-sm text-ink-400">{t.noDocuments}</p>
        </div>
      ) : (
        <ul className="mt-6 grid gap-3 sm:grid-cols-2">
          {docs.map((d, i) => (
            <li
              key={d.id}
              className="glass group relative animate-fade-up overflow-hidden rounded-xl p-4 transition hover:border-white/15"
              style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}
            >
              {d.status === "processing" && <div className="shimmer absolute inset-0" />}
              <div className="relative flex items-start gap-3">
                <div
                  className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border ${
                    d.status === "failed"
                      ? "border-red-500/30 bg-red-500/10 text-red-300"
                      : "border-amber-400/20 bg-gradient-to-br from-amber-400/15 to-orange-500/5 text-amber-300"
                  }`}
                >
                  <Icon name="file" className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-white" title={d.name}>
                    {d.name}
                  </p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-ink-400">
                    <StatusBadge status={d.status} />
                    <Flag lang={d.language} />
                    {d.page_count != null && (
                      <span>
                        {d.page_count} {t.pages}
                      </span>
                    )}
                    <span className="text-ink-500">· {fmtDate(d.created_at)}</span>
                  </div>
                  {d.status === "failed" && d.error && <p className="mt-2 text-xs leading-relaxed text-red-300">{d.error}</p>}
                </div>
                <button
                  onClick={() => remove(d)}
                  className="-m-1 rounded-lg p-2.5 text-ink-500 transition hover:bg-red-500/10 hover:text-red-300 pointer-fine:opacity-60 pointer-fine:group-hover:opacity-100 sm:m-0 sm:p-1.5"
                  aria-label={`${t.delete} ${d.name}`}
                  title={t.delete}
                >
                  <Icon name="trash" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div className="hidden text-right sm:block">
      <p className="font-mono text-lg font-semibold leading-none text-white">{value}</p>
      <p className="mt-1 text-[11px] uppercase tracking-wider text-ink-400">{label}</p>
    </div>
  );
}

function StatusBadge({ status }: { status: DocumentRow["status"] }) {
  const { t } = useI18n();
  const styles = {
    processing: "border-amber-400/25 bg-amber-400/10 text-amber-200",
    ready: "border-emerald-400/25 bg-emerald-400/10 text-emerald-300",
    failed: "border-red-400/25 bg-red-400/10 text-red-300",
  }[status];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-1.5 py-0.5 text-[11px] font-medium ${styles}`}>
      {status === "processing" ? <Spinner className="h-2.5 w-2.5" /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {t[status]}
    </span>
  );
}
