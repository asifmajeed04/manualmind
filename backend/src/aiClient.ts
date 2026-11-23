export type QueryBody = {
  question: string;
  user_id: string;
  document_ids?: string[];
};

export interface AiClient {
  startIngest(documentId: string, storagePath: string): Promise<void>;
  /** Starts a streaming answer; resolves with the SSE response from the AI service. */
  queryStream(body: QueryBody, signal: AbortSignal): Promise<Response>;
}

export function createAiClient(baseUrl: string, secret: string): AiClient {
  const headers = { "Content-Type": "application/json", "X-AI-Service-Secret": secret };
  return {
    async startIngest(documentId, storagePath) {
      const res = await fetch(`${baseUrl}/ingest`, {
        method: "POST",
        headers,
        body: JSON.stringify({ document_id: documentId, storage_path: storagePath }),
        signal: AbortSignal.timeout(10_000),
      });
      if (!res.ok) throw new Error(`AI service responded ${res.status}`);
    },
    async queryStream(body, signal) {
      return fetch(`${baseUrl}/query`, {
        method: "POST",
        headers,
        body: JSON.stringify({ ...body, stream: true }),
        signal,
      });
    },
  };
}
