"""PDF ingestion: extract text per page, detect language, chunk, embed, store."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

import pymupdf
import tiktoken
from langdetect import DetectorFactory, LangDetectException, detect

from .embeddings import Embedder
from .lang import is_quota_error

DetectorFactory.seed = 0  # deterministic language detection

logger = logging.getLogger(__name__)

CHUNK_TOKENS = 500
OVERLAP_TOKENS = 50
MIN_TEXT_CHARS = 20


class IngestError(Exception):
    """An error whose message is safe to show to the user."""


@dataclass
class Chunk:
    page_number: int  # 1-based
    chunk_index: int  # sequential across the whole document
    content: str
    embedding: list[float] | None = field(default=None, repr=False)


@lru_cache
def _encoder() -> tiktoken.Encoding:
    # Same tokenizer as text-embedding-3-small.
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder().encode(text))


# ---------------------------------------------------------------------------
# 1. Text extraction
# ---------------------------------------------------------------------------
def _clean(text: str) -> str:
    text = text.replace("\x00", "")  # Postgres rejects NUL bytes
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_pages(pdf_bytes: bytes) -> list[str]:
    """Returns the cleaned text of every page; index 0 = page 1."""
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise IngestError("File is not a valid PDF.") from e
    with doc:
        if doc.needs_pass:
            raise IngestError("PDF is password-protected.")
        return [_clean(page.get_text("text")) for page in doc]


# ---------------------------------------------------------------------------
# 2. Language detection
# ---------------------------------------------------------------------------
def detect_language(text: str) -> str | None:
    """'de' or 'en' (other languages / undetectable -> None)."""
    try:
        lang = detect(text[:5000])
    except LangDetectException:
        return None
    return lang if lang in ("de", "en") else None


# ---------------------------------------------------------------------------
# 3. Chunking: ~500 tokens, 50-token overlap, never across page boundaries
# ---------------------------------------------------------------------------
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?:;])\s+|\n+")


def _split_long(unit: str, size: int, overlap: int) -> list[str]:
    """Hard-split a unit that alone exceeds `size` tokens."""
    enc = _encoder()
    tokens = enc.encode(unit)
    step = size - overlap
    return [enc.decode(tokens[i : i + size]) for i in range(0, max(len(tokens) - overlap, 1), step)]


def chunk_text(text: str, size: int = CHUNK_TOKENS, overlap: int = OVERLAP_TOKENS) -> list[str]:
    """Pack sentences/lines into chunks of <= `size` tokens.

    Each new chunk starts with the trailing sentences of the previous one
    (up to `overlap` tokens), so context isn't lost at chunk edges.
    """
    units: list[tuple[str, int]] = []
    for raw in _SENTENCE_SPLIT.split(text):
        raw = raw.strip()
        if not raw:
            continue
        n = count_tokens(raw)
        if n > size:
            units.extend((part, count_tokens(part)) for part in _split_long(raw, size, overlap))
        else:
            units.append((raw, n))

    chunks: list[str] = []
    current: list[tuple[str, int]] = []
    current_tokens = 0
    new_since_emit = False

    for unit, n in units:
        # +1 approximates the joining space
        if current and current_tokens + n + 1 > size:
            chunks.append(" ".join(u for u, _ in current))
            # carry over the tail as overlap
            tail: list[tuple[str, int]] = []
            tail_tokens = 0
            for u, t in reversed(current):
                if tail_tokens + t > overlap:
                    break
                tail.insert(0, (u, t))
                tail_tokens += t
            current, current_tokens = tail, tail_tokens
            new_since_emit = False
        current.append((unit, n))
        current_tokens += n + 1
        new_since_emit = True

    if current and new_since_emit:
        chunks.append(" ".join(u for u, _ in current))
    return chunks


def chunk_pages(pages: list[str], size: int = CHUNK_TOKENS, overlap: int = OVERLAP_TOKENS) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page_number, text in enumerate(pages, start=1):
        for content in chunk_text(text, size, overlap):
            chunks.append(Chunk(page_number, len(chunks), content))
    return chunks


# ---------------------------------------------------------------------------
# 4. Pipeline
# ---------------------------------------------------------------------------
class Store(Protocol):
    def download_file(self, storage_path: str) -> bytes: ...
    def update_document(self, document_id: str, fields: dict) -> None: ...
    def replace_chunks(self, document_id: str, chunks: list[Chunk]) -> None: ...
    def get_document_name(self, document_id: str) -> str | None: ...


def document_title(name: str | None) -> str | None:
    """'SEW_MOVITRAC_LTE-B_Betriebsanleitung_DE.pdf' -> 'SEW MOVITRAC LTE-B Betriebsanleitung DE'."""
    if not name:
        return None
    stem = re.sub(r"\.pdf$", "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", stem.replace("_", " ")).strip() or None


def embed_chunks(chunks: list[Chunk], embedder: Embedder, title: str | None = None) -> None:
    try:
        vectors = embedder.embed([c.content for c in chunks], task="document", title=title)
    except Exception as e:
        if is_quota_error(e):
            raise IngestError(
                "The free AI quota for creating embeddings is used up. Please upload this document again later."
            ) from e
        raise IngestError("Creating embeddings failed. Please try again later.") from e
    if len(vectors) != len(chunks):
        raise IngestError("Creating embeddings failed (unexpected response).")
    for c, v in zip(chunks, vectors):
        c.embedding = v


def run_ingest(document_id: str, storage_path: str, store: Store, embedder: Embedder) -> None:
    """Never raises: on failure the document is marked 'failed' with a message."""
    logger.info("ingest start document=%s", document_id)
    try:
        pdf_bytes = store.download_file(storage_path)
        pages = extract_pages(pdf_bytes)
        full_text = "\n".join(pages)
        if len(full_text.strip()) < MIN_TEXT_CHARS:
            raise IngestError(
                "No text found in this PDF. Scanned PDFs (images only) are not supported."
            )
        chunks = chunk_pages(pages)
        try:
            title = document_title(store.get_document_name(document_id))
        except Exception:  # title is an optimisation only
            title = None
        embed_chunks(chunks, embedder, title)
        store.replace_chunks(document_id, chunks)
        store.update_document(
            document_id,
            {
                "status": "ready",
                "error": None,
                "page_count": len(pages),
                "language": detect_language(full_text),
            },
        )
        logger.info("ingest done document=%s pages=%d chunks=%d", document_id, len(pages), len(chunks))
    except Exception as e:
        message = str(e) if isinstance(e, IngestError) else "Processing failed due to an internal error."
        logger.exception("ingest failed document=%s", document_id)
        try:
            store.update_document(document_id, {"status": "failed", "error": message})
        except Exception:
            logger.exception("could not mark document=%s as failed", document_id)
