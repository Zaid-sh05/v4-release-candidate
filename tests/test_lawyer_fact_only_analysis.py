from app.cognition import CaseCognitionEngine
from app.lawyer_case_analysis_v4 import generate_lawyer_case_analysis_answer
from app.routing_guard import apply_case_route, route_query


CASE = (
    "خرج شابان ليلا في سيارة وكان كلاهما لا يحمل رخصة قيادة. ارتطمت السيارة بالجزيرة الوسطية "
    "وتضررت وانصاب أحدهما. أمام الشرطة قال الأب إنه كان يقود، ثم تغيرت شهادة المصاب وقال إن شهادته "
    "الأولى كانت تحت التهديد، وكان قد طلب مبلغا ماليا مقابل الشهادة."
)


def test_fact_issue_analysis_survives_empty_legal_retrieval_without_inventing_law():
    case = CaseCognitionEngine().analyze(CASE, "ar")
    route = apply_case_route(route_query(CASE, "ar", None), case, None)

    answer = generate_lawyer_case_analysis_answer(CASE, route, case, [])

    assert answer is not None
    text = answer.text
    assert "التحليل الأولي للحالة" in text
    assert "قيادة دون رخصة" in text
    assert "تعارض أو تغير في الأقوال" in text
    assert "محاور البحث القانوني التالية" in text
    assert "لم يُسترجع نص رسمي مقروء ومحدد بما يكفي" in text
    assert "حدود الاستناد" in text
    assert "سرقة محتملة" not in text
    assert "المادة 31" not in text
    assert "الحبس" not in text
    assert "غرامة" not in text


def test_fact_only_english_analysis_preserves_grounding_boundary():
    text = (
        "Two people were in a car and neither had a driving license. The car crashed and one passenger was injured. "
        "At the police station the father said he was driving. The passenger later changed his statement and claimed "
        "the first statement was under threat."
    )
    case = CaseCognitionEngine().analyze(text, "en")
    route = apply_case_route(route_query(text, "en", None), case, None)

    answer = generate_lawyer_case_analysis_answer(text, route, case, [])

    assert answer is not None
    rendered = answer.text.lower()
    assert "preliminary case analysis" in rendered
    assert "unlicensed driving" in rendered
    assert "conflicting or changed statements" in rendered
    assert "no sufficiently specific readable official provision" in rendered
    assert "grounding boundary" in rendered
