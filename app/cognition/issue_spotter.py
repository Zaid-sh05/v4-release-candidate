from __future__ import annotations

import re

from .models import CaseModel, LegalHypothesis


_ARABIC_DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")


def _normalize(text: str) -> str:
    text = _ARABIC_DIACRITICS_RE.sub("", text.lower())
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
    """Generate competing legal hypotheses from facts without deciding guilt.

    This module intentionally produces candidates. Final legal characterization must
    be based on verified Jordanian legal sources plus the facts needed for each element.
    """
    text = " ".join([case.raw_message] + [f.text for f in case.facts])
    hypotheses: list[LegalHypothesis] = []

    if _contains(text, "قتل", "توفى", "توفي", "مات", "وفاة"):
        intentional_markers = _contains(text, "قصداً", "قصدا", "متعمد", "عمد", "خطط", "سبق الإصرار", "سبق الاصرار")
        accidental_markers = _contains(text, "بالغلط", "خطأ", "حادث", "دون قصد", "غير مقصود")
        self_defense_markers = _contains(text, "دفاع", "دافع عن", "هاجمه", "اعتدى عليه")

        hypotheses.append(LegalHypothesis(
            code="criminal.intentional_homicide",
            label_ar="قتل قصدي/عمد محتمل",
            domain="criminal",
            rationale=["وجود وفاة أو قتل ضمن الوقائع"],
            missing_elements=[] if intentional_markers else ["طبيعة القصد وقت الفعل", "كيفية وقوع الفعل والأداة والظروف"],
            contradictions=["وجود وصف صريح بأن الواقعة كانت خطأ"] if accidental_markers else [],
            confidence=0.78 if intentional_markers else 0.42,
            status="candidate" if intentional_markers else "needs_clarification",
        ))
        hypotheses.append(LegalHypothesis(
            code="criminal.unintentional_death",
            label_ar="تسبب بالوفاة/قتل غير مقصود محتمل",
            domain="criminal",
            rationale=["يجب استبعاد أو إثبات القصد قبل التكييف النهائي"],
            missing_elements=[] if accidental_markers else ["هل أراد الفاعل إحداث الوفاة أو الأذى؟", "هل وقع إهمال أو رعونة أو مخالفة واجب؟"],
            contradictions=["وجود تخطيط أو سبق إصرار ظاهر"] if intentional_markers else [],
            confidence=0.78 if accidental_markers else 0.35,
            status="candidate" if accidental_markers else "needs_clarification",
        ))
        if self_defense_markers:
            hypotheses.append(LegalHypothesis(
                code="criminal.self_defense",
                label_ar="دفاع شرعي محتمل",
                domain="criminal",
                rationale=["الوقائع تتضمن اعتداءً أو دفاعاً عن النفس"],
                missing_elements=["هل كان الخطر حالاً؟", "هل كان الرد لازماً ومتناسباً؟"],
                confidence=0.60,
                status="needs_clarification",
            ))

    if _contains(text, "سرق", "سرقة", "أخذ", "اخذ"):
        hypotheses.append(LegalHypothesis(
            code="criminal.theft",
            label_ar="سرقة محتملة",
            domain="criminal",
            rationale=["وجود استيلاء مذكور على مال أو شيء منقول"],
            missing_elements=["ملكية المال", "رضا المالك من عدمه", "قصد التملك"],
            confidence=0.58,
            status="needs_clarification",
        ))

    if _contains(text, "كسر الباب", "كسر قفل", "خلع", "تسلق", "دخل البيت", "دخل المنزل", "الدخول إلى منزل", "الدخول الى منزل"):
        hypotheses.append(LegalHypothesis(
            code="criminal.aggravating_entry",
            label_ar="دخول/كسر قد يشكل ظرفاً قانونياً مؤثراً",
            domain="criminal",
            rationale=["طريقة الدخول قد تغيّر التكييف أو العقوبة"],
            missing_elements=["هل كان الدخول دون إذن؟", "هل وقع ليلاً؟", "هل كان المكان مسكوناً؟"],
            confidence=0.64,
            status="needs_clarification",
        ))

    if _contains(text, "فصلني", "طردني", "انهاء عقد", "إنهاء عقد"):
        hypotheses.append(LegalHypothesis(
            code="labor.termination",
            label_ar="إنهاء علاقة العمل",
            domain="labor",
            rationale=["المستخدم يصف إنهاء علاقة عمل"],
            missing_elements=["نوع العقد", "مدة الخدمة", "سبب الإنهاء", "وجود إشعار خطي"],
            confidence=0.84,
            status="needs_clarification",
        ))

    if _contains(text, "استئناف", "استأنف", "أستأنف", "استانف", "مستأنف", "اطعن", "طعن", "تمييز"):
        hypotheses.append(LegalHypothesis(
            code="procedure.appeal",
            label_ar="طريق طعن أو استئناف",
            domain="procedure",
            rationale=["المستخدم يسأل عن مراجعة حكم أو قرار"],
            missing_elements=["نوع المحكمة", "نوع القضية", "وصف الحكم: وجاهي/غيابي/بمثابة الوجاهي", "تاريخ الصدور أو التبليغ"],
            confidence=0.86,
            status="needs_clarification",
        ))

    return sorted(hypotheses, key=lambda h: h.confidence, reverse=True)
