"""Minimal Supabase client (REST + Storage) using the service role key."""

from __future__ import annotations

from urllib.parse import quote

import httpx

from .config import Settings
from .embeddings import to_pgvector
from .ingest import Chunk

BUCKET = "documents"
INSERT_BATCH = 100  # rows now carry 1536-dim vectors (~20 KB each)


class SupabaseStore:
    def __init__(self, settings: Settings):
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured")
        key = settings.supabase_service_role_key
        self._client = httpx.Client(
            base_url=settings.supabase_url.rstrip("/"),
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=60,
        )

    def download_file(self, storage_path: str) -> bytes:
        r = self._client.get(f"/storage/v1/object/{BUCKET}/{quote(storage_path)}")
        r.raise_for_status()
        return r.content

    def get_document_name(self, document_id: str) -> str | None:
        r = self._client.get("/rest/v1/documents", params={"id": f"eq.{document_id}", "select": "name"})
        r.raise_for_status()
        rows = r.json()
        return rows[0]["name"] if rows else None

    def update_document(self, document_id: str, fields: dict) -> None:
        r = self._client.patch(
            "/rest/v1/documents",
            params={"id": f"eq.{document_id}"},
            json=fields,
            headers={"Prefer": "return=minimal"},
        )
        r.raise_for_status()

    def match_chunks_vector(
        self, embedding: list[float], user_id: str, k: int, document_ids: list[str] | None
    ) -> list[dict]:
        r = self._client.post(
            "/rest/v1/rpc/match_chunks_vector",
            json={
                "query_embedding": to_pgvector(embedding),
                "p_user_id": user_id,
                "k": k,
                "p_document_ids": document_ids,
            },
        )
        r.raise_for_status()
        return r.json()

    def match_chunks_keyword(
        self, query_text: str, user_id: str, k: int, document_ids: list[str] | None
    ) -> list[dict]:
        r = self._client.post(
            "/rest/v1/rpc/match_chunks_keyword",
            json={"query_text": query_text, "p_user_id": user_id, "k": k, "p_document_ids": document_ids},
        )
        r.raise_for_status()
        return r.json()

    def replace_chunks(self, document_id: str, chunks: list[Chunk]) -> None:
        """Idempotent: re-ingesting a document replaces its chunks."""
        r = self._client.delete("/rest/v1/chunks", params={"document_id": f"eq.{document_id}"})
        r.raise_for_status()
        rows = [
            {
                "document_id": document_id,
                "page_number": c.page_number,
                "chunk_index": c.chunk_index,
                "content": c.content,
                "embedding": to_pgvector(c.embedding) if c.embedding is not None else None,
            }
            for c in chunks
        ]
        for i in range(0, len(rows), INSERT_BATCH):
            r = self._client.post(
                "/rest/v1/chunks",
                json=rows[i : i + INSERT_BATCH],
                headers={"Prefer": "return=minimal"},
            )
            r.raise_for_status()
