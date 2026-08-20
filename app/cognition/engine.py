from __future__ import annotations

import re

from .case_graph import build_case_graph
from .clarification import choose_questions
from .decision_gate import decide_next_action
from .issue_spotter import spot_issues
from .llm_enricher import CognitionEnricher, CognitionEnrichment, default_cognition_enricher
from .models import Actor, CaseModel, EvidenceItem, Event, Fact, SemanticSignal
from .retrieval_planner import build_retrieval_queries


EVIDENCE_TERMS = {
    "camera": ["كاميرا", "كاميرات", "cctv", "تصوير"],
    "witness": ["شاهد", "شهود"],
    "document": ["عقد", "مستند", "كتاب خطي", "ورقة", "إيصال", "فاتورة"],
    "digital": ["واتساب", "رسالة", "رسائل", "محادثة", "سكرين", "لقطة شاشة", "هاتف"],
    "physical": ["ضبط", "عثر", "وجدت الشرطة", "بصمات", "أداة", "سلاح"],
}

_ARABIC_DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")


def _normalize_arabic(text: str) -> str:
    text = _ARABIC_DIACRITICS_RE.sub("", (text or "").lower())
    return " ".join(
        text.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ٱ", "ا")
        .replace("ى", "ي")
        .replace("ؤ", "و")
        .split()
    )


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[\n\r.!؟?؛]+", text)
    return [p.strip(" ،.\t") for p in parts if p.strip(" ،.\t")]


def _extract_amounts(text: str) -> list[str]:
    pattern = r"(?:حوالي\s*)?\d+(?:[.,]\d+)?\s*(?:دينار|دنانير|JD|JOD|ألف|الف)"
    return re.findall(pattern, text, flags=re.IGNORECASE)


def _extract_dates(text: str) -> list[str]:
    patterns = [
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b",
        r"(?:اليوم|أمس|امس|غداً|غدا|قبل\s+\d+\s+(?:يوم|أيام|شهر|أشهر|سنة|سنوات))",
    ]
    out: list[str] = []
    for pattern in patterns:
        out.extend(re.findall(pattern, text, flags=re.IGNORECASE))
    return out


def _mentions_appeal(text: str) -> bool:
    low = _normalize_arabic(text)
    return any(term in low for term in ["استئناف", "استانف", "مستانف", "اطعن", "طعن", "تمييز"])


def _goal(text: str) -> str:
    low = _normalize_arabic(text)
    if any(x in low for x in ["شو العقوبه", "ما العقوبه", "ما هي العقوبه", "عقوب"]):
        return "penalty"
    if any(x in low for x in ["شو حقوقي", "ما حقوقي", "حقوقي", "استحق"]):
        return "rights"
    if _mentions_appeal(text):
        return "appeal"
    if any(x in low for x in ["شو اعمل", "كيف اقدم", "الاجراء"]):
        return "procedure"
    return "legal_analysis"


def _procedural_posture(text: str) -> str:
    low = _normalize_arabic(text)
    if any(x in low for x in ["صدر الحكم", "حكمت المحكمه", "الحكم كان"]) or _mentions_appeal(text):
        return "post_judgment"
    if any(x in low for x in ["المدعي العام", "النيابه", "الشرطه حققت", "تم توقيف", "موقوف"]):
        return "investigation"
    if any(x in low for x in ["رفعت دعوي", "المحكمه", "جلسه", "القضيه"]):
        return "litigation"
    return "pre_case"


def _extract_evidence(text: str) -> list[EvidenceItem]:
    low = text.lower()
    out: list[EvidenceItem] = []
    for kind, terms in EVIDENCE_TERMS.items():
        matched = [term for term in terms if term.lower() in low]
        if matched:
            out.append(
                EvidenceItem(
                    kind=kind,
                    description=f"ذكر المستخدم دليلاً/قرينة مرتبطة بـ: {', '.join(matched)}",
                    source="deterministic",
                )
            )
    return out


def _extract_actors(text: str) -> list[Actor]:
    actors: list[Actor] = []
    role_terms = [
        ("employer", ["صاحب العمل", "الشركة"]),
        ("worker", ["العامل", "الموظف"]),
        ("police", ["الشرطة", "الأمن العام"]),
        ("prosecutor", ["المدعي العام", "النيابة العامة"]),
        ("victim", ["المجني عليه", "الضحية", "صاحب المنزل", "صاحب البيت"]),
        ("suspect", ["المتهم", "الجاني", "الفاعل"]),
    ]
    low = text.lower()
    idx = 1
    for role, terms in role_terms:
        for term in terms:
            if term.lower() in low:
                actors.append(Actor(id=f"a{idx}", label=term, role=role))
                idx += 1
                break

    # Word-boundary-anchored so a trigger word never matches as a substring of a longer word
    # (e.g. unanchored "بيت" previously matched inside "البيت" and captured whatever followed
    # it as a fake actor). Arabic letters are \w under Python's default Unicode regex, so \b
    # works the same way it does for Latin text.
    name_patterns = [
        r"\b(?:قام|قال|طلب|رفض|أيد|ايد|عاد|أصيب|اصيب|اتصل|ذهب|خرج|هرب|اعترف|أنكر|انكر|"
        r"ضرب|دخل|أخذ|اخذ|قتل|طعن)\s+([\u0621-\u064A]{3,})",
        r"\b(?:جاره|منزل|بيت)\s+([\u0621-\u064A]{3,})",
    ]
    for pattern in name_patterns:
        for name in re.findall(pattern, text):
            if name not in {a.label for a in actors} and name not in {"الشخص", "الرجل", "المتهم", "المكان", "الباب"}:
                actors.append(Actor(id=f"a{idx}", label=name, role="person"))
                idx += 1

    # Natural Arabic narrative order very commonly puts the subject BEFORE the verb ("زيد قال",
    # "عدي طلب"), which the trigger-verb-first patterns above never capture, silently dropping
    # the story's actual named parties. Relies on the same downstream prune_non_person_actors
    # blocklist as the safety net against non-name words that happen to precede these verbs.
    subject_verb_pattern = (
        r"([ء-ي]{3,})\s+"
        r"(?:قال|قالت|طلب|طلبت|رفض|رفضت|أيد|ايد|أيدت|ايدت|عاد|عادت|أصيب|اصيب|أصيبت|اصيبت|"
        r"اتصل|اتصلت|ذهب|ذهبت|خرج|خرجت|هرب|هربت|اعترف|اعترفت|أنكر|انكر|أنكرت|انكرت)\b"
    )
    for name in re.findall(subject_verb_pattern, text):
        if name not in {a.label for a in actors}:
            actors.append(Actor(id=f"a{idx}", label=name, role="person"))
            idx += 1
    return actors


def _categorize_fact(sentence: str) -> str:
    normalized = _normalize_arabic(sentence)
    if _extract_amounts(sentence):
        return "amount"
    if any(x in normalized for x in ["كاميرا", "شهود", "الشرطه", "ضبط", "عثر"]):
        return "evidence"
    if any(x in normalized for x in ["قصد", "خطط", "بالغلط", "خطا", "تعمد", "سبق الاصرار"]):
        return "mental_state"
    if any(x in normalized for x in ["دخل", "دخول", "كسر", "اخذ", "ضرب", "قتل", "فصلني", "طردني"]):
        return "conduct"
    return "context"


EVENT_TERMS: list[tuple[str, list[str]]] = [
    ("entry", ["دخل", "دخول", "تسلل"]),
    ("breaking", ["كسر", "خلع"]),
    ("taking", ["أخذ", "اخذ", "سرق"]),
    ("violence", ["ضرب", "طعن", "أطلق", "اطلق"]),
    ("death", ["قتل", "توفي", "توفى", "مات"]),
    ("termination", ["فصلني", "طردني", "أنهى عقد", "انهى عقد"]),
    ("judgment", ["صدر الحكم", "حكمت المحكمة"]),
]


def _event_types(sentence: str) -> list[str]:
    normalized = _normalize_arabic(sentence)
    found: list[str] = []
    for event_type, terms in EVENT_TERMS:
        if any(_normalize_arabic(term) in normalized for term in terms):
            found.append(event_type)
    return found


def _actor_id_for_label(case: CaseModel, label: str) -> str | None:
    wanted = _normalize_arabic(label)
    if not wanted:
        return None
    for actor in case.actors:
        if _normalize_arabic(actor.label) == wanted:
            return actor.id
    return None


def _event_position(message: str, event: Event) -> int:
    raw = event.support_span or event.text
    direct = message.find(raw)
    if direct >= 0:
        return direct
    normalized_message = _normalize_arabic(message)
    normalized_raw = _normalize_arabic(raw)
    pos = normalized_message.find(normalized_raw)
    return pos if pos >= 0 else 10**9


def _merge_enrichment(case: CaseModel, enrichment: CognitionEnrichment) -> None:
    """Merge only grounded linguistic enrichment; never legal conclusions."""
    case.cognition_provider = enrichment.provider or "llm"
    case.cognition_model = enrichment.model or ""
    case.cognition_ambiguities = [
        {
            "question": str(item.get("question") or "").strip(),
            "reason": str(item.get("reason") or "").strip(),
            "material": bool(item.get("material")),
        }
        for item in enrichment.ambiguities
        if item.get("question")
    ]

    # The deterministic goal/posture wins when it already recognized a specific intent.
    if case.user_goal == "legal_analysis" and enrichment.user_goal in {
        "penalty", "rights", "appeal", "procedure", "conversation"
    }:
        case.user_goal = enrichment.user_goal
    if case.procedural_posture == "pre_case" and enrichment.procedural_posture in {
        "investigation", "litigation", "post_judgment"
    }:
        case.procedural_posture = enrichment.procedural_posture

    existing_actor_labels = {_normalize_arabic(actor.label) for actor in case.actors}
    allowed_roles = {"person", "worker", "employer", "victim", "suspect", "police", "prosecutor", "court", "other"}
    for item in enrichment.actors:
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        normalized = _normalize_arabic(label)
        role = str(item.get("role") or "person")
        role = role if role in allowed_roles else "person"
        support_span = str(item.get("support_span") or "").strip() or None
        existing = next((a for a in case.actors if _normalize_arabic(a.label) == normalized), None)
        if existing:
            if existing.role in {"unknown", "person"} and role not in {"unknown", "person", "other"}:
                existing.role = role
                existing.source = "hybrid"
                existing.support_span = support_span
            continue
        case.actors.append(
            Actor(
                id=f"a{len(case.actors) + 1}",
                label=label,
                role=role,
                source="llm",
                support_span=support_span,
            )
        )
        existing_actor_labels.add(normalized)

    allowed_event_types = {
        "entry", "breaking", "taking", "violence", "death", "injury", "threat",
        "termination", "judgment", "payment", "communication", "other",
    }
    allowed_intents = {"accidental", "intentional", "premeditated", "self_defense_claim", "unknown"}
    for item in enrichment.events:
        event_type = str(item.get("event_type") or "other")
        if event_type not in allowed_event_types:
            event_type = "other"
        support_span = str(item.get("support_span") or "").strip()
        if not support_span:
            continue
        intent = str(item.get("intent") or "unknown")
        if intent not in allowed_intents:
            intent = "unknown"
        actor_id = _actor_id_for_label(case, str(item.get("actor_label") or ""))
        target = str(item.get("target") or "").strip() or None
        time_expression = str(item.get("time_expression") or "").strip() or None
        location = str(item.get("location") or "").strip() or None

        span_norm = _normalize_arabic(support_span)
        existing = next(
            (
                event
                for event in case.events
                if event.event_type == event_type
                and (
                    span_norm in _normalize_arabic(event.text)
                    or _normalize_arabic(event.text) in span_norm
                )
            ),
            None,
        )
        if existing:
            if actor_id and actor_id not in existing.actors:
                existing.actors.append(actor_id)
            if target and not existing.target:
                existing.target = target
            if existing.intent == "unknown" and intent != "unknown":
                existing.intent = intent
            if time_expression and not existing.time_expression:
                existing.time_expression = time_expression
            if location and not existing.location:
                existing.location = location
            existing.source = "hybrid"
            existing.support_span = support_span
            continue

        case.events.append(
            Event(
                order=len(case.events) + 1,
                text=support_span,
                event_type=event_type,
                actors=[actor_id] if actor_id else [],
                target=target,
                intent=intent,
                time_expression=time_expression,
                location=location,
                source="llm",
                support_span=support_span,
            )
        )

    # Re-establish narrative order after adding events the deterministic parser missed.
    case.events.sort(key=lambda event: (_event_position(case.raw_message, event), event.order))
    for index, event in enumerate(case.events, start=1):
        event.order = index

    existing_evidence = {(item.kind, _normalize_arabic(item.support_span or item.description)) for item in case.evidence}
    for item in enrichment.evidence:
        kind = str(item.get("kind") or "other")
        description = str(item.get("description") or "").strip()
        support_span = str(item.get("support_span") or "").strip()
        key = (kind, _normalize_arabic(support_span or description))
        if not description or key in existing_evidence:
            continue
        case.evidence.append(
            EvidenceItem(
                kind=kind,
                description=description,
                reliability="medium",
                source="llm",
                support_span=support_span,
            )
        )
        existing_evidence.add(key)

    existing_signals = {(signal.code, _normalize_arabic(signal.support_span)) for signal in case.semantic_signals}
    for item in enrichment.semantic_signals:
        code = str(item.get("code") or "").strip()
        support_span = str(item.get("support_span") or "").strip()
        confidence = str(item.get("confidence") or "medium")
        confidence = confidence if confidence in {"low", "medium", "high"} else "medium"
        key = (code, _normalize_arabic(support_span))
        if not code or not support_span or key in existing_signals:
            continue
        case.semantic_signals.append(
            SemanticSignal(code=code, support_span=support_span, confidence=confidence, source="llm")
        )
        existing_signals.add(key)


class CaseCognitionEngine:
    """Create a structured case model before legal retrieval.

    The deterministic layer always runs first. An optional LLM may enrich language
    understanding, but only grounded spans are accepted and the LLM never becomes a
    source of Jordanian law. If the LLM is unavailable, analysis continues normally.
    """

    def __init__(self, enricher: CognitionEnricher | None = None, enable_llm: bool = True):
        self.enricher = enricher if enricher is not None else (default_cognition_enricher() if enable_llm else None)

    def analyze(self, message: str, language: str = "ar") -> CaseModel:
        case = CaseModel(
            raw_message=message.strip(),
            language=language,
            user_goal=_goal(message),
            procedural_posture=_procedural_posture(message),
        )
        case.actors = _extract_actors(message)
        case.amounts = _extract_amounts(message)
        case.dates = _extract_dates(message)
        case.evidence = _extract_evidence(message)

        event_order = 1
        for sentence in _sentences(message):
            case.facts.append(Fact(text=sentence, category=_categorize_fact(sentence)))
            for event_type in _event_types(sentence):
                case.events.append(Event(order=event_order, text=sentence, event_type=event_type))
                event_order += 1

        if self.enricher:
            enrichment = self.enricher.enrich(message, language)
            if enrichment:
                _merge_enrichment(case, enrichment)

        # Build the graph only after all grounded cognition enrichment has been merged.
        case.graph = build_case_graph(case)
        case.hypotheses = spot_issues(case)
        case.domains = list(dict.fromkeys(h.domain for h in case.hypotheses)) or ["general"]
        case.clarifying_questions = choose_questions(case)
        case.retrieval_queries = build_retrieval_queries(case)

        if not case.hypotheses:
            case.warnings.append("لم يتم تكوين فرضية قانونية كافية بعد؛ يلزم فهم إضافي قبل البحث المتخصص.")
        if case.hypotheses and all(h.status == "needs_clarification" for h in case.hypotheses):
            case.warnings.append("لا ينبغي إعطاء تكييف نهائي قبل استكمال الوقائع الجوهرية المحددة في أسئلة التوضيح.")

        case.decision = decide_next_action(case)
        return case
