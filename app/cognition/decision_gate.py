from __future__ import annotations

from .models import CaseModel, MaterialDecision


HIGH_STAKES_GOALS = {"penalty", "rights", "appeal", "procedure"}


def _rich_fact_pattern(case: CaseModel) -> bool:
    """A detailed narrative can support preliminary retrieval even before final classification."""
    return len(case.events) >= 2 and (len(case.evidence) >= 1 or len(case.facts) >= 2)


def decide_next_action(case: CaseModel) -> MaterialDecision:
    """Choose whether to clarify first or start grounded retrieval.

    Cognition V2 does not force every incomplete scenario into a dead-end clarification.
    A rich fact pattern may proceed to *preliminary* retrieval while still carrying the
    material follow-up questions. Final penalty/deadline/liability answers remain blocked
    until the decisive facts and verified legal text are available.
    """
    material_questions = [q for q in case.clarifying_questions if q.priority >= 70]
    viable = [h for h in case.hypotheses if h.status != "unlikely"]
    competing = [h for h in viable if h.confidence >= 0.30]
    question_ids = [q.id for q in sorted(material_questions, key=lambda q: q.priority, reverse=True)[:3]]

    if not viable:
        return MaterialDecision(
            action="clarify",
            reason="لم تتكوّن فرضية قانونية كافية من الوقائع الحالية.",
            blockers=["no_viable_legal_hypothesis"],
            question_ids=question_ids,
            safe_to_answer=False,
        )

    codes = {h.code for h in competing}
    homicide_competition = (
        "criminal.intentional_homicide" in codes
        and "criminal.unintentional_death" in codes
        and any(h.missing_elements for h in competing if h.code.startswith("criminal."))
    )

    if homicide_competition:
        return MaterialDecision(
            action="clarify",
            reason="القصد وطريقة وقوع الوفاة يمكن أن يغيّرا التكييف جذرياً؛ يجب حسم الوقائع الفاصلة قبل نتيجة نهائية.",
            blockers=["material_competing_hypotheses"],
            question_ids=question_ids,
            safe_to_answer=False,
        )

    if case.user_goal == "appeal" and material_questions:
        return MaterialDecision(
            action="clarify",
            reason="مدة وطريق الطعن يعتمدان على نوع القضية والمحكمة ووصف الحكم والتواريخ؛ يلزم استكمال هذه البيانات أولاً.",
            blockers=["appeal_material_facts_missing"],
            question_ids=question_ids,
            safe_to_answer=False,
        )

    if case.user_goal in {"penalty", "rights", "procedure"} and material_questions and not _rich_fact_pattern(case):
        return MaterialDecision(
            action="clarify",
            reason="توجد وقائع ناقصة يمكن أن تغيّر النتيجة المطلوبة مباشرة.",
            blockers=["material_facts_missing"],
            question_ids=question_ids,
            safe_to_answer=False,
        )

    if case.retrieval_queries:
        reason = "الوقائع كافية مبدئياً لبدء بحث قانوني موجّه."
        if material_questions:
            reason += " يمكن تقديم تحليل أولي مع إبقاء الأسئلة الجوهرية مفتوحة قبل أي تكييف أو نتيجة نهائية."
        return MaterialDecision(
            action="retrieve",
            reason=reason,
            question_ids=question_ids,
            safe_to_answer=False,
        )

    return MaterialDecision(
        action="clarify",
        reason="المعطيات الحالية لا تكفي لتحديد بحث قانوني موثوق.",
        blockers=["insufficient_case_structure"],
        question_ids=question_ids,
        safe_to_answer=False,
    )
