import { randomUUID } from "node:crypto";
import { Router } from "express";
import multer from "multer";
import type { AiClient } from "../aiClient.js";
import type { DocumentRow, Store } from "../store.js";

export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: MAX_UPLOAD_BYTES, files: 1 },
});

export function documentsRouter(store: Store, ai: AiClient) {
  const router = Router();

  // POST /api/documents  (multipart form, field "file")
  router.post("/", upload.single("file"), async (req, res, next) => {
    try {
      const file = req.file;
      if (!file) return res.status(400).json({ error: "No file uploaded (use form field 'file')." });
      // Check the real file content, not just the extension / declared type.
      if (file.buffer.subarray(0, 5).toString("latin1") !== "%PDF-") {
        return res.status(400).json({ error: "Only PDF files are supported." });
      }

      const userId: string = res.locals.userId;
      const id = randomUUID();
      const storagePath = `${userId}/${id}.pdf`;
      // multer decodes filenames as latin1; fix umlauts like "Größe.pdf"
      const name = Buffer.from(file.originalname, "latin1").toString("utf8");

      await store.uploadFile(storagePath, file.buffer, "application/pdf");
      let doc: DocumentRow;
      try {
        doc = await store.createDocument({ id, user_id: userId, name, storage_path: storagePath });
      } catch (err) {
        await store.removeFile(storagePath).catch(() => {});
        throw err;
      }

      try {
        await ai.startIngest(id, storagePath);
      } catch (err) {
        console.error("startIngest failed", err);
        const error = "Processing service is unavailable. Please try again later.";
        await store.updateDocument(id, { status: "failed", error });
        return res.status(202).json({ ...doc, status: "failed", error });
      }

      res.status(202).json(doc);
    } catch (err) {
      next(err);
    }
  });

  router.get("/", async (_req, res, next) => {
    try {
      res.json(await store.listDocuments(res.locals.userId));
    } catch (err) {
      next(err);
    }
  });

  router.get("/:id", async (req, res, next) => {
    try {
      if (!UUID_RE.test(req.params.id)) return res.status(404).json({ error: "Document not found" });
      const doc = await store.getDocument(res.locals.userId, req.params.id);
      if (!doc) return res.status(404).json({ error: "Document not found" });
      res.json(doc);
    } catch (err) {
      next(err);
    }
  });

  router.delete("/:id", async (req, res, next) => {
    try {
      if (!UUID_RE.test(req.params.id)) return res.status(404).json({ error: "Document not found" });
      const doc = await store.getDocument(res.locals.userId, req.params.id);
      if (!doc) return res.status(404).json({ error: "Document not found" });
      await store.deleteDocument(res.locals.userId, doc.id); // chunks cascade
      await store.removeFile(doc.storage_path).catch((err) => console.error("file cleanup failed", err));
      res.status(204).end();
    } catch (err) {
      next(err);
    }
  });

  return router;
}
