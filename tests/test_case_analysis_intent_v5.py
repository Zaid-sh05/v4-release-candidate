from __future__ import annotations

from app.routing_guard_v5 import route_query


def test_explicit_arabic_case_analysis_overrides_incidental_rights_terms():
    route = route_query(
        "أنا موظف وما دفعوا راتبي وبشتغل أوفر تايم. حلل الحالة قانونياً بدون افتراض النتيجة.",
        "ar",
        None,
    )
    assert route.primary_domain == "labor"
    assert route.intent == "legal_question"


def test_direct_arabic_rights_question_remains_rights_intent():
    route = route_query("فصلني صاحب العمل بدون إنذار، شو حقوقي؟", "ar", None)
    assert route.primary_domain == "labor"
    assert route.intent == "rights"


def test_explicit_english_case_analysis_overrides_incidental_rights_terms():
    route = route_query(
        "My employer did not pay my salary and requires overtime. Analyze the issues and missing facts.",
        "en",
        None,
    )
    assert route.primary_domain == "labor"
    assert route.intent == "legal_question"
