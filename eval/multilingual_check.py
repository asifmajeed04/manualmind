r"""Milestone 7 — multilingual check: German docs with English questions and vice versa.

For every item in eval/questions.json the full pipeline runs (hybrid search + LLM), then:
  * retrieval hit  — expected document + page among the 6 chunks given to the LLM
  * answer language — detected language of the answer == language of the question
  * citation ok    — the answer cites the expected page
Results are grouped by (document language -> question language).

Usage (from the repo root):
    ai-service\.venv\Scripts\python eval\multilingual_check.py            # reuse already-ingested docs
    ai-service\.venv\Scripts\python eval\multilingual_check.py --fresh    # re-ingest eval/docs/*.pdf
    ... --mode vector|keyword|hybrid   --delay 2   --out eval/results/multilingual.md

The documents are ingested for the first user in Supabase Auth (or --user <uuid>) so they also
show up in that user's library in the app.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai-service"))

import httpx  # noqa: E402

from app.answer import answer_events, collect  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.embeddings import create_embedder  # noqa: E402
from app.ingest import detect_language, run_ingest  # noqa: E402
from app.llm import create_llm  # noqa: E402
from app.supabase_store import BUCKET, SupabaseStore  # noqa: E402

EVAL = ROOT / "eval"


def supabase_http(settings) -> httpx.Client:
    key = settings.supabase_service_role_key
    return httpx.Client(
        base_url=settings.supabase_url.rstrip("/"),
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=60,
    )


def ensure_documents(http, store, embedder, user_id: str, fresh: bool) -> dict[str, dict]:
    """Ingest every PDF in eval/docs for the user (or reuse a ready copy). Returns name -> document row."""
    pdfs = sorted((EVAL / "docs").glob("*.pdf"))
    if not pdfs:
        sys.exit("No PDFs in eval/docs — run eval/make_sample_docs.py or add real manuals.")
    existing = http.get(
        "/rest/v1/documents",
        params={"user_id": f"eq.{user_id}", "select": "id,name,status,language,page_count,storage_path"},
    ).json()
    by_name = {d["name"]: d for d in existing}
    docs: dict[str, dict] = {}
    for pdf in pdfs:
        old = by_name.get(pdf.name)
        if old and old["status"] == "ready" and not fresh:
            docs[pdf.name] = old
            continue
        doc_id = str(uuid.uuid4())
        path = f"{user_id}/{doc_id}.pdf"
        print(f"  ingesting {pdf.name} ...", flush=True)
        http.post(f"/storage/v1/object/{BUCKET}/{path}", content=pdf.read_bytes(),
                  headers={"Content-Type": "application/pdf"}).raise_for_status()
        http.post("/rest/v1/documents", json={"id": doc_id, "user_id": user_id, "name": pdf.name,
                                              "storage_path": path}).raise_for_status()
        run_ingest(doc_id, path, store, embedder)
        new = http.get("/rest/v1/documents", params={"id": f"eq.{doc_id}", "select": "*"}).json()[0]
        # replace the old copy only once the new one is ready (a failed re-ingest keeps the old one)
        keep, drop = (new, old) if new["status"] == "ready" or not old or old["status"] != "ready" else (old, new)
        if drop:
            http.delete("/rest/v1/documents", params={"id": f"eq.{drop['id']}"})
            http.request("DELETE", f"/storage/v1/object/{BUCKET}", json={"prefixes": [drop["storage_path"]]})
        if keep is old:
            print(f"  re-ingest of {pdf.name} failed ({new.get('error')}); kept the previous copy")
        docs[pdf.name] = keep
    for name, d in docs.items():
        if d["status"] != "ready":
            sys.exit(f"{name} failed to ingest: {d.get('error')}")
    return docs


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--ingest-only", action="store_true", help="(re-)ingest eval/docs and stop")
    ap.add_argument("--user")
    ap.add_argument("--mode", default="hybrid", choices=["vector", "keyword", "hybrid"])
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between questions (free-tier rate limits)")
    ap.add_argument("--out", default=str(EVAL / "results" / "multilingual.md"))
    args = ap.parse_args()

    s = get_settings()
    store = SupabaseStore(s)
    embedder = create_embedder(s.embedding_provider, s.embedding_model, s.gemini_api_key, s.openai_api_key, s.embedding_tpm)
    llm = create_llm(s.llm_provider, s.llm_model, s.gemini_api_key, s.openai_api_key, s.llm_fallback_models)
    http = supabase_http(s)
    user_id = args.user or (http.get("/auth/v1/admin/users").json().get("users") or [{}])[0].get("id")
    if not user_id:
        sys.exit("Need one user in Supabase Auth (or --user).")

    questions = json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))
    print(f"Documents ({EVAL / 'docs'}):")
    docs = ensure_documents(http, store, embedder, user_id, args.fresh)
    for name, d in docs.items():
        print(f"  {d['language'] or '??'}  {d['page_count']:>3} p.  {name}")
    if args.ingest_only:
        return 0
    scope = [d["id"] for d in docs.values()]

    rows = []
    groups: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    print(f"\nRunning {len(questions)} questions (mode={args.mode}) ...\n")
    for i, q in enumerate(questions, 1):
        doc = docs.get(q["expected_document"])
        if not doc:
            print(f"  skip (document not found): {q['expected_document']}")
            continue
        t0 = time.time()
        try:
            res = collect(answer_events(q["question"], user_id, store, embedder, llm, document_ids=scope, mode=args.mode))
        except Exception as e:  # e.g. every model overloaded — count as failure, keep going
            print(f"{i:>2}. ERROR {type(e).__name__}: {str(e)[:100]}  {q['question']}")
            res = {"sources": [], "citations": [], "answer": ""}
        secs = time.time() - t0
        pages = set(q.get("expected_pages") or [q["expected_page"]])
        rank = next((n for n, src in enumerate(res["sources"], 1)
                     if src["document_id"] == doc["id"] and src["page"] in pages), None)
        hit = rank is not None
        cited = any(c["document_id"] == doc["id"] and c["page"] in pages for c in res["citations"])
        ans_lang = detect_language(res["answer"])
        lang_ok = ans_lang == q["language"]
        key = f"{doc['language']}→{q['language']}"
        g = groups[key]
        g["n"] += 1
        g["hit"] += hit
        g["lang"] += lang_ok
        g["cite"] += cited
        mark = lambda ok: "✔" if ok else "✘"  # noqa: E731
        print(f"{i:>2}. [{key}] {mark(hit)} hit{f'#{rank}' if rank else ''}  {mark(lang_ok)} lang({ans_lang})  {mark(cited)} cite  {secs:4.1f}s  {q['question']}")
        if not (hit and lang_ok and cited):
            print(f"      answer: {res['answer'][:160]!r}")
        rows.append({**q, "doc_language": doc["language"], "hit": hit, "rank": rank, "answer_language": ans_lang,
                     "lang_ok": lang_ok, "cited": cited, "answer": res["answer"], "seconds": round(secs, 1)})
        time.sleep(args.delay)

    # ---- report ----
    def pct(a, b):
        return f"{a / b:.0%}" if b else "–"

    order = ["de→de", "de→en", "en→en", "en→de"]
    label = {"de→de": "German doc · German question", "de→en": "German doc · **English** question",
             "en→en": "English doc · English question", "en→de": "English doc · **German** question"}
    lines = [
        f"| Document → question ({args.mode}) | n | Retrieval hit @6 | Answer in question language | Correct page cited |",
        "|---|---|---|---|---|",
    ]
    tot = defaultdict(int)
    for k in order + [k for k in groups if k not in order]:
        g = groups.get(k)
        if not g:
            continue
        for f in ("n", "hit", "lang", "cite"):
            tot[f] += g[f]
        lines.append(f"| {label.get(k, k)} | {g['n']} | {pct(g['hit'], g['n'])} | {pct(g['lang'], g['n'])} | {pct(g['cite'], g['n'])} |")
    lines.append(f"| **All** | {tot['n']} | {pct(tot['hit'], tot['n'])} | {pct(tot['lang'], tot['n'])} | {pct(tot['cite'], tot['n'])} |")
    cross = [r for r in rows if r["doc_language"] != r["language"]]
    if cross:
        lines.append(f"\nCross-language questions: {len(cross)} — "
                     f"hit {pct(sum(r['hit'] for r in cross), len(cross))}, "
                     f"answer language {pct(sum(r['lang_ok'] for r in cross), len(cross))}, "
                     f"citation {pct(sum(r['cited'] for r in cross), len(cross))}.")
    table = "\n".join(lines)
    print("\n" + table)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        f"# Multilingual check\n\nModels: embeddings `{s.embedding_model or s.embedding_provider}`, "
        f"LLM `{s.llm_model or s.llm_provider}`. Documents: {', '.join(docs)}.\n\n{table}\n",
        encoding="utf-8",
    )
    out.with_suffix(".json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {out} and {out.with_suffix('.json').name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
