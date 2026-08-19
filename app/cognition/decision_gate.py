from __future__ import annotations

from .models import CaseModel, MaterialDecision


HIGH_STAKES_GOALS = {"penalty", "rights", "appeal", "procedure"}


def decide_next_action(case: CaseModel) -> MaterialDecision:
    """Choose whether Qanoni should clarify, retrieve, or answer.

    The gate is intentionally conservative. Missing facts block a direct legal answer
    only when they can materially change the legal characterization, remedy, deadline,
    penalty, or applicable court/procedure.
    """
    material_questions = [q for q in case.clarifying_questions if q.priority >= 70]
    viable = [h for h in case.hypotheses if h.status != "unlikely"]
    competing = [h for h in viable if h.confidence >= 0.30]

    blockers: list[str] = []
    reasons: list[str] = []

    if not viable:
        blockers.append("no_viable_legal_hypothesis")
        reasons.append("لم تتكوّن فرضية قانونية كافية من الوقائع الحالية.")

    if len(competing) >= 2:
        domains = {h.code.split(".", 1)[0] for h in competing}
        if "criminal" in domains and any(h.missing_elements for h in competing):
            blockers.append("material_competing_hypotheses")
            reasons.append("هناك أكثر من تكييف قانوني محتمل، وبعض العناصر الفاصلة ما زالت غير محسومة.")

    if material_questions:
        blockers.append("material_facts_missing")
        reasons.append("توجد وقائع ناقصة يمكن أن تغيّر النتيجة القانونية بشكل جوهري.")

    if case.user_goal in HIGH_STAKES_GOALS and case.warnings:
        blockers.append("high_stakes_uncertainty")
        reasons.append("السؤال عالي الأثر ولا ينبغي إعطاء نتيجة نهائية مع بقاء تحذيرات جوهرية.")

    if blockers:
        return MaterialDecision(
            action="clarify",
            reason=" ".join(dict.fromkeys(reasons)),
            blockers=list(dict.fromkeys(blockers)),
            question_ids=[q.id for q in sorted(material_questions, key=lambda q: q.priority, reverse=True)[:3]],
            safe_to_answer=False,
        )

    if case.retrieval_queries:
        return MaterialDecision(
            action="retrieve",
            reason="الوقائع كافية مبدئياً لبدء بحث قانوني موجّه، مع بقاء التكييف النهائي معلقاً على النصوص المسترجعة.",
            safe_to_answer=False,
        )

    return MaterialDecision(
        action="clarify",
        reason="المعطيات الحالية لا تكفي لتحديد بحث قانوني موثوق.",
        blockers=["insufficient_case_structure"],
        safe_to_answer=False,
    )
