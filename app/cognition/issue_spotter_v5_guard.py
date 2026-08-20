from __future__ import annotations

from .issue_spotter_v5 import spot_issues as base_spot_issues
from .language_match import normalize_flexible
from .models import CaseModel, LegalHypothesis


def _add(items: list[LegalHypothesis], hypothesis: LegalHypothesis) -> None:
    if any(item.code == hypothesis.code for item in items):
        return
    items.append(hypothesis)


def spot_issues(case: CaseModel) -> list[LegalHypothesis]:
    """Semantic guards for dialectal employment wording and family-law 'taking' language."""
    items = list(base_spot_issues(case))
    n = normalize_flexible(case.raw_message or "")

    # Jordanian/Levantine users commonly say "ما دفعوا راتبي" or "ما قبضت راتبي". Exact phrase
    # matching is brittle because the employer may be plural or implicit, so anchor on the wage
    # object plus a non-payment predicate instead.
    employment = any(term in n for term in ("موظف", "عامل", "صاحب العمل", "الشركه", "شركة", "employer", "employee"))
    wage_object = any(term in n for term in ("راتب", "اجر", "أجر", "salary", "wage"))
    nonpayment = any(term in n for term in (
        "ما دفع", "لم يدفع", "ما قبض", "لم اقبض", "لم أقبض", "متاخر", "متأخر",
        "غير مدفوع", "حجز راتب", "withheld", "unpaid", "not paid",
    ))
    if employment and wage_object and nonpayment:
        _add(items, LegalHypothesis(
            code="labor.unpaid_wages",
            label_ar="مطالبة محتملة بأجر/راتب غير مدفوع",
            domain="labor",
            rationale=["الرواية تتضمن أجراً أو راتباً يدعي العامل أنه لم يُدفع"],
            missing_elements=[
                "الفترة التي لم يُدفع عنها الأجر",
                "مقدار الأجر المتفق عليه وطريقة إثباته",
                "كشوف الرواتب/التحويلات البنكية أو أي إيصالات",
                "هل انتهت علاقة العمل أم ما زالت قائمة؟",
            ],
            confidence=0.90,
            status="needs_clarification",
        ))

    # "أخذ الأولاد" in a custody/contact dispute describes physical custody/control of children,
    # not taking movable property. Remove the legacy theft hypothesis unless an independent explicit
    # property-taking marker remains in the same narrative.
    child_context = any(term in n for term in (
        "الاولاد", "الأولاد", "الاطفال", "الأطفال", "ابني", "ابنتي", "طفلي", "حضانة", "حضانه",
        "custody", "children", "child",
    ))
    custody_context = child_context and any(term in n for term in (
        "حضانة", "حضانه", "مشاهده", "مشاهدة", "رؤيت", "اخذ الاولاد", "أخذ الأولاد",
        "custody", "visitation", "access",
    ))
    explicit_property = any(term in n for term in (
        "سرق", "سرقه", "سرقة", "استولى على المال", "استولى على الهاتف", "استولى على جهاز",
        "اخذ المال", "أخذ المال", "اخذ الهاتف", "أخذ الهاتف", "اخذ اللابتوب", "أخذ اللابتوب",
        "stole", "theft", "took the money", "took the phone", "took the laptop",
    ))
    if custody_context and not explicit_property:
        items = [item for item in items if item.code != "criminal.theft"]

    return sorted(items, key=lambda hypothesis: hypothesis.confidence, reverse=True)


__all__ = ["spot_issues"]
