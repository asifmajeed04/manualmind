import { createClient, type SupabaseClient } from "@supabase/supabase-js";

export type DocumentRow = {
  id: string;
  user_id: string;
  name: string;
  storage_path: string;
  language: "de" | "en" | null;
  page_count: number | null;
  status: "processing" | "ready" | "failed";
  error: string | null;
  created_at: string;
};

export type Citation = {
  index: number;
  document_id: string;
  document_name: string;
  page: number;
  chunk_id: string;
  snippet: string;
};

export type ChatMessageRow = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
  created_at: string;
};

/** Everything the API needs from Supabase — swapped for a fake in tests. */
export interface Store {
  saveMessage(userId: string, role: "user" | "assistant", content: string, citations: Citation[] | null): Promise<void>;
  listMessages(userId: string, limit: number): Promise<ChatMessageRow[]>;
  clearMessages(userId: string): Promise<void>;
  getUserIdFromToken(token: string): Promise<string | null>;
  uploadFile(path: string, data: Buffer, contentType: string): Promise<void>;
  removeFile(path: string): Promise<void>;
  createDocument(doc: Pick<DocumentRow, "id" | "user_id" | "name" | "storage_path">): Promise<DocumentRow>;
  listDocuments(userId: string): Promise<DocumentRow[]>;
  getDocument(userId: string, id: string): Promise<DocumentRow | null>;
  updateDocument(id: string, fields: Partial<DocumentRow>): Promise<void>;
  deleteDocument(userId: string, id: string): Promise<void>;
}

const BUCKET = "documents";
const COLUMNS = "id,user_id,name,storage_path,language,page_count,status,error,created_at";

export function createSupabaseStore(url: string, serviceRoleKey: string): Store {
  // Service role client bypasses RLS, so every query filters by user_id explicitly.
  const db: SupabaseClient = createClient(url, serviceRoleKey, { auth: { persistSession: false } });

  return {
    async getUserIdFromToken(token) {
      const { data, error } = await db.auth.getUser(token);
      return error || !data.user ? null : data.user.id;
    },
    async uploadFile(path, data, contentType) {
      const { error } = await db.storage.from(BUCKET).upload(path, data, { contentType });
      if (error) throw new Error(`Storage upload failed: ${error.message}`);
    },
    async removeFile(path) {
      const { error } = await db.storage.from(BUCKET).remove([path]);
      if (error) throw new Error(`Storage delete failed: ${error.message}`);
    },
    async createDocument(doc) {
      const { data, error } = await db.from("documents").insert(doc).select(COLUMNS).single();
      if (error) throw new Error(`Insert failed: ${error.message}`);
      return data as DocumentRow;
    },
    async listDocuments(userId) {
      const { data, error } = await db
        .from("documents")
        .select(COLUMNS)
        .eq("user_id", userId)
        .order("created_at", { ascending: false });
      if (error) throw new Error(error.message);
      return data as DocumentRow[];
    },
    async getDocument(userId, id) {
      const { data, error } = await db
        .from("documents")
        .select(COLUMNS)
        .eq("user_id", userId)
        .eq("id", id)
        .maybeSingle();
      if (error) throw new Error(error.message);
      return data as DocumentRow | null;
    },
    async updateDocument(id, fields) {
      const { error } = await db.from("documents").update(fields).eq("id", id);
      if (error) throw new Error(error.message);
    },
    async saveMessage(userId, role, content, citations) {
      const { error } = await db.from("chat_messages").insert({ user_id: userId, role, content, citations });
      if (error) throw new Error(`Saving message failed: ${error.message}`);
    },
    async listMessages(userId, limit) {
      // newest N, returned oldest-first
      const { data, error } = await db
        .from("chat_messages")
        .select("id,role,content,citations,created_at")
        .eq("user_id", userId)
        .order("created_at", { ascending: false })
        .limit(limit);
      if (error) throw new Error(error.message);
      return (data as ChatMessageRow[]).reverse();
    },
    async clearMessages(userId) {
      const { error } = await db.from("chat_messages").delete().eq("user_id", userId);
      if (error) throw new Error(error.message);
    },
    async deleteDocument(userId, id) {
      // chunks are removed by ON DELETE CASCADE
      const { error } = await db.from("documents").delete().eq("user_id", userId).eq("id", id);
      if (error) throw new Error(error.message);
    },
  };
}
