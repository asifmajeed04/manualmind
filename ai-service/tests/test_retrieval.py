import math
from types import SimpleNamespace

import pytest

from app.embeddings import BATCH_SIZE, GeminiEmbedder, OpenAIEmbedder, create_embedder, to_pgvector
from app.retrieval import keyword_query, keyword_search, keyword_terms, rrf_merge, search, vector_search, SearchResult


# --- OpenAI embedder ---------------------------------------------------------
class FakeOpenAIEmbeddings:
    def __init__(self):
        self.requests: list[int] = []

    def create(self, model, input):
        self.requests.append(len(input))
        # return items out of order to check that index ordering is respected
        data = [SimpleNamespace(index=i, embedding=[float(i)]) for i in range(len(input))][::-1]
        return SimpleNamespace(data=data, usage=SimpleNamespace(total_tokens=len(input) * 10))


def test_openai_embedder_batches_max_100_and_keeps_order():
    e = OpenAIEmbedder(api_key="test", model="text-embedding-3-small")
    fake = FakeOpenAIEmbeddings()
    e._client = SimpleNamespace(embeddings=fake)
    vecs = e.embed([f"t{i}" for i in range(250)])
    assert fake.requests == [BATCH_SIZE, BATCH_SIZE, 50]
    assert vecs[0] == [0.0] and vecs[99] == [99.0] and vecs[100] == [0.0]


# --- Gemini embedder ---------------------------------------------------------
class FakeGeminiModels:
    def __init__(self):
        self.calls: list[tuple] = []

    def embed_content(self, model, contents, config):
        self.calls.append((model, len(contents), config.task_type, config.output_dimensionality, config.title))
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[3.0, 4.0]) for _ in contents])


def make_gemini():
    e = GeminiEmbedder(api_key="test", model="gemini-embedding-001")
    fake = FakeGeminiModels()
    e._client = SimpleNamespace(models=fake)
    return e, fake


def test_gemini_embedder_batches_sets_task_and_dims_and_normalizes():
    e, fake = make_gemini()
    vecs = e.embed([f"t{i}" for i in range(150)], task="document")
    assert [c[1] for c in fake.calls] == [100, 50]
    assert all(c[2] == "RETRIEVAL_DOCUMENT" and c[3] == 1536 for c in fake.calls)
    assert len(vecs) == 150
    assert vecs[0] == pytest.approx([0.6, 0.8])  # unit length
    assert math.isclose(sum(x * x for x in vecs[0]), 1.0)


def test_gemini_embedder_query_task():
    e, fake = make_gemini()
    e.embed(["What is E42?"], task="query")
    assert fake.calls[0][2] == "RETRIEVAL_QUERY"


# --- provider switch -----------------------------------------------------------
def test_create_embedder_picks_provider_and_default_model():
    g = create_embedder("gemini", "", gemini_api_key="g", openai_api_key="")
    assert isinstance(g, GeminiEmbedder) and g._model == "gemini-embedding-001"
    o = create_embedder("OpenAI", "", gemini_api_key="", openai_api_key="o")
    assert isinstance(o, OpenAIEmbedder) and o._model == "text-embedding-3-small"


def test_create_embedder_errors():
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        create_embedder("gemini", "", gemini_api_key="", openai_api_key="x")
    with pytest.raises(RuntimeError, match="Unknown"):
        create_embedder("cohere", "", gemini_api_key="x", openai_api_key="x")


def test_to_pgvector_format():
    assert to_pgvector([0.5, -1.0, 0.125]) == "[0.5,-1,0.125]"


# --- vector search -------------------------------------------------------------
class FakeSearchStore:
    def __init__(self):
        self.args = None

    def match_chunks_vector(self, embedding, user_id, k, document_ids):
        self.args = (embedding, user_id, k, document_ids)
        return [
            {"id": "c1", "document_id": "d1", "document_name": "Manual.pdf", "page_number": 3,
             "chunk_index": 7, "content": "Fehlercode E42", "similarity": 0.82},
        ]


class OneVector:
    def __init__(self):
        self.task = None

    def embed(self, texts, task="document", title=None):
        assert len(texts) == 1
        self.task = task
        return [[0.1, 0.2]]


def test_vector_search_embeds_as_query_and_passes_filters():
    store, emb = FakeSearchStore(), OneVector()
    res = vector_search("What is E42?", "user-1", store, emb, k=5, document_ids=["d1"])
    assert emb.task == "query"
    assert store.args == ([0.1, 0.2], "user-1", 5, ["d1"])
    assert res[0].document_name == "Manual.pdf" and res[0].page_number == 3 and res[0].score == 0.82
    assert res[0].ranks == {"vector": 1}


def test_vector_search_empty_filter_means_all_documents():
    store = FakeSearchStore()
    vector_search("q", "user-1", store, OneVector(), document_ids=[])
    assert store.args[3] is None


# --- keyword query ---------------------------------------------------------------
def test_keyword_terms_drop_stopwords_keep_codes():
    assert keyword_terms("What does error code E42 mean?") == ["error", "code", "e42"]
    assert keyword_terms("Was bedeutet der Fehlercode E42?") == ["fehlercode", "e42"]
    assert keyword_terms("Ersatzteil 6ES7 214-1AG40-0XB0 für die Pumpe") == ["ersatzteil", "6es7", "214-1ag40-0xb0", "pumpe"]
    assert keyword_terms("Wie oft muss die Dichtung geprüft werden?") == ["oft", "dichtung", "geprüft"]
    assert keyword_terms("what is the") == []


def test_keyword_query_focuses_on_identifiers_when_present():
    assert keyword_query("What does error E42 mean?") == "e42"
    assert keyword_query("Ersatzteil 6ES7 214-1AG40 für die Pumpe") == "6es7 or 214-1ag40"
    assert keyword_query("Wartung alle 500 Betriebsstunden") == "wartung or 500 or betriebsstunden"  # numbers alone aren't ids


def test_keyword_query_ors_terms_and_strips_operators():
    assert keyword_query("Fehlercode Überdruck or Motor") == "fehlercode or überdruck or motor"
    assert keyword_query('-pump "seal"') == "pump or seal"  # no negation / phrase syntax leaks through
    assert keyword_query("e42 e42 E42") == "e42"


class KeywordStore:
    def __init__(self, rows):
        self.rows, self.queries = rows, []

    def match_chunks_keyword(self, query_text, user_id, k, document_ids):
        self.queries.append(query_text)
        return self.rows


def test_keyword_search_skips_db_when_only_stopwords():
    store = KeywordStore([{"id": "x"}])
    assert keyword_search("what is the", "u", store) == []
    assert store.queries == []


# --- RRF ---------------------------------------------------------------------------
def ranked(ids, mode):
    return [SearchResult(c, "d", "M.pdf", 1, int(c[1:]), c, 0.0, {mode: i}) for i, c in enumerate(ids, start=1)]


def test_rrf_scores_and_order():
    vec = ranked(["c1", "c2", "c3"], "vector")
    kw = ranked(["c3", "c4"], "keyword")
    merged = rrf_merge(vec, kw)
    by_id = {m.id: m for m in merged}
    assert by_id["c3"].score == pytest.approx(1 / 63 + 1 / 61)  # in both lists
    assert by_id["c1"].score == pytest.approx(1 / 61)
    assert by_id["c3"].ranks == {"vector": 3, "keyword": 1}
    # c2 (vector #2) and c4 (keyword #2) tie at 1/62 -> earlier chunk first
    assert [m.id for m in merged] == ["c3", "c1", "c2", "c4"]
    assert len(merged) == 4  # deduplicated


def test_rrf_tie_break_follows_preferred_retriever():
    # c1: vector #1 + keyword #2, c2: vector #2 + keyword #1 -> identical RRF scores
    vec, kw = ranked(["c1", "c2"], "vector"), ranked(["c2", "c1"], "keyword")
    assert [m.id for m in rrf_merge(vec, kw, prefer="vector")] == ["c1", "c2"]
    assert [m.id for m in rrf_merge(vec, kw, prefer="keyword")] == ["c2", "c1"]


def test_rrf_tie_without_preferred_rank_uses_best_rank_then_chunk_order():
    merged = rrf_merge(ranked(["c5"], "vector"), ranked(["c2"], "keyword"), prefer="other")
    assert [m.id for m in merged] == ["c2", "c5"]


def test_hybrid_prefers_keyword_on_ties_only_for_identifier_questions():
    class TieStore:
        def match_chunks_vector(self, embedding, user_id, k, document_ids):
            return [row("a"), row("b")]

        def match_chunks_keyword(self, query_text, user_id, k, document_ids):
            return [row("b"), row("a")]

    assert [x.id for x in search("6ES7 214-1AG40", "u", TieStore(), OneVector())] == ["b", "a"]
    # plain-language question: adaptive hybrid uses vector search only
    res = search("motor overheats", "u", TieStore(), OneVector())
    assert [x.id for x in res] == ["a", "b"] and all(set(x.ranks) == {"vector"} for x in res)


def test_hybrid_skips_keyword_search_without_identifiers():
    class Store:
        keyword_calls = 0

        def match_chunks_vector(self, embedding, user_id, k, document_ids):
            return [row("v")]

        def match_chunks_keyword(self, query_text, user_id, k, document_ids):
            Store.keyword_calls += 1
            return [row("k")]

    assert [x.id for x in search("Welche Schutzart hat der FC 51?", "u", Store(), OneVector())] == ["v"]
    assert Store.keyword_calls == 0
    assert {x.id for x in search("Was bedeutet E42?", "u", Store(), OneVector())} == {"v", "k"}
    assert Store.keyword_calls == 1


def row(cid):
    return {"id": cid, "document_id": "d", "document_name": "M.pdf", "page_number": 1, "chunk_index": 0,
            "content": cid, "similarity": 0.5, "rank": 0.5}


def test_rrf_does_not_mutate_inputs():
    vec = ranked(["c1"], "vector")
    rrf_merge(vec, ranked(["c1"], "keyword"))
    assert vec[0].score == 0.0 and vec[0].ranks == {"vector": 1}


class BothStore(FakeSearchStore):
    def match_chunks_keyword(self, query_text, user_id, k, document_ids):
        return [{"id": "k1", "document_id": "d2", "document_name": "Spec.pdf", "page_number": 9,
                 "chunk_index": 0, "content": "6ES7 214-1AG40", "rank": 0.3}]


def test_search_modes():
    assert [x.id for x in search("6ES7", "u", BothStore(), OneVector(), mode="vector")] == ["c1"]
    assert [x.id for x in search("6ES7", "u", BothStore(), OneVector(), mode="keyword")] == ["k1"]
    hybrid = search("6ES7", "u", BothStore(), OneVector(), mode="hybrid")
    assert {x.id for x in hybrid} == {"c1", "k1"}
    with pytest.raises(ValueError):
        search("q", "u", BothStore(), OneVector(), mode="fuzzy")


# --- embedding rate limiting (Gemini free tier: 30k tokens/min) -------------------
from app.embeddings import TokenRateLimiter, estimate_tokens, token_batches  # noqa: E402


class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.slept: list[float] = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def test_token_batches_respect_item_and_token_limits():
    texts = ["word " * 400] * 10  # ~460 est. tokens each
    batches = token_batches(texts, max_items=100, max_tokens=1500)
    assert [len(b) for b, _ in batches] == [3, 3, 3, 1]
    assert all(t <= 1500 for _, t in batches)
    assert sum(len(b) for b, _ in batches) == 10
    assert [len(b) for b, _ in token_batches(["x"] * 250, 100, 10**9)] == [100, 100, 50]


def test_rate_limiter_waits_for_window_instead_of_failing():
    clock = FakeClock()
    lim = TokenRateLimiter(30_000, clock=clock.now, sleep=clock.sleep)
    lim.acquire(18_000)
    lim.acquire(10_000)  # 28k used -> fits
    assert clock.slept == []
    lim.acquire(18_000)  # would be 46k -> must wait until the first request leaves the window
    assert len(clock.slept) == 1 and 59 < clock.slept[0] <= 61


def test_rate_limiter_lets_oversized_request_through_on_empty_window():
    clock = FakeClock()
    lim = TokenRateLimiter(1_000, clock=clock.now, sleep=clock.sleep)
    lim.acquire(5_000)
    assert clock.slept == []


def test_rate_limiter_disabled_with_zero():
    clock = FakeClock()
    lim = TokenRateLimiter(0, clock=clock.now, sleep=clock.sleep)
    for _ in range(10):
        lim.acquire(100_000)
    assert clock.slept == []


def test_estimate_tokens_has_margin():
    assert estimate_tokens("Fehlercode E42: Überdruck im System.") > 5


def test_gemini_daily_quota_fails_fast():
    import app.embeddings as emb_mod
    emb_mod._limiters.clear()

    class Quota(Exception):
        code = 429

        def __str__(self):
            return "429 RESOURCE_EXHAUSTED {'retryDelay': '83610s'}"

    class Models:
        def embed_content(self, model, contents, config):
            raise Quota()

    e = GeminiEmbedder(api_key="test", model="m-daily")
    e._client = SimpleNamespace(models=Models())
    with pytest.raises(RuntimeError, match="Daily embedding quota"):
        e.embed(["text"])


def test_gemini_document_title_only_for_documents():
    import app.embeddings as emb_mod
    emb_mod._limiters.clear()
    e, fake = make_gemini()
    e.embed(["chunk"], task="document", title="Wilo-Stratos PICO plus Betriebsanleitung DE")
    e.embed(["question"], task="query", title="ignored")
    assert fake.calls[0][4] == "Wilo-Stratos PICO plus Betriebsanleitung DE"
    assert fake.calls[1][4] is None


def test_openai_title_is_prefixed():
    e = OpenAIEmbedder(api_key="test", model="text-embedding-3-small")
    seen = []

    class Emb:
        def create(self, model, input):
            seen.extend(input)
            return SimpleNamespace(data=[SimpleNamespace(index=i, embedding=[0.0]) for i in range(len(input))],
                                   usage=SimpleNamespace(total_tokens=1))

    e._client = SimpleNamespace(embeddings=Emb())
    e.embed(["chunk"], title="Manual X")
    assert seen == ["Manual X\n\nchunk"]
