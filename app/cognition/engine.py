from __future__ import annotations

import re

from .clarification import choose_questions
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


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[\n\r.!؟?؛]+|،\s+(?=[ثمفبعدلاحق])", text)
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


def _goal(text: str) -> str:
    low = text.lower()
    if any(x in low for x in ["شو العقوبة", "ما العقوبة", "ما هي العقوبة", "عقوب"]):
        return "penalty"
    if any(x in low for x in ["شو حقوقي", "ما حقوقي", "حقوقي", "استحق"]):
        return "rights"
    if any(x in low for x in ["استئناف", "اطعن", "طعن", "تمييز"]):
        return "appeal"
    if any(x in low for x in ["شو اعمل", "شو أعمل", "كيف اقدم", "كيف أقدم", "الإجراء", "الاجراء"]):
        return "procedure"
    return "legal_analysis"


def _procedural_posture(text: str) -> str:
    low = text.lower()
    if any(x in low for x in ["صدر الحكم", "حكمت المحكمة", "الحكم كان", "استئناف", "تمييز"]):
        return "post_judgment"
    if any(x in low for x in ["المدعي العام", "النيابة", "الشرطة حققت", "تم توقيف", "موقوف"]):
        return "investigation"
    if any(x in low for x in ["رفعت دعوى", "المحكمة", "جلسة", "القضية"]):
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
    # Named Arabic persons are useful in long scenarios even when their role is unknown.
    for name in re.findall(r"(?:قام|قال|ضرب|دخل|أخذ|اخذ)\s+([\u0621-\u064A]{3,})", text):
        if name not in {a.label for a in actors} and name not in {"الشخص", "الرجل", "المتهم"}:
            actors.append(Actor(id=f"a{idx}", label=name, role="person"))
            idx += 1
    return actors


def _categorize_fact(sentence: str) -> str:
    if _extract_amounts(sentence):
        return "amount"
    if any(x in sentence for x in ["كاميرا", "شهود", "الشرطة", "ضبط", "عثر"]):
        return "evidence"
    if any(x in sentence for x in ["قصد", "خطط", "بالغلط", "خطأ", "تعمد"]):
        return "mental_state"
    if any(x in sentence for x in ["دخل", "كسر", "أخذ", "اخذ", "ضرب", "قتل", "فصلني", "طردني"]):
        return "conduct"
    return "context"


def _event_type(sentence: str) -> str:
    mapping = [
        ("entry", ["دخل", "تسلل"]),
        ("breaking", ["كسر", "خلع"]),
        ("taking", ["أخذ", "اخذ", "سرق"]),
        ("violence", ["ضرب", "طعن", "أطلق", "اطلق"]),
        ("death", ["قتل", "توفي", "توفى", "مات"]),
        ("termination", ["فصلني", "طردني", "أنهى عقد", "انهى عقد"]),
        ("judgment", ["صدر الحكم", "حكمت المحكمة"]),
    ]
    for event_type, terms in mapping:
        if any(t in sentence for t in terms):
            return event_type
    return "context"


class CaseCognitionEngine:
    """Build a structured representation of a user's legal situation before retrieval.

    The deterministic extractor is deliberately conservative. A future optional LLM
    adapter may enrich this structure, but the schema and safety rules remain the same.
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

        for index, sentence in enumerate(_sentences(message), start=1):
            case.facts.append(Fact(text=sentence, category=_categorize_fact(sentence)))
            if _event_type(sentence) != "context":
                case.events.append(Event(order=index, text=sentence, event_type=_event_type(sentence)))

        case.hypotheses = spot_issues(case)
        case.domains = list(dict.fromkeys(h.domain for h in case.hypotheses)) or ["general"]
        case.clarifying_questions = choose_questions(case)
        case.retrieval_queries = build_retrieval_queries(case)

        if not case.hypotheses:
            case.warnings.append("لم يتم تكوين فرضية قانونية كافية بعد؛ يلزم فهم إضافي قبل البحث المتخصص.")
        if case.hypotheses and all(h.status == "needs_clarification" for h in case.hypotheses):
            case.warnings.append("لا ينبغي إعطاء تكييف نهائي قبل استكمال الوقائع الجوهرية المحددة في أسئلة التوضيح.")
        return case
