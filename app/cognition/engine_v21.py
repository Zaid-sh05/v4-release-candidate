from __future__ import annotations

import re

from .clarification import choose_questions
from .decision_gate import decide_next_action
from .engine import CaseCognitionEngine as BaseCaseCognitionEngine
from .issue_spotter import spot_issues
from .language_match import contains_fuzzy, normalize_flexible
from .models import MaterialDecision, SemanticSignal
from .retrieval_planner import build_retrieval_queries


def _norm(text: str) -> str:
    return normalize_flexible(text)


def _contains(text: str, *terms: str) -> bool:
    return contains_fuzzy(text, *terms)


def _add_signal(case, code: str, support_span: str, confidence: str = "high") -> None:
    if any(signal.code == code for signal in case.semantic_signals):
        return
    case.semantic_signals.append(
        SemanticSignal(
            code=code,
            support_span=support_span,
            confidence=confidence,
            source="deterministic",
        )
    )


def _seed_deterministic_signals(case) -> None:
    """Add high-value semantic cues that must not depend on optional LLM availability.

    These are language-understanding signals only. They are never legal conclusions and
    never replace grounded legal retrieval. Matching is bilingual and typo-tolerant, but
    deliberately conservative for short words to avoid false legal-domain triggers.
    """
    text = case.raw_message

    if _contains(
        text,
        "بالغلط", "بالخطأ", "بالخطا", "خطأ", "خطا", "دون قصد", "بدون قصد",
        "غير مقصود", "ما كنت أقصد", "ما كنت اقصد", "لم أقصد", "لم اقصد",
        "دون أن أتعمد", "دون ان اتعمد", "لم أتعمد", "لم اتعمد",
        "accidentally", "by accident", "did not mean", "didn't mean",
    ):
        _add_signal(case, "intent.accidental", "وصف المستخدم الواقعة بأنها غير مقصودة")

    if _contains(text, "دفاع عن نفسي", "دفاعاً عن نفسي", "دفاعا عن نفسي", "دفاع شرعي", "هاجمني", "self defense", "self-defense"):
        _add_signal(case, "intent.self_defense_claim", "ذكر المستخدم ادعاء دفاع عن النفس")

    if case.user_goal == "appeal" or _contains(text, "استئناف", "استأنف", "استانف", "أستأنف", "اطعن", "طعن", "تمييز", "appeal", "cassation"):
        _add_signal(case, "goal.appeal", "ذكر المستخدم الاستئناف أو الطعن")

    if case.user_goal == "penalty":
        _add_signal(case, "goal.penalty", "سؤال المستخدم عن العقوبة", "medium")
    elif case.user_goal == "rights":
        _add_signal(case, "goal.rights", "سؤال المستخدم عن الحقوق", "medium")
    elif case.user_goal == "procedure":
        _add_signal(case, "goal.procedure", "سؤال المستخدم عن إجراء", "medium")

    if _contains(text, "فصلني", "طردني", "انهاء عقد", "إنهاء عقد", "سبب الفصل", "fired", "dismissed", "terminated", "let me go from my job"):
        _add_signal(case, "employment.termination", "ذكر المستخدم إنهاء علاقة العمل")

    if _contains(text, "سرق", "سرقة", "أخذ", "اخذ", "استولى", "took", "stole", "stolen", "theft"):
        _add_signal(case, "property.taking", "ذكر المستخدم أخذ أو استيلاء على مال")

    if _contains(text, "توفي", "توفى", "مات", "وفاة", "قتل", "died", "death", "killed"):
        _add_signal(case, "event.death", "ذكر المستخدم وفاة أو قتل")

    if _contains(text, "هدد", "هددني", "يهددني", "بهددني", "بتهددني", "تهديد", "ابتزاز", "ابتزني", "ببتزني", "يبتزني", "threatened", "threat", "blackmail", "extortion"):
        _add_signal(case, "event.threat", "ذكر المستخدم تهديداً أو ابتزازاً")

    if _contains(text, "اصابة", "إصابة", "انصاب", "اصيب", "أصيب", "جرح", "المستشفى", "injured", "injury", "hospital"):
        _add_signal(case, "event.injury", "ذكر المستخدم إصابة")


_EVENT_CUES: dict[str, tuple[str, ...]] = {
    "entry": ("دخل", "دخول", "تسلل", "اقتحم", "entered", "entry", "broke in", "broke into"),
    "breaking": ("كسر", "خلع", "حطم", "broke", "breaking", "forced entry"),
    "taking": ("أخذ", "اخذ", "سرق", "استولى", "استيلاء", "took", "stole", "stolen", "taking", "theft"),
    "violence": ("ضرب", "طعن", "اعتدى", "هاجم", "اطلق", "أطلق", "hit", "stabbed", "assaulted", "attacked", "shot"),
    "death": ("توفي", "توفى", "مات", "قتل", "وفاة", "died", "death", "killed"),
    "injury": ("اصيب", "أصيب", "انصاب", "جرح", "اصابة", "إصابة", "injured", "injury", "hurt"),
    "threat": ("هدد", "تهديد", "ابتزاز", "ابتز", "threatened", "threat", "blackmail", "extortion"),
    "termination": ("فصل", "طرد", "انهى عقد العمل", "أنهى عقد العمل", "فصلني", "fired", "dismissed", "terminated", "let me go"),
    "judgment": ("صدر الحكم", "حكمت المحكمة", "الحكم", "judgment", "court ruled", "verdict"),
    "payment": ("دفع", "دفعت", "حول", "عربون", "مبلغ", "دينار", "paid", "payment", "deposit", "transferred"),
    "communication": ("قال", "قالت", "بحكي", "رسالة", "واتساب", "ابلغ", "أبلغ", "said", "told", "message", "whatsapp"),
}


def _prune_semantically_invalid_llm_events(case) -> bool:
    """Reject LLM-only event labels that are grounded textually but semantically mismatched.

    Grounding alone is not enough: a model can quote "نقلوه عالمستشفى" and still label
    it as a taking event. Hybrid events already corroborated by deterministic parsing are
    preserved; only unsupported LLM-only labels are removed.
    """
    kept = []
    changed = False
    for event in case.events:
        if event.source != "llm" or event.event_type == "other":
            kept.append(event)
            continue
        cues = _EVENT_CUES.get(event.event_type)
        span = event.support_span or event.text
        if cues and not _contains(span, *cues):
            changed = True
            continue
        kept.append(event)

    if changed:
        case.events = kept
        for index, event in enumerate(case.events, start=1):
            event.order = index
    return changed


def _mark_disputed_facts(case) -> bool:
    markers = (
        "الشرطة بتقول", "الشرطة تقول", "بتقول إني", "بتقول اني", "يقول إني", "يقول اني",
        "يدعي", "يدّعي", "بحكي إنه", "بحكي انه", "أنا بنكر", "انا بنكر", "أنكر", "انكر",
        "ينكر", "حسب كلام", "حسب قوله", "متهمني", "اتهمني",
        "police say", "police says", "alleged", "alleges", "i deny", "denies",
    )
    changed = False
    for fact in case.facts:
        if _contains(fact.text, *markers) and not fact.disputed:
            fact.disputed = True
            changed = True
    return changed


_RAW_EXPLICIT_GOAL_CUES = (
    "عقوبة", "عقوبه", "غرامة", "غرامه", "حبس", "سجن",
    "حقوقي", "حقوق", "حقي", "استحق", "تعويض",
    "استئناف", "استأنف", "استانف", "طعن", "تمييز",
    "شكوى", "اشتكي", "أشتكي", "اجراءات", "إجراءات",
    "شو اعمل", "شو أعمل", "ماذا افعل", "ماذا أفعل", "كيف",
    "ما هي", "كم", "هل", "متى", "بدي",
    "what", "how", "rights", "penalty", "fine", "appeal",
    "complaint", "procedure", "deadline", "compensation",
)


def _is_raw_short_ambiguous(message: str) -> bool:
    """Classify a short bare factual utterance before optional LLM enrichment."""
    normalized = _norm(message)
    prompt_tokens = re.findall(r"[A-Za-z0-9_\u0600-\u06ff]+", normalized)
    if not prompt_tokens or len(prompt_tokens) > 6:
        return False
    if _contains(message, *_RAW_EXPLICIT_GOAL_CUES):
        return False
    return True


def _is_short_ambiguous(case) -> bool:
    prompt_tokens = [token for token in case.raw_message.replace("؟", " ").replace("?", " ").split() if token]
    if case.user_goal != "legal_analysis" or len(prompt_tokens) > 6:
        return False
    if case.dates or case.amounts or case.evidence:
        return False
    return len(case.facts) <= 1 and len(case.events) <= 2


class CaseCognitionEngine(BaseCaseCognitionEngine):
    """Cognition V2.5 wrapper with bilingual typo-tolerant semantic validation."""

    def analyze(self, message: str, language: str = "ar"):
        raw_short_ambiguous = _is_raw_short_ambiguous(message)
        case = super().analyze(message, language)

        before_signals = {(signal.code, signal.support_span) for signal in case.semantic_signals}
        _seed_deterministic_signals(case)
        after_signals = {(signal.code, signal.support_span) for signal in case.semantic_signals}

        events_changed = _prune_semantically_invalid_llm_events(case)
        disputed_changed = _mark_disputed_facts(case)

        if after_signals != before_signals or events_changed or disputed_changed:
            case.hypotheses = spot_issues(case)
            case.domains = list(dict.fromkeys(h.domain for h in case.hypotheses)) or ["general"]
            case.clarifying_questions = choose_questions(case)
            case.retrieval_queries = build_retrieval_queries(case)
            case.decision = decide_next_action(case)

        if _is_short_ambiguous(case) or (raw_short_ambiguous and (case.events or case.hypotheses)):
            case.decision = MaterialDecision(
                action="clarify",
                reason="العبارة قصيرة وتحتمل أكثر من سياق قانوني؛ يلزم توضيح العلاقة بين الأطراف وسبب الفعل قبل بدء بحث قانوني موجّه.",
                blockers=["short_ambiguous_prompt"],
                question_ids=[q.id for q in case.clarifying_questions[:3]],
                safe_to_answer=False,
            )

        return case
