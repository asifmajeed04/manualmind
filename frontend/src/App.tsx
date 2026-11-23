import { useCallback, useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./lib/supabase";
import { api, type DocumentRow } from "./lib/api";
import { I18nProvider, errorText, useI18n } from "./lib/i18n";
import { Login } from "./components/Login";
import { DocumentsPage } from "./components/DocumentsPage";
import { ChatPage } from "./components/ChatPage";
import { LangToggle } from "./components/LangToggle";
import { Brand, Icon, Spinner } from "./components/ui";

export default function App() {
  return (
    <I18nProvider>
      <Root />
    </I18nProvider>
  );
}

function Root() {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const [demo, setDemo] = useState(false);

  useEffect(() => {
    // DEV-only preview with fake data: http://localhost:5173/?demo
    if (import.meta.env.DEV && new URLSearchParams(window.location.search).has("demo")) {
      import("./dev/demo").then((m) => {
        m.installDemo();
        setDemo(true);
      });
      return;
    }
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data } = supabase.auth.onAuthStateChange((_event, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  if (import.meta.env.DEV && demo) return <Shell email="demo@manualmind.dev" />;
  if (session === undefined)
    return (
      <div className="bg-blueprint flex min-h-screen items-center justify-center text-amber-300">
        <Spinner />
      </div>
    );
  return session ? <Shell email={session.user.email ?? ""} /> : <Login />;
}

type Tab = "documents" | "chat";

function Shell({ email }: { email: string }) {
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>("documents");
  const [docs, setDocsState] = useState<DocumentRow[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const setDocs = useCallback((fn: (d: DocumentRow[]) => DocumentRow[]) => setDocsState(fn), []);

  useEffect(() => {
    api
      .listDocuments()
      .then((d) => {
        setDocsState(d);
        const forceDocs = import.meta.env.DEV && new URLSearchParams(window.location.search).get("tab") === "documents";
        if (d.some((x) => x.status === "ready") && !forceDocs) setTab("chat");
      })
      .catch((err) => setLoadError(errorText(t, err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ready = docs.filter((d) => d.status === "ready").length;
  const processing = docs.some((d) => d.status === "processing");

  const tabBtn = (id: Tab, icon: "file" | "chat", label: string, badge?: string) => (
    <button
      onClick={() => setTab(id)}
      aria-current={tab === id ? "page" : undefined}
      aria-label={label}
      className={`relative inline-flex h-10 items-center gap-2 rounded-lg px-3 text-sm font-medium transition sm:h-auto sm:py-1.5 ${
        tab === id ? "bg-white/[0.08] text-white" : "text-ink-400 hover:bg-white/[0.04] hover:text-ink-200"
      }`}
    >
      <Icon name={icon} className="h-4 w-4" />
      <span className="hidden sm:inline">{label}</span>
      {badge && (
        <span className={`rounded-full px-1.5 text-[10px] font-semibold ${tab === id ? "bg-amber-400 text-ink-950" : "bg-white/10 text-ink-300"}`}>
          {badge}
        </span>
      )}
    </button>
  );

  return (
    <div className="bg-blueprint flex h-dvh flex-col">
      <header className="relative z-10 border-b border-white/[0.06] bg-ink-900/70 backdrop-blur-xl">
        <div className="flex h-14 items-center gap-3 px-4 sm:gap-6 sm:px-5">
          <Brand compact />
          <nav className="flex gap-1">
            {tabBtn("documents", "file", t.documents, docs.length ? String(docs.length) : undefined)}
            {tabBtn("chat", "chat", t.chat)}
          </nav>
          {processing && (
            <span className="hidden items-center gap-1.5 text-xs text-amber-300 lg:inline-flex">
              <Spinner className="h-3 w-3" /> {t.processing}
            </span>
          )}
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            {ready > 0 && (
              <span className="hidden items-center gap-1.5 rounded-full border border-emerald-400/20 bg-emerald-400/[0.07] px-2.5 py-1 text-[11px] font-medium text-emerald-300 lg:inline-flex">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                {t.readyCount(ready)}
              </span>
            )}
            <LangToggle />
            <div className="hidden items-center gap-2 xl:flex">
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-ink-600 to-ink-700 text-xs font-semibold uppercase text-ink-100 ring-1 ring-white/10">
                {email.slice(0, 1)}
              </span>
              <span className="max-w-40 truncate text-xs text-ink-400">{email}</span>
            </div>
            <button onClick={() => supabase.auth.signOut()} className="btn-ghost h-10 w-10 !p-0 sm:h-auto sm:w-auto sm:!px-2.5 sm:!py-1.5" title={t.signOut} aria-label={t.signOut}>
              <Icon name="logout" />
            </button>
          </div>
        </div>
      </header>

      <main className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        {tab === "documents" ? (
          <DocumentsPage docs={docs} setDocs={setDocs} loadError={loadError} onOpenChat={() => setTab("chat")} />
        ) : (
          <ChatPage docs={docs} onOpenDocuments={() => setTab("documents")} />
        )}
      </main>
    </div>
  );
}
