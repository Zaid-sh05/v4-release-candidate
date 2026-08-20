from __future__ import annotations

# Compatibility bridge while V3.6 chat orchestration remains the stable retrieval/answer shell.
# The function object in app.chat resolves its module globals at call time, so replacing these
# routing/retrieval hooks makes the live API use V4 cognition safeguards without duplicating
# the whole chat stack.
from . import chat as _legacy_chat
from .routing_guard import apply_case_route, route_query
from .source_quality import looks_garbled_legal_text
from .text import normalize_ar


_ORIGINAL_RETRIEVAL_FALLBACK = _legacy_chat.retrieval_fallback


def _allowed_domains(domains):
    allowed = {d for d in (domains or []) if d not in {"general", "conversation"}}
    return allowed or None


def _item_excerpt(item) -> str:
    return getattr(item, "excerpt", "") or ""


def _row_excerpt(row: dict) -> str:
    return (row.get("excerpt") or row.get("body") or "") if isinstance(row, dict) else ""


def _filter_source_items(items, domains):
    """Reject unrelated-domain and visibly corrupted legal evidence before answering."""
    allowed = _allowed_domains(domains)
    out = []
    for item in items or []:
        if allowed is not None and getattr(item, "domain", None) not in allowed:
            continue
        if looks_garbled_legal_text(_item_excerpt(item)):
            continue
        out.append(item)
    return out


def _filter_source_rows(rows, domains):
    allowed = _allowed_domains(domains)
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if allowed is not None and row.get("domain") not in allowed:
            continue
        if looks_garbled_legal_text(_row_excerpt(row)):
            continue
        out.append(row)
    return out


def _theft_fact_pattern(message: str) -> bool:
    n = normalize_ar(message or "")
    theft = any(x in n for x in ("سرقه", "سرق", "استولى"))
    taking = any(x in n for x in ("اخذ", "استولى"))
    entry = any(x in n for x in ("كسر", "قفل", "دخل المنزل", "دخل البيت", "الدخول الى منزل", "اقتحم", "تسلل"))
    return theft or (taking and entry)


def _v4_retrieval_fallback(message, route, sources):
    """Give a safe case-oriented summary instead of dumping a raw law/PDF excerpt."""
    if route.language == "ar" and route.primary_domain == "criminal" and route.intent == "legal_question" and _theft_fact_pattern(message):
        chosen = None
        for i, source in enumerate(sources or [], 1):
            if getattr(source, "domain", None) != "criminal":
                continue
            if looks_garbled_legal_text(_item_excerpt(source)):
                continue
            title_n = normalize_ar(getattr(source, "title", "") or "")
            excerpt_n = normalize_ar(_item_excerpt(source))
            if "قانون العقوبات" in title_n or "سرق" in title_n or "سرق" in excerpt_n:
                chosen = (i, source)
                break
        if chosen:
            i, source = chosen
            article = f"، المادة {source.article}" if getattr(source, "article", None) else ""
            return (
                "التكييف المبدئي للوقائع: المسار الأساسي هنا جزائي وليس مرورياً. "
                "الوصف يتضمن أخذ مال أو منقولات من منزل الغير، ومع وجود كسر للقفل أو دخول إلى المنزل "
                "يجب فحص النص الخاص بهذه الصورة قبل تحديد المادة والعقوبة الدقيقة. "
                f"[S{i}]\n\n"
                f"الأساس القانوني المسترجع: {source.title}{article}. [S{i}]\n\n"
                "لن أطبّق عقوبة السرقة العامة تلقائياً على واقعة تتضمن كسراً ودخول منزل ما لم يكن النص الرسمي "
                "المسترجع واضحاً بشأن هذه الظروف؛ لذلك الأفضل هنا عرض التكييف الصحيح أولاً وعدم اختراع مادة أو عقوبة."
            )
    return _ORIGINAL_RETRIEVAL_FALLBACK(message, route, sources)


class _GuardedRepository:
    def __init__(self, inner):
        self._inner = inner

    def search(self, query, domains, limit=8):
        return _filter_source_items(self._inner.search(query, domains, limit), domains)

    def adaptive_search(self, message, domains, intent, limit=12, expansions=None):
        return _filter_source_items(
            self._inner.adaptive_search(message, domains, intent, limit, expansions or []),
            domains,
        )

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _GuardedSupabaseStore:
    def __init__(self, inner):
        self._inner = inner

    @property
    def configured(self):
        return self._inner.configured

    def hybrid_search(self, query, embedding, domains, limit=8):
        rows = self._inner.hybrid_search(query, embedding, domains, limit)
        return _filter_source_rows(rows, domains)

    def keyword_search(self, query, domains, limit=8):
        rows = self._inner.keyword_search(query, domains, limit)
        return _filter_source_rows(rows, domains)

    def __getattr__(self, name):
        return getattr(self._inner, name)


_legacy_chat.analyze_query = route_query
_legacy_chat._apply_cognition_to_route = apply_case_route
_legacy_chat.retrieval_fallback = _v4_retrieval_fallback
_legacy_chat.repository = _GuardedRepository(_legacy_chat.repository)
_legacy_chat.supabase_store = _GuardedSupabaseStore(_legacy_chat.supabase_store)

handle_chat = _legacy_chat.handle_chat

__all__ = [
    "handle_chat",
    "_filter_source_items",
    "_filter_source_rows",
    "_v4_retrieval_fallback",
]
