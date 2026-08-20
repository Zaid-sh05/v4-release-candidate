from __future__ import annotations

import time
from collections import Counter

from .config import settings
from .repository import repository
from .supabase_store import supabase_store

_CLOUD_CACHE: dict[str, object] = {"at": 0.0, "value": None}


def _paged_rows(table: str, columns: str, page_size: int = 1000) -> list[dict]:
    """Read a bounded Supabase table in pages so PostgREST row caps do not hide data."""
    if not supabase_store.client:
        return []
    rows: list[dict] = []
    start = 0
    while True:
        batch = (
            supabase_store.client.table(table)
            .select(columns)
            .range(start, start + page_size - 1)
            .execute()
            .data
            or []
        )
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def clear_observability_cache() -> None:
    _CLOUD_CACHE["at"] = 0.0
    _CLOUD_CACHE["value"] = None


def cloud_corpus_stats(ttl_seconds: float = 60.0) -> dict | None:
    """Return the corpus that cloud retrieval actually searches, not the bundled fallback DB."""
    if not supabase_store.configured:
        return None

    now = time.monotonic()
    cached = _CLOUD_CACHE.get("value")
    cached_at = float(_CLOUD_CACHE.get("at") or 0.0)
    if cached is not None and now - cached_at < ttl_seconds:
        return dict(cached)

    try:
        chunk_rows = _paged_rows("legal_chunks", "id,domain")
        document_rows = _paged_rows("legal_documents", "id")
    except Exception:
        return None

    domains = Counter((row.get("domain") or "general") for row in chunk_rows)
    local = repository.stats()
    value = {
        "store": "supabase",
        "chunks": len(chunk_rows),
        "documents": len(document_rows),
        "registered_official_sources": local.get("registered_official_sources", 0),
        "canonical_documents": local.get("canonical_documents", 0),
        "domains": dict(sorted(domains.items(), key=lambda item: (-item[1], item[0]))),
        "local_fallback": {
            "chunks": local.get("chunks", 0),
            "documents": local.get("documents", 0),
        },
    }
    _CLOUD_CACHE["at"] = now
    _CLOUD_CACHE["value"] = value
    return dict(value)


def effective_corpus_stats() -> dict:
    cloud = cloud_corpus_stats()
    if cloud is not None:
        return cloud
    local = dict(repository.stats())
    local["store"] = "sqlite" if not supabase_store.configured else "sqlite_fallback"
    return local


def ai_runtime_status() -> dict:
    provider = (settings.cognition_llm_provider or "auto").strip().lower()
    cognition_enabled = bool(settings.cognition_llm_enabled) and provider != "off"
    groq_ready = cognition_enabled and bool(settings.groq_api_key) and provider in {"auto", "groq"}

    cognition = {
        "enabled": cognition_enabled,
        "provider": "groq" if groq_ready else "deterministic",
        "configured": groq_ready,
        "model": settings.groq_cognition_model if groq_ready else None,
        "fallback": "deterministic",
    }
    answering = {
        "provider": "openai" if settings.openai_api_key else "extractive",
        "configured": bool(settings.openai_api_key),
        "model": settings.openai_model if settings.openai_api_key else None,
    }
    return {"answer_generation": answering, "cognition": cognition}
