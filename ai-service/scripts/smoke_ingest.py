"""Live test against your Supabase + embedding provider: ingest a PDF, then run vector searches.

Usage (from ai-service/):
    .venv\\Scripts\\python -m scripts.smoke_ingest                 # generated German test manual
    .venv\\Scripts\\python -m scripts.smoke_ingest my.pdf          # your own PDF
    .venv\\Scripts\\python -m scripts.smoke_ingest my.pdf --keep   # keep data afterwards
    ... --user <uuid>   # owner of the test document (default: first user in Supabase Auth)
    ... --ask "question" (repeatable)  # custom search questions

The document is owned by an existing Supabase user (vector search is per user).
Everything created is deleted at the end unless --keep is given.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

import httpx
import pymupdf

from app.answer import answer_events, collect
from app.config import get_settings
from app.embeddings import create_embedder
from app.llm import create_llm
from app.ingest import run_ingest
from app.retrieval import vector_search
from app.supabase_store import BUCKET, SupabaseStore

SAMPLE_PAGES = [
    "Betriebsanleitung Kreiselpumpe KP-300\n\n1. Sicherheitshinweise\n"
    "Vor allen Wartungsarbeiten die Pumpe vom Netz trennen. Nur geschultes Personal darf "
    "Arbeiten an der Anlage durchführen. Schutzbrille und Handschuhe tragen.",
    "2. Wartung\nDie Gleitringdichtung ist alle 500 Betriebsstunden zu prüfen. "
    "Das Lager wird alle 2000 Betriebsstunden mit Fett nachgeschmiert. "
    "Ersatzteil Drucksensor: 6ES7 214-1AG40-0XB0.",
    "3. Störungen\nFehlercode E42: Überdruck im System. Ursache: Druckventil verstopft. "
    "Abhilfe: Ventil reinigen und Drucksensor prüfen.\n"
    "Fehlercode E17: Motor überhitzt. Lüfter und Umgebungstemperatur prüfen.",
]
SAMPLE_QUESTIONS = [
    ("What does error E42 mean?", 3),               # English question, German doc
    ("Wie oft muss die Dichtung geprüft werden?", 2),
    ("What safety equipment should I wear?", 1),
]
UNANSWERABLE = "What is the warranty period of the pump?"


def make_sample_pdf() -> bytes:
    doc = pymupdf.open()
    for text in SAMPLE_PAGES:
        doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # show umlauts correctly on Windows consoles
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", nargs="?")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--user")
    ap.add_argument("--ask", action="append")
    args = ap.parse_args()

    settings = get_settings()
    try:
        embedder = create_embedder(
            settings.embedding_provider, settings.embedding_model,
            settings.gemini_api_key, settings.openai_api_key, settings.embedding_tpm,
        )
    except RuntimeError as e:
        print(f"{e} — set it in .env")
        return 1
    try:
        llm = create_llm(settings.llm_provider, settings.llm_model, settings.gemini_api_key, settings.openai_api_key,
                          settings.llm_fallback_models)
    except RuntimeError as e:
        print(f"LLM disabled: {e}")
        llm = None
    store = SupabaseStore(settings)
    key = settings.supabase_service_role_key
    http = httpx.Client(
        base_url=settings.supabase_url.rstrip("/"),
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=60,
    )

    user_id = args.user
    if not user_id:
        users = http.get("/auth/v1/admin/users").json().get("users", [])
        if not users:
            print("No users in Supabase Auth. Add one (Authentication -> Users -> Add user) or pass --user <uuid>.")
            return 1
        user_id = users[0]["id"]

    if args.pdf:
        path = Path(args.pdf)
        pdf, name = path.read_bytes(), path.name
        questions = [(q, None) for q in (args.ask or [])]
    else:
        pdf, name = make_sample_pdf(), "smoke-test-kreiselpumpe.pdf"
        questions = [(q, None) for q in args.ask] if args.ask else SAMPLE_QUESTIONS

    doc_id = str(uuid.uuid4())
    storage_path = f"{user_id}/{doc_id}.pdf"
    print(f"1. Uploading '{name}' ({len(pdf) // 1024} KB) for user {user_id[:8]}...")
    http.post(
        f"/storage/v1/object/{BUCKET}/{storage_path}",
        content=pdf,
        headers={"Content-Type": "application/pdf"},
    ).raise_for_status()

    ok = True
    try:
        print("2. Creating documents row (status=processing)")
        http.post(
            "/rest/v1/documents",
            json={"id": doc_id, "user_id": user_id, "name": name, "storage_path": storage_path},
        ).raise_for_status()

        print("3. Running ingestion (parse, chunk, embed, store) ...")
        run_ingest(doc_id, storage_path, store, embedder)

        doc = http.get("/rest/v1/documents", params={"id": f"eq.{doc_id}", "select": "*"}).json()[0]
        chunks = http.get(
            "/rest/v1/chunks",
            params={"document_id": f"eq.{doc_id}", "select": "chunk_index,embedding", "order": "chunk_index"},
        ).json()
        embedded = sum(1 for c in chunks if c["embedding"])

        print("\n=== Ingestion ===")
        print(f"status     : {doc['status']}" + (f"  ({doc['error']})" if doc["error"] else ""))
        print(f"language   : {doc['language']}")
        print(f"page_count : {doc['page_count']}")
        print(f"chunks     : {len(chunks)} ({embedded} with embeddings)")
        ok = doc["status"] == "ready" and embedded == len(chunks) > 0

        if ok and questions:
            print("\n=== Vector search (top 3, this document only) ===")
            for q, expected_page in questions:
                results = vector_search(q, user_id, store, embedder, k=3, document_ids=[doc_id])
                pages = [r.page_number for r in results]
                mark = ""
                if expected_page is not None:
                    hit = pages and pages[0] == expected_page
                    ok = ok and bool(hit)
                    mark = "  OK" if hit else f"  MISS (expected p.{expected_page})"
                print(f"\nQ: {q}{mark}")
                for r in results:
                    print(f"   p.{r.page_number}  sim={r.score:.3f}  {r.content[:70]}...")

        if ok and questions and llm:
            print("\n=== LLM answers with citations ===")
            for q, expected_page in questions + ([(UNANSWERABLE, None)] if not args.pdf and not args.ask else []):
                res = collect(answer_events(q, user_id, store, embedder, llm, document_ids=[doc_id]))
                cited = [c["page"] for c in res["citations"]]
                mark = ""
                if expected_page is not None:
                    hit = expected_page in cited
                    ok = ok and hit
                    mark = "  OK" if hit else f"  MISS (expected citation of p.{expected_page})"
                elif q == UNANSWERABLE:
                    mark = "  (not in the manual — should say so)"
                print(f"\nQ: {q}{mark}")
                print(f"A: {res['answer']}")
                for c in res["citations"]:
                    print(f"   [{c['index']}] {c['document_name']}, page {c['page']}")
        return 0 if ok else 1
    finally:
        if args.keep:
            print(f"\n--keep: left document {doc_id} in Supabase")
        else:
            http.delete("/rest/v1/documents", params={"id": f"eq.{doc_id}"})  # chunks cascade
            http.request("DELETE", f"/storage/v1/object/{BUCKET}", json={"prefixes": [storage_path]})
            print("\nCleaned up test document, chunks and file.")


if __name__ == "__main__":
    sys.exit(main())
