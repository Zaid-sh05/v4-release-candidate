from app.case_analysis import generate_case_analysis_answer
from app.lawyer_case_analysis import generate_lawyer_case_analysis_answer
from app.cognition import CaseCognitionEngine
from app.cognition.language_match import contains_fuzzy, language_mix
from app.models import SourceItem
from app.routing_guard import apply_case_route, route_query


def _codes(case):
    return {h.code for h in case.hypotheses}


def _signals(case):
    return {s.code for s in case.semantic_signals}


def _source(*, sid="penal", article=None, kind="official_sync"):
    return SourceItem(
        id=sid,
        title="قانون العقوبات رقم 16 لسنة 1960 وتعديلاته" + (f" — المادة {article}" if article else ""),
        authority="جهة رسمية أردنية",
        domain="criminal",
        source_url="https://example.gov.jo/penal",
        article=article,
        excerpt=(
            "نص رسمي نظيف من قانون العقوبات يتناول أحكام السرقة والأخذ والظروف المرتبطة بطريقة وقوع الفعل."
        ),
        source_kind=kind,
        score=0.9,
    )


def test_flexible_match_handles_arabic_variants_doubling_and_english_typos():
    assert contains_fuzzy("صار في سررقة وكسروا القفل", "سرقة")
    assert contains_fuzzy("هو كسسر قفل الباب", "كسر قفل")
    assert contains_fuzzy("he brok the lock and stol the laptop", "broke")
    assert contains_fuzzy("he brok the lock and stol the laptop", "stole")
    assert contains_fuzzy("police recovred the laptop", "police recovered")
    assert language_mix("كسر lock واخذ laptop") == "mixed"


def test_arabic_typo_rich_case_still_forms_theft_and_entry_hypotheses():
    message = (
        "دخل احمد منزل خالد وكسسر قفل الباب واخذ اللابتوب و500 دينار. "
        "بعدها عثرت الشرطة على اللابتوب عنده وكاميرا مراقبة صورته قرب المنزل."
    )
    case = CaseCognitionEngine(enable_llm=False).analyze(message, "ar")
    route = apply_case_route(route_query(message, "ar"), case)

    assert "property.taking" in _signals(case)
    assert "criminal.theft" in _codes(case)
    assert "criminal.aggravating_entry" in _codes(case)
    assert route.primary_domain == "criminal"
    assert route.intent != "smalltalk"


def test_english_typo_rich_case_still_routes_and_understands_theft():
    message = (
        "He brok into the house and stol a laptop and 500 JOD. "
        "Police recovred the laptop later and a camra showd him outside the house."
    )
    raw_route = route_query(message, "en")
    assert raw_route.intent == "legal_question"
    assert raw_route.primary_domain == "criminal"

    case = CaseCognitionEngine(enable_llm=False).analyze(message, "en")
    route = apply_case_route(raw_route, case)

    assert "property.taking" in _signals(case)
    assert "criminal.theft" in _codes(case)
    assert "criminal.aggravating_entry" in _codes(case)
    assert route.primary_domain == "criminal"
    assert route.intent != "smalltalk"


def test_hi_inside_him_can_never_turn_substantive_english_case_into_smalltalk():
    message = "Police recovred the laptop and camra showd him outside after he stol it."
    route = route_query(message, "en")

    assert route.intent != "smalltalk"
    assert route.primary_domain == "criminal"


def test_real_english_smalltalk_remains_conversation():
    for message in ("Hi", "Hello there", "How are you?", "Who are you?", "Thank you"):
        route = route_query(message, "en")
        assert route.intent == "smalltalk", message
        assert route.primary_domain == "conversation", message


def test_scenario_fidelity_does_not_treat_stolen_laptop_as_person_or_cash_as_payment():
    message = (
        "دخل احمد منزل خالد وكسسر قفل الباب واخذ اللابتوب و500 دينار. "
        "بعدها عثرت الشرطة على اللابتوب عنده وكاميرا مراقبة صورته قرب المنزل."
    )
    case = CaseCognitionEngine(enable_llm=False).analyze(message, "ar")

    actor_labels = {actor.label for actor in case.actors}
    event_types = [event.event_type for event in case.events]

    assert "احمد" in actor_labels
    assert "خالد" in actor_labels
    assert "اللابتوب" not in actor_labels
    assert "payment" not in event_types
    assert "500 دينار" in case.amounts


def test_scenario_fidelity_preserves_real_payment_event():
    message = "دفعت 500 دينار عربون للشقة وحولت المبلغ للبائع"
    case = CaseCognitionEngine(enable_llm=False).analyze(message, "ar")

    assert "500 دينار" in case.amounts
    assert any(event.event_type == "payment" for event in case.events)


def test_typo_burglary_chronology_follows_user_narrative_entry_breaking_taking():
    message = "دخل احمد المنزل وكسسر القفل وبعدها اخذ اللابتوب و500 دينار"
    case = CaseCognitionEngine(enable_llm=False).analyze(message, "ar")

    event_types = [event.event_type for event in case.events]
    assert event_types.index("entry") < event_types.index("breaking") < event_types.index("taking")
    assert "payment" not in event_types


def test_arabic_case_analysis_is_structured_and_does_not_overclaim_article_407():
    message = (
        "دخل أحمد منزل خالد وكسر القفل وأخذ اللابتوب و500 دينار. "
        "عثرت الشرطة على اللابتوب معه وأظهرت كاميرا مراقبة وجوده أمام المنزل."
    )
    case = CaseCognitionEngine(enable_llm=False).analyze(message, "ar")
    route = apply_case_route(route_query(message, "ar"), case)
    route.intent = "legal_question"
    sources = [_source(article="407", kind="official_guidance")]

    answer = generate_case_analysis_answer(message, route, case, sources)

    assert answer is not None
    assert "التحليل الأولي للحالة" in answer.text
    assert "سرقة محتملة" in answer.text
    assert "الوقائع المؤثرة قانونياً" in answer.text
    assert "الأدلة/القرائن المذكورة" in answer.text
    assert "[S1]" in answer.text
    assert "لا يكفي وحده" in answer.text
    assert "لن أحدد رقم مادة أو عقوبة" in answer.text
    assert "قانون السير" not in answer.text


def test_english_case_analysis_stays_english_and_preserves_grounding_boundary():
    message = (
        "He broke into the house, stole a laptop and 500 JOD. "
        "Police recovered the laptop and CCTV showed him outside the house."
    )
    case = CaseCognitionEngine(enable_llm=False).analyze(message, "en")
    route = apply_case_route(route_query(message, "en"), case)
    route.intent = "legal_question"
    sources = [_source()]

    answer = generate_case_analysis_answer(message, route, case, sources)

    assert answer is not None
    assert "Preliminary case analysis" in answer.text
    assert "possible theft" in answer.text
    assert "Legally important facts" in answer.text
    assert "Evidence/indicators mentioned" in answer.text
    assert "[S1]" in answer.text
    assert "I will not assign an article number or penalty" in answer.text


def test_lawyer_analysis_exposes_issue_matrix_chronology_evidence_gaps_and_research_focus_ar():
    message = (
        "دخل أحمد منزل خالد وكسر القفل وأخذ اللابتوب و500 دينار. "
        "عثرت الشرطة على اللابتوب معه وأظهرت كاميرا مراقبة وجوده أمام المنزل."
    )
    case = CaseCognitionEngine(enable_llm=False).analyze(message, "ar")
    route = apply_case_route(route_query(message, "ar"), case)
    route.intent = "legal_question"

    answer = generate_lawyer_case_analysis_answer(message, route, case, [_source(article="407", kind="official_guidance")])

    assert answer is not None
    assert "التحليل الأولي للحالة" in answer.text
    assert "الوقائع المؤثرة قانونياً والتسلسل الزمني" in answer.text
    assert "المسائل القانونية التي يجب فحصها" in answer.text
    assert "ما يثيرها:" in answer.text
    assert "ما يزال جوهرياً:" in answer.text
    assert "الأدلة/القرائن المذكورة" in answer.text
    assert "لا يفترض النظام صحتها أو قبولها أو وزنها الإثباتي" in answer.text
    assert "الوقائع الجوهرية التي ما زال يلزم حسمها" in answer.text
    assert "محاور البحث القانوني التالية" in answer.text
    assert "الأساس القانوني الرسمي المسترجع" in answer.text
    assert "حدود الاستناد" in answer.text
    assert "[S1]" in answer.text


def test_lawyer_analysis_handles_noisy_english_as_substantive_case_not_conversation():
    message = (
        "He brok into the house and stol a laptop and 500 JOD. "
        "Police recovred the laptop later and a camra showd him outside the house."
    )
    route = route_query(message, "en")
    assert route.intent == "legal_question"

    case = CaseCognitionEngine(enable_llm=False).analyze(message, "en")
    route = apply_case_route(route, case)
    answer = generate_lawyer_case_analysis_answer(message, route, case, [_source(kind="official_guidance")])

    assert answer is not None
    assert "Preliminary case analysis" in answer.text
    assert "Legally important facts and chronology" in answer.text
    assert "Issues that should be tested" in answer.text
    assert "support:" in answer.text
    assert "still material:" in answer.text
    assert "Evidence/indicators mentioned" in answer.text
    assert "authenticity, admissibility and evidential weight are not assumed" in answer.text
    assert "Material facts still to resolve" in answer.text
    assert "Next legal research focus" in answer.text
    assert "Retrieved official legal basis" in answer.text
    assert "Grounding boundary" in answer.text
    assert "[S1]" in answer.text
