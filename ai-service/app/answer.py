"""Question answering pipeline: retrieve -> prompt -> stream LLM -> parse citations.

Produces a sequence of events (name, payload) used both for SSE streaming and JSON responses:
  sources  {"sources": [...]}              the top chunks given to the LLM ([1]..[n])
  token    {"text": "..."}                 answer text as it is generated
  done     {"answer": ..., "citations": [...], "mode": "hybrid"}
"""

from __future__ import annotations

from collections.abc import Iterator

from .embeddings import Embedder
from .lang import question_language
from .llm import LLM, SYSTEM_PROMPT, Citation, build_user_prompt, make_citation, parse_citations
from .retrieval import CANDIDATES, Mode, SearchStore, search

TOP_N_CONTEXT = 6  # chunks given to the LLM

NO_RESULTS = {
    "de": "Ich konnte in Ihren Dokumenten keine passenden Informationen finden.",
    "en": "I couldn't find any relevant information in your documents.",
}

Event = tuple[str, dict]


def _source_dicts(results) -> list[dict]:
    return [
        {**make_citation(i, r).to_dict(), "score": r.score, "ranks": r.ranks}
        for i, r in enumerate(results, start=1)
    ]


def answer_events(
    question: str,
    user_id: str,
    store: SearchStore,
    embedder: Embedder,
    llm: LLM,
    document_ids: list[str] | None = None,
    k: int = CANDIDATES,
    top_n: int = TOP_N_CONTEXT,
    mode: Mode = "hybrid",
) -> Iterator[Event]:
    results = search(question, user_id, store, embedder, mode=mode, k=k, document_ids=document_ids)[:top_n]
    yield "sources", {"sources": _source_dicts(results)}

    if not results:
        msg = NO_RESULTS[question_language(question)]
        yield "token", {"text": msg}
        yield "done", {"answer": msg, "citations": [], "mode": mode}
        return

    parts: list[str] = []
    for text in llm.stream(SYSTEM_PROMPT, build_user_prompt(question, results)):
        parts.append(text)
        yield "token", {"text": text}

    answer, citations = parse_citations("".join(parts), results)
    yield "done", {"answer": answer, "citations": [c.to_dict() for c in citations], "mode": mode}


def collect(events: Iterator[Event]) -> dict:
    """Run the pipeline to completion and return the final JSON shape."""
    result: dict = {}
    for name, payload in events:
        if name == "sources":
            result["sources"] = payload["sources"]
        elif name == "done":
            result.update(payload)
    return result


__all__ = ["answer_events", "collect", "Citation", "TOP_N_CONTEXT"]
