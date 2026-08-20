from __future__ import annotations

from app.cognition import CaseCognitionEngine
from app.lawyer_case_analysis_v4 import generate_lawyer_case_analysis_answer
from app.models import SourceItem
from app.routing_guard import apply_case_route, route_query


COMPLEX_TRAFFIC_STATEMENTS = (
    "خرج شابان ليلا في سيارة والد أحدهما وكان كلاهما لا يحمل رخصة قيادة. أثناء السير ارتطمت السيارة "
    "بالجزيرة الوسطية وتضررت المركبة واصطدمت أيضا بعمود كهربائي. لم يصب الأول بشيء وجرح وجه الثاني "
    "جرحا صغيرا. بعد ذلك عاد الأول مع والده إلى موقع الحادث مع وصول الشرطة، وأخبرهم الأب أنه هو من كان "
    "يقود المركبة، وتم أخذ أقواله وشهد المصاب أن الأب هو السائق. بعد يوم طلب المصاب مبلغا ماليا من الأب "
    "مقابل الشهادة فرفض الأب، ثم ذهب المصاب إلى المركز الأمني وقال إن شهادته الأولى كانت تحت التهديد."
)


def analyze(text: str, language: str = "ar"):
    case = CaseCognitionEngine().analyze(text, language)
    route = route_query(text, language, None)
    route = apply_case_route(route, case, None)
    return case, route


def codes(case) -> set[str]:
    return {hypothesis.code for hypothesis in case.hypotheses}


def event_types(case) -> list[str]:
    return [event.event_type for event in case.events]


def signal_codes(case) -> set[str]:
    return {signal.code for signal in case.semantic_signals}


def actor_labels(case) -> set[str]:
    return {actor.label.strip() for actor in case.actors}


def assert_grounded(case, source_text: str) -> None:
    for actor in case.actors:
        if actor.support_span:
            assert actor.support_span in source_text
    for event in case.events:
        if event.support_span:
            assert event.support_span in source_text
    for evidence in case.evidence:
        if evidence.support_span:
            assert evidence.support_span in source_text


def test_realistic_complex_traffic_statement_case_is_multi_issue_not_fake_theft():
    case, route = analyze(COMPLEX_TRAFFIC_STATEMENTS)
    issue_codes = codes(case)
    events = event_types(case)
    signals = signal_codes(case)

    assert route.primary_domain == "traffic"
    assert route.domains[:4] == ["traffic", "procedure", "criminal", "civil"]
    assert {
        "traffic.unlicensed_driving",
        "traffic.collision_injury",
        "civil.accident_damage",
        "procedure.statement_conflict",
        "procedure.statement_coercion_claim",
        "criminal.statement_linked_money_demand",
    }.issubset(issue_codes)
    assert "criminal.theft" not in issue_codes
    assert "taking" not in events
    assert "payment" not in events
    assert {"collision", "property_damage", "statement", "money_demand", "injury"}.issubset(set(events))
    assert {
        "traffic.unlicensed_status",
        "procedure.police_statement",
        "statement.changed_or_recanted",
        "statement.coercion_claim",
        "traffic.driver_identity_material",
    }.issubset(signals)
    assert case.procedural_posture == "investigation"

    forbidden = {"ايضا", "أيضا", "انه", "إنه", "اقواله", "أقواله", "شهادته", "لاخبار", "لإخبار"}
    assert not (actor_labels(case) & forbidden)
    assert_grounded(case, COMPLEX_TRAFFIC_STATEMENTS)


def test_taking_a_police_statement_never_becomes_property_theft():
    text = "وصلت الشرطة وتم أخذ أقوالي في المركز الأمني ثم وقعت على الإفادة."
    case, _ = analyze(text)
    assert "criminal.theft" not in codes(case)
    assert "taking" not in event_types(case)
    assert "property.taking" not in signal_codes(case)


def test_real_theft_survives_even_when_police_also_take_statements():
    text = "سرق شخص هاتفي من السيارة، وبعدها حضرت الشرطة وتم أخذ أقوالي في المركز الأمني."
    case, route = analyze(text)
    assert route.primary_domain == "criminal"
    assert "criminal.theft" in codes(case)
    assert "taking" in event_types(case)
    assert "procedure.police_statement" in signal_codes(case)


def test_money_request_is_not_a_completed_payment():
    text = "طلب الشاهد مني 500 دينار مقابل أن يبقى على نفس الشهادة لكني رفضت ولم أدفع له شيئا."
    case, _ = analyze(text)
    assert "money_demand" in event_types(case)
    assert "payment" not in event_types(case)
    assert "criminal.statement_linked_money_demand" in codes(case)
    assert "criminal.theft" not in codes(case)


def test_actual_transfer_remains_a_payment_event():
    text = "بعد أن هددني على واتساب حولت له 500 دينار عن طريق البنك."
    case, route = analyze(text)
    assert route.primary_domain == "cyber"
    assert "threat" in event_types(case)
    assert "payment" in event_types(case)


def test_simple_unlicensed_injury_collision_spots_traffic_and_civil_tracks():
    text = "كنت بسوق بدون رخصة وصدمت الرصيف وانصاب الشخص اللي كان راكب معي وتضررت السيارة."
    case, route = analyze(text)
    assert route.primary_domain == "traffic"
    assert "traffic.unlicensed_driving" in codes(case)
    assert "traffic.collision_injury" in codes(case)
    assert "civil.accident_damage" in codes(case)
    assert {"collision", "injury", "property_damage"}.issubset(set(event_types(case)))


def test_changed_statement_and_coercion_remain_allegations_not_proven_truth():
    text = (
        "شهد الشخص أمام الشرطة أن الأب كان السائق، ثم رجع عن شهادته وقال إن شهادته الأولى كانت تحت التهديد."
    )
    case, route = analyze(text)
    assert "procedure" in route.domains
    assert "procedure.statement_conflict" in codes(case)
    assert "procedure.statement_coercion_claim" in codes(case)
    assert any(fact.disputed for fact in case.facts)


def test_cyber_blackmail_does_not_leak_unrelated_general_criminal_issue():
    text = "شخص على فيسبوك هدد ينشر صوري الخاصة إذا ما حولت له مبلغ مالي."
    case, route = analyze(text)
    assert route.domains[:2] == ["cyber", "criminal"]
    assert "threat" in event_types(case)
    assert "criminal.theft" not in codes(case)


def test_noisy_bilingual_property_case_still_reaches_criminal_cognition():
    text = "He brok the lok ودخل البيت وبعدين stol اللابتوب، والcamra صورت him عند الباب."
    case, route = analyze(text, "en")
    assert route.primary_domain == "criminal"
    assert "criminal.theft" in codes(case)
    assert {"entry", "breaking", "taking"}.issubset(set(event_types(case)))


def test_denial_and_police_allegation_do_not_become_a_guilt_finding():
    text = "الشرطة بتقول إني سرقت التلفون لكن أنا بنكر، والدليل شاهد قال إنه شافني قريب من المكان."
    case, route = analyze(text)
    assert route.primary_domain == "criminal"
    assert "criminal.theft" in codes(case)
    assert any(fact.disputed for fact in case.facts)
    assert case.decision is not None


def test_complex_case_answer_surfaces_conflicts_investigation_and_research_limits():
    case, route = analyze(COMPLEX_TRAFFIC_STATEMENTS)
    sources = [
        SourceItem(
            id="traffic-source",
            title="قانون السير — نص رسمي قابل للقراءة",
            authority="جهة رسمية أردنية",
            domain="traffic",
            source_url="https://example.gov.jo/traffic",
            article="31",
            excerpt="نص رسمي مقروء يتعلق بقيادة المركبات والرخص والالتزامات المرورية.",
            source_kind="canonical_verified",
            score=10,
        ),
        SourceItem(
            id="procedure-source",
            title="نص إجرائي رسمي متعلق بالأقوال والتحقيق",
            authority="جهة رسمية أردنية",
            domain="procedure",
            source_url="https://example.gov.jo/procedure",
            excerpt="نص رسمي مقروء يتعلق بالإجراءات والأقوال أمام الجهات المختصة.",
            source_kind="canonical_verified",
            score=9,
        ),
        SourceItem(
            id="criminal-source",
            title="قانون العقوبات — نص رسمي قابل للقراءة",
            authority="جهة رسمية أردنية",
            domain="criminal",
            source_url="https://example.gov.jo/criminal",
            excerpt="نص جزائي رسمي مقروء يحتاج مطابقة دقيقة للوقائع قبل اختيار المادة.",
            source_kind="canonical_verified",
            score=8,
        ),
    ]

    answer = generate_lawyer_case_analysis_answer(COMPLEX_TRAFFIC_STATEMENTS, route, case, sources)
    assert answer is not None
    text = answer.text
    assert "مرحلة تحقيق/استدلال" in text
    assert "قيادة دون رخصة" in text
    assert "تعارض أو تغير في الأقوال" in text
    assert "ادعاء إكراه/تهديد" in text
    assert "طلب منفعة مالية" in text
    assert "محاور البحث القانوني التالية" in text
    assert "حدود الاستناد" in text
    assert "سرقة محتملة" not in text
    assert "أخذ أو استيلاء على مال/منقول" not in text


def test_complex_case_english_presenter_has_equivalent_issue_language():
    text = (
        "Two cousins were in a car at night and neither had a driving license. The car crashed into the median, "
        "one passenger was injured and the car was damaged. At the police station the father said he was driving. "
        "The passenger first supported that statement, later changed his statement, claimed he was under threat, "
        "and had asked the father for money in exchange for keeping the testimony."
    )
    case, route = analyze(text, "en")
    sources = [
        SourceItem(
            id="traffic-en",
            title="Official traffic-law source",
            authority="Jordanian official source",
            domain="traffic",
            source_url="https://example.gov.jo/traffic-en",
            excerpt="Readable official traffic-law text about driving and licensing.",
            source_kind="canonical_verified",
            score=10,
        )
    ]
    answer = generate_lawyer_case_analysis_answer(text, route, case, sources)
    assert answer is not None
    rendered = answer.text.lower()
    assert "unlicensed driving" in rendered
    assert "conflicting or changed statements" in rendered
    assert "threat or coercion" in rendered
    assert "grounding boundary" in rendered
