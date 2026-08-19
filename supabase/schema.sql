-- Qanoni | قانوني Pilot V3.6 FINAL
-- Run this file once in Supabase SQL Editor.
-- All tables are private by default: the backend uses the service-role key server-side only.

create extension if not exists vector with schema extensions;

create table if not exists public.legal_documents (
  id text primary key,
  title_ar text not null,
  authority text not null,
  domain text not null,
  source_url text not null,
  law_number text,
  year text,
  source_kind text not null,
  verified_at timestamptz,
  created_at timestamptz default now()
);

create table if not exists public.legal_chunks (
  id text primary key,
  document_id text not null references public.legal_documents(id) on delete cascade,
  title text not null,
  authority text not null,
  domain text not null,
  source_url text not null,
  law_number text,
  year text,
  article text,
  body text not null,
  verified_at timestamptz,
  source_kind text not null,
  embedding extensions.vector(1536),
  fts tsvector generated always as (
    to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(body,''))
  ) stored
);

create index if not exists legal_chunks_domain_idx on public.legal_chunks(domain);
create index if not exists legal_chunks_fts_idx on public.legal_chunks using gin(fts);
create index if not exists legal_chunks_embedding_idx
  on public.legal_chunks using hnsw (embedding vector_cosine_ops);

-- Conversation continuity / QA telemetry.
create table if not exists public.qanoni_conversations (
  id text primary key,
  language text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.qanoni_messages (
  id text primary key,
  conversation_id text not null references public.qanoni_conversations(id) on delete cascade,
  role text not null check (role in ('user','assistant','system')),
  content text not null,
  primary_domain text,
  intent text,
  created_at timestamptz not null default now()
);
create index if not exists qanoni_messages_conversation_idx
  on public.qanoni_messages(conversation_id, created_at desc);

create table if not exists public.qanoni_answer_evaluations (
  id text primary key,
  conversation_id text references public.qanoni_conversations(id) on delete set null,
  message text not null,
  intent text,
  primary_domain text,
  passed boolean not null,
  score double precision not null,
  reasons jsonb not null default '[]'::jsonb,
  mode text,
  created_at timestamptz not null default now()
);

create table if not exists public.qanoni_feedback (
  id text primary key,
  conversation_id text references public.qanoni_conversations(id) on delete set null,
  rating text not null check (rating in ('helpful','not_helpful')),
  note text,
  created_at timestamptz not null default now()
);

alter table public.legal_documents enable row level security;
alter table public.legal_chunks enable row level security;
alter table public.qanoni_conversations enable row level security;
alter table public.qanoni_messages enable row level security;
alter table public.qanoni_answer_evaluations enable row level security;
alter table public.qanoni_feedback enable row level security;

-- No public RLS policies are created. Never put the service-role key in frontend code.

create or replace function public.hybrid_search_legal_chunks(
  query_text text,
  query_embedding extensions.vector(1536),
  filter_domains text[] default array['general']::text[],
  match_count int default 8
)
returns table (
  id text,
  title text,
  authority text,
  domain text,
  source_url text,
  law_number text,
  year text,
  article text,
  excerpt text,
  verified_at text,
  source_kind text,
  score double precision
)
language sql
stable
as $$
with semantic as (
  select lc.id,
         row_number() over (order by lc.embedding <=> query_embedding) as rank
  from public.legal_chunks lc
  where lc.embedding is not null
    and (
      filter_domains is null
      or array_length(filter_domains,1) is null
      or 'general'=any(filter_domains)
      or lc.domain=any(filter_domains)
    )
  order by lc.embedding <=> query_embedding
  limit greatest(match_count*8, 40)
),
keyword as (
  select lc.id,
         row_number() over (
           order by ts_rank_cd(lc.fts, websearch_to_tsquery('simple', query_text)) desc
         ) as rank
  from public.legal_chunks lc
  where lc.fts @@ websearch_to_tsquery('simple', query_text)
    and (
      filter_domains is null
      or array_length(filter_domains,1) is null
      or 'general'=any(filter_domains)
      or lc.domain=any(filter_domains)
    )
  order by ts_rank_cd(lc.fts, websearch_to_tsquery('simple', query_text)) desc
  limit greatest(match_count*8, 40)
),
fused as (
  select coalesce(s.id,k.id) as id,
         coalesce(1.0/(60+s.rank),0) + coalesce(1.0/(60+k.rank),0) as score
  from semantic s full outer join keyword k using(id)
)
select lc.id,lc.title,lc.authority,lc.domain,lc.source_url,lc.law_number,lc.year,lc.article,
       left(lc.body,1450) as excerpt,
       lc.verified_at::text,lc.source_kind,f.score
from fused f
join public.legal_chunks lc on lc.id=f.id
order by f.score desc
limit match_count;
$$;
