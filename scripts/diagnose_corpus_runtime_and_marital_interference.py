"""One-shot CI diagnostic for two linked production reports:

1. `/api/health` showing `corpus.store=sqlite_fallback` with `supabase.reachable=true`.
2. Production answering "المادة الرسمية المسترجعة غير كافية..." to
   "ما حكم افساد علاقة زوجية ؟" and its paraphrases.

Requires real SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY (this script is meant to run in CI, which
has them as repo secrets; the sandbox this was developed in does not). Read-only against
Supabase -- no writes. Optionally hits QANONI_BASE_URL's live /api/health if set.
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import observability
from app.chat_v4 import handle_chat
from app.diagnostics import RequestTrace
from app.models import ChatRequest
from app.supabase_store import supabase_store

QUERIES = [
    "ما حكم افساد علاقة زوجية ؟",
    "افسد علاقتها بزوجها",
    "شخص يحاول يخرب بين زوج وزوجته",
    "حرضها تترك زوجها",
    "تدخل بين زوجين حتى تنفصل عنه",
    "شو عقوبة اللي بخرب علاقة زوجية",
]


def part_one_runtime_store():
    print("=" * 90)
    print("PART ONE: runtime-store / corpus.store diagnostic")
    print("=" * 90)
    print("supabase_store.configured:", supabase_store.configured)
    print("supabase_store.health():", supabase_store.health())

    observability.clear_observability_cache()
    t0 = time.monotonic()
    try:
        chunk_rows = observability._paged_rows("legal_chunks", "id,domain")
        doc_rows = observability._paged_rows("legal_documents", "id,source_kind")
        print(f"_paged_rows OK in {time.monotonic()-t0:.2f}s: chunks={len(chunk_rows)} documents={len(doc_rows)}")
    except Exception:
        print(f"_paged_rows RAISED after {time.monotonic()-t0:.2f}s:")
        traceback.print_exc()

    observability.clear_observability_cache()
    stats = observability.effective_corpus_stats()
    print("effective_corpus_stats():", {k: v for k, v in stats.items() if k != "domains"})

    base_url = os.environ.get("QANONI_BASE_URL")
    if base_url:
        import requests
        try:
            r = requests.get(f"{base_url}/api/health", timeout=30)
            body = r.json()
            print("LIVE /api/health supabase:", body.get("supabase"))
            print("LIVE /api/health corpus (no domains):", {k: v for k, v in (body.get("corpus") or {}).items() if k != "domains"})
            print("LIVE /api/health runtime_store:", body.get("runtime_store"))
        except Exception as exc:
            print("LIVE /api/health request FAILED:", f"{type(exc).__name__}: {exc}")


def part_two_marital_interference():
    print()
    print("=" * 90)
    print("PART TWO: first-failure trace, real Supabase-backed retrieval")
    print("=" * 90)
    for q in QUERIES:
        trace = RequestTrace()
        resp = handle_chat(ChatRequest(message=q, language="ar"), trace=trace)
        print("-" * 90)
        print("QUERY:", q)
        print("primary_domain:", trace.primary_domain, "domains:", trace.detected_domains)
        print("retrieval_queries:", trace.retrieval_queries)
        print("raw_candidates:", [(c.stage, c.article, c.domain, c.title[:40]) for c in trace.raw_candidates][:10])
        print("guarded_candidates:", [(c.article, c.domain, c.title[:40]) for c in trace.guarded_candidates])
        print("rejected_candidates:", [(c.article, c.domain, c.rejected_reason) for c in trace.rejected_candidates][:10])
        print("final_mode:", trace.final_mode, "fallback_reason:", trace.fallback_reason)
        print("ANSWER:", resp.answer[:280])


if __name__ == "__main__":
    part_one_runtime_store()
    part_two_marital_interference()
