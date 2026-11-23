import { Router } from "express";
import type { AiClient } from "../aiClient.js";
import type { Citation, Store } from "../store.js";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_QUESTION = 2000;
const HISTORY_LIMIT = 100;

type DonePayload = { answer: string; citations: Citation[] };

/** Splits an SSE text buffer into complete events; returns [events, rest]. */
export function parseSse(buffer: string): [{ event: string; data: string }[], string] {
  const events: { event: string; data: string }[] = [];
  const blocks = buffer.split("\n\n");
  const rest = blocks.pop() ?? "";
  for (const block of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice(7);
      else if (line.startsWith("data: ")) data.push(line.slice(6));
    }
    if (data.length) events.push({ event, data: data.join("\n") });
  }
  return [events, rest];
}

export function chatRouter(store: Store, ai: AiClient) {
  const router = Router();

  // POST /api/chat  { question, document_ids? }  ->  text/event-stream (sources, token*, done | error)
  router.post("/", async (req, res, next) => {
    const question = typeof req.body?.question === "string" ? req.body.question.trim() : "";
    const documentIds = req.body?.document_ids;
    if (!question) return res.status(400).json({ error: "Question is required." });
    if (question.length > MAX_QUESTION) return res.status(400).json({ error: "Question is too long (max 2000 characters)." });
    if (
      documentIds !== undefined &&
      (!Array.isArray(documentIds) || !documentIds.every((d) => typeof d === "string" && UUID_RE.test(d)))
    ) {
      return res.status(400).json({ error: "document_ids must be a list of document ids." });
    }

    const userId: string = res.locals.userId;
    const abort = new AbortController();
    // stop the LLM call if the browser goes away
    res.on("close", () => {
      if (!res.writableEnded) abort.abort();
    });

    let upstream: Response;
    try {
      await store.saveMessage(userId, "user", question, null);
      upstream = await ai.queryStream(
        { question, user_id: userId, ...(documentIds?.length ? { document_ids: documentIds } : {}) },
        abort.signal,
      );
    } catch (err) {
      if (abort.signal.aborted) return;
      console.error("chat: AI service unreachable", err);
      return res.status(502).json({ error: "The answer service is unavailable. Please try again later." });
    }
    if (!upstream.ok || !upstream.body) {
      console.error("chat: AI service responded", upstream.status, await upstream.text().catch(() => ""));
      return res.status(502).json({ error: "The answer service is unavailable. Please try again later." });
    }

    res.writeHead(200, {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    });

    let done: DonePayload | null = null;
    let buffer = "";
    const decoder = new TextDecoder();
    try {
      for await (const chunk of upstream.body as unknown as AsyncIterable<Uint8Array>) {
        const text = decoder.decode(chunk, { stream: true });
        res.write(text); // pass through unchanged
        const [events, rest] = parseSse(buffer + text);
        buffer = rest;
        for (const e of events) if (e.event === "done") done = JSON.parse(e.data) as DonePayload;
      }
      if (done) await store.saveMessage(userId, "assistant", done.answer, done.citations);
    } catch (err) {
      if (!abort.signal.aborted) {
        console.error("chat: stream failed", err);
        res.write(`event: error\ndata: ${JSON.stringify({ message: "The answer was interrupted. Please try again." })}\n\n`);
      }
    } finally {
      res.end();
    }
  });

  router.get("/history", async (_req, res, next) => {
    try {
      res.json(await store.listMessages(res.locals.userId, HISTORY_LIMIT));
    } catch (err) {
      next(err);
    }
  });

  router.delete("/history", async (_req, res, next) => {
    try {
      await store.clearMessages(res.locals.userId);
      res.status(204).end();
    } catch (err) {
      next(err);
    }
  });

  return router;
}
