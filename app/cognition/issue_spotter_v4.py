from __future__ import annotations

from .issue_spotter import spot_issues as base_spot_issues
from .language_match import contains_fuzzy
from .models import CaseModel, LegalHypothesis


def _add(items: list[LegalHypothesis], hypothesis: LegalHypothesis) -> None:
    if any(item.code == hypothesis.code for item in items):
        return
    items.append(hypothesis)


def spot_issues(case: CaseModel) -> list[LegalHypothesis]:
    """Extend the stable issue spotter with neutral multi-issue scenario analysis.

    Codes in this layer are issue candidates, not findings of guilt/liability. The purpose is to
    tell a lawyer what must be researched and proved next without converting allegations, police
    statements, witness recantations, or money requests into established offences.
    """
    items = list(base_spot_issues(case))
    text = case.raw_message
    signals = {signal.code for signal in case.semantic_signals}
    event_types = {event.event_type for event in case.events}

    unlicensed = "traffic.unlicensed_status" in signals or contains_fuzzy(
        text, "بدون رخصه", "بدون رخصة", "لا يحمل رخصه", "لا يحمل رخصة", "unlicensed", "no driving license", "no driving licence"
    )
    collision = "collision" in event_types or "traffic.collision" in signals
    injury = "injury" in event_types or "event.injury" in signals
    property_damage = "property_damage" in event_types
    police_statement = "procedure.police_statement" in signals
    statement_changed = "statement.changed_or_recanted" in signals
    coercion_claim = "statement.coercion_claim" in signals
    money_demand = "money_demand" in event_types or "statement.money_demand_link" in signals
    driver_identity_material = "traffic.driver_identity_material" in signals

    if unlicensed:
        missing = ["هوية من كان يقود المركبة وقت الواقعة"] if driver_identity_material else ["من كان يقود المركبة فعلياً؟"]
        missing += ["حالة رخصة السائق الفعلي وقت القيادة", "مكان وطبيعة القيادة وقت الواقعة"]
        _add(items, LegalHypothesis(
            code="traffic.unlicensed_driving",
            label_ar="قيادة دون رخصة محتملة — تتوقف على تحديد السائق الفعلي",
            domain="traffic",
            rationale=["الرواية تتضمن أن شخصاً أو أكثر لا يحمل رخصة قيادة"],
            missing_elements=missing,
            confidence=0.91,
            status="needs_clarification" if driver_identity_material else "candidate",
        ))

    if collision:
        missing = ["هوية السائق الفعلي وقت الاصطدام"] if driver_identity_material else []
        missing += ["كيفية وقوع الاصطدام وسببه الفني", "مخطط/تقرير الحادث إن وجد"]
        if injury:
            missing += ["التقرير الطبي ودرجة الإصابة", "علاقة الإصابة بالاصطدام"]
        _add(items, LegalHypothesis(
            code="traffic.collision_injury" if injury else "traffic.collision",
            label_ar="حادث سير يحتاج فحص المسؤولية والسببية" + (" والإصابة" if injury else ""),
            domain="traffic",
            rationale=["الرواية تتضمن اصطداماً مرورياً" + (" وإصابة شخص" if injury else "")],
            missing_elements=missing,
            confidence=0.88 if injury else 0.84,
            status="needs_clarification",
        ))

    if collision and (injury or property_damage):
        missing = []
        if injury:
            missing += ["التقرير الطبي والضرر المثبت للمصاب", "الرابطة السببية بين الحادث والضرر"]
        if property_damage:
            missing += ["تقدير الضرر المادي وملكية الممتلكات المتضررة", "التأمين والتقارير الفنية إن وجدت"]
        _add(items, LegalHypothesis(
            code="civil.accident_damage",
            label_ar="آثار مدنية/تعويضية محتملة عن الإصابة أو الضرر المادي",
            domain="civil",
            rationale=["الحادث يتضمن ضرراً بدنياً أو مادياً يحتاج تقديراً وإثباتاً"],
            missing_elements=missing,
            confidence=0.68,
            status="needs_clarification",
        ))

    if police_statement and statement_changed:
        _add(items, LegalHypothesis(
            code="procedure.statement_conflict",
            label_ar="تعارض أو تغير في الأقوال/الشهادة يحتاج فحصاً مستقلاً",
            domain="procedure",
            rationale=["الرواية تتضمن أقوالاً أولى ثم تغييراً/تراجعاً أو رواية لاحقة مختلفة"],
            missing_elements=[
                "النص الدقيق للأقوال الأولى ومن أدلى بها",
                "النص الدقيق للأقوال اللاحقة وتاريخها",
                "صفة كل إفادة: أقوال استدلالية أم شهادة أمام جهة قضائية",
                "الأدلة المستقلة التي تؤيد أياً من الروايتين",
            ],
            contradictions=["وجود روايتين مختلفتين حول واقعة مادية مؤثرة"],
            confidence=0.89,
            status="needs_clarification",
        ))

    if coercion_claim:
        _add(items, LegalHypothesis(
            code="procedure.statement_coercion_claim",
            label_ar="ادعاء إكراه/تهديد مرتبط بأقوال أو شهادة يحتاج تحققاً",
            domain="procedure",
            rationale=["إحدى الروايات تقول إن أقوالاً سابقة صدرت تحت تهديد أو إكراه"],
            missing_elements=[
                "من الذي يُدعى أنه هدد أو أكره الشخص؟",
                "متى وأين وكيف وقع التهديد المزعوم؟",
                "هل توجد رسائل أو تسجيلات أو شهود أو قرائن مستقلة؟",
                "ما الذي تغير تحديداً بين الإفادة الأولى واللاحقة؟",
            ],
            confidence=0.82,
            status="needs_clarification",
        ))

    if money_demand:
        _add(items, LegalHypothesis(
            code="criminal.statement_linked_money_demand",
            label_ar="طلب منفعة مالية مرتبط بأقوال/شهادة — مسألة جزائية محتملة تحتاج فحصاً",
            domain="criminal",
            rationale=["الرواية تربط طلب مبلغ مالي باستمرار شهادة أو تغيير/موقف من الأقوال"],
            missing_elements=[
                "الصياغة الدقيقة لطلب المال والشرط المرتبط به",
                "هل توجد رسائل أو تسجيلات أو شهود على الطلب؟",
                "هل تم دفع أي مبلغ أم بقي الطلب مرفوضاً؟",
                "هل كان الطلب مقابل الإدلاء بقول، الاستمرار عليه، تغييره، أو الامتناع عنه؟",
            ],
            confidence=0.72,
            status="needs_clarification",
        ))

    return sorted(items, key=lambda hypothesis: hypothesis.confidence, reverse=True)


__all__ = ["spot_issues"]
