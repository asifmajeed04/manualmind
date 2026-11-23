import request from "supertest";
import { createApp } from "./app.js";
import type { AiClient } from "./aiClient.js";
import type { ChatMessageRow, DocumentRow, Store } from "./store.js";

const PDF = Buffer.from("%PDF-1.4\n%fake test pdf\n");
const USERS: Record<string, string> = { "token-alice": "alice", "token-bob": "bob" };

function fakeStore() {
  const docs = new Map<string, DocumentRow>();
  const files = new Map<string, Buffer>();
  const messages: (ChatMessageRow & { user_id: string })[] = [];
  const store: Store = {
    async saveMessage(user_id, role, content, citations) {
      messages.push({ id: String(messages.length + 1), user_id, role, content, citations, created_at: new Date().toISOString() });
    },
    async listMessages(u, limit) {
      return messages.filter((m) => m.user_id === u).slice(-limit).map(({ user_id, ...m }) => m);
    },
    async clearMessages(u) {
      for (let i = messages.length - 1; i >= 0; i--) if (messages[i].user_id === u) messages.splice(i, 1);
    },
    async getUserIdFromToken(t) {
      return USERS[t] ?? null;
    },
    async uploadFile(p, d) {
      files.set(p, d);
    },
    async removeFile(p) {
      files.delete(p);
    },
    async createDocument(d) {
      const row: DocumentRow = {
        ...d,
        language: null,
        page_count: null,
        status: "processing",
        error: null,
        created_at: new Date().toISOString(),
      };
      docs.set(d.id, row);
      return row;
    },
    async listDocuments(u) {
      return [...docs.values()].filter((d) => d.user_id === u);
    },
    async getDocument(u, id) {
      const d = docs.get(id);
      return d && d.user_id === u ? d : null;
    },
    async updateDocument(id, f) {
      Object.assign(docs.get(id)!, f);
    },
    async deleteDocument(u, id) {
      if (docs.get(id)?.user_id === u) docs.delete(id);
    },
  };
  return { store, docs, files, messages };
}

const sse = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const SSE_OK =
  sse("sources", { sources: [] }) +
  sse("token", { text: "E42 means " }) +
  sse("token", { text: "overpressure [1]." }) +
  sse("done", {
    answer: "E42 means overpressure [1].",
    citations: [{ index: 1, document_id: "d1", document_name: "M.pdf", page: 3, chunk_id: "c1", snippet: "E42" }],
    mode: "vector",
  });

function setup(aiFails = false, sse = SSE_OK) {
  const s = fakeStore();
  const ingestCalls: [string, string][] = [];
  const queries: unknown[] = [];
  const ai: AiClient = {
    async startIngest(id, path) {
      if (aiFails) throw new Error("down");
      ingestCalls.push([id, path]);
    },
    async queryStream(body) {
      if (aiFails) throw new Error("down");
      queries.push(body);
      // deliver in small pieces to exercise event re-assembly across chunks
      const bytes = new TextEncoder().encode(sse);
      const stream = new ReadableStream({
        start(c) {
          for (let i = 0; i < bytes.length; i += 7) c.enqueue(bytes.slice(i, i + 7));
          c.close();
        },
      });
      return new Response(stream, { headers: { "Content-Type": "text/event-stream" } });
    },
  };
  return { ...s, ingestCalls, queries, app: createApp({ store: s.store, ai }) };
}

const auth = (t = "token-alice") => ({ Authorization: `Bearer ${t}` });

describe("health & auth", () => {
  it("GET /api/health is public", async () => {
    const res = await request(setup().app).get("/api/health");
    expect(res.status).toBe(200);
    expect(res.body.status).toBe("ok");
  });

  it("rejects missing and invalid tokens", async () => {
    const { app } = setup();
    expect((await request(app).get("/api/documents")).status).toBe(401);
    expect((await request(app).get("/api/documents").set(auth("nope"))).status).toBe(401);
  });
});

describe("POST /api/documents", () => {
  it("stores the file, creates a processing document and starts ingestion", async () => {
    const { app, files, ingestCalls } = setup();
    const res = await request(app)
      .post("/api/documents")
      .set(auth())
      .attach("file", PDF, { filename: "Wartungsanleitung.pdf", contentType: "application/pdf" });

    expect(res.status).toBe(202);
    expect(res.body).toMatchObject({ name: "Wartungsanleitung.pdf", status: "processing", user_id: "alice" });
    expect(res.body.storage_path).toBe(`alice/${res.body.id}.pdf`);
    expect(files.has(res.body.storage_path)).toBe(true);
    expect(ingestCalls).toEqual([[res.body.id, res.body.storage_path]]);
  });

  it("rejects non-PDF content even with a .pdf name", async () => {
    const res = await request(setup().app)
      .post("/api/documents")
      .set(auth())
      .attach("file", Buffer.from("hello"), { filename: "fake.pdf", contentType: "application/pdf" });
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/Only PDF/);
  });

  it("rejects a missing file", async () => {
    const res = await request(setup().app).post("/api/documents").set(auth());
    expect(res.status).toBe(400);
  });

  it("rejects files over 20 MB", async () => {
    const big = Buffer.concat([PDF, Buffer.alloc(20 * 1024 * 1024)]);
    const res = await request(setup().app)
      .post("/api/documents")
      .set(auth())
      .attach("file", big, { filename: "big.pdf", contentType: "application/pdf" });
    expect(res.status).toBe(413);
    expect(res.body.error).toMatch(/20 MB/);
  });

  it("marks the document failed when the AI service is down", async () => {
    const { app, docs } = setup(true);
    const res = await request(app)
      .post("/api/documents")
      .set(auth())
      .attach("file", PDF, { filename: "a.pdf", contentType: "application/pdf" });
    expect(res.status).toBe(202);
    expect(res.body.status).toBe("failed");
    expect(docs.get(res.body.id)?.status).toBe("failed");
  });
});

describe("GET / DELETE /api/documents", () => {
  async function uploadAs(app: ReturnType<typeof setup>["app"], token = "token-alice") {
    const res = await request(app)
      .post("/api/documents")
      .set(auth(token))
      .attach("file", PDF, { filename: "a.pdf", contentType: "application/pdf" });
    return res.body as DocumentRow;
  }

  it("lists only the user's own documents", async () => {
    const { app } = setup();
    await uploadAs(app, "token-alice");
    await uploadAs(app, "token-bob");
    const res = await request(app).get("/api/documents").set(auth());
    expect(res.status).toBe(200);
    expect(res.body).toHaveLength(1);
    expect(res.body[0].user_id).toBe("alice");
  });

  it("returns status for own document, 404 for others' or invalid ids", async () => {
    const { app } = setup();
    const doc = await uploadAs(app);
    expect((await request(app).get(`/api/documents/${doc.id}`).set(auth())).body.status).toBe("processing");
    expect((await request(app).get(`/api/documents/${doc.id}`).set(auth("token-bob"))).status).toBe(404);
    expect((await request(app).get("/api/documents/not-a-uuid").set(auth())).status).toBe(404);
  });

  it("deletes the document and its file", async () => {
    const { app, docs, files } = setup();
    const doc = await uploadAs(app);
    expect((await request(app).delete(`/api/documents/${doc.id}`).set(auth("token-bob"))).status).toBe(404);
    expect((await request(app).delete(`/api/documents/${doc.id}`).set(auth())).status).toBe(204);
    expect(docs.has(doc.id)).toBe(false);
    expect(files.has(doc.storage_path)).toBe(false);
  });
});

describe("chat", () => {
  const DOC = "22222222-2222-2222-2222-222222222222";

  it("streams the AI service events through and saves both messages", async () => {
    const { app, messages, queries } = setup();
    const res = await request(app).post("/api/chat").set(auth()).send({ question: " What is E42? ", document_ids: [DOC] });
    expect(res.status).toBe(200);
    expect(res.headers["content-type"]).toMatch(/text\/event-stream/);
    expect(res.text).toBe(SSE_OK);
    expect(queries).toEqual([{ question: "What is E42?", user_id: "alice", document_ids: [DOC] }]);
    expect(messages.map((m) => [m.user_id, m.role, m.content])).toEqual([
      ["alice", "user", "What is E42?"],
      ["alice", "assistant", "E42 means overpressure [1]."],
    ]);
    expect(messages[1].citations?.[0].page).toBe(3);
  });

  it("does not save an assistant message when the stream ends with an error", async () => {
    const { app, messages } = setup(false, sse("sources", { sources: [] }) + sse("error", { message: "x" }));
    const res = await request(app).post("/api/chat").set(auth()).send({ question: "q" });
    expect(res.text).toContain("event: error");
    expect(messages.map((m) => m.role)).toEqual(["user"]);
  });

  it("validates input", async () => {
    const { app } = setup();
    expect((await request(app).post("/api/chat").set(auth()).send({ question: "  " })).status).toBe(400);
    expect((await request(app).post("/api/chat").set(auth()).send({ question: "x".repeat(2001) })).status).toBe(400);
    expect((await request(app).post("/api/chat").set(auth()).send({ question: "q", document_ids: ["nope"] })).status).toBe(400);
    expect((await request(app).post("/api/chat").send({ question: "q" })).status).toBe(401);
  });

  it("returns 502 when the AI service is down", async () => {
    const res = await request(setup(true).app).post("/api/chat").set(auth()).send({ question: "q" });
    expect(res.status).toBe(502);
  });

  it("history is per user and can be cleared", async () => {
    const { app } = setup();
    await request(app).post("/api/chat").set(auth()).send({ question: "alice asks" });
    await request(app).post("/api/chat").set(auth("token-bob")).send({ question: "bob asks" });
    const hist = await request(app).get("/api/chat/history").set(auth());
    expect(hist.body.map((m: ChatMessageRow) => m.content)).toEqual(["alice asks", "E42 means overpressure [1]."]);
    expect((await request(app).delete("/api/chat/history").set(auth())).status).toBe(204);
    expect((await request(app).get("/api/chat/history").set(auth())).body).toEqual([]);
    expect((await request(app).get("/api/chat/history").set(auth("token-bob"))).body).toHaveLength(2);
  });
});

describe("CORS", () => {
  it("allows each configured origin", async () => {
    const { app } = setup();
    const res = await request(app).get("/api/health").set("Origin", "http://localhost:5173");
    expect(res.headers["access-control-allow-origin"]).toBe("http://localhost:5173");
  });
});
