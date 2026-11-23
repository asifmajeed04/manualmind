import type { RequestHandler } from "express";
import type { Store } from "../store.js";

/** Verifies the Supabase JWT from `Authorization: Bearer <token>` and sets res.locals.userId. */
export function requireAuth(store: Store): RequestHandler {
  return async (req, res, next) => {
    const token = req.headers.authorization?.match(/^Bearer (.+)$/)?.[1];
    if (!token) return res.status(401).json({ error: "Missing auth token" });
    try {
      const userId = await store.getUserIdFromToken(token);
      if (!userId) return res.status(401).json({ error: "Invalid or expired auth token" });
      res.locals.userId = userId;
      next();
    } catch (err) {
      next(err);
    }
  };
}
