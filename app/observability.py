from __future__ import annotations

import time
from collections import Counter, defaultdict

from .config import settings
from .repository import repository
from .supabase_store import supabase_store
from .text import normalize_ar

_CLOUD_CACHE: dict[str, object] = {"at": 0.0, "value": None}
_COVERAGE_CACHE: dict[str, object] = {"at": 0.0, "value": None}

CORE_LAWS = [
    ("قانون الأحوال الشخصية رقم 15 لسنة 2019", "personal_status"),
    ("قانون الشركات رقم 22 لسنة 1997 وتعديلاته", "commercial"),
    ("قانون السير رقم 49 لسنة 2008 وتعديلاته", "traffic"),
    ("نظام النقاط المرورية لسنة 2024", "traffic"),
    ("قانون الجرائم الإلكترونية رقم 17 لسنة 2023", "cyber"),
    ("قانون العمل رقم 8 لسنة 1996 وتعديلاته", "labor"),
    ("قانون أصول المحاكمات الشرعية وتعديلاته", "personal_status"),
    ("قانون العقوبات رقم 16 لسنة 1960 وتعديلاته", "criminal"),
    ("القانون المدني رقم 43 لسنة 1976 وتعديلاته", "civil"),
    ("قانون أصول المحاكمات الجزائية رقم 9 لسنة 1961 وتعديلاته", "procedure"),
    ("قانون أصول المحاكمات المدنية رقم 24 لسنة 1988 وتعديلاته", "procedure"),
]


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
    for cache in (_CLOUD_CACHE, _COVERAGE_CACHE):
        cache["at"] = 0.0
        cache["value"] = None


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
        document_rows = _paged_rows("legal_documents", "id,source_kind")
    except Exception:
        return None

    domains = Counter((row.get("domain") or "general") for row in chunk_rows)
    local = repository.stats()
    value = {
        "store": "supabase",
        "chunks": len(chunk_rows),
        "documents": len(document_rows),
        "registered_official_sources": local.get("registered_official_sources", 0),
        "canonical_documents": sum(
            1 for row in document_rows if str(row.get("source_kind") or "").startswith("canonical")
        ),
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


def _title_matches(candidate: str, target: str) -> bool:
    candidate_n = normalize_ar(candidate or "")
    target_n = normalize_ar(target or "")
    if not candidate_n or not target_n:
        return False
    return candidate_n == target_n or target_n in candidate_n or candidate_n in target_n


def cloud_coverage(ttl_seconds: float = 60.0) -> list[dict] | None:
    """Compute core-law coverage from the same Supabase tables searched by live chat."""
    if not supabase_store.configured:
        return None

    now = time.monotonic()
    cached = _COVERAGE_CACHE.get("value")
    cached_at = float(_COVERAGE_CACHE.get("at") or 0.0)
    if cached is not None and now - cached_at < ttl_seconds:
        return [dict(row) for row in cached]

    try:
        documents = _paged_rows(
            "legal_documents",
            "id,title_ar,domain,source_url,source_kind",
        )
        chunks = _paged_rows("legal_chunks", "document_id,article")
    except Exception:
        return None

    chunks_by_document: dict[str, list[dict]] = defaultdict(list)
    for chunk in chunks:
        document_id = str(chunk.get("document_id") or "")
        if document_id:
            chunks_by_document[document_id].append(chunk)

    result: list[dict] = []
    for title, domain in CORE_LAWS:
        matches = [
            doc
            for doc in documents
            if doc.get("domain") == domain and _title_matches(str(doc.get("title_ar") or ""), title)
        ]
        chunk_count = 0
        articles: set[str] = set()
        urls: list[str] = []
        kinds: set[str] = set()
        for doc in matches:
            document_id = str(doc.get("id") or "")
            rows = chunks_by_document.get(document_id, [])
            chunk_count += len(rows)
            articles.update(str(row["article"]) for row in rows if row.get("article"))
            if doc.get("source_url"):
                urls.append(str(doc["source_url"]))
            if doc.get("source_kind"):
                kinds.add(str(doc["source_kind"]))

        if any(kind.startswith("canonical") for kind in kinds):
            status = "canonical"
        elif kinds and all(kind == "reference" for kind in kinds):
            status = "reference_only"
        elif chunk_count:
            status = "partial"
        else:
            status = "reference_only"

        result.append(
            {
                "title": title,
                "domain": domain,
                "status": status,
                "chunks": chunk_count,
                "distinct_articles": len(articles),
                "source_urls": list(dict.fromkeys(urls))[:3],
                "store": "supabase",
            }
        )

    _COVERAGE_CACHE["at"] = now
    _COVERAGE_CACHE["value"] = result
    return [dict(row) for row in result]


def effective_coverage() -> list[dict]:
    cloud = cloud_coverage()
    if cloud is not None:
        return cloud
    return repository.coverage()


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
