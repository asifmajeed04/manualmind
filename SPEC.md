# Project Spec: Multilingual RAG Assistant for Industrial Documentation

## 1. Goal
A web app where users upload technical documents (PDF manuals, datasheets, maintenance guides) in **German or English**, ask questions in **either language**, and get answers with **page-level citations**.

Key differentiators:
1. **Multilingual (DE + EN):** ask in English about German docs and vice versa.
2. **Hybrid search:** keyword search (Postgres full-text) + vector search (pgvector), merged with Reciprocal Rank Fusion (RRF). Needed because industrial docs contain exact terms like part numbers and error codes (e.g. "Fehlercode E42", "6ES7 214-1AG40").
3. **Evaluation suite:** a test set of questions with measured retrieval and answer quality.

## 2. Tech Stack
| Layer | Technology |
|---|---|
| Frontend | React (Vite) + TypeScript + Tailwind CSS |
| Backend API | Node.js + Express (TypeScript): auth, uploads, chat routing |
| AI service | Python + FastAPI: parsing, chunking, embeddings, retrieval, LLM calls |
| Database | Supabase (Postgres + pgvector + full-text search) |
| File storage | Supabase Storage |
| Embeddings | OpenAI `text-embedding-3-small` (multilingual, 1536 dims) |
| LLM | OpenAI `gpt-4o-mini` (configurable via env var) |
| PDF parsing | `pymupdf` (PyMuPDF), keep page numbers |
| Deployment | Frontend: Vercel · Node + Python: Render or Railway (Docker) |

## 3. Architecture & Flow

```
React  ──►  Express API  ──►  FastAPI (AI service)  ──►  Supabase (Postgres + pgvector)
                                     │
                                     └──►  OpenAI (embeddings + chat)
```

### 3.1 Ingestion flow (upload)
1. User uploads PDF in React → Express receives it (multer), stores the file in Supabase Storage, creates a `documents` row with `status = 'processing'`.
2. Express calls FastAPI `POST /ingest` with `document_id` and the file path.
3. FastAPI:
   - Extracts text **page by page** (keep `page_number`).
   - Detects language per document (`langdetect`), store as `de` or `en`.
   - Splits into chunks: ~500 tokens, 50-token overlap, never crossing page boundaries.
   - Creates embeddings in batches (max 100 per request).
   - Inserts chunks into `chunks` table (text, page, embedding, tsvector).
   - Updates `documents.status = 'ready'` (or `'failed'` with error message).
4. React polls `GET /api/documents/:id` until status is `ready`.

### 3.2 Question flow (chat)
1. User asks a question → Express → FastAPI `POST /query`.
2. FastAPI:
   - Embeds the question.
   - **Vector search:** top 20 chunks by cosine similarity (pgvector).
   - **Keyword search:** top 20 chunks by `ts_rank` using Postgres full-text search. Use the `simple` text search config so German and English both work (no language-specific stemming that breaks part numbers).
   - **Merge with RRF:** `score = Σ 1 / (60 + rank)` across both lists; keep top 6.
   - Builds a prompt with the 6 chunks, each labeled `[1]`, `[2]`… with document name and page.
   - Calls the LLM. System prompt rules:
     - Answer **in the language of the question**.
     - Use only the provided sources; cite as `[1]`, `[2]`.
     - If the answer isn't in the sources, say so. Do not guess.
   - Returns `{ answer, citations: [{ index, document_name, page, snippet }] }`.
3. Stream the answer to React (Server-Sent Events) and show clickable citations.

## 4. Database Schema (Supabase / Postgres)

```sql
create extension if not exists vector;

create table documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  name text not null,
  storage_path text not null,
  language text,                 -- 'de' | 'en'
  page_count int,
  status text not null default 'processing',  -- processing | ready | failed
  error text,
  created_at timestamptz default now()
);

create table chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid references documents(id) on delete cascade,
  page_number int not null,
  chunk_index int not null,
  content text not null,
  embedding vector(1536),
  tsv tsvector generated always as (to_tsvector('simple', content)) stored
);

create index on chunks using hnsw (embedding vector_cosine_ops);
create index on chunks using gin (tsv);

create table chat_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  role text not null,            -- user | assistant
  content text not null,
  citations jsonb,
  created_at timestamptz default now()
);
```

Enable Row Level Security so users only see their own documents, chunks and messages.

Create SQL functions (RPC) `match_chunks_vector(query_embedding, user_id, k)` and `match_chunks_keyword(query_text, user_id, k)` that FastAPI calls.

## 5. API Endpoints

### Express (public, `/api`)
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/documents` | Upload PDF (max 20 MB) |
| GET | `/api/documents` | List user's documents |
| GET | `/api/documents/:id` | Document status |
| DELETE | `/api/documents/:id` | Delete document + chunks + file |
| POST | `/api/chat` | Ask a question (SSE stream) |
| GET | `/api/chat/history` | Past messages |

Auth: Supabase Auth (email magic link). Express verifies the Supabase JWT on every request.

### FastAPI (internal only, protected by shared secret header)
| Method | Path | Purpose |
|---|---|---|
| POST | `/ingest` | Parse, chunk, embed, store |
| POST | `/query` | Hybrid search + LLM answer (streaming) |
| GET | `/health` | Health check |

## 6. Frontend Pages
1. **Login:** Supabase magic link.
2. **Documents:** drag-and-drop upload, list with name, language badge (DE/EN), page count, status, delete button.
3. **Chat:**
   - Message list with streamed answers.
   - Citations `[1]` rendered as clickable chips → open a side panel with the source snippet, document name and page number.
   - Option to restrict the question to selected documents.
4. Language toggle for UI text (DE/EN) — nice to have.

## 7. Evaluation Suite (`/eval` folder, Python)
- `eval/questions.json`: 30–50 items, mix of German and English questions:
  ```json
  { "question": "...", "language": "en", "expected_document": "...", "expected_page": 12, "expected_answer": "..." }
  ```
- `eval/run_eval.py` compares three retrieval modes: **vector only**, **keyword only**, **hybrid**.
- Metrics:
  - **Hit rate @6:** was the expected page among the top 6 chunks?
  - **MRR:** how high the correct chunk ranked.
  - **Answer faithfulness:** LLM-as-judge (score 1–5: is the answer supported by the sources?).
- Output a Markdown results table → paste into README.

## 8. Project Structure
```
rag-industrial-docs/
├── frontend/            # React + Vite
├── backend/             # Express (TypeScript)
├── ai-service/          # FastAPI (Python)
│   ├── app/
│   │   ├── ingest.py
│   │   ├── retrieval.py   # vector, keyword, RRF
│   │   ├── llm.py
│   │   └── main.py
│   └── Dockerfile
├── eval/
├── supabase/migrations/
├── docker-compose.yml   # run everything locally
└── README.md
```

## 9. Environment Variables
```
OPENAI_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=    # backend + ai-service only
SUPABASE_ANON_KEY=            # frontend
AI_SERVICE_URL=
AI_SERVICE_SECRET=
LLM_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small
```

## 10. Build Order (milestones)
1. **Setup:** monorepo, docker-compose, Supabase project, migrations.
2. **Ingestion:** upload → parse → chunk → store (no embeddings yet). Test with one PDF.
3. **Embeddings + vector search:** working `/query` with vector-only retrieval.
4. **LLM answers with citations:** prompt + citation parsing.
5. **Frontend:** documents page + chat with streaming and citation side panel.
6. **Hybrid search:** keyword search + RRF merge.
7. **Multilingual check:** test German docs with English questions and vice versa.
8. **Evaluation suite:** questions set + comparison table.
9. **Deploy + README:** demo GIF, architecture diagram, eval results, "known limitations".

## 11. Non-Functional Requirements
- Unit tests for chunking and RRF (pytest), API tests for Express (Jest/Supertest).
- Clear error messages for failed uploads (scanned PDFs without text → show "no text found").
- Log token usage per request.
- Never expose the service role key or OpenAI key to the frontend.

## 12. Test Data
Use 5–10 public technical PDFs, mixed German and English (e.g. machine manuals, product datasheets, safety datasheets from manufacturers' websites).

## 13. Out of Scope (v1)
- OCR for scanned PDFs
- Table/image understanding
- Multiple users sharing documents
- Rerankers (possible v2 improvement)
