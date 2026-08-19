from __future__ import annotations

import re

from .case_graph import build_case_graph
from .clarification import choose_questions
from .decision_gate import decide_next_action
from .issue_spotter import spot_issues
from .models import Actor, CaseModel, EvidenceItem, Event, Fact
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
    text = _ARABIC_DIACRITICS_RE.sub("", text.lower())
    return (
        text.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ٱ", "ا")
        .replace("ى", "ي")
        .replace("ؤ", "و")
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
            out.append(EvidenceItem(kind=kind, description=f"ذكر المستخدم دليلاً/قرينة مرتبطة بـ: {', '.join(matched)}"))
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

    # Conservative Arabic proper-name extraction from common narrative positions.
    name_patterns = [
        r"(?:قام|قال|ضرب|دخل|أخذ|اخذ|قتل|طعن)\s+([\u0621-\u064A]{3,})",
        r"(?:جاره|منزل|بيت)\s+([\u0621-\u064A]{3,})",
    ]
    for pattern in name_patterns:
        for name in re.findall(pattern, text):
            if name not in {a.label for a in actors} and name not in {"الشخص", "الرجل", "المتهم", "المكان", "الباب"}:
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


class CaseCognitionEngine:
    """Create a structured case model before legal retrieval.

    V4 deliberately separates *understanding facts* from *deciding the law*. The
    deterministic layer is conservative and can later be enriched by a free/local LLM
    without allowing the model to become the legal source of truth.
    """

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

        # Cognition V2: build a fact graph before legal issue selection.
        case.graph = build_case_graph(case)

        case.hypotheses = spot_issues(case)
        case.domains = list(dict.fromkeys(h.domain for h in case.hypotheses)) or ["general"]
        case.clarifying_questions = choose_questions(case)
        case.retrieval_queries = build_retrieval_queries(case)

        if not case.hypotheses:
            case.warnings.append("لم يتم تكوين فرضية قانونية كافية بعد؛ يلزم فهم إضافي قبل البحث المتخصص.")
        if case.hypotheses and all(h.status == "needs_clarification" for h in case.hypotheses):
            case.warnings.append("لا ينبغي إعطاء تكييف نهائي قبل استكمال الوقائع الجوهرية المحددة في أسئلة التوضيح.")

        # The gate decides whether the system should ask, retrieve, or eventually answer.
        case.decision = decide_next_action(case)
        return case
