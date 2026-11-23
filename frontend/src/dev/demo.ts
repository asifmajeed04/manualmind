/**
 * DEV-ONLY demo mode (http://localhost:5173/?demo): fakes the backend with sample data so the
 * signed-in UI can be previewed / screenshotted without an account. Never included in production builds.
 */
const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:3001";

const now = Date.now();
const docs = [
  { id: "d1", name: "Kreiselpumpe_KP-300_Betriebsanleitung.pdf", language: "de", page_count: 48, status: "ready", error: null, created_at: new Date(now - 864e5 * 3).toISOString() },
  { id: "d2", name: "DP-50_Dosing_Pump_Datasheet.pdf", language: "en", page_count: 6, status: "ready", error: null, created_at: new Date(now - 864e5).toISOString() },
  { id: "d3", name: "SIMATIC_S7-1200_Systemhandbuch.pdf", language: "de", page_count: null, status: "processing", error: null, created_at: new Date(now).toISOString() },
  { id: "d4", name: "scan_wartungsplan_2019.pdf", language: null, page_count: null, status: "failed", error: "No text found in this PDF. Scanned PDFs (images only) are not supported.", created_at: new Date(now - 864e5 * 7).toISOString() },
];

const citations = [
  { index: 1, document_id: "d1", document_name: docs[0].name, page: 31, chunk_id: "c1", snippet: "7.3 Störungen\nFehlercode E42: Überdruck im System. Ursache: Druckventil verstopft oder Absperrschieber auf der Druckseite geschlossen. Abhilfe: Ventil reinigen, Absperrschieber öffnen und Drucksensor 6ES7 214-1AG40-0XB0 prüfen." },
  { index: 2, document_id: "d1", document_name: docs[0].name, page: 12, chunk_id: "c2", snippet: "4.2 Sicherheitshinweise\nVor allen Wartungsarbeiten die Pumpe vom Netz trennen und gegen Wiedereinschalten sichern. Druck im System vollständig abbauen." },
];

const answer =
  "Error code **E42** indicates **overpressure in the system** [1]. Typical causes are a clogged pressure valve or a closed shut-off valve on the discharge side [1].\n\n" +
  "To fix it:\n" +
  "1. Disconnect the pump from the power supply and release the system pressure first [2].\n" +
  "2. Clean the pressure valve and open the shut-off valve [1].\n" +
  "3. Check the pressure sensor 6ES7 214-1AG40-0XB0 [1].";

const history = [
  { id: "h1", role: "user", content: "How often must the mechanical seal be checked?", citations: null, created_at: new Date(now - 6e5).toISOString() },
  {
    id: "h2",
    role: "assistant",
    content: "The mechanical seal (Gleitringdichtung) must be checked every **500 operating hours** [1].",
    citations: [{ index: 1, document_id: "d1", document_name: docs[0].name, page: 27, chunk_id: "c9", snippet: "6.1 Wartung\nDie Gleitringdichtung ist alle 500 Betriebsstunden auf Leckage zu prüfen. Das Lager wird alle 2000 Betriebsstunden nachgeschmiert." }],
    created_at: new Date(now - 5.9e5).toISOString(),
  },
  { id: "h3", role: "user", content: "What does error code E42 mean and how do I fix it?", citations: null, created_at: new Date(now - 3e5).toISOString() },
  { id: "h4", role: "assistant", content: answer, citations, created_at: new Date(now - 2.9e5).toISOString() },
];

function sseStream(): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  const ev = (name: string, data: unknown) => enc.encode(`event: ${name}\ndata: ${JSON.stringify(data)}\n\n`);
  const tokens = answer.match(/.{1,6}/gs) ?? [answer];
  return new ReadableStream({
    async start(c) {
      c.enqueue(ev("sources", { sources: citations }));
      await new Promise((r) => setTimeout(r, 700));
      for (const tok of tokens) {
        c.enqueue(ev("token", { text: tok }));
        await new Promise((r) => setTimeout(r, 18));
      }
      c.enqueue(ev("done", { answer, citations, mode: "hybrid" }));
      c.close();
    },
  });
}

export function installDemo() {
  const realFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (!url.startsWith(API_URL)) return realFetch(input, init);
    const path = url.slice(API_URL.length);
    const method = init?.method ?? "GET";
    const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
    if (path === "/api/documents" && method === "GET") return json(docs);
    if (path.startsWith("/api/documents/") && method === "GET") return json(docs.find((d) => path.endsWith(d.id)));
    if (path === "/api/chat/history" && method === "GET") return json(history);
    if (path === "/api/chat" && method === "POST") return new Response(sseStream(), { headers: { "Content-Type": "text/event-stream" } });
    return new Response(null, { status: 204 });
  };
}

