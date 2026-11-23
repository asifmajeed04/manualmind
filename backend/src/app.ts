import express, { type ErrorRequestHandler } from "express";
import cors from "cors";
import multer from "multer";
import { config } from "./config.js";
import type { Store } from "./store.js";
import type { AiClient } from "./aiClient.js";
import { requireAuth } from "./middleware/auth.js";
import { documentsRouter } from "./routes/documents.js";
import { chatRouter } from "./routes/chat.js";

export type Deps = { store: Store; ai: AiClient };

export function createApp({ store, ai }: Deps) {
  const app = express();
  // CORS_ORIGIN may list several origins, e.g. "http://localhost:5173,https://manualmind.vercel.app"
  const origins = config.corsOrigin.split(",").map((o) => o.trim()).filter(Boolean);
  app.use(cors({ origin: origins.length > 1 ? origins : origins[0] }));
  app.use(express.json());

  app.get("/api/health", async (_req, res) => {
    let aiService = "unreachable";
    try {
      const r = await fetch(`${config.aiServiceUrl}/health`, { signal: AbortSignal.timeout(3000) });
      // must be *our* AI service, not just any server answering 200 (e.g. a mistyped URL)
      const body = r.ok ? await r.json().catch(() => null) : null;
      aiService = body?.service === "ai-service" ? "ok" : r.ok ? "wrong-service" : "unreachable";
    } catch {
      /* keep "unreachable" */
    }
    res.json({ status: "ok", aiService });
  });

  // Everything below requires a logged-in user.
  app.use("/api", requireAuth(store));
  app.get("/api/me", (_req, res) => res.json({ userId: res.locals.userId }));
  app.use("/api/documents", documentsRouter(store, ai));
  app.use("/api/chat", chatRouter(store, ai));

  const errorHandler: ErrorRequestHandler = (err, _req, res, _next) => {
    if (err instanceof multer.MulterError) {
      if (err.code === "LIMIT_FILE_SIZE") return res.status(413).json({ error: "File is too large (max 20 MB)." });
      return res.status(400).json({ error: `Upload error: ${err.message}` });
    }
    console.error(err);
    res.status(500).json({ error: "Internal server error" });
  };
  app.use(errorHandler);

  return app;
}
