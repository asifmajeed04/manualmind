import { useEffect, useState, type FormEvent } from "react";
import { supabase, supabaseConfigured } from "../lib/supabase";
import { useI18n } from "../lib/i18n";
import { LangToggle } from "./LangToggle";
import { Brand, FlagMark, Icon, Spinner } from "./ui";
import { renderCodes } from "./AnswerText";

export function Login() {
  const { t } = useI18n();

  return (
    <div className="bg-blueprint relative min-h-dvh overflow-hidden">
      <header className="relative z-10 mx-auto flex max-w-7xl items-center justify-between px-5 py-5 sm:px-8">
        <Brand />
        <LangToggle />
      </header>

      <main className="relative z-10 mx-auto grid max-w-7xl items-center gap-12 px-5 pb-16 pt-4 sm:px-8 lg:grid-cols-[minmax(0,1fr)_380px] lg:gap-12 xl:grid-cols-[minmax(0,1fr)_400px] xl:gap-20 lg:pt-12">
        {/* Hero */}
        <section className="min-w-0 animate-fade-up">
          <span className="inline-flex items-center gap-2 rounded-full border border-amber-400/25 bg-amber-400/[0.07] px-3 py-1 text-xs font-medium text-amber-200">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400 shadow-[0_0_8px_2px_rgb(251_191_36/0.6)]" />
            {t.heroBadge}
          </span>
          <h1 className="mt-6 text-[2.15rem] font-extrabold leading-[1.08] tracking-tight text-white [hyphens:auto] sm:text-5xl xl:text-[3.6rem]">
            {t.heroTitle1}
            <br />
            <span className="text-gradient">{t.heroTitle2}</span>
          </h1>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-ink-300 sm:text-lg">{t.heroText}</p>

          <DemoCard />

          <ul className="mt-10 grid gap-4 sm:grid-cols-3">
            {[
              { icon: "globe" as const, title: t.feat1Title, text: t.feat1Text },
              { icon: "search" as const, title: t.feat2Title, text: t.feat2Text },
              { icon: "quote" as const, title: t.feat3Title, text: t.feat3Text },
            ].map((f, i) => (
              <li key={f.title} className="animate-fade-up" style={{ animationDelay: `${150 + i * 80}ms` }}>
                <div className="mb-2.5 flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-amber-300">
                  <Icon name={f.icon} />
                </div>
                <p className="text-sm font-semibold text-white">{f.title}</p>
                <p className="mt-1 text-sm leading-relaxed text-ink-400">{renderCodes(f.text)}</p>
              </li>
            ))}
          </ul>
        </section>

        {/* Sign in */}
        <section className="animate-fade-up w-full lg:justify-self-end" style={{ animationDelay: "120ms" }}>
          <SignInCard />
        </section>
      </main>
    </div>
  );
}

/** Animated example: English question answered from a German manual, with a citation. */
function DemoCard() {
  const { t } = useI18n();
  const [shown, setShown] = useState(0);
  const full = t.demoAnswer;

  useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setShown(full.length);
      return;
    }
    setShown(0);
    let i = 0;
    let pause = 0;
    const id = setInterval(() => {
      if (i < full.length) {
        i += 2;
        setShown(Math.min(i, full.length));
      } else if (++pause > 90) {
        i = 0;
        pause = 0;
        setShown(0);
      }
    }, 28);
    return () => clearInterval(id);
  }, [full]);

  const typing = shown < full.length;
  return (
    <div className="glass mt-8 max-w-xl animate-float rounded-2xl p-4 shadow-[0_30px_80px_-30px_rgb(0_0_0/0.8)]">
      <div className="flex justify-end">
        <p className="rounded-2xl rounded-br-md bg-white/[0.07] px-3.5 py-2 text-sm text-white">{renderCodes(t.demoQuestion)}</p>
      </div>
      <div className="mt-3 flex gap-3">
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-amber-300 to-orange-500 text-ink-950">
          <Icon name="sparkle" className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 text-sm leading-relaxed text-ink-200">
          <p className="min-h-[3.25rem]">
            {renderCodes(full.slice(0, shown))}
            {typing ? (
              <span className="ml-0.5 inline-block h-4 w-1.5 animate-blink bg-amber-300 align-middle" />
            ) : (
              <span className="code-tag ml-1 !font-sans !text-[11px] font-semibold">1</span>
            )}
          </p>
          <div className={`mt-2 inline-flex items-center gap-2 rounded-lg border border-white/10 bg-ink-950/50 px-2.5 py-1.5 text-xs text-ink-300 ${typing ? "invisible" : "visible animate-fade-up"}`}>
            <Icon name="file" className="h-3.5 w-3.5 text-amber-300" />
            {t.demoSource}
            <FlagMark lang="de" />
          </div>
        </div>
      </div>
    </div>
  );
}

function SignInCard() {
  const { t } = useI18n();
  const [mode, setMode] = useState<"link" | "password">("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { error } =
      mode === "link"
        ? await supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: window.location.origin } })
        : await supabase.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (error) setError(error.message);
    else if (mode === "link") setSent(true);
  }

  const tab = (m: "link" | "password", label: string) => (
    <button
      type="button"
      role="tab"
      aria-selected={mode === m}
      onClick={() => {
        setMode(m);
        setError(null);
        setSent(false);
      }}
      className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition ${
        mode === m ? "bg-white/10 text-white shadow-sm" : "text-ink-400 hover:text-ink-200"
      }`}
    >
      {label}
    </button>
  );

  return (
    <form onSubmit={submit} className="glass w-full rounded-2xl p-7 mx-auto max-w-[400px] shadow-[0_40px_100px_-40px_rgb(0_0_0/0.9)]">
      <h2 className="text-xl font-semibold text-white">{t.welcome}</h2>
      <p className="mt-1 text-sm text-ink-400">{t.signInHint}</p>

      {!supabaseConfigured && <p className="mt-4 rounded-lg bg-red-500/10 p-3 text-sm text-red-300">{t.configMissing}</p>}

      <div role="tablist" className="mt-6 flex gap-1 rounded-lg border border-white/[0.06] bg-ink-950/60 p-1">
        {tab("password", t.password)}
        {tab("link", t.magicLink)}
      </div>

      <label className="mt-5 block text-xs font-medium uppercase tracking-wider text-ink-400">{t.email}</label>
      <input
        type="email"
        required
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="name@company.com"
        className="input mt-1.5"
      />

      {mode === "password" && (
        <>
          <label className="mt-4 block text-xs font-medium uppercase tracking-wider text-ink-400">{t.password}</label>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="input mt-1.5"
          />
        </>
      )}

      {error && (
        <p className="mt-4 flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 p-2.5 text-sm text-red-300">
          <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
          {error}
        </p>
      )}
      {sent && (
        <p className="mt-4 flex items-start gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-2.5 text-sm text-emerald-300">
          <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0" />
          {t.linkSent}
        </p>
      )}

      <button type="submit" disabled={busy} className="btn-primary mt-6 w-full">
        {busy ? <Spinner /> : null}
        {busy ? t.sending : mode === "link" ? t.sendLink : t.signIn}
      </button>
    </form>
  );
}
