# Evaluation

| File | Purpose |
|---|---|
| `docs/` | Real public manuals (2 German, 2 English) — see *Documents* below. |
| `docs_sample/`, `questions_sample.json` | Two tiny generated PDFs + 16 questions (first sanity check; `make_sample_docs.py`). |
| `questions.json` | 40 questions on the real manuals (24 cross-language) with expected document/page/answer (SPEC §7). |
| `multilingual_check.py` | **Milestone 7** — cross-language check (DE docs ⇄ EN questions). |
| `results/` | Generated reports (`multilingual.md` + raw `multilingual.json`). |
| `run_eval.py` | Milestone 8 — vector vs keyword vs hybrid, hit rate / MRR / faithfulness. |

## Run (from the repo root)

```bash
ai-service\.venv\Scripts\python eval\make_sample_docs.py
ai-service\.venv\Scripts\python eval\multilingual_check.py          # reuses ingested docs
ai-service\.venv\Scripts\python eval\multilingual_check.py --fresh  # re-ingest everything
```

Documents are ingested for the first user in Supabase Auth (or `--user <uuid>`), so they also appear in
that user's library in the app. Free-tier Gemini can be slow or overloaded; the LLM falls back to the
models in `LLM_FALLBACK_MODELS`, and `--delay` spaces out requests.

## Adding real documents

1. Put the PDF in `docs/` (text-based PDFs only — scanned images are not supported).
2. Add questions to `questions.json`: `question`, `language` (`de`/`en`), `expected_document` (file name),
   `expected_page` (1-based PDF page), `expected_answer`. Ask some questions in the *other* language.

## Documents (`docs/`)

| File | Lang | Pages | Source |
|---|---|---|---|
| `SEW_MOVITRAC_LTE-B_Betriebsanleitung_DE.pdf` | DE | 108 | SEW-EURODRIVE, `download.sew-eurodrive.com/download/pdf_u/20265735.pdf` |
| `Wilo-Stratos_PICO_plus_Betriebsanleitung_DE.pdf` | DE | 26 | Wilo, `cms.media.wilo.com/.../wilo522782.pdf` — **German pages 1–26 only** (the original is an 80-page multi-language bundle; page numbers unchanged) |
| `Danfoss_VLT_Micro_Drive_FC51_Operating_Guide_EN.pdf` | EN | 38 | Danfoss, `assets.danfoss.com/documents/latest/271209/AQ276736419659en-000101.pdf` |
| `Grundfos_CR_CRI_CRN_Installation_Operating_EN.pdf` | EN | 36 | Grundfos, `api.grundfos.com/literature/Grundfosliterature-6679374.pdf` |

Two cross-language pairs on similar topics (frequency inverters SEW ⇄ Danfoss, pumps Wilo ⇄ Grundfos), so
retrieval must pick the right document, not just the right topic. Public manufacturer documents; not redistributed
with this repo — re-download from the sources above.
