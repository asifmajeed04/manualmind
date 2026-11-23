"""Compare vector / keyword / hybrid retrieval on two small test documents (live Supabase + embeddings).

Usage (from ai-service/):  .venv\\Scripts\\python -m scripts.compare_modes

Ingests a German pump manual and an English datasheet with deliberately similar codes,
asks questions in all three modes and prints where the expected page ranks. Cleans up afterwards.
"""

from __future__ import annotations

import sys
import uuid

import httpx
import pymupdf

from app.config import get_settings
from app.embeddings import create_embedder
from app.ingest import run_ingest
from app.retrieval import MODES, search
from app.supabase_store import BUCKET, SupabaseStore
from scripts.smoke_ingest import SAMPLE_PAGES

DATASHEET_PAGES = [
    "Dosing Pump DP-50 — Datasheet\n\nTechnical data: max. pressure 10 bar, flow rate 50 l/h, "
    "motor 0.37 kW. Controller part number 6ES7 214-1BG40-0XB0. Operating temperature 5–40 °C.",
    "Troubleshooting\nError E41: low flow — check the suction line for air.\n"
    "Error E43: motor stall — check the motor and the gearbox.\n"
    "Seal kit replacement every 4000 operating hours.",
]

# (question, expected document, expected page)
QUESTIONS = [
    ("6ES7 214-1AG40", "manual", 2),                         # exact part number
    ("E17", "manual", 3),                                    # bare error code
    ("What does error E42 mean?", "manual", 3),              # EN question, DE doc
    ("Wie oft muss die Dichtung geprüft werden?", "manual", 2),
    ("What should I check when the motor overheats?", "manual", 3),
    ("Fehler E43 an der Dosierpumpe", "datasheet", 2),        # DE question, EN doc
    ("maximum pressure of the dosing pump", "datasheet", 1),
]


def make_pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    s = get_settings()
    store = SupabaseStore(s)
    embedder = create_embedder(s.embedding_provider, s.embedding_model, s.gemini_api_key, s.openai_api_key, s.embedding_tpm)
    key = s.supabase_service_role_key
    http = httpx.Client(base_url=s.supabase_url.rstrip("/"), headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=60)
    users = http.get("/auth/v1/admin/users").json().get("users", [])
    if not users:
        print("Need one user in Supabase Auth.")
        return 1
    user_id = users[0]["id"]

    docs = {
        "manual": ("Kreiselpumpe_KP-300.pdf", make_pdf(SAMPLE_PAGES)),
        "datasheet": ("DP-50_Datasheet.pdf", make_pdf(DATASHEET_PAGES)),
    }
    ids: dict[str, str] = {}
    paths: list[str] = []
    try:
        for key_, (name, pdf) in docs.items():
            doc_id = str(uuid.uuid4())
            path = f"{user_id}/{doc_id}.pdf"
            http.post(f"/storage/v1/object/{BUCKET}/{path}", content=pdf, headers={"Content-Type": "application/pdf"}).raise_for_status()
            paths.append(path)
            http.post("/rest/v1/documents", json={"id": doc_id, "user_id": user_id, "name": name, "storage_path": path}).raise_for_status()
            ids[key_] = doc_id
            run_ingest(doc_id, path, store, embedder)
        print(f"Ingested: {', '.join(n for n, _ in docs.values())}\n")

        scope = list(ids.values())  # only search the test documents
        rr = {m: 0.0 for m in MODES}
        hits = {m: 0 for m in MODES}
        print(f"{'question':48} {'vector':>7} {'keyword':>8} {'hybrid':>7}")
        for q, exp_doc, exp_page in QUESTIONS:
            row = []
            for mode in MODES:
                results = search(q, user_id, store, embedder, mode=mode, document_ids=scope)[:6]
                rank = next(
                    (i for i, r in enumerate(results, 1) if r.document_id == ids[exp_doc] and r.page_number == exp_page),
                    None,
                )
                if rank:
                    hits[mode] += 1
                    rr[mode] += 1 / rank
                row.append(f"#{rank}" if rank else "miss")
            print(f"{q[:48]:48} {row[0]:>7} {row[1]:>8} {row[2]:>7}")
        n = len(QUESTIONS)
        print(f"\n{'hit rate @6':48} " + " ".join(f"{hits[m] / n:>7.0%}" if m != 'keyword' else f"{hits[m] / n:>8.0%}" for m in MODES))
        print(f"{'MRR':48} " + " ".join(f"{rr[m] / n:>7.2f}" if m != 'keyword' else f"{rr[m] / n:>8.2f}" for m in MODES))
        return 0
    finally:
        for doc_id in ids.values():
            http.delete("/rest/v1/documents", params={"id": f"eq.{doc_id}"})
        if paths:
            http.request("DELETE", f"/storage/v1/object/{BUCKET}", json={"prefixes": paths})
        print("\nCleaned up test documents.")


if __name__ == "__main__":
    sys.exit(main())
