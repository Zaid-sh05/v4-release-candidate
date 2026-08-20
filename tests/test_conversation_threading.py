from app.chat import _guard_sources
from app.context import contextualize_message
from app.models import SourceItem
from app.router import analyze_query
from app.text import looks_garbled_text


BURGLARY = (
    "قام أحمد بالدخول إلى منزل جاره خالد أثناء غيابه، بعد أن كسر قفل الباب الخارجي. "
    "أخذ جهاز حاسوب محمول ومبلغا نقديا مقداره 500 دينار، ثم غادر المكان. "
    "لاحقا عثرت الشرطة على الحاسوب في منزل أحمد، وأظهرت كاميرا مراقبة وجوده أمام منزل خالد."
)

BURGLARY_CLARIFY = (
    "قبل التكييف النهائي أو تحديد العقوبة، قد يلزم حسم النقاط التالية: "
    "هل كان الدخول دون إذن؟ هل وقع ليلاً؟ هل كان المكان مسكوناً؟ ملكية المال؟ رضا المالك من عدمه؟"
)

BURGLARY_FOLLOWUP = (
    "من غير اذن. لا لم يقع ليلا. والمكان مسكون لكن اهله ذهبوا لقضاء امورهم. "
    "المال لخالد والمالك لم يوافق."
)


def test_clarification_answers_are_joined_to_the_active_burglary_case():
    history = [
        {"role": "user", "content": BURGLARY},
        {"role": "assistant", "content": BURGLARY_CLARIFY},
    ]
    route = analyze_query(BURGLARY_FOLLOWUP, "ar")
    effective, used = contextualize_message(BURGLARY_FOLLOWUP, history, route)

    assert used is True
    assert BURGLARY in effective
    assert BURGLARY_FOLLOWUP in effective
    assert "نفس القضية" in effective


def test_new_traffic_case_does_not_inherit_previous_cyber_case():
    cyber = "تعرضت لابتزاز على فيسبوك، شو أعمل؟"
    traffic = "كنت بسوق وصار حادث وانصاب شخص كان راكب معي وانا لا احمل رخصة، شو وضعي؟"
    history = [
        {"role": "user", "content": cyber},
        {"role": "assistant", "content": "يمكنك الإبلاغ لوحدة مكافحة الجرائم الإلكترونية."},
    ]
    route = analyze_query(traffic, "ar")
    effective, used = contextualize_message(traffic, history, route)

    assert used is False
    assert effective == traffic
    assert cyber not in effective


def test_explicit_domain_correction_keeps_same_case_context():
    cyber_story = (
        "قام احمد بتهديد سارة بأنه سوف ينشر صور سارة على مواقع التواصل الاجتماعي بغير اذنها "
        "اذا لم تحول له مبلغ مالي"
    )
    correction = "انا بسال عن جرائم الكترونية"
    history = [
        {"role": "user", "content": cyber_story},
        {"role": "assistant", "content": "جواب غير مناسب من مجال آخر"},
    ]
    route = analyze_query(correction, "ar")
    effective, used = contextualize_message(correction, history, route)

    assert used is True
    assert cyber_story in effective
    assert correction in effective


def test_broken_traffic_pdf_extraction_is_rejected():
    broken = (
        "المادة )31( غرامﺔ ﻻ تقل ᗷ شهر أوᣢد عᗫᖂ وﻻ تᡧ ᢕᣌس مدة ﻻ تقل عن أسبوع "
        "مرخصﺔ ᢕᣂﺔ غᘘ مرك ᣢب عᗫب أو التدرᗫــــح تدرᗫ ᣆ تᣢب السواقﺔ دون الحصول عᗫتدر"
    )
    assert looks_garbled_text(broken) is True
    assert looks_garbled_text("المادة 31: يعاقب من يقود مركبة دون رخصة وفق الشروط المبينة في القانون.") is False
    assert looks_garbled_text("Article 31 sets out the applicable traffic-law rule in readable official text.") is False


def test_cyber_primary_domain_cannot_be_displaced_by_generic_criminal_article():
    message = "قام بتهديدي على فيسبوك بنشر صوري اذا لم ادفع له مبلغ مالي"
    route = analyze_query(message, "ar")
    assert route.primary_domain == "cyber"

    cyber = SourceItem(
        id="cyber18",
        title="قانون الجرائم الإلكترونية رقم 17 لسنة 2023 — المادة 18",
        authority="جهة رسمية أردنية",
        domain="cyber",
        source_url="https://example.gov.jo/cyber",
        article="18",
        excerpt="يعالج النص الرسمي الابتزاز أو التهديد المرتبط باستخدام نظام معلومات أو منصة تواصل اجتماعي.",
        source_kind="canonical_verified",
        score=7.0,
    )
    unrelated = SourceItem(
        id="penal282",
        title="قانون العقوبات — المادة 282",
        authority="جهة رسمية أردنية",
        domain="criminal",
        source_url="https://example.gov.jo/penal",
        article="282",
        excerpt="نص جزائي عام لا يتعلق بواقعة الابتزاز الإلكتروني محل السؤال.",
        source_kind="canonical_verified",
        score=99.0,
    )

    guarded = _guard_sources(route, [unrelated, cyber])
    assert [s.id for s in guarded] == ["cyber18"]


def test_short_new_case_after_completed_answer_does_not_inherit_prior_case():
    # Real production defect: a short, dialect-heavy new case (no legal keywords the
    # lightweight router recognizes) following a COMPLETED prior answer was silently
    # merged into that unrelated prior case, because the router's low-confidence/general
    # classification was (wrongly) treated as evidence of being a followup to it. The
    # fallback must require that the assistant actually asked something.
    labor_case = "فصلني صاحب العمل من شغلي بدون سبب واضح وبدون انذار مسبق وانا موظف عنده من ثلاث سنين"
    history = [
        {"role": "user", "content": labor_case},
        {"role": "assistant", "content": "يمكن أن يشكل هذا فصلاً تعسفياً بحسب قانون العمل."},
    ]
    for new_case in ("سرق مني حدا موبايلي", "بنتي تعبانة ونفقتها علي"):
        route = analyze_query(new_case, "ar")
        effective, used = contextualize_message(new_case, history, route)
        assert used is False, f"{new_case!r} wrongly inherited the prior labor case: {effective!r}"
        assert effective == new_case


def test_short_answer_to_an_actual_clarifying_question_still_merges():
    # The fallback above must not become so strict that it breaks the real use case:
    # a short, lexically-unrecognized answer to a genuine open clarifying question.
    labor_case = "فصلني صاحب العمل من شغلي بدون سبب واضح"
    history = [
        {"role": "user", "content": labor_case},
        {"role": "assistant", "content": "قبل تحديد التكييف: هل كان الفصل بسبب ضعف الأداء؟ متى صار ذلك؟"},
    ]
    followup = "مش بسبب ضعف الاداء، صار الشهر الماضي"
    route = analyze_query(followup, "ar")
    effective, used = contextualize_message(followup, history, route)
    assert used is True
    assert labor_case in effective


def test_garbled_source_is_removed_even_when_domain_is_correct():
    route = analyze_query("كنت بسوق وصار حادث وانا لا احمل رخصة", "ar")
    bad = SourceItem(
        id="traffic31-bad",
        title="قانون السير — المادة 31",
        authority="جهة رسمية أردنية",
        domain="traffic",
        source_url="https://example.gov.jo/traffic",
        article="31",
        excerpt="المادة 31 غرامﺔ ᗷ شهر ᣢد عᗫᖂ وﻻ تᡧ ᢕᣌس مرخصﺔ ᢕᣂﺔ غᘘ مرك",
        source_kind="official_sync",
        score=10.0,
    )
    assert _guard_sources(route, [bad]) == []
