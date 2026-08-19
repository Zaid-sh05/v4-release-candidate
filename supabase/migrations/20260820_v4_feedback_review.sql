-- Qanoni V4 grounded feedback self-correction migration
-- Safe to run after 20260820_v4_cloud_updater.sql on an existing project.

create table if not exists public.qanoni_feedback_reviews (
  id text primary key,
  feedback_id text references public.qanoni_feedback(id) on delete set null,
  conversation_id text references public.qanoni_conversations(id) on delete set null,
  question_fingerprint text not null,
  question text not null,
  previous_answer text,
  feedback_note text,
  primary_domain text not null,
  status text not null check (status in ('auto_corrected','needs_review')),
  old_score double precision,
  proposed_answer text,
  new_score double precision,
  source_refs jsonb not null default '[]'::jsonb,
  retrieval_hints jsonb not null default '[]'::jsonb,
  review_reason text,
  created_at timestamptz not null default now()
);

create index if not exists qanoni_feedback_reviews_question_idx
  on public.qanoni_feedback_reviews(question_fingerprint, primary_domain, created_at desc);
create index if not exists qanoni_feedback_reviews_status_idx
  on public.qanoni_feedback_reviews(status, created_at desc);

alter table public.qanoni_feedback_reviews enable row level security;
grant all on table public.qanoni_feedback_reviews to service_role;

-- Intentionally no anon/authenticated policy. Reviews can contain sensitive case context
-- and are available only through the server-side service role / protected admin endpoint.
