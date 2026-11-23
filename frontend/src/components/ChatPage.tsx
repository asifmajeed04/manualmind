import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { api, streamChat, type Citation, type DocumentRow } from "../lib/api";
import { errorText, useI18n } from "../lib/i18n";
import { AnswerText, renderCodes } from "./AnswerText";
import { CitationPanel } from "./CitationPanel";
import { Flag, FlagMark, Icon, Kbd, Spinner } from "./ui";

type Msg = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
  sources?: Citation[]; // all chunks given to the LLM (available while streaming)
  streaming?: boolean;
  error?: string;
};

export function ChatPage({ docs, onOpenDocuments }: { docs: DocumentRow[]; onOpenDocuments: () => void }) {
  const { t } = useI18n();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [active, setActive] = useState<{ msgId: string; citation: Citation } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const readyDocs = docs.filter((d) => d.status === "ready");
  const busy = messages.some((m) => m.streaming);

  useEffect(() => {
    api
      .getHistory()
      .then((h) => {
        setMessages(h.map((m) => ({ ...m })));
        // DEV-only (screenshots): ?demo&cite=1 opens the first citation of the last answer
        if (import.meta.env.DEV && new URLSearchParams(window.location.search).has("cite")) {
          const last = [...h].reverse().find((m) => m.role === "assistant" && m.citations?.length);
          if (last?.citations) setActive({ msgId: last.id, citation: last.citations[0] });
        }
      })
      .catch((err) => setLoadError(errorText(t, err)))
      .finally(() => setLoaded(true));
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  // drop filter entries for documents that were deleted
  useEffect(() => {
    setSelected((s) => s.filter((id) => readyDocs.some((d) => d.id === id)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docs]);

  // auto-grow textarea
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [input]);

  const update = (id: string, fn: (m: Msg) => Msg) => setMessages((ms) => ms.map((m) => (m.id === id ? fn(m) : m)));

  async function send(text?: string) {
    const question = (text ?? input).trim();
    if (!question || busy || readyDocs.length === 0) return;
    setInput("");
    const now = Date.now();
    const botId = `a${now}`;
    setMessages((ms) => [
      ...ms,
      { id: `u${now}`, role: "user", content: question, citations: null },
      { id: botId, role: "assistant", content: "", citations: null, streaming: true },
    ]);

    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await streamChat(
        question,
        selected,
        {
          onSources: (sources) => update(botId, (m) => ({ ...m, sources })),
          onToken: (tok) => update(botId, (m) => ({ ...m, content: m.content + tok })),
          onDone: (answer, citations) => update(botId, (m) => ({ ...m, content: answer, citations, streaming: false })),
          onError: (message) =>
            update(botId, (m) => ({ ...m, streaming: false, error: message === "interrupted" ? t.interrupted : message })),
        },
        ac.signal,
      );
    } catch (err) {
      if (ac.signal.aborted) update(botId, (m) => ({ ...m, streaming: false }));
      else update(botId, (m) => ({ ...m, streaming: false, error: errorText(t, err) }));
    }
  }

  async function clear() {
    if (!window.confirm(t.confirmClear)) return;
    try {
      await api.clearHistory();
      setMessages([]);
      setActive(null);
    } catch (err) {
      setLoadError(errorText(t, err));
    }
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  const findCitation = (m: Msg, n: number) =>
    m.citations?.find((c) => c.index === n) ?? m.sources?.find((c) => c.index === n) ?? null;
  const openCitation = (m: Msg, n: number) => {
    const c = findCitation(m, n);
    if (c) setActive({ msgId: m.id, citation: c });
  };
  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const empty = loaded && messages.length === 0;

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
            {loadError && (
              <p className="mb-4 flex items-start gap-2 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-2.5 text-sm text-red-300">
                <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
                {loadError}
              </p>
            )}

            {empty && <Welcome hasDocs={readyDocs.length > 0} onAsk={send} onOpenDocuments={onOpenDocuments} />}

            <div className="space-y-7">
              {messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="flex animate-fade-up justify-end">
                    <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md border border-white/[0.08] bg-gradient-to-b from-ink-600/80 to-ink-700/80 px-4 py-2.5 text-[14.5px] text-white shadow-lg">
                      {renderCodes(m.content)}
                    </p>
                  </div>
                ) : (
                  <div key={m.id} className="flex animate-fade-up gap-3">
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-amber-300 to-orange-500 text-ink-950 shadow-[0_0_20px_-4px_rgb(251_146_60/0.6)]">
                      <Icon name="sparkle" className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1 pt-1 text-[14.5px] text-ink-100">
                      {m.content ? (
                        <AnswerText
                          text={m.content}
                          canCite={(n) => findCitation(m, n) !== null}
                          onCite={(n) => openCitation(m, n)}
                          activeIndex={active?.msgId === m.id ? active.citation.index : null}
                        />
                      ) : (
                        m.streaming && (
                          <div className="flex items-center gap-3 text-sm text-ink-400">
                            <span className="flex gap-1">
                              {[0, 1, 2].map((i) => (
                                <span key={i} className="h-1.5 w-1.5 animate-bounce rounded-full bg-amber-300" style={{ animationDelay: `${i * 120}ms` }} />
                              ))}
                            </span>
                            {t.thinking}
                          </div>
                        )
                      )}
                      {m.streaming && m.content && <span className="ml-0.5 inline-block h-4 w-1.5 animate-blink bg-amber-300 align-middle" />}
                      {m.error && (
                        <p className="mt-2 flex items-start gap-2 text-sm text-red-300">
                          <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
                          {m.error}
                        </p>
                      )}

                      {!m.streaming && m.citations && m.citations.length > 0 && (
                        <div className="mt-4">
                          <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-ink-500">{t.sources}</p>
                          <div className="grid gap-2 sm:grid-cols-2">
                            {m.citations.map((c) => {
                              const isActive = active?.msgId === m.id && active.citation.index === c.index;
                              return (
                                <button
                                  key={c.index}
                                  onClick={() => setActive({ msgId: m.id, citation: c })}
                                  className={`group min-w-0 rounded-xl border p-3 text-left transition ${
                                    isActive
                                      ? "border-amber-400/60 bg-amber-400/[0.08] shadow-[0_0_30px_-10px_rgb(251_191_36/0.5)]"
                                      : "border-white/[0.08] bg-white/[0.025] hover:border-amber-400/30 hover:bg-white/[0.05]"
                                  }`}
                                >
                                  <div className="flex items-center gap-2">
                                    <span className={`flex h-[18px] min-w-[18px] items-center justify-center rounded-md px-1 text-[10.5px] font-bold ${isActive ? "bg-amber-400 text-ink-950" : "bg-amber-400/15 text-amber-300"}`}>
                                      {c.index}
                                    </span>
                                    <span className="min-w-0 flex-1 truncate text-xs font-medium text-ink-200">{c.document_name}</span>
                                    <span className="shrink-0 font-mono text-[10.5px] text-ink-400">
                                      {t.page} {c.page}
                                    </span>
                                  </div>
                                  <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-ink-400 group-hover:text-ink-300">{c.snippet}</p>
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ),
              )}
            </div>
            <div ref={bottomRef} className="h-2" />
          </div>
        </div>

        {/* Composer */}
        <div className="border-t border-white/[0.06] bg-ink-900/70 backdrop-blur-xl">
          <div className="mx-auto max-w-3xl px-4 pb-4 pt-3 sm:px-6">
            {readyDocs.length > 1 && (
              <div className="mb-2.5 flex items-center gap-1.5 overflow-x-auto text-xs [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                <span className="inline-flex shrink-0 items-center gap-1 text-ink-500">
                  <Icon name="filter" className="h-3.5 w-3.5" />
                  {t.searchIn}
                </span>
                <button
                  onClick={() => setSelected([])}
                  className={`shrink-0 rounded-full border px-2.5 py-1 transition ${
                    selected.length === 0 ? "border-amber-400/50 bg-amber-400/15 text-amber-200" : "border-white/10 text-ink-400 hover:border-white/20 hover:text-ink-200"
                  }`}
                >
                  {t.allDocuments}
                </button>
                {readyDocs.map((d) => (
                  <button
                    key={d.id}
                    onClick={() => toggle(d.id)}
                    title={d.name}
                    className={`inline-flex max-w-52 shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 transition ${
                      selected.includes(d.id) ? "border-amber-400/50 bg-amber-400/15 text-amber-200" : "border-white/10 text-ink-400 hover:border-white/20 hover:text-ink-200"
                    }`}
                  >
                    {d.language && <FlagMark lang={d.language} />}
                    <span className="truncate">{d.name}</span>
                  </button>
                ))}
              </div>
            )}

            <div className="glass flex items-end gap-2 rounded-2xl p-2 transition focus-within:border-amber-400/40 focus-within:shadow-[0_0_0_4px_rgb(251_191_36/0.08)]">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                rows={1}
                maxLength={2000}
                placeholder={t.askPlaceholder}
                disabled={readyDocs.length === 0}
                aria-label={t.askPlaceholder}
                className="max-h-[180px] min-h-[40px] flex-1 resize-none bg-transparent px-2.5 py-2 text-base text-white sm:text-[14.5px] outline-none placeholder:text-ink-500 disabled:opacity-50"
              />
              {busy ? (
                <button onClick={() => abortRef.current?.abort()} className="btn-ghost h-10 w-10 !p-0" aria-label={t.stop} title={t.stop}>
                  <Icon name="stop" className="h-4 w-4" />
                </button>
              ) : (
                <button onClick={() => send()} disabled={!input.trim() || readyDocs.length === 0} className="btn-primary h-10 w-10 !p-0" aria-label={t.send} title={t.send}>
                  <Icon name="send" className="h-4 w-4" />
                </button>
              )}
            </div>
            <div className="mt-2 flex items-center justify-between gap-3 px-1 text-[11px] text-ink-500">
              <span className="hidden min-w-0 items-center gap-1.5 truncate whitespace-nowrap lg:inline-flex">
                <Kbd>Enter</Kbd> {t.send} · <Kbd>Shift</Kbd>+<Kbd>Enter</Kbd> ↵ · {t.chunksHint}
              </span>
              {messages.length > 0 && !busy && (
                <button onClick={clear} className="ml-auto inline-flex shrink-0 items-center gap-1 whitespace-nowrap transition hover:text-red-300">
                  <Icon name="trash" className="h-3.5 w-3.5" /> {t.clearChat}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {active && <CitationPanel citation={active.citation} onClose={() => setActive(null)} />}
    </div>
  );
}

function Welcome({ hasDocs, onAsk, onOpenDocuments }: { hasDocs: boolean; onAsk: (q: string) => void; onOpenDocuments: () => void }) {
  const { t } = useI18n();
  return (
    <div className="animate-fade-up py-8 text-center sm:py-14">
      <div className="mx-auto flex h-14 w-14 animate-float items-center justify-center rounded-2xl bg-gradient-to-br from-amber-300 to-orange-500 text-ink-950 shadow-[0_0_50px_-10px_rgb(251_146_60/0.7)]">
        <Icon name="sparkle" className="h-6 w-6" />
      </div>
      <h1 className="mt-5 text-2xl font-bold tracking-tight text-white sm:text-3xl">{t.chatTitle}</h1>
      <p className="mx-auto mt-2 max-w-md text-sm text-ink-400">{hasDocs ? t.emptyChat : t.needDocuments}</p>

      {hasDocs ? (
        <>
          <p className="mt-8 text-[11px] font-semibold uppercase tracking-widest text-ink-500">{t.suggestTitle}</p>
          <div className="mx-auto mt-3 grid max-w-2xl gap-2.5 text-left sm:grid-cols-2">
            {t.suggestions.map((q, i) => (
              <button
                key={q}
                onClick={() => onAsk(q)}
                className="glass group flex animate-fade-up items-start gap-3 rounded-xl p-3.5 text-sm text-ink-200 transition hover:-translate-y-0.5 hover:border-amber-400/30 hover:text-white"
                style={{ animationDelay: `${100 + i * 60}ms` }}
              >
                <Icon name="chat" className="mt-0.5 h-4 w-4 shrink-0 text-amber-300/70 group-hover:text-amber-300" />
                <span>{renderCodes(q)}</span>
              </button>
            ))}
          </div>
          <p className="mt-6 inline-flex items-center gap-2 text-xs text-ink-500">
            <Flag lang="de" /> ⇄ <Flag lang="en" />
          </p>
        </>
      ) : (
        <button onClick={onOpenDocuments} className="btn-primary mt-6">
          <Icon name="upload" /> {t.documents}
        </button>
      )}
    </div>
  );
}
