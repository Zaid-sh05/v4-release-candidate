from __future__ import annotations

import re

from .models import CaseModel, LegalHypothesis


_ARABIC_DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")


def _normalize(text: str) -> str:
    text = _ARABIC_DIACRITICS_RE.sub("", (text or "").lower())
    return (
        text.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ٱ", "ا")
        .replace("ى", "ي")
        .replace("ؤ", "و")
    )


def _contains(text: str, *terms: str) -> bool:
    low = _normalize(text)
    return any(_normalize(term) in low for term in terms)


def spot_issues(case: CaseModel) -> list[LegalHypothesis]:
    """Generate competing legal hypotheses without deciding guilt or liability.

    Grounded LLM semantic signals may improve language understanding, but they remain
    linguistic indicators. Final legal characterization still requires verified law.
    """
    text = " ".join([case.raw_message] + [f.text for f in case.facts])
    hypotheses: list[LegalHypothesis] = []
    signals = {signal.code for signal in case.semantic_signals}
    event_types = {event.event_type for event in case.events}
    event_intents = {event.intent for event in case.events if event.intent != "unknown"}

    death_present = (
        "death" in event_types
        or "event.death" in signals
        or _contains(text, "قتل", "توفى", "توفي", "مات", "وفاة")
    )

    # Keep intent hypotheses distinct. A bare substring such as "عمد" must not turn
    # "دون أن أتعمد" into evidence of intentional homicide. Explicit negation of
    # death intent should instead make the unintentional hypothesis stronger while
    # preserving intentional homicide as a weaker competing hypothesis.
    premeditated_markers = (
        "premeditated" in event_intents
        or "intent.premeditated" in signals
        or _contains(text, "خطط", "سبق الإصرار", "سبق الاصرار", "انتظر لقتله", "حضّر لقتله", "حضر لقتله")
    )
    explicit_non_intent = (
        "accidental" in event_intents
        or "intent.accidental" in signals
        or _contains(
            text,
            "بالغلط",
            "خطأ",
            "حادث",
            "دون قصد",
            "بدون قصد",
            "غير مقصود",
            "دون أن أتعمد",
            "دون ان اتعمد",
            "لم أقصد",
            "لم اقصد",
            "ما كنت أقصد",
            "ما كنت اقصد",
            "ما قصدت",
            "لم أتعمد",
            "لم اتعمد",
        )
    )
    affirmative_intent = (
        "intentional" in event_intents
        or "intent.intentional" in signals
        or _contains(
            text,
            "قصداً",
            "قصدا",
            "عمداً",
            "عمدا",
            "قتل عمد",
            "متعمد",
            "تعمد قتله",
            "قاصداً قتله",
            "قاصدا قتله",
        )
    )
    intentional_markers = premeditated_markers or affirmative_intent
    accidental_markers = explicit_non_intent

    self_defense_markers = (
        "self_defense_claim" in event_intents
        or "intent.self_defense_claim" in signals
        or _contains(text, "دفاع", "دافع عن", "هاجمه", "اعتدى عليه")
    )

    if death_present:
        if premeditated_markers:
            intentional_confidence = 0.92
            unintentional_confidence = 0.20
        elif intentional_markers and accidental_markers:
            # Mixed evidence can happen when the user intended an assault but explicitly
            # denied intending the death. Do not collapse that into a final legal finding.
            intentional_confidence = 0.58
            unintentional_confidence = 0.74
        elif intentional_markers:
            intentional_confidence = 0.82
            unintentional_confidence = 0.30
        elif accidental_markers:
            intentional_confidence = 0.30
            unintentional_confidence = 0.84
        else:
            intentional_confidence = 0.42
            unintentional_confidence = 0.35

        hypotheses.append(LegalHypothesis(
            code="criminal.intentional_homicide",
            label_ar="قتل قصدي/عمد محتمل",
            domain="criminal",
            rationale=["وجود وفاة أو قتل ضمن الوقائع"],
            missing_elements=[] if intentional_markers else ["طبيعة القصد وقت الفعل", "كيفية وقوع الفعل والأداة والظروف"],
            contradictions=["وجود وصف أو إشارة بأن الواقعة غير مقصودة"] if accidental_markers else [],
            confidence=intentional_confidence,
            status="candidate" if intentional_confidence >= 0.65 else "needs_clarification",
        ))
        hypotheses.append(LegalHypothesis(
            code="criminal.unintentional_death",
            label_ar="تسبب بالوفاة/وفاة غير مقصودة محتملة",
            domain="criminal",
            rationale=["يجب استبعاد أو إثبات القصد قبل التكييف النهائي"],
            missing_elements=[] if accidental_markers else ["هل أراد الفاعل إحداث الوفاة أو الأذى؟", "هل وقع إهمال أو رعونة أو مخالفة واجب؟"],
            contradictions=["وجود تخطيط أو قصد ظاهر"] if intentional_markers else [],
            confidence=unintentional_confidence,
            status="candidate" if unintentional_confidence >= 0.65 else "needs_clarification",
        ))
        if self_defense_markers:
            hypotheses.append(LegalHypothesis(
                code="criminal.self_defense",
                label_ar="دفاع شرعي محتمل",
                domain="criminal",
                rationale=["الوقائع تتضمن ادعاء دفاع أو اعتداء سابق"],
                missing_elements=["هل كان الخطر حالاً؟", "هل كان الرد لازماً ومتناسباً؟"],
                confidence=0.62,
                status="needs_clarification",
            ))

    taking_present = (
        "taking" in event_types
        or "property.taking" in signals
        or _contains(text, "سرق", "سرقة", "أخذ", "اخذ")
    )
    if taking_present:
        hypotheses.append(LegalHypothesis(
            code="criminal.theft",
            label_ar="سرقة محتملة",
            domain="criminal",
            rationale=["وجود استيلاء مذكور على مال أو شيء منقول"],
            missing_elements=["ملكية المال", "رضا المالك من عدمه", "قصد التملك"],
            confidence=0.60,
            status="needs_clarification",
        ))

    entry_present = "entry" in event_types
    breaking_present = "breaking" in event_types
    if (
        (entry_present and breaking_present)
        or _contains(text, "كسر الباب", "كسر قفل", "خلع", "تسلق", "دخل البيت", "دخل المنزل", "الدخول إلى منزل", "الدخول الى منزل")
    ):
        hypotheses.append(LegalHypothesis(
            code="criminal.aggravating_entry",
            label_ar="دخول/كسر قد يشكل ظرفاً قانونياً مؤثراً",
            domain="criminal",
            rationale=["طريقة الدخول قد تغيّر التكييف أو العقوبة"],
            missing_elements=["هل كان الدخول دون إذن؟", "هل وقع ليلاً؟", "هل كان المكان مسكوناً؟"],
            confidence=0.66,
            status="needs_clarification",
        ))

    termination_present = (
        "termination" in event_types
        or "employment.termination" in signals
        or _contains(text, "فصلني", "طردني", "انهاء عقد", "إنهاء عقد")
    )
    if termination_present:
        hypotheses.append(LegalHypothesis(
            code="labor.termination",
            label_ar="إنهاء علاقة العمل",
            domain="labor",
            rationale=["المستخدم يصف إنهاء علاقة عمل"],
            missing_elements=["نوع العقد", "مدة الخدمة", "سبب الإنهاء", "وجود إشعار خطي"],
            confidence=0.84,
            status="needs_clarification",
        ))

    appeal_present = (
        case.user_goal == "appeal"
        or "goal.appeal" in signals
        or _contains(text, "استئناف", "استأنف", "أستأنف", "استانف", "مستأنف", "اطعن", "طعن", "تمييز")
    )
    if appeal_present:
        hypotheses.append(LegalHypothesis(
            code="procedure.appeal",
            label_ar="طريق طعن أو استئناف",
            domain="procedure",
            rationale=["المستخدم يسأل عن مراجعة حكم أو قرار"],
            missing_elements=["نوع المحكمة", "نوع القضية", "وصف الحكم: وجاهي/غيابي/بمثابة الوجاهي", "تاريخ الصدور أو التبليغ"],
            confidence=0.88,
            status="needs_clarification",
        ))

    return sorted(hypotheses, key=lambda h: h.confidence, reverse=True)
