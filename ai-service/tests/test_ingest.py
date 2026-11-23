import pymupdf
import pytest

from app.embeddings import EMBEDDING_DIMS
from app.ingest import (
    Chunk,
    IngestError,
    chunk_pages,
    chunk_text,
    count_tokens,
    detect_language,
    extract_pages,
    run_ingest,
)

EN = (
    "The pump must be inspected every 500 operating hours. Check the seal for leaks. "
    "If error code E42 appears, replace the pressure sensor 6ES7 214-1AG40. "
)
DE = (
    "Die Pumpe muss alle 500 Betriebsstunden geprüft werden. Prüfen Sie die Dichtung auf Undichtigkeiten. "
    "Wenn der Fehlercode E42 erscheint, ersetzen Sie den Drucksensor 6ES7 214-1AG40. "
)


def make_pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(40, 40, 560, 800), text, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


# --- chunking --------------------------------------------------------------
def test_short_text_is_one_chunk():
    assert chunk_text(EN) == [EN.strip()]


def test_empty_text_gives_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n ") == []


def test_chunks_respect_size_and_overlap():
    text = " ".join(f"Sentence number {i} describes maintenance step {i} in detail." for i in range(300))
    chunks = chunk_text(text, size=100, overlap=20)
    assert len(chunks) > 5
    for c in chunks:
        assert count_tokens(c) <= 100
    # consecutive chunks share text (overlap)
    for a, b in zip(chunks, chunks[1:]):
        assert b.split(".")[0] in a
    # nothing lost: every sentence appears somewhere
    joined = " ".join(chunks)
    assert all(f"Sentence number {i} " in joined for i in range(300))


def test_very_long_sentence_is_hard_split():
    text = "word " * 2000  # one "sentence", ~2000 tokens
    chunks = chunk_text(text, size=500, overlap=50)
    assert len(chunks) >= 4
    assert all(count_tokens(c) <= 500 for c in chunks)


def test_chunks_never_cross_pages_and_indices_are_sequential():
    pages = [EN * 30, "", DE * 30]
    chunks = chunk_pages(pages, size=120, overlap=20)
    assert {c.page_number for c in chunks} == {1, 3}  # empty page 2 skipped
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    for c in chunks:
        if c.page_number == 1:
            assert "Pumpe" not in c.content
        else:
            assert "pump must" not in c.content


def test_part_numbers_survive_chunking():
    chunks = chunk_text(EN * 50, size=100, overlap=20)
    assert any("6ES7 214-1AG40" in c for c in chunks)


# --- extraction & language ------------------------------------------------
def test_extract_pages_keeps_page_order():
    pages = extract_pages(make_pdf(["First page E42", "", "Third page 6ES7 214-1AG40"]))
    assert len(pages) == 3
    assert "First page" in pages[0]
    assert pages[1] == ""
    assert "6ES7 214-1AG40" in pages[2]


def test_extract_rejects_non_pdf():
    with pytest.raises(IngestError):
        extract_pages(b"not a pdf")


def test_detect_language():
    assert detect_language(DE * 3) == "de"
    assert detect_language(EN * 3) == "en"
    assert detect_language("12345") is None


# --- pipeline ---------------------------------------------------------------
class FakeEmbedder:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls: list[list[str]] = []

    def embed(self, texts, task="document", title=None):
        assert task == "document"
        if self.fail:
            raise RuntimeError("openai down, key sk-secret")
        self.calls.append(texts)
        return [[0.01] * EMBEDDING_DIMS for _ in texts]


class FakeStore:
    def __init__(self, pdf: bytes):
        self.pdf = pdf
        self.updates: list[dict] = []
        self.chunks: list[Chunk] = []

    def download_file(self, path):
        return self.pdf

    def update_document(self, document_id, fields):
        self.updates.append(fields)

    def get_document_name(self, document_id):
        return "Kreiselpumpe_KP-300_DE.pdf"

    def replace_chunks(self, document_id, chunks):
        self.chunks = chunks


def test_run_ingest_success():
    store = FakeStore(make_pdf([DE * 5, DE * 5]))
    run_ingest("doc-1", "u/doc-1.pdf", store, FakeEmbedder())
    assert store.updates[-1] == {"status": "ready", "error": None, "page_count": 2, "language": "de"}
    assert {c.page_number for c in store.chunks} == {1, 2}


def test_run_ingest_scanned_pdf_fails_with_message():
    store = FakeStore(make_pdf(["", ""]))
    run_ingest("doc-1", "u/doc-1.pdf", store, FakeEmbedder())
    assert store.updates[-1]["status"] == "failed"
    assert "No text found" in store.updates[-1]["error"]
    assert store.chunks == []


def test_run_ingest_hides_internal_errors():
    class Broken(FakeStore):
        def download_file(self, path):
            raise RuntimeError("secret connection string leaked")

    store = Broken(b"")
    run_ingest("doc-1", "x", store, FakeEmbedder())
    assert store.updates[-1]["status"] == "failed"
    assert "secret" not in store.updates[-1]["error"]


def test_run_ingest_embeds_every_chunk():
    store, emb = FakeStore(make_pdf([EN * 40, DE * 40])), FakeEmbedder()
    run_ingest("doc-1", "p", store, emb)
    assert store.chunks and all(len(c.embedding) == EMBEDDING_DIMS for c in store.chunks)
    assert emb.calls == [[c.content for c in store.chunks]]


def test_run_ingest_embedding_failure_marks_failed_without_leaking():
    store = FakeStore(make_pdf([EN * 5]))
    run_ingest("doc-1", "p", store, FakeEmbedder(fail=True))
    assert store.updates[-1]["status"] == "failed"
    assert "embeddings" in store.updates[-1]["error"]
    assert "sk-secret" not in store.updates[-1]["error"]
    assert store.chunks == []  # nothing half-written


def test_document_title_from_file_name():
    from app.ingest import document_title
    assert document_title("SEW_MOVITRAC_LTE-B_Betriebsanleitung_DE.pdf") == "SEW MOVITRAC LTE-B Betriebsanleitung DE"
    assert document_title(None) is None


def test_run_ingest_passes_document_title_to_embedder():
    seen = {}

    class TitleEmbedder(FakeEmbedder):
        def embed(self, texts, task="document", title=None):
            seen["title"] = title
            return super().embed(texts, task)

    run_ingest("doc-1", "p", FakeStore(make_pdf([EN * 3])), TitleEmbedder())
    assert seen["title"] == "Kreiselpumpe KP-300 DE"


def test_ingest_quota_error_message():
    class QuotaEmbedder(FakeEmbedder):
        def embed(self, texts, task="document", title=None):
            raise RuntimeError("Daily embedding quota exhausted — try again tomorrow.")

    store = FakeStore(make_pdf([EN * 3]))
    run_ingest("doc-1", "p", store, QuotaEmbedder())
    assert store.updates[-1]["status"] == "failed" and "quota" in store.updates[-1]["error"]
