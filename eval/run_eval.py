r"""Milestone 8 — evaluation: vector vs keyword vs hybrid retrieval, plus answer quality.

For every question in eval/questions.json:
  * Retrieval (all three modes): rank of the first chunk from the expected document + page
    (or any of `expected_pages`) within the top 6 → hit rate @6 and MRR @6.
    The question is embedded once; hybrid is computed from the same vector + keyword results
    with the production logic (adaptive RRF), so modes are compared on identical inputs.
  * Answers (default: hybrid only, --answers-for to change): generated from the top 6 chunks,
    then scored 1–5 by an LLM judge for faithfulness (claims supported by the sources) and
    correctness (agreement with expected_answer).

Usage (repo root):
    ai-service\.venv\Scripts\python eval\run_eval.py                    # retrieval + hybrid answers
    ai-service\.venv\Scripts\python eval\run_eval.py --no-answers       # retrieval only (no LLM calls)
    ai-service\.venv\Scripts\python eval\run_eval.py --answers-for vector,keyword,hybrid
    ... --tag after_titles   (writes eval/results/eval_<tag>.md/.json)

Documents must be ingested already (run eval/multilingual_check.py once).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai-service"))

import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.embeddings import create_embedder  # noqa: E402
from app.llm import SYSTEM_PROMPT, build_user_prompt, create_llm, parse_citations  # noqa: E402
from app.retrieval import (  # noqa: E402
    CANDIDATES,
    identifier_terms,
    keyword_search,
    rrf_merge,
    vector_search,
)
from app.supabase_store import SupabaseStore  # noqa: E402

EVAL = ROOT / "eval"
TOP_N = 6
MODES = ("vector", "keyword", "hybrid")

JUDGE_PROMPT = """You grade the answer of a document question-answering system.

Sources given to the system:
{sources}

Question: {question}
System answer: {answer}
Reference answer: {reference}

Score two things from 1 to 5:
- "faithfulness": are ALL claims in the system answer supported by the sources? 5 = every claim is supported,
  3 = partly supported, 1 = mostly unsupported or invented. If the answer says the sources do not contain the
  information and they really do not, that is faithful (5).
- "correctness": does the system answer agree with the reference answer? 5 = fully, 3 = partially, 1 = wrong or
  missing. Ignore language and wording differences.

Reply with JSON only: {{"faithfulness": <1-5>, "correctness": <1-5>, "reason": "<one short sentence>"}}"""


def judge(llm, question: str, reference: str, answer: str, sources) -> dict:
    src = "\n\n".join(f"[{i}] {s.document_name}, page {s.page_number}:\n{s.content}" for i, s in enumerate(sources, 1))
    prompt = JUDGE_PROMPT.format(sources=src or "(none)", question=question, answer=answer, reference=reference)
    text = "".join(llm.stream("You are a strict, fair evaluator. Output JSON only.", prompt))
    m = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
        return {"faithfulness": int(data["faithfulness"]), "correctness": int(data["correctness"]),
                "reason": str(data.get("reason", ""))[:200]}
    except (KeyError, ValueError, TypeError):
        return {"faithfulness": None, "correctness": None, "reason": f"unparseable judge output: {text[:120]!r}"}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-answers", action="store_true")
    ap.add_argument("--answers-for", default="hybrid", help="comma-separated modes to generate + judge answers for")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--user")
    ap.add_argument("--resume", action="store_true", help="reuse answers already judged in eval_<tag>.json")
    args = ap.parse_args()
    answer_modes = [] if args.no_answers else [m.strip() for m in args.answers_for.split(",") if m.strip()]

    s = get_settings()
    store = SupabaseStore(s)
    embedder = create_embedder(s.embedding_provider, s.embedding_model, s.gemini_api_key, s.openai_api_key, s.embedding_tpm)
    llm = create_llm(s.llm_provider, s.llm_model, s.gemini_api_key, s.openai_api_key, s.llm_fallback_models) if answer_modes else None
    key = s.supabase_service_role_key
    http = httpx.Client(base_url=s.supabase_url.rstrip("/"), headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=60)
    user_id = args.user or http.get("/auth/v1/admin/users").json()["users"][0]["id"]

    names = {p.name for p in (EVAL / "docs").glob("*.pdf")}
    docs = {d["name"]: d for d in http.get("/rest/v1/documents", params={
        "user_id": f"eq.{user_id}", "select": "id,name,language,status"}).json() if d["name"] in names}
    missing = names - {n for n, d in docs.items() if d["status"] == "ready"}
    if missing:
        sys.exit(f"Not ingested yet: {sorted(missing)} — run eval/multilingual_check.py first.")
    scope = [d["id"] for d in docs.values()]
    questions = json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))

    suffix = f"_{args.tag}" if args.tag else ""
    out = EVAL / "results" / f"eval{suffix}.md"
    previous: dict[tuple[str, str], dict] = {}
    if args.resume and out.with_suffix(".json").exists():
        for r in json.loads(out.with_suffix(".json").read_text(encoding="utf-8")):
            for m, e in r["modes"].items():
                if e.get("faithfulness") is not None:
                    previous[(r["question"], m)] = e
        print(f"resume: reusing {len(previous)} judged answers")

    rows = []
    print(f"{len(questions)} questions · {len(docs)} documents · answers for: {answer_modes or 'none'}\n")
    for i, q in enumerate(questions, 1):
        doc = docs[q["expected_document"]]
        pages = set(q.get("expected_pages") or [q["expected_page"]])
        ids = bool(identifier_terms(q["question"]))
        vec = vector_search(q["question"], user_id, store, embedder, k=CANDIDATES, document_ids=scope)
        kw = keyword_search(q["question"], user_id, store, k=CANDIDATES, document_ids=scope)
        results = {
            "vector": vec,
            "keyword": kw,
            # production logic (retrieval.search): keyword only joins for identifier questions
            "hybrid": rrf_merge(vec, kw, prefer="keyword") if ids else vec,
        }
        row = {"question": q["question"], "language": q["language"], "doc_language": doc["language"],
               "identifiers": ids, "expected_document": q["expected_document"], "pages": sorted(pages), "modes": {}}
        line = []
        for mode in MODES:
            top = results[mode][:TOP_N]
            rank = next((n for n, r in enumerate(top, 1) if r.document_id == doc["id"] and r.page_number in pages), None)
            entry = {"rank": rank, "top": [f"{r.document_name.split('_')[0]} p{r.page_number}" for r in top]}
            prev = previous.get((q["question"], mode))
            if mode in answer_modes and prev:
                entry.update({k: prev[k] for k in ("answer", "cited_expected", "faithfulness", "correctness", "reason", "seconds") if k in prev})
            elif mode in answer_modes:
                t0 = time.time()
                try:
                    raw = "".join(llm.stream(SYSTEM_PROMPT, build_user_prompt(q["question"], top))) if top else ""
                    answer, cits = parse_citations(raw, top)
                    time.sleep(args.delay)  # stay under per-minute LLM limits between answer and judge
                    entry["answer"] = answer
                    entry["cited_expected"] = any(c.document_id == doc["id"] and c.page in pages for c in cits)
                    entry.update(judge(llm, q["question"], q["expected_answer"], answer, top))
                except Exception as e:  # keep going on quota/overload errors
                    entry.update({"answer": "", "error": f"{type(e).__name__}: {str(e)[:120]}",
                                  "faithfulness": None, "correctness": None})
                entry["seconds"] = round(time.time() - t0, 1)
                time.sleep(args.delay)
            row["modes"][mode] = entry
            line.append(f"{mode[:3]}#{rank or '-'}")
        h = row["modes"].get("hybrid", {})
        judged = f"  F{h.get('faithfulness')} C{h.get('correctness')}" if "hybrid" in answer_modes else ""
        print(f"{i:>2}. {' '.join(line):26}{judged}  {q['question'][:70]}")
        rows.append(row)
        time.sleep(0.3)

    # ---------------- report ----------------
    def agg(mode, subset):
        n = len(subset)
        ranks = [r["modes"][mode]["rank"] for r in subset]
        hit = sum(1 for x in ranks if x) / n if n else 0
        mrr = sum(1 / x for x in ranks if x) / n if n else 0
        return hit, mrr

    cross = [r for r in rows if r["language"] != r["doc_language"]]
    codes = [r for r in rows if r["identifiers"]]
    lines = [
        "| Retrieval mode | Hit rate @6 | MRR @6 | Cross-language hit @6 | Code/part-number hit @6 | Faithfulness (1–5) | Correctness (1–5) |",
        "|---|---|---|---|---|---|---|",
    ]
    for mode in MODES:
        hit, mrr = agg(mode, rows)
        chit, _ = agg(mode, cross)
        khit, _ = agg(mode, codes)
        f = [r["modes"][mode].get("faithfulness") for r in rows if r["modes"][mode].get("faithfulness")]
        c = [r["modes"][mode].get("correctness") for r in rows if r["modes"][mode].get("correctness")]
        fs = f"{sum(f) / len(f):.2f} (n={len(f)})" if f else "–"
        cs = f"{sum(c) / len(c):.2f} (n={len(c)})" if c else "–"
        lines.append(f"| {mode} | {hit:.0%} | {mrr:.2f} | {chit:.0%} | {khit:.0%} | {fs} | {cs} |")
    table = "\n".join(lines)
    note = (f"\n{len(rows)} questions ({len(cross)} cross-language, {len(codes)} with codes/part numbers), "
            f"{len(docs)} documents. Embeddings `{s.embedding_model}`, LLM `{s.llm_model}` "
            f"(fallbacks `{s.llm_fallback_models}`); the same LLM family acts as judge.")
    print("\n" + table + note)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"# Evaluation{(' — ' + args.tag) if args.tag else ''}\n\n{table}\n{note}\n", encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nSaved {out.relative_to(ROOT)} and {out.with_suffix('.json').name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
