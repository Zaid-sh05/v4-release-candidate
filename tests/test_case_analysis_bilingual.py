from app.case_analysis import generate_case_analysis_answer
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


def test_english_typo_rich_case_still_routes_and_understands_theft():
    message = (
        "He brok into the house and stol a laptop and 500 JOD. "
        "Police recovred the laptop later and a camra showd him outside the house."
    )
    case = CaseCognitionEngine(enable_llm=False).analyze(message, "en")
    route = apply_case_route(route_query(message, "en"), case)

    assert "property.taking" in _signals(case)
    assert "criminal.theft" in _codes(case)
    assert "criminal.aggravating_entry" in _codes(case)
    assert route.primary_domain == "criminal"


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
