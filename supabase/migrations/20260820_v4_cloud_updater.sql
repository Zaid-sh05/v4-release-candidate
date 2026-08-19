-- Qanoni V4 cloud updater migration
-- Safe to run on an existing V3.6/V4 Supabase project.

create table if not exists public.qanoni_legal_sync_fingerprints (
  source_url text primary key,
  source_id text not null,
  title text not null,
  domain text not null,
  fingerprint text not null,
  promoted_at timestamptz not null
);
create index if not exists qanoni_legal_sync_fingerprints_source_idx
  on public.qanoni_legal_sync_fingerprints(source_id, promoted_at desc);

create table if not exists public.qanoni_legal_update_events (
  id text primary key,
  source_id text not null,
  source_url text not null,
  title text,
  domain text,
  action text not null check (action in ('new','changed','unchanged','rejected')),
  fingerprint text,
  reason text,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists qanoni_legal_update_events_created_idx
  on public.qanoni_legal_update_events(created_at desc);
create index if not exists qanoni_legal_update_events_source_idx
  on public.qanoni_legal_update_events(source_id, created_at desc);

alter table public.qanoni_legal_sync_fingerprints enable row level security;
alter table public.qanoni_legal_update_events enable row level security;
grant all on table public.legal_documents to service_role;
grant all on table public.legal_chunks to service_role;
grant all on table public.qanoni_legal_sync_fingerprints to service_role;
grant all on table public.qanoni_legal_update_events to service_role;

create or replace function public.keyword_search_legal_chunks(
  query_text text,
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
with query_value as (
  select websearch_to_tsquery('simple', coalesce(query_text,'')) as q
), ranked as (
  select lc.id,
         ts_rank_cd(lc.fts, qv.q)::double precision as score
  from public.legal_chunks lc
  cross join query_value qv
  where qv.q <> ''::tsquery
    and lc.fts @@ qv.q
    and (
      filter_domains is null
      or array_length(filter_domains,1) is null
      or 'general'=any(filter_domains)
      or lc.domain=any(filter_domains)
    )
  order by score desc, lc.verified_at desc nulls last
  limit greatest(least(match_count,30),1)
)
select lc.id,lc.title,lc.authority,lc.domain,lc.source_url,lc.law_number,lc.year,lc.article,
       left(lc.body,1450) as excerpt,
       lc.verified_at::text,lc.source_kind,r.score
from ranked r
join public.legal_chunks lc on lc.id=r.id
order by r.score desc, lc.verified_at desc nulls last;
$$;

grant execute on function public.keyword_search_legal_chunks(text,text[],int) to service_role;
