"""Retrieval: vector search, keyword search (Postgres full-text) and hybrid (RRF merge)."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Literal, Protocol

from .embeddings import Embedder

Mode = Literal["vector", "keyword", "hybrid"]
MODES: tuple[Mode, ...] = ("vector", "keyword", "hybrid")

CANDIDATES = 20  # per retriever
RRF_K = 60


@dataclass
class SearchResult:
    id: str
    document_id: str
    document_name: str
    page_number: int
    chunk_index: int
    content: str
    score: float  # cosine similarity (vector), ts_rank (keyword) or RRF score (hybrid)
    ranks: dict[str, int] = field(default_factory=dict)  # e.g. {"vector": 3, "keyword": 1}

    def to_dict(self) -> dict:
        return asdict(self)


class SearchStore(Protocol):
    def match_chunks_vector(
        self, embedding: list[float], user_id: str, k: int, document_ids: list[str] | None
    ) -> list[dict]: ...

    def match_chunks_keyword(
        self, query_text: str, user_id: str, k: int, document_ids: list[str] | None
    ) -> list[dict]: ...


def _to_results(rows: list[dict], score_key: str, mode: str) -> list[SearchResult]:
    return [
        SearchResult(
            id=r["id"],
            document_id=r["document_id"],
            document_name=r["document_name"],
            page_number=r["page_number"],
            chunk_index=r["chunk_index"],
            content=r["content"],
            score=r[score_key],
            ranks={mode: i},
        )
        for i, r in enumerate(rows, start=1)
    ]


# ---------------------------------------------------------------------------
# Vector search
# ---------------------------------------------------------------------------
def vector_search(
    question: str,
    user_id: str,
    store: SearchStore,
    embedder: Embedder,
    k: int = CANDIDATES,
    document_ids: list[str] | None = None,
) -> list[SearchResult]:
    [embedding] = embedder.embed([question], task="query")
    rows = store.match_chunks_vector(embedding, user_id, k, document_ids or None)
    return _to_results(rows, "similarity", "vector")


# ---------------------------------------------------------------------------
# Keyword search
# ---------------------------------------------------------------------------
# Question/filler words in English and German. Without this, OR-ing all words
# would rank chunks by how often they contain "the" / "der".
STOPWORDS = frozenset(
    """
    a an and are as at be been being but by can could did do does doing for from had has have how i if in
    into is it its me my no not of on or our should so than that the their them then there these they this
    those to up was we were what when where which who whom why will with would you your about after before
    any all also each just more most other over same some such only very must may might shall need please
    tell explain describe show give mean means meaning
    aber alle als also am an auch auf aus bei beim bin bis bist da damit dann das dass dem den der des die dies
    diese dieser dieses doch dort du durch ein eine einem einen einer eines er es für gibt hab habe haben hat
    hatte ich ihr im in ist ja kann können könnte man mein mit muss müssen nach nicht noch nur ob oder ohne
    sein seine sich sie sind so soll sollte über um und uns unter vom von vor war waren was welche welcher
    welches wenn wer werden wie wir wird wo zu zum zur bitte erklären erkläre bedeutet bedeuten heißt
    """.split()
)

_TOKEN_RE = re.compile(r"\w[\w\-./]*\w|\w", re.UNICODE)


def keyword_terms(question: str) -> list[str]:
    """Meaningful search terms: lower-cased, stopwords removed, codes like 6ES7 / 214-1AG40 / E42 kept."""
    terms: list[str] = []
    for tok in _TOKEN_RE.findall(question.lower()):
        tok = tok.strip("-./")
        if not tok or tok in STOPWORDS:
            continue
        if len(tok) == 1 and not tok.isdigit():
            continue
        if tok not in terms:
            terms.append(tok)
    return terms


def is_identifier(term: str) -> bool:
    """Part numbers / error codes: contain both a digit and a letter (E42, 6es7, 214-1ag40)."""
    return any(c.isdigit() for c in term) and any(c.isalpha() for c in term)


def identifier_terms(question: str) -> list[str]:
    return [t for t in keyword_terms(question) if is_identifier(t)]


def keyword_query(question: str) -> str:
    """Postgres websearch syntax: any term may match ("a or b or c").

    If the question contains identifiers (part numbers, error codes), only those are
    searched: they are the precise signal, and ts_rank has no IDF, so generic words
    like "error" would otherwise outweigh "E42". Plain-language questions use all terms.
    """
    return " or ".join(identifier_terms(question) or keyword_terms(question))


def keyword_search(
    question: str,
    user_id: str,
    store: SearchStore,
    k: int = CANDIDATES,
    document_ids: list[str] | None = None,
) -> list[SearchResult]:
    query = keyword_query(question)
    if not query:
        return []
    rows = store.match_chunks_keyword(query, user_id, k, document_ids or None)
    return _to_results(rows, "rank", "keyword")


# ---------------------------------------------------------------------------
# Hybrid: Reciprocal Rank Fusion
# ---------------------------------------------------------------------------
def rrf_merge(*result_lists: list[SearchResult], k: int = RRF_K, prefer: str = "vector") -> list[SearchResult]:
    """score(chunk) = Σ 1 / (k + rank) over every list the chunk appears in (rank starts at 1).

    Ties (e.g. vector #1 + keyword #2 vs. vector #2 + keyword #1) go to the chunk ranked
    better by the `prefer`red retriever, then to the best rank anywhere, then document order.
    """
    merged: dict[str, SearchResult] = {}
    for results in result_lists:
        for rank, r in enumerate(results, start=1):
            entry = merged.get(r.id)
            if entry is None:
                entry = SearchResult(**{**asdict(r), "score": 0.0, "ranks": {}})
                merged[r.id] = entry
            entry.score += 1.0 / (k + rank)
            entry.ranks.update(r.ranks)
    missing = float("inf")
    return sorted(
        merged.values(),
        key=lambda r: (-round(r.score, 12), r.ranks.get(prefer, missing), min(r.ranks.values()), r.chunk_index),
    )


def search(
    question: str,
    user_id: str,
    store: SearchStore,
    embedder: Embedder,
    mode: Mode = "hybrid",
    k: int = CANDIDATES,
    document_ids: list[str] | None = None,
) -> list[SearchResult]:
    if mode == "vector":
        return vector_search(question, user_id, store, embedder, k, document_ids)
    if mode == "keyword":
        return keyword_search(question, user_id, store, k, document_ids)
    if mode != "hybrid":
        raise ValueError(f"unknown mode {mode!r}")
    # Adaptive hybrid: keyword search only joins when the question contains identifiers
    # (part numbers / error codes). Measured on 40 real DE/EN questions, equal-weight RRF
    # for plain-language questions dropped hit@6 from 82% to 70%: keyword search can't
    # match across languages, and OR-ed generic words ("pump", "danfoss", "51") flood RRF
    # with noise. See eval/README.md.
    if not identifier_terms(question):
        return vector_search(question, user_id, store, embedder, k, document_ids)
    # both retrievers are network-bound: run them concurrently
    with ThreadPoolExecutor(max_workers=2) as pool:
        vec = pool.submit(vector_search, question, user_id, store, embedder, k, document_ids)
        kw = pool.submit(keyword_search, question, user_id, store, k, document_ids)
        # exact codes in the question -> trust the lexical match on ties
        return rrf_merge(vec.result(), kw.result(), prefer="keyword")
