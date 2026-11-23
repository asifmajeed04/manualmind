import json
import logging
from collections.abc import Iterator
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .answer import Event, answer_events, collect
from .config import Settings, get_settings
from .embeddings import Embedder, create_embedder
from .ingest import Store, run_ingest
from .lang import QUOTA_MESSAGE, is_quota_error, question_language
from .llm import LLM, create_llm
from .retrieval import Mode, SearchStore
from .security import require_secret
from .supabase_store import SupabaseStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="RAG AI Service", version="0.6.0")


def get_store(settings: Settings = Depends(get_settings)) -> SupabaseStore:
    return SupabaseStore(settings)


def get_embedder(settings: Settings = Depends(get_settings)) -> Embedder:
    try:
        return create_embedder(
            settings.embedding_provider,
            settings.embedding_model,
            settings.gemini_api_key,
            settings.openai_api_key,
            settings.embedding_tpm,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


def get_llm(settings: Settings = Depends(get_settings)) -> LLM:
    try:
        return create_llm(settings.llm_provider, settings.llm_model, settings.gemini_api_key, settings.openai_api_key,
                          settings.llm_fallback_models)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ai-service"}


internal = APIRouter(dependencies=[Depends(require_secret)])


@internal.get("/internal/ping")
def ping() -> dict:
    return {"status": "ok"}


class IngestRequest(BaseModel):
    document_id: str
    storage_path: str


@internal.post("/ingest", status_code=202)
def ingest(
    req: IngestRequest,
    background: BackgroundTasks,
    store: Store = Depends(get_store),
    embedder: Embedder = Depends(get_embedder),
) -> dict:
    """Accepts the job and processes it in the background; status lands in `documents`."""
    background.add_task(run_ingest, req.document_id, req.storage_path, store, embedder)
    return {"status": "accepted", "document_id": req.document_id}


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    user_id: UUID
    document_ids: list[UUID] | None = None
    k: int = Field(default=20, ge=1, le=50)  # candidates per retriever; top 6 go to the LLM
    mode: Mode = "hybrid"  # vector | keyword | hybrid (RRF)
    stream: bool = True  # SSE (default) or a single JSON response


def _sse_event(name: str, payload: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _error_message(err: Exception, question: str) -> str:
    if is_quota_error(err):
        return QUOTA_MESSAGE[question_language(question)]
    return "Generating the answer failed. Please try again."


def _sse(events: Iterator[Event], question: str) -> Iterator[str]:
    try:
        for name, payload in events:
            yield _sse_event(name, payload)
    except Exception as e:
        logger.exception("query stream failed")
        yield _sse_event("error", {"message": _error_message(e, question)})


@internal.post("/query")
def query(
    req: QueryRequest,
    store: SearchStore = Depends(get_store),
    embedder: Embedder = Depends(get_embedder),
    llm: LLM = Depends(get_llm),
):
    """Hybrid retrieval (vector + keyword, RRF) + LLM answer with citations.

    stream=true  -> text/event-stream with events: sources, token*, done | error
    stream=false -> {"answer", "citations", "sources", "mode"}
    """
    events = answer_events(
        req.question,
        str(req.user_id),
        store,
        embedder,
        llm,
        document_ids=[str(d) for d in req.document_ids] if req.document_ids else None,
        k=req.k,
        mode=req.mode,
    )
    if req.stream:
        return StreamingResponse(
            _sse(events, req.question),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    try:
        return collect(events)
    except Exception as e:
        logger.exception("query failed")
        raise HTTPException(status_code=429 if is_quota_error(e) else 502, detail=_error_message(e, req.question)) from e


app.include_router(internal)
