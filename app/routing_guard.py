from __future__ import annotations

import re

from .models import RouteResult
from .router import DOMAIN_LABELS, analyze_query
from .text import normalize_ar


_SMALLTALK_ONLY = {
    "مرحبا", "اهلا", "هلا", "هلو", "هلوو", "هاي", "السلام عليكم",
    "صباح الخير", "مساء الخير", "hi", "hello", "hey",
}

_TOKEN_EDGE_RE = re.compile(r"^[\s\.,،؛:!?؟()\[\]{}\"'«»]+|[\s\.,،؛:!?؟()\[\]{}\"'«»]+$")


def _canonical_token(token: str) -> str:
    """Normalize one token without creating Arabic substring false positives."""
    token = _TOKEN_EDGE_RE.sub("", normalize_ar(token or "")).strip()
    if not token:
        return ""

    # Strip only safe Arabic article/clitic combinations. Never strip a bare و/ب/ف
    # here because words such as واتساب would otherwise be damaged. Bare conjunctions
    # are handled as alternate matching variants instead of mutating the source token.
    for prefix in ("وال", "فال", "بال", "كال", "لل", "ال"):
        if token.startswith(prefix) and len(token) > len(prefix) + 2:
            token = token[len(prefix):]
            break
    return token


def _token_variants(token: str) -> set[str]:
    """Return conservative spoken-Arabic clitic variants for matching only.

    Jordanian users frequently attach the conjunction waw to verbs (وأخذ، وانصاب)
    and contract على + ال into عالـ (عالمستشفى). Keep the original token and expose
    a stripped alternative without globally rewriting words that genuinely start with و.
    """
    variants = {token}
    if token.startswith("و") and len(token) > 4:
        variants.add(token[1:])
    if token.startswith("عال") and len(token) > 5:
        variants.add(token[3:])
    if token.startswith("وعال") and len(token) > 6:
        variants.add(token[4:])
    return {v for v in variants if v}


def _tokens(text: str) -> list[str]:
    return [tok for raw in normalize_ar(text).split() if (tok := _canonical_token(raw))]


def _phrase_tokens(text: str) -> list[str]:
    return _tokens(text)


def _has(text: str, *phrases: str) -> bool:
    """Token/phrase-aware Arabic matching; never raw substring matching."""
    words = _tokens(text)
    variants = [_token_variants(word) for word in words]
    normalized = " ".join(words)
    for phrase in phrases:
        pwords = _phrase_tokens(phrase)
        if not pwords:
            continue
        if len(pwords) == 1:
            if any(pwords[0] in options for options in variants):
                return True
        else:
            width = len(pwords)
            if any(
                all(pwords[offset] in variants[i + offset] for offset in range(width))
                for i in range(len(words) - width + 1)
            ):
                return True
        p = " ".join(pwords)
        # English/mixed phrases can safely use word-bounded normalized text here.
        if all(ord(ch) < 128 for ch in p) and f" {p} " in f" {normalized} ":
            return True
    return False


def _set_primary(route: RouteResult, primary: str, extras: list[str] | None = None, confidence: float = 0.9) -> RouteResult:
    domains = [primary]
    for domain in extras or []:
        if domain in DOMAIN_LABELS and domain not in domains:
            domains.append(domain)
    route.primary_domain = primary
    route.domains = domains[:4]
    route.confidence = max(route.confidence, confidence)
    return route


def route_query(text: str, requested_language: str = "auto", force_domain: str | None = None) -> RouteResult:
    """Run the legacy lexical router, then apply conservative V4 semantic guards."""
    route = analyze_query(text, requested_language, force_domain)
    if force_domain:
        return route

    n = normalize_ar(text)
    compact = " ".join(n.split())
    if compact in {normalize_ar(x) for x in _SMALLTALK_ONLY}:
        return RouteResult(
            language=route.language,
            intent="smalltalk",
            primary_domain="conversation",
            domains=["conversation"],
            confidence=1.0,
            matched_terms=[],
            article_numbers=route.article_numbers,
            law_numbers=route.law_numbers,
            years=route.years,
            normalized_text=route.normalized_text,
        )

    appeal = _has(text, "استئناف", "استأنف", "استانف", "تمييز", "طعن", "appeal", "cassation")
    complaint = _has(text, "شكوى", "المدعي العام", "مدعي عام", "نيابة عامة", "ادعاء عام", "complaint", "prosecutor")
    personal = _has(text, "طلاق", "خلع", "نفقة", "حضانة", "زواج", "مطلقة", "طليقي", "محكمة شرعية", "divorce", "custody", "alimony")
    labor = _has(text, "فصلني", "طردني", "الفصل", "سبب الفصل", "صاحب العمل", "عقد عمل", "راتب", "اجر", "إنذار مكتوب", "انذار مكتوب", "ضعف الاداء", "employer", "fired", "dismissed")
    traffic = _has(text, "اشارة حمراء", "إشارة حمراء", "حادث", "صدمت", "دهست", "تصادم", "سيارة", "مركبة", "سائق", "مسرع", "red light", "road accident", "vehicle")
    cyber = _has(
        text,
        "واتساب", "انستغرام", "فيسبوك", "ابتزاز", "ابتزني", "ببتزني", "يبتزني",
        "اختراق", "تهكير", "whatsapp", "online blackmail", "cybercrime",
    )
    threat = _has(
        text,
        "هدد", "هددني", "يهددني", "بهددني", "بتهددني", "تهديد",
        "ابتزاز", "ابتزني", "ببتزني", "يبتزني", "مبتزني",
        "threat", "blackmail", "extortion",
    )
    violence = _has(text, "قتل", "قتله", "اعتداء", "ضرب", "ضربني", "طعن", "هاجمني", "سلاح", "سرقة", "سرقت", "سرق", "murder", "assault", "theft")
    taking = _has(text, "أخذ", "اخذ", "أخذت", "اخذت", "سرق", "سرقت", "استولى", "took", "stole")
    forced_entry = _has(text, "كسر", "خلع", "دخل البيت", "دخل المنزل", "تسلل", "اقتحم", "forced entry")
    self_defense = _has(text, "دفاع عن نفسي", "دفاعا عن نفسي", "هاجمني", "self defense", "self-defense")
    injury = _has(text, "اصابة", "إصابة", "انصاب", "اصيب", "أصيب", "جرح", "المستشفى", "injury", "injured", "hospital")
    death = _has(text, "وفاة", "توفي", "توفى", "مات", "قتل", "death", "died", "killed")

    if appeal:
        extras: list[str] = []
        if personal:
            extras.append("personal_status")
        if violence or taking:
            extras.append("criminal")
        _set_primary(route, "procedure", extras, 0.94)
    elif complaint:
        _set_primary(route, "procedure", ["criminal"], 0.94)
    elif traffic:
        extras = []
        if injury or death:
            extras.append("civil")
        if death:
            extras.append("criminal")
        _set_primary(route, "traffic", extras, 0.91)
    elif cyber:
        _set_primary(route, "cyber", ["criminal"] if threat else [], 0.91)
    elif labor:
        _set_primary(route, "labor", [], 0.92)
    elif self_defense or violence or (taking and forced_entry):
        _set_primary(route, "criminal", [], 0.9)
    elif personal:
        _set_primary(route, "personal_status", [], 0.92)

    if personal and _has(text, "اجراءات", "إجراءات", "شو الخطوات", "procedure", "how do i") and not appeal:
        route.intent = "procedure"

    return route


def apply_case_route(route: RouteResult, case, force_domain: str | None = None) -> RouteResult:
    """Fuse grounded cognition with lexical routing without letting either layer dominate blindly."""
    if force_domain:
        return route

    case_domains = [d for d in case.domains if d in DOMAIN_LABELS and d != "general"]
    strong_domains: list[str] = []
    for hypothesis in case.hypotheses:
        if hypothesis.confidence >= 0.75 and hypothesis.domain in DOMAIN_LABELS and hypothesis.domain not in strong_domains:
            strong_domains.append(hypothesis.domain)

    existing = [d for d in route.domains if d not in {"general", "conversation"}]
    if route.primary_domain in {"general", "conversation"} and case_domains:
        route.primary_domain = case_domains[0]
    elif strong_domains and route.primary_domain not in strong_domains and route.primary_domain not in {"procedure", "traffic", "cyber"}:
        # Example: "الشركة قالت سبب الفصل" must be labor, not commercial merely because it says شركة.
        route.primary_domain = strong_domains[0]

    route.domains = list(dict.fromkeys(([route.primary_domain] if route.primary_domain not in {"general", "conversation"} else []) + existing + case_domains))[:4]
    if not route.domains:
        route.domains = ["general"]
    route.confidence = max(route.confidence, 0.74 if case.cognition_provider != "deterministic" else 0.64)

    if route.intent == "legal_question":
        mapped = {"penalty": "penalty", "rights": "rights", "appeal": "appeal", "procedure": "procedure"}.get(case.user_goal)
        if mapped:
            route.intent = mapped
    return route
