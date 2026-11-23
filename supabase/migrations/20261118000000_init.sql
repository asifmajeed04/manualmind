-- Milestone 1: initial schema for the multilingual RAG assistant.

create extension if not exists vector;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
create table documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  name text not null,
  storage_path text not null,
  language text check (language in ('de', 'en')),
  page_count int,
  status text not null default 'processing'
    check (status in ('processing', 'ready', 'failed')),
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
  -- 'simple' config: no stemming, so part numbers / error codes stay intact.
  tsv tsvector generated always as (to_tsvector('simple', content)) stored
);

create table chat_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  citations jsonb,
  created_at timestamptz default now()
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
create index on chunks using hnsw (embedding vector_cosine_ops);
create index on chunks using gin (tsv);
create index on chunks (document_id);
create index on documents (user_id);
create index on chat_messages (user_id, created_at);

-- ---------------------------------------------------------------------------
-- Row Level Security: users only see their own rows.
-- (Backend + AI service use the service role key, which bypasses RLS.)
-- ---------------------------------------------------------------------------
alter table documents enable row level security;
alter table chunks enable row level security;
alter table chat_messages enable row level security;

create policy "own documents" on documents
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "own chunks" on chunks
  for all using (
    exists (select 1 from documents d where d.id = chunks.document_id and d.user_id = auth.uid())
  ) with check (
    exists (select 1 from documents d where d.id = chunks.document_id and d.user_id = auth.uid())
  );

create policy "own messages" on chat_messages
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- Retrieval RPCs (called by FastAPI with the service role key).
-- Only searches 'ready' documents of the given user; optional document filter.
-- ---------------------------------------------------------------------------
create or replace function match_chunks_vector(
  query_embedding vector(1536),
  p_user_id uuid,
  k int default 20,
  p_document_ids uuid[] default null
)
returns table (
  id uuid,
  document_id uuid,
  document_name text,
  page_number int,
  chunk_index int,
  content text,
  similarity float
)
language sql stable
as $$
  select c.id, c.document_id, d.name, c.page_number, c.chunk_index, c.content,
         1 - (c.embedding <=> query_embedding) as similarity
  from chunks c
  join documents d on d.id = c.document_id
  where d.user_id = p_user_id
    and d.status = 'ready'
    and c.embedding is not null
    and (p_document_ids is null or c.document_id = any(p_document_ids))
  order by c.embedding <=> query_embedding
  limit k;
$$;

create or replace function match_chunks_keyword(
  query_text text,
  p_user_id uuid,
  k int default 20,
  p_document_ids uuid[] default null
)
returns table (
  id uuid,
  document_id uuid,
  document_name text,
  page_number int,
  chunk_index int,
  content text,
  rank float
)
language sql stable
as $$
  select c.id, c.document_id, d.name, c.page_number, c.chunk_index, c.content,
         ts_rank(c.tsv, q)::float as rank
  from chunks c
  join documents d on d.id = c.document_id,
       websearch_to_tsquery('simple', query_text) q
  where d.user_id = p_user_id
    and d.status = 'ready'
    and c.tsv @@ q
    and (p_document_ids is null or c.document_id = any(p_document_ids))
  order by rank desc
  limit k;
$$;

-- Not callable by browser clients; only the service role uses these.
revoke execute on function match_chunks_vector(vector, uuid, int, uuid[]) from public, anon, authenticated;
revoke execute on function match_chunks_keyword(text, uuid, int, uuid[]) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Private storage bucket for uploaded PDFs (20 MB limit, PDFs only).
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('documents', 'documents', false, 20971520, array['application/pdf'])
on conflict (id) do nothing;
