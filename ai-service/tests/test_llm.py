import pytest

from app.answer import NO_RESULTS, answer_events, collect
from app.llm import GeminiLLM, OpenAILLM, build_user_prompt, create_llm, parse_citations
from app.retrieval import SearchResult


def src(i: int, page: int, content: str = "text", name: str = "Manual.pdf") -> SearchResult:
    return SearchResult(f"c{i}", f"d{i}", name, page, i, content, 0.9 - i / 100)


SOURCES = [src(1, 3, "Fehlercode E42: Überdruck"), src(2, 2, "Wartung alle 500 h"), src(3, 1, "x" * 400)]


# --- prompt ------------------------------------------------------------------
def test_prompt_labels_sources_with_document_and_page():
    p = build_user_prompt("What is E42?", SOURCES)
    assert "[1] Manual.pdf — page 3\nFehlercode E42: Überdruck" in p
    assert "[2] Manual.pdf — page 2" in p
    assert "\nQuestion: What is E42?\n" in p and p.rstrip().endswith("Answer in English.")


# --- citations ---------------------------------------------------------------
def test_parse_citations_maps_used_sources_in_order():
    answer, cits = parse_citations("E42 means overpressure [1]. Service every 500 h [2][1].", SOURCES)
    assert answer == "E42 means overpressure [1]. Service every 500 h [2][1]."
    assert [(c.index, c.page, c.document_name) for c in cits] == [(1, 3, "Manual.pdf"), (2, 2, "Manual.pdf")]
    assert cits[0].snippet == "Fehlercode E42: Überdruck" and cits[0].chunk_id == "c1"


def test_parse_citations_handles_comma_lists_and_drops_invalid_numbers():
    answer, cits = parse_citations("A [1, 2]. B [9]. C [0, 3].", SOURCES)
    assert answer == "A [1][2]. B. C [3]."
    assert [c.index for c in cits] == [1, 2, 3]


def test_parse_citations_without_markers():
    answer, cits = parse_citations("The documents do not contain this information.", SOURCES)
    assert cits == [] and answer.startswith("The documents")


def test_long_snippets_are_truncated():
    _, [c] = parse_citations("[3]", SOURCES)
    assert len(c.snippet) <= 301 and c.snippet.endswith("…")


# --- providers ---------------------------------------------------------------
def test_create_llm():
    assert isinstance(create_llm("gemini", "", "g", ""), GeminiLLM)
    assert create_llm("gemini", "", "g", "")._model == "gemini-3.1-flash-lite"
    assert isinstance(create_llm("openai", "", "", "o"), OpenAILLM)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        create_llm("gemini", "", "", "")
    with pytest.raises(RuntimeError, match="Unknown"):
        create_llm("llama", "", "x", "x")


# --- pipeline ----------------------------------------------------------------
class FakeStore:
    def __init__(self, rows):
        self.rows = rows

    def match_chunks_vector(self, embedding, user_id, k, document_ids):
        return self.rows[:k]

    def match_chunks_keyword(self, query_text, user_id, k, document_ids):
        return []


class FakeEmbedder:
    def embed(self, texts, task="document"):
        return [[0.0] for _ in texts]


class FakeLLM:
    def __init__(self, chunks):
        self.chunks = chunks
        self.prompts = []

    def stream(self, system, user):
        self.prompts.append((system, user))
        yield from self.chunks


def rows(n):
    return [
        {"id": f"c{i}", "document_id": "d1", "document_name": "M.pdf", "page_number": i,
         "chunk_index": i, "content": f"chunk {i}", "similarity": 1 - i / 100}
        for i in range(1, n + 1)
    ]


def test_answer_events_streams_tokens_and_returns_citations():
    llm = FakeLLM(["E42 is ", "overpressure [2", "]. See [7]."])
    events = list(answer_events("What is E42?", "u1", FakeStore(rows(10)), FakeEmbedder(), llm))
    names = [n for n, _ in events]
    assert names[0] == "sources" and names[-1] == "done" and names.count("token") == 3
    assert len(events[0][1]["sources"]) == 6  # only top 6 go to the LLM
    assert "[6] M.pdf — page 6" in llm.prompts[0][1] and "[7]" not in llm.prompts[0][1]
    done = events[-1][1]
    assert done["answer"] == "E42 is overpressure [2]. See."
    assert [(c["index"], c["page"]) for c in done["citations"]] == [(2, 2)]


def test_system_prompt_has_the_rules():
    llm = FakeLLM(["ok"])
    list(answer_events("q", "u1", FakeStore(rows(1)), FakeEmbedder(), llm))
    system = llm.prompts[0][0]
    assert "SAME LANGUAGE" in system and "ONLY" in system and "Do not guess" in system


def test_no_results_skips_llm_and_answers_in_question_language():
    llm = FakeLLM(["should not be called"])
    de = collect(answer_events("Wie oft muss die Dichtung der Pumpe geprüft werden?", "u1",
                               FakeStore([]), FakeEmbedder(), llm))
    assert de["answer"] == NO_RESULTS["de"] and de["citations"] == [] and llm.prompts == []
    en = collect(answer_events("How often must the pump seal be checked?", "u1",
                               FakeStore([]), FakeEmbedder(), llm))
    assert en["answer"] == NO_RESULTS["en"]


# --- Gemini fallback chain ---------------------------------------------------------
class APIErr(Exception):
    def __init__(self, code):
        super().__init__(f"{code} error")
        self.code = code


def chunk(text):
    from types import SimpleNamespace
    return SimpleNamespace(text=text, usage_metadata=None)


class FakeModels:
    def __init__(self, behaviour):
        self.behaviour, self.calls = behaviour, []

    def generate_content_stream(self, model, contents, config):
        self.calls.append(model)
        b = self.behaviour[model]
        if isinstance(b, Exception):
            raise b
        for item in b:
            if isinstance(item, Exception):
                raise item
            yield chunk(item)


def gemini_with(behaviour, fallbacks):
    from types import SimpleNamespace
    llm = GeminiLLM("key", "main", fallbacks)
    fake = FakeModels(behaviour)
    llm._client = SimpleNamespace(models=fake)
    return llm, fake


def test_gemini_falls_back_when_model_overloaded():
    llm, fake = gemini_with({"main": APIErr(503), "fb1": APIErr(429), "fb2": ["Hallo ", "Welt"]}, ["fb1", "fb2"])
    assert "".join(llm.stream("s", "u")) == "Hallo Welt"
    assert fake.calls == ["main", "fb1", "fb2"]


def test_gemini_no_fallback_for_client_errors():
    import app.llm as llm_mod
    llm_mod._uses_level.discard("main")
    llm, fake = gemini_with({"main": APIErr(400), "fb1": ["x"]}, ["fb1"])
    with pytest.raises(APIErr):
        list(llm.stream("s", "u"))
    # one retry on the same model (thinking_level instead of thinking_budget), never another model
    assert fake.calls == ["main", "main"]
    llm_mod._uses_level.discard("main")


def test_gemini_no_fallback_after_text_started():
    llm, fake = gemini_with({"main": ["partial ", APIErr(503)], "fb1": ["x"]}, ["fb1"])
    with pytest.raises(APIErr):
        list(llm.stream("s", "u"))
    assert fake.calls == ["main"]


def test_gemini_raises_when_all_models_overloaded():
    llm, _ = gemini_with({"main": APIErr(503), "fb1": APIErr(503)}, ["fb1"])
    with pytest.raises(APIErr):
        list(llm.stream("s", "u"))


def test_create_llm_fallback_config():
    assert create_llm("gemini", "", "k", "")._models == ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]
    assert create_llm("gemini", "m1", "k", "", fallbacks="m2, m1 ,m3")._models == ["m1", "m2", "m3"]
    assert create_llm("gemini", "m1", "k", "", fallbacks="")._models == ["m1"]


def test_overloaded_model_is_skipped_during_cooldown():
    import app.llm as llm_mod
    llm_mod._cooldown_until.clear()
    quota = APIErr(429)
    quota.args = ("429 RESOURCE_EXHAUSTED {'retryDelay': '83610s'}",)
    llm, fake = gemini_with({"main": quota, "fb1": ["ok"]}, ["fb1"])
    assert "".join(llm.stream("s", "u")) == "ok"
    assert fake.calls == ["main", "fb1"]
    # capped at 1 hour even though Google suggested ~23 h
    remaining = llm_mod._cooldown_until["main"] - __import__("time").monotonic()
    assert 3500 < remaining <= 3600
    # second request goes straight to the fallback
    llm2, fake2 = gemini_with({"main": ["should not be used"], "fb1": ["ok2"]}, ["fb1"])
    assert "".join(llm2.stream("s", "u")) == "ok2"
    assert fake2.calls == ["fb1"]
    llm_mod._cooldown_until.clear()


def test_all_models_cooling_down_still_tries():
    import app.llm as llm_mod
    llm_mod._cooldown_until.clear()
    llm_mod._cooldown_until.update({"main": 1e18, "fb1": 1e18})
    llm, fake = gemini_with({"main": ["back"], "fb1": ["x"]}, ["fb1"])
    assert "".join(llm.stream("s", "u")) == "back"
    llm_mod._cooldown_until.clear()


def test_timeout_before_first_token_falls_back():
    import app.llm as llm_mod
    llm_mod._cooldown_until.clear()

    class ReadTimeout(Exception):
        pass

    llm, fake = gemini_with({"main": ReadTimeout("timed out"), "fb1": ["ok"]}, ["fb1"])
    assert "".join(llm.stream("s", "u")) == "ok"
    assert fake.calls == ["main", "fb1"]
    llm_mod._cooldown_until.clear()


# --- answer language ----------------------------------------------------------------
def test_prompt_ends_with_explicit_language_instruction():
    assert build_user_prompt("What does E021 mean?", SOURCES).rstrip().endswith("Answer in English.")
    assert build_user_prompt("Was bedeutet O-hEat?", SOURCES).rstrip().endswith("Antworte auf Deutsch.")


def test_question_language_on_labelled_eval_questions():
    import json
    from pathlib import Path
    from app.lang import question_language
    root = Path(__file__).resolve().parents[2] / "eval"
    qs = []
    for f in ("questions.json", "questions_sample.json"):
        if (root / f).exists():
            qs += json.loads((root / f).read_text(encoding="utf-8"))
    assert qs, "eval questions not found"
    wrong = [q["question"] for q in qs if question_language(q["question"]) != q["language"]]
    assert wrong == []


def test_gemini_switches_to_thinking_level_when_budget_rejected():
    import app.llm as llm_mod
    llm_mod._cooldown_until.clear()
    llm_mod._uses_level.discard("main")
    seen = []

    class Models:
        def generate_content_stream(self, model, contents, config):
            tc = config.thinking_config
            seen.append((tc.thinking_budget, tc.thinking_level))
            if tc.thinking_budget is not None:
                raise APIErr(400)
            yield chunk("ok")

    from types import SimpleNamespace
    llm = GeminiLLM("key", "main", [])
    llm._client = SimpleNamespace(models=Models())
    APIErr.__str__ = lambda self: "400 INVALID_ARGUMENT thinking_budget is not supported"
    try:
        assert "".join(llm.stream("s", "u")) == "ok"
        assert "".join(llm.stream("s", "u")) == "ok"  # remembered: no second rejection
    finally:
        del APIErr.__str__
    assert seen[0][0] == 0 and seen[1][0] is None and seen[2][0] is None
    llm_mod._uses_level.discard("main")
