from fastapi.testclient import TestClient

from app.config import Settings, get_settings
import json

from app.main import app, get_embedder, get_llm, get_store

calls: list[tuple] = []
USER = "11111111-1111-1111-1111-111111111111"


class FakeStore:
    def download_file(self, path):
        calls.append(("download", path))
        return b"not a pdf"

    def update_document(self, document_id, fields):
        calls.append(("update", document_id, fields))

    def get_document_name(self, document_id):
        return "Kreiselpumpe_KP-300_DE.pdf"

    def replace_chunks(self, document_id, chunks):
        calls.append(("chunks", document_id))

    def match_chunks_vector(self, embedding, user_id, k, document_ids):
        calls.append(("search", user_id, k, document_ids))
        return [{"id": "c1", "document_id": "d1", "document_name": "M.pdf", "page_number": 2,
                 "chunk_index": 0, "content": "E42", "similarity": 0.9}]

    def match_chunks_keyword(self, query_text, user_id, k, document_ids):
        calls.append(("keyword", query_text, k, document_ids))
        return [{"id": "c1", "document_id": "d1", "document_name": "M.pdf", "page_number": 2,
                 "chunk_index": 0, "content": "E42", "rank": 0.5}]


class FakeEmbedder:
    def embed(self, texts, task="document", title=None):
        return [[0.0] * 1536 for _ in texts]


class FakeLLM:
    def stream(self, system, user):
        yield "E42 means "
        yield "overpressure [1]."


class BrokenLLM:
    def stream(self, system, user):
        yield "partial "
        raise RuntimeError("boom")


app.dependency_overrides[get_settings] = lambda: Settings(ai_service_secret="test-secret", embedding_provider="gemini", gemini_api_key="", openai_api_key="")
app.dependency_overrides[get_store] = lambda: FakeStore()
app.dependency_overrides[get_embedder] = lambda: FakeEmbedder()
app.dependency_overrides[get_llm] = lambda: FakeLLM()
client = TestClient(app)
SECRET = {"X-AI-Service-Secret": "test-secret"}


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_internal_requires_secret():
    assert client.get("/internal/ping").status_code == 401
    assert client.get("/internal/ping", headers={"X-AI-Service-Secret": "wrong"}).status_code == 401
    assert client.get("/internal/ping", headers=SECRET).status_code == 200


def test_ingest_and_query_require_secret():
    assert client.post("/ingest", json={"document_id": "d1", "storage_path": "x"}).status_code == 401
    assert client.post("/query", json={"question": "q", "user_id": USER}).status_code == 401


def test_ingest_accepts_and_runs_in_background():
    calls.clear()
    res = client.post("/ingest", json={"document_id": "d1", "storage_path": "u/d1.pdf"}, headers=SECRET)
    assert res.status_code == 202
    # TestClient runs background tasks before returning; invalid PDF -> failed
    assert ("download", "u/d1.pdf") in calls
    assert calls[-1][0] == "update" and calls[-1][2]["status"] == "failed"


def test_query_json_mode_returns_answer_and_citations():
    calls.clear()
    doc = "22222222-2222-2222-2222-222222222222"
    res = client.post(
        "/query",
        json={"question": "Was bedeutet E42?", "user_id": USER, "document_ids": [doc], "stream": False},
        headers=SECRET,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["answer"] == "E42 means overpressure [1]."
    assert body["citations"] == [{"index": 1, "document_id": "d1", "document_name": "M.pdf", "page": 2,
                                  "chunk_id": "c1", "snippet": "E42"}]
    assert body["mode"] == "hybrid"
    # found by both retrievers at rank 1 -> RRF score 2/61
    assert body["sources"][0]["ranks"] == {"vector": 1, "keyword": 1}
    assert abs(body["sources"][0]["score"] - 2 / 61) < 1e-9
    assert sorted(calls) == sorted([("search", USER, 20, [doc]), ("keyword", "e42", 20, [doc])])


def test_query_mode_vector_only():
    calls.clear()
    res = client.post("/query", json={"question": "E42?", "user_id": USER, "stream": False, "mode": "vector"},
                      headers=SECRET)
    assert res.json()["mode"] == "vector"
    assert [c[0] for c in calls] == ["search"]
    assert client.post("/query", json={"question": "q", "user_id": USER, "mode": "magic"},
                       headers=SECRET).status_code == 422


def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        event_line, data_line = block.split("\n")
        events.append((event_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: "))))
    return events


def test_query_stream_mode_sends_sse_events():
    with client.stream("POST", "/query", json={"question": "E42?", "user_id": USER}, headers=SECRET) as res:
        assert res.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(res.read().decode())
    assert [n for n, _ in events] == ["sources", "token", "token", "done"]
    assert "".join(d["text"] for n, d in events if n == "token") == "E42 means overpressure [1]."
    assert events[-1][1]["citations"][0]["page"] == 2


def test_query_stream_reports_errors_as_event():
    app.dependency_overrides[get_llm] = lambda: BrokenLLM()
    try:
        res = client.post("/query", json={"question": "E42?", "user_id": USER}, headers=SECRET)
        events = parse_sse(res.text)
        assert events[-1][0] == "error" and "boom" not in events[-1][1]["message"]
    finally:
        app.dependency_overrides[get_llm] = lambda: FakeLLM()


def test_query_validates_input():
    assert client.post("/query", json={"question": "", "user_id": USER}, headers=SECRET).status_code == 422
    assert client.post("/query", json={"question": "q", "user_id": "nope"}, headers=SECRET).status_code == 422
    assert client.post("/query", json={"question": "q", "user_id": USER, "k": 500}, headers=SECRET).status_code == 422


def test_missing_openai_key_gives_503():
    del app.dependency_overrides[get_embedder]
    try:
        res = client.post("/query", json={"question": "q", "user_id": USER}, headers=SECRET)
        assert res.status_code == 503
        assert "GEMINI_API_KEY" in res.json()["detail"]
    finally:
        app.dependency_overrides[get_embedder] = lambda: FakeEmbedder()


class QuotaLLM:
    def stream(self, system, user):
        class Quota(Exception):
            code = 429

        raise Quota("429 RESOURCE_EXHAUSTED quota")
        yield ""  # pragma: no cover


def test_quota_errors_get_a_clear_message():
    app.dependency_overrides[get_llm] = lambda: QuotaLLM()
    try:
        events = parse_sse(client.post("/query", json={"question": "Was bedeutet E42?", "user_id": USER}, headers=SECRET).text)
        assert events[-1][0] == "error" and "Kontingent" in events[-1][1]["message"]
        res = client.post("/query", json={"question": "What is E42?", "user_id": USER, "stream": False}, headers=SECRET)
        assert res.status_code == 429 and "quota" in res.json()["detail"]
    finally:
        app.dependency_overrides[get_llm] = lambda: FakeLLM()
