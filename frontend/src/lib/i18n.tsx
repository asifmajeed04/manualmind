import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Lang = "en" | "de";

const en = {
  appName: "Manualmind",
  heroBadge: "Hybrid RAG · German + English",
  heroTitle1: "Your machine manuals,",
  heroTitle2: "answered in seconds.",
  heroText: "Upload PDF manuals, datasheets and maintenance guides. Ask in English or German — get precise answers with page-level citations you can verify.",
  feat1Title: "Cross-language",
  feat1Text: "Ask in English about German manuals — and vice versa.",
  feat2Title: "Exact codes",
  feat2Text: "Hybrid search finds part numbers and error codes like 6ES7 214-1AG40.",
  feat3Title: "Every claim cited",
  feat3Text: "Click a citation to see the source page and passage.",
  demoQuestion: "What does error E42 mean?",
  demoAnswer: "E42 means overpressure in the system, caused by a clogged pressure valve. Clean the valve and check the pressure sensor.",
  demoSource: "Kreiselpumpe_KP-300.pdf · page 3",
  welcome: "Welcome back",
  signInHint: "Sign in to your workspace",
  orUse: "or",
  suggestTitle: "Try asking",
  suggestions: ["What does error code E42 mean?", "How often must the seal be checked?", "Which spare part number does the pressure sensor have?", "What safety equipment is required for maintenance?"],
  docsTitle: "Document library",
  docsSubtitle: "PDFs are parsed page by page, chunked and embedded for search.",
  chatTitle: "Ask your documents",
  docCount: (n: number) => (n === 1 ? "1 document" : `${n} documents`),
  readyCount: (n: number) => `${n} ready`,
  chunksHint: "Answers use the 6 most relevant passages (hybrid search).",
  you: "You",
  assistant: "Manualmind",
  sources: "Sources",
  openSource: "Open source",
  passage: "Passage",
  dropActive: "Release to upload",
  tapTitle: "Tap to choose PDF files",
  tapHint: "PDF only · max 20 MB",

  tagline: "Ask questions about your technical documents — in English or German.",
  documents: "Documents",
  chat: "Chat",
  signOut: "Sign out",
  // login
  signIn: "Sign in",
  email: "Email",
  password: "Password",
  magicLink: "Magic link",
  sendLink: "Send magic link",
  sending: "Sending…",
  linkSent: "Check your inbox — we sent you a sign-in link.",
  signInWithPassword: "Sign in with password",
  configMissing: "Supabase is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in .env.",
  // documents
  dropTitle: "Drop PDF files here",
  dropHint: "or click to choose · PDF only · max 20 MB",
  uploading: "Uploading",
  noDocuments: "No documents yet. Upload a manual, datasheet or maintenance guide to get started.",
  name: "Name",
  language: "Language",
  pages: "Pages",
  status: "Status",
  processing: "Processing",
  ready: "Ready",
  failed: "Failed",
  delete: "Delete",
  confirmDelete: (n: string) => `Delete "${n}"? Its chunks and file will be removed.`,
  notPdf: (n: string) => `"${n}" is not a PDF.`,
  tooLarge: (n: string) => `"${n}" is larger than 20 MB.`,
  // chat
  askPlaceholder: "Ask a question… (Enter to send, Shift+Enter for a new line)",
  send: "Send",
  stop: "Stop",
  allDocuments: "All documents",
  searchIn: "Search in",
  clearChat: "Clear chat",
  confirmClear: "Delete the whole chat history?",
  emptyChat: "Ask anything about your documents, e.g. “What does error E42 mean?”",
  needDocuments: "Upload and process at least one document first.",
  source: "Source",
  page: "Page",
  close: "Close",
  thinking: "Searching documents…",
  interrupted: "The answer was interrupted. Please try again.",
  // errors
  network: "Cannot reach the server. Is the backend running?",
  genericError: "Something went wrong.",
};

const de: typeof en = {
  appName: "Manualmind",
  heroBadge: "Hybrid-RAG · Deutsch + Englisch",
  heroTitle1: "Ihre Maschinen­handbücher,", // soft hyphen: breaks cleanly on phones
  heroTitle2: "in Sekunden beantwortet.",
  heroText: "Laden Sie PDF-Handbücher, Datenblätter und Wartungsanleitungen hoch. Fragen Sie auf Deutsch oder Englisch — mit präzisen Antworten und Quellenangaben auf Seitenebene.",
  feat1Title: "Sprachübergreifend",
  feat1Text: "Fragen Sie auf Englisch zu deutschen Handbüchern — und umgekehrt.",
  feat2Title: "Exakte Codes",
  feat2Text: "Hybride Suche findet Teilenummern und Fehlercodes wie 6ES7 214-1AG40.",
  feat3Title: "Jede Aussage belegt",
  feat3Text: "Klicken Sie auf eine Quelle, um Seite und Textstelle zu sehen.",
  demoQuestion: "Was bedeutet Fehler E42?",
  demoAnswer: "E42 bedeutet Überdruck im System, verursacht durch ein verstopftes Druckventil. Ventil reinigen und Drucksensor prüfen.",
  demoSource: "Kreiselpumpe_KP-300.pdf · Seite 3",
  welcome: "Willkommen zurück",
  signInHint: "Melden Sie sich bei Ihrem Arbeitsbereich an",
  orUse: "oder",
  suggestTitle: "Beispielfragen",
  suggestions: ["Was bedeutet der Fehlercode E42?", "Wie oft muss die Dichtung geprüft werden?", "Welche Ersatzteilnummer hat der Drucksensor?", "Welche Schutzausrüstung ist bei der Wartung nötig?"],
  docsTitle: "Dokumentenbibliothek",
  docsSubtitle: "PDFs werden seitenweise gelesen, in Abschnitte geteilt und für die Suche eingebettet.",
  chatTitle: "Fragen Sie Ihre Dokumente",
  docCount: (n: number) => (n === 1 ? "1 Dokument" : `${n} Dokumente`),
  readyCount: (n: number) => `${n} bereit`,
  chunksHint: "Antworten nutzen die 6 relevantesten Textstellen (hybride Suche).",
  you: "Sie",
  assistant: "Manualmind",
  sources: "Quellen",
  openSource: "Quelle öffnen",
  passage: "Textstelle",
  dropActive: "Loslassen zum Hochladen",
  tapTitle: "Tippen, um PDF-Dateien auszuwählen",
  tapHint: "Nur PDF · max. 20 MB",

  tagline: "Stellen Sie Fragen zu Ihren technischen Dokumenten — auf Deutsch oder Englisch.",
  documents: "Dokumente",
  chat: "Chat",
  signOut: "Abmelden",
  signIn: "Anmelden",
  email: "E-Mail",
  password: "Passwort",
  magicLink: "Magic Link",
  sendLink: "Magic Link senden",
  sending: "Wird gesendet…",
  linkSent: "Prüfen Sie Ihr Postfach — wir haben Ihnen einen Anmeldelink geschickt.",
  signInWithPassword: "Mit Passwort anmelden",
  configMissing: "Supabase ist nicht konfiguriert. Setzen Sie VITE_SUPABASE_URL und VITE_SUPABASE_ANON_KEY in .env.",
  dropTitle: "PDF-Dateien hier ablegen",
  dropHint: "oder klicken zum Auswählen · nur PDF · max. 20 MB",
  uploading: "Wird hochgeladen",
  noDocuments: "Noch keine Dokumente. Laden Sie ein Handbuch, Datenblatt oder eine Wartungsanleitung hoch.",
  name: "Name",
  language: "Sprache",
  pages: "Seiten",
  status: "Status",
  processing: "In Bearbeitung",
  ready: "Bereit",
  failed: "Fehlgeschlagen",
  delete: "Löschen",
  confirmDelete: (n: string) => `„${n}“ löschen? Abschnitte und Datei werden entfernt.`,
  notPdf: (n: string) => `„${n}“ ist keine PDF-Datei.`,
  tooLarge: (n: string) => `„${n}“ ist größer als 20 MB.`,
  askPlaceholder: "Frage stellen… (Enter zum Senden, Umschalt+Enter für neue Zeile)",
  send: "Senden",
  stop: "Stopp",
  allDocuments: "Alle Dokumente",
  searchIn: "Suchen in",
  clearChat: "Chat leeren",
  confirmClear: "Den gesamten Chatverlauf löschen?",
  emptyChat: "Fragen Sie etwas zu Ihren Dokumenten, z. B. „Was bedeutet Fehlercode E42?“",
  needDocuments: "Laden Sie zuerst mindestens ein Dokument hoch.",
  source: "Quelle",
  page: "Seite",
  close: "Schließen",
  thinking: "Dokumente werden durchsucht…",
  interrupted: "Die Antwort wurde unterbrochen. Bitte erneut versuchen.",
  network: "Server nicht erreichbar. Läuft das Backend?",
  genericError: "Etwas ist schiefgelaufen.",
};

export type Strings = typeof en;
const STRINGS: Record<Lang, Strings> = { en, de };

function initialLang(): Lang {
  const fromUrl = new URLSearchParams(window.location.search).get("lang");
  if (fromUrl === "en" || fromUrl === "de") return fromUrl;
  try {
    const saved = localStorage.getItem("lang");
    if (saved === "en" || saved === "de") return saved;
  } catch {
    /* storage unavailable */
  }
  return navigator.language.toLowerCase().startsWith("de") ? "de" : "en";
}

const I18nContext = createContext<{ lang: Lang; t: Strings; setLang: (l: Lang) => void } | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  const setLang = (l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem("lang", l);
    } catch {
      /* ignore */
    }
  };
  return <I18nContext.Provider value={{ lang, t: STRINGS[lang], setLang }}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n outside I18nProvider");
  return ctx;
}

/** Maps API errors to readable text. */
export function errorText(t: Strings, err: unknown): string {
  if (err instanceof Error) {
    if (err.message === "network") return t.network;
    if (err.message === "interrupted") return t.interrupted;
    return err.message;
  }
  return t.genericError;
}
