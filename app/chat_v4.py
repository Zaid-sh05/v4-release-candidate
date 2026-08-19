from __future__ import annotations

# Compatibility bridge while V3.6 chat orchestration remains the stable retrieval/answer shell.
# The function object in app.chat resolves its module globals at call time, so replacing these
# routing/retrieval hooks makes the live API use V4 cognition safeguards without duplicating
# the whole chat stack.
from . import chat as _legacy_chat
from .routing_guard import apply_case_route, route_query


def _allowed_domains(domains):
    allowed = {d for d in (domains or []) if d not in {"general", "conversation"}}
    return allowed or None


def _filter_source_items(items, domains):
    """Never let a legal answer consume evidence from an unrelated routed domain."""
    allowed = _allowed_domains(domains)
    if allowed is None:
        return list(items or [])
    return [item for item in (items or []) if getattr(item, "domain", None) in allowed]


def _filter_source_rows(rows, domains):
    allowed = _allowed_domains(domains)
    if allowed is None:
        return list(rows or [])
    return [row for row in (rows or []) if isinstance(row, dict) and row.get("domain") in allowed]


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
_legacy_chat.repository = _GuardedRepository(_legacy_chat.repository)
_legacy_chat.supabase_store = _GuardedSupabaseStore(_legacy_chat.supabase_store)

handle_chat = _legacy_chat.handle_chat

__all__ = [
    "handle_chat",
    "_filter_source_items",
    "_filter_source_rows",
]
