import { supabase } from "./supabase";

const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:3001";

export type DocumentRow = {
  id: string;
  name: string;
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
  score?: number;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
  created_at: string;
};

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function authHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { ...(await authHeaders()), ...(init.headers ?? {}) },
    });
  } catch {
    throw new ApiError("network", 0);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.error ?? `HTTP ${res.status}`, res.status);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const api = {
  listDocuments: () => request<DocumentRow[]>("/api/documents"),
  getDocument: (id: string) => request<DocumentRow>(`/api/documents/${id}`),
  deleteDocument: (id: string) => request<void>(`/api/documents/${id}`, { method: "DELETE" }),
  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentRow>("/api/documents", { method: "POST", body: form });
  },
  getHistory: () => request<ChatMessage[]>("/api/chat/history"),
  clearHistory: () => request<void>("/api/chat/history", { method: "DELETE" }),
};

// ---------------------------------------------------------------------------
// Streaming chat (Server-Sent Events over a POST request)
// ---------------------------------------------------------------------------
export type ChatHandlers = {
  onSources: (sources: Citation[]) => void;
  onToken: (text: string) => void;
  onDone: (answer: string, citations: Citation[]) => void;
  onError: (message: string) => void;
};

export async function streamChat(
  question: string,
  documentIds: string[],
  handlers: ChatHandlers,
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ question, ...(documentIds.length ? { document_ids: documentIds } : {}) }),
    signal,
  });
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.error ?? `HTTP ${res.status}`, res.status);
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  let finished = false;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (!data) continue;
      const payload = JSON.parse(data);
      if (event === "sources") handlers.onSources(payload.sources);
      else if (event === "token") handlers.onToken(payload.text);
      else if (event === "done") {
        finished = true;
        handlers.onDone(payload.answer, payload.citations);
      } else if (event === "error") {
        finished = true;
        handlers.onError(payload.message);
      }
    }
  }
  if (!finished) handlers.onError("interrupted");
}
