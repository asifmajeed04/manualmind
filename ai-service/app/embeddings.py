"""Embeddings: Gemini (free tier) or OpenAI, batched (max 100 inputs/request), usage logged.

Both produce 1536-dim vectors to match `chunks.embedding vector(1536)`.
NOTE: vectors from different providers/models are not comparable — re-ingest
documents after switching EMBEDDING_PROVIDER or EMBEDDING_MODEL.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from collections import deque
from functools import lru_cache
from typing import Literal, Protocol

logger = logging.getLogger(__name__)

EMBEDDING_DIMS = 1536
BATCH_SIZE = 100

Task = Literal["document", "query"]


class Embedder(Protocol):
    def embed(self, texts: list[str], task: Task = "document", title: str | None = None) -> list[list[float]]: ...


def _batches(texts: list[str]):
    for i in range(0, len(texts), BATCH_SIZE):
        yield texts[i : i + BATCH_SIZE]


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


@lru_cache
def _encoder():
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


def estimate_tokens(text: str) -> int:
    """cl100k count + 15 % margin (Gemini's tokenizer differs slightly; German needs a bit more)."""
    return int(len(_encoder().encode(text)) * 1.15) + 1


class TokenRateLimiter:
    """Sliding 60-second window of tokens sent. `acquire` blocks until the request fits.

    Process-wide and thread-safe: ingestion runs in background threads and several uploads
    may embed at the same time, but they all share the provider's per-minute quota.
    """

    WINDOW_S = 60.0

    def __init__(self, tokens_per_minute: int, clock=time.monotonic, sleep=time.sleep):
        self.limit = tokens_per_minute
        self._events: deque[tuple[float, int]] = deque()
        self._lock = threading.Lock()
        self._clock, self._sleep = clock, sleep

    def acquire(self, tokens: int) -> None:
        if self.limit <= 0:
            return
        while True:
            with self._lock:
                now = self._clock()
                while self._events and now - self._events[0][0] >= self.WINDOW_S:
                    self._events.popleft()
                used = sum(t for _, t in self._events)
                # a single request larger than the limit is let through on an empty window
                if used + tokens <= self.limit or not self._events:
                    self._events.append((now, tokens))
                    return
                wait = self.WINDOW_S - (now - self._events[0][0]) + 0.25
            logger.info("embeddings rate limit: %d/%d tokens used in last minute, waiting %.1fs", used, self.limit, wait)
            self._sleep(wait)


_limiters: dict[tuple[str, int], TokenRateLimiter] = {}
_limiters_lock = threading.Lock()


def _shared_limiter(model: str, tpm: int) -> TokenRateLimiter:
    with _limiters_lock:
        return _limiters.setdefault((model, tpm), TokenRateLimiter(tpm))


def token_batches(texts: list[str], max_items: int, max_tokens: int) -> list[tuple[list[str], int]]:
    """Consecutive batches with at most `max_items` inputs and ~`max_tokens` tokens each."""
    batches: list[tuple[list[str], int]] = []
    cur: list[str] = []
    cur_tokens = 0
    for t in texts:
        n = estimate_tokens(t)
        if cur and (len(cur) >= max_items or cur_tokens + n > max_tokens):
            batches.append((cur, cur_tokens))
            cur, cur_tokens = [], 0
        cur.append(t)
        cur_tokens += n
    if cur:
        batches.append((cur, cur_tokens))
    return batches


def _retry_delay_s(err: Exception) -> float | None:
    m = re.search(r"retryDelay'?\"?:\s*'?\"?(\d+(?:\.\d+)?)s|retry in (\d+(?:\.\d+)?)s", str(err))
    return float(m.group(1) or m.group(2)) if m else None


class GeminiEmbedder:
    """Google `gemini-embedding-001`, truncated to 1536 dims (Matryoshka) and re-normalized.

    Free tier allows ~30k embedding tokens per minute: batches are sized by tokens and a shared
    rate limiter waits for capacity instead of failing, so large manuals ingest slowly but reliably.
    """

    _TASKS = {"document": "RETRIEVAL_DOCUMENT", "query": "RETRIEVAL_QUERY"}
    MAX_429_RETRIES = 5
    MAX_WAIT_S = 120.0  # longer suggested waits mean the *daily* quota is gone

    def __init__(self, api_key: str, model: str, tokens_per_minute: int = 30_000):
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        from google import genai
        from google.genai import types

        self._types = types
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=60_000,
                # transient 5xx only; per-minute 429s are handled below with Google's retry delay
                retry_options=types.HttpRetryOptions(attempts=3, initial_delay=2.0, max_delay=10.0),
            ),
        )
        self._model = model
        self._limiter = _shared_limiter(model, tokens_per_minute)
        # keep each request well below the per-minute budget so requests can interleave
        self._max_batch_tokens = max(2_000, int(tokens_per_minute * 0.6)) if tokens_per_minute > 0 else 10**9

    def _embed_batch(self, batch: list[str], tokens: int, config):
        for attempt in range(self.MAX_429_RETRIES + 1):
            self._limiter.acquire(tokens)
            try:
                return self._client.models.embed_content(model=self._model, contents=batch, config=config)
            except Exception as e:
                if getattr(e, "code", None) != 429 or attempt == self.MAX_429_RETRIES:
                    raise
                wait = _retry_delay_s(e) or 30.0
                if wait > self.MAX_WAIT_S:
                    raise RuntimeError("Daily embedding quota exhausted — try again tomorrow.") from e
                logger.warning("embeddings 429 (per-minute quota), retrying in %.0fs", wait)
                time.sleep(wait + 1)

    def embed(self, texts: list[str], task: Task = "document", title: str | None = None) -> list[list[float]]:
        # Gemini supports a document title for RETRIEVAL_DOCUMENT: it tells the model which
        # product/manual a chunk belongs to (spec tables rarely repeat the product name).
        config = self._types.EmbedContentConfig(
            task_type=self._TASKS[task],
            output_dimensionality=EMBEDDING_DIMS,
            title=title if task == "document" and title else None,
        )
        vectors: list[list[float]] = []
        batches = token_batches(texts, BATCH_SIZE, self._max_batch_tokens)
        t0 = time.monotonic()
        for batch, tokens in batches:
            res = self._embed_batch(batch, tokens, config)
            vectors.extend(_normalize(list(e.values)) for e in res.embeddings)
        logger.info(
            "embeddings provider=gemini model=%s task=%s inputs=%d requests=%d est_tokens=%d seconds=%.1f",
            self._model, task, len(texts), len(batches), sum(t for _, t in batches), time.monotonic() - t0,
        )
        return vectors


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, max_retries=3, timeout=60)
        self._model = model

    def embed(self, texts: list[str], task: Task = "document", title: str | None = None) -> list[list[float]]:
        if title and task == "document":
            texts = [f"{title}\n\n{t}" for t in texts]
        vectors: list[list[float]] = []
        total_tokens = 0
        requests = 0
        for batch in _batches(texts):
            res = self._client.embeddings.create(model=self._model, input=batch)
            # API returns items with an index; sort to be safe
            vectors.extend(d.embedding for d in sorted(res.data, key=lambda d: d.index))
            total_tokens += res.usage.total_tokens
            requests += 1
        logger.info(
            "embeddings provider=openai model=%s inputs=%d requests=%d tokens=%d",
            self._model, len(texts), requests, total_tokens,
        )
        return vectors


DEFAULT_MODELS = {"gemini": "gemini-embedding-001", "openai": "text-embedding-3-small"}


def create_embedder(
    provider: str, model: str, gemini_api_key: str, openai_api_key: str, tokens_per_minute: int = 30_000
) -> Embedder:
    provider = provider.lower()
    model = model or DEFAULT_MODELS.get(provider, "")
    if provider == "gemini":
        return GeminiEmbedder(gemini_api_key, model, tokens_per_minute)
    if provider == "openai":
        return OpenAIEmbedder(openai_api_key, model)
    raise RuntimeError(f"Unknown EMBEDDING_PROVIDER '{provider}' (use 'gemini' or 'openai')")


def to_pgvector(vec: list[float]) -> str:
    """pgvector text format, e.g. '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{x:.7g}" for x in vec) + "]"
