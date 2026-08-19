from __future__ import annotations

from .clarification import choose_questions
from .decision_gate import decide_next_action
from .engine import CaseCognitionEngine as BaseCaseCognitionEngine
from .issue_spotter import spot_issues
from .models import MaterialDecision, SemanticSignal
from .retrieval_planner import build_retrieval_queries


def _norm(text: str) -> str:
    return " ".join(
        (text or "").lower()
        .replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ٱ", "ا")
        .replace("ى", "ي")
        .replace("ؤ", "و")
        .split()
    )


def _contains(text: str, *terms: str) -> bool:
    n = _norm(text)
    return any(_norm(term) in n for term in terms)


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
    never replace grounded legal retrieval.
    """
    text = case.raw_message

    if _contains(
        text,
        "بالغلط", "بالخطأ", "بالخطا", "خطأ", "خطا", "دون قصد", "بدون قصد",
        "غير مقصود", "ما كنت أقصد", "ما كنت اقصد", "لم أقصد", "لم اقصد",
        "دون أن أتعمد", "دون ان اتعمد", "لم أتعمد", "لم اتعمد",
    ):
        _add_signal(case, "intent.accidental", "وصف المستخدم الواقعة بأنها غير مقصودة")

    if _contains(text, "دفاع عن نفسي", "دفاعاً عن نفسي", "دفاعا عن نفسي", "دفاع شرعي", "هاجمني"):
        _add_signal(case, "intent.self_defense_claim", "ذكر المستخدم ادعاء دفاع عن النفس")

    if case.user_goal == "appeal" or _contains(text, "استئناف", "استأنف", "استانف", "أستأنف", "اطعن", "طعن", "تمييز"):
        _add_signal(case, "goal.appeal", "ذكر المستخدم الاستئناف أو الطعن")

    if case.user_goal == "penalty":
        _add_signal(case, "goal.penalty", "سؤال المستخدم عن العقوبة", "medium")
    elif case.user_goal == "rights":
        _add_signal(case, "goal.rights", "سؤال المستخدم عن الحقوق", "medium")
    elif case.user_goal == "procedure":
        _add_signal(case, "goal.procedure", "سؤال المستخدم عن إجراء", "medium")

    if _contains(text, "فصلني", "طردني", "انهاء عقد", "إنهاء عقد", "سبب الفصل"):
        _add_signal(case, "employment.termination", "ذكر المستخدم إنهاء علاقة العمل")

    if _contains(text, "سرق", "سرقة", "أخذ", "اخذ", "استولى"):
        _add_signal(case, "property.taking", "ذكر المستخدم أخذ أو استيلاء على مال")

    if _contains(text, "توفي", "توفى", "مات", "وفاة", "قتل"):
        _add_signal(case, "event.death", "ذكر المستخدم وفاة أو قتل")

    if _contains(text, "هدد", "هددني", "يهددني", "بهددني", "بتهددني", "تهديد", "ابتزاز", "ابتزني", "ببتزني", "يبتزني"):
        _add_signal(case, "event.threat", "ذكر المستخدم تهديداً أو ابتزازاً")

    if _contains(text, "اصابة", "إصابة", "انصاب", "اصيب", "أصيب", "جرح", "المستشفى"):
        _add_signal(case, "event.injury", "ذكر المستخدم إصابة")


def _is_short_ambiguous(case) -> bool:
    tokens = [token for token in case.raw_message.replace("؟", " ").replace("?", " ").split() if token]
    if case.user_goal != "legal_analysis" or len(tokens) > 6:
        return False
    if case.dates or case.amounts or case.evidence:
        return False
    # A short bare act such as "أخذ المصاري ومشي" should trigger clarification rather
    # than preliminary legal retrieval. Specific penalty/appeal/rights questions are
    # handled by their explicit user_goal and do not enter this branch.
    return len(case.facts) <= 1 and len(case.events) <= 2


class CaseCognitionEngine(BaseCaseCognitionEngine):
    """Cognition V2.1 wrapper with deterministic semantics and conservative ambiguity gating."""

    def analyze(self, message: str, language: str = "ar"):
        case = super().analyze(message, language)

        before = {(signal.code, signal.support_span) for signal in case.semantic_signals}
        _seed_deterministic_signals(case)
        after = {(signal.code, signal.support_span) for signal in case.semantic_signals}

        # New deterministic semantic cues can materially change competing hypotheses,
        # retrieval planning, and clarification priority. Recompute only when needed.
        if after != before:
            case.hypotheses = spot_issues(case)
            case.domains = list(dict.fromkeys(h.domain for h in case.hypotheses)) or ["general"]
            case.clarifying_questions = choose_questions(case)
            case.retrieval_queries = build_retrieval_queries(case)
            case.decision = decide_next_action(case)

        if _is_short_ambiguous(case):
            case.decision = MaterialDecision(
                action="clarify",
                reason="العبارة قصيرة وتحتمل أكثر من سياق قانوني؛ يلزم توضيح العلاقة بين الأطراف وسبب الفعل قبل بدء بحث قانوني موجّه.",
                blockers=["short_ambiguous_prompt"],
                question_ids=[q.id for q in case.clarifying_questions[:3]],
                safe_to_answer=False,
            )

        return case
