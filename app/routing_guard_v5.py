from __future__ import annotations

from .models import RouteResult
from .routing_guard import apply_case_route, route_query as base_route_query
from .text import normalize_ar


_AR_CASE_ANALYSIS_PHRASES = (
    "حلل الحالة",
    "حلل الحاله",
    "حلل الملف",
    "حلل الوقائع",
    "حلل المسائل",
    "حلل عناصر النزاع",
    "حلل النزاع",
    "حلل الوضع قانونيا",
    "حلل الحالة قانونيا",
    "تحليل الحالة",
    "تحليل الملف",
    "تحليل الوقائع",
)

_EN_CASE_ANALYSIS_PHRASES = (
    "analyze the case",
    "analyse the case",
    "analyze the issues",
    "analyse the issues",
    "analyze the facts",
    "analyse the facts",
    "analyze the situation",
    "analyse the situation",
    "case analysis",
    "issue spotting",
)


def _explicit_case_analysis_request(text: str) -> bool:
    raw = (text or "").strip().lower()
    ar = normalize_ar(text or "")
    return any(phrase in ar for phrase in _AR_CASE_ANALYSIS_PHRASES) or any(
        phrase in raw for phrase in _EN_CASE_ANALYSIS_PHRASES
    )


def route_query(text: str, requested_language: str = "auto", force_domain: str | None = None) -> RouteResult:
    """V5 intent guard: explicit lawyer-analysis requests outrank incidental rights keywords.

    A narrative containing words such as salary, compensation or rights may otherwise be classified
    as a direct ``rights`` question. When the user explicitly asks to analyze the case/issues/facts,
    the correct product behavior is structured issue-spotting first. Direct questions such as
    ``شو حقوقي؟`` remain untouched because they do not contain an explicit analysis request.
    """
    route = base_route_query(text, requested_language, force_domain)
    if not force_domain and route.intent != "smalltalk" and _explicit_case_analysis_request(text):
        route.intent = "legal_question"
    return route


__all__ = ["route_query", "apply_case_route"]
