from __future__ import annotations

from app.cognition import CaseCognitionEngine
from app.routing_guard import apply_case_route, route_query


def analyze(text: str, language: str = "ar"):
    case = CaseCognitionEngine().analyze(text, language)
    route = route_query(text, language, None)
    route = apply_case_route(route, case, None)
    return case, route


def codes(case) -> set[str]:
    return {item.code for item in case.hypotheses}


def hypothesis(case, code: str):
    return next(item for item in case.hypotheses if item.code == code)


def test_labor_unpaid_salary_is_wage_issue_not_generic_debt():
    case, route = analyze("أنا موظف بالشركة وما دفعوا راتبي عن آخر شهرين رغم أني ما زلت على رأس عملي.")
    assert route.primary_domain == "labor"
    assert "labor.unpaid_wages" in codes(case)
    assert "civil.debt_claim" not in codes(case)
    assert any("الفترة" in item for item in hypothesis(case, "labor.unpaid_wages").missing_elements)


def test_labor_overtime_is_separate_from_salary_nonpayment():
    case, route = analyze("صاحب العمل يطلب مني ساعتين أوفر تايم كل يوم وما بدفع بدل الساعات الإضافية.")
    assert route.primary_domain == "labor"
    assert "labor.overtime" in codes(case)
    assert any("ساعات" in item for item in hypothesis(case, "labor.overtime").missing_elements)


def test_labor_leave_dispute_spots_leave_balance():
    case, route = analyze("أنا موظف من ثلاث سنوات والشركة ترفض تعطيني إجازتي السنوية وبتقول ما إلي رصيد.")
    assert route.primary_domain == "labor"
    assert "labor.leave_entitlement" in codes(case)


def test_labor_termination_can_coexist_with_unpaid_wages():
    case, route = analyze("فصلني صاحب العمل بدون إنذار ولسا ما دفع راتبي عن الشهر الماضي.")
    assert route.primary_domain == "labor"
    assert {"labor.termination", "labor.unpaid_wages"}.issubset(codes(case))


def test_civil_contract_breach_spots_performance_issue():
    case, route = analyze("وقعت عقد توريد ودفعنا الدفعة الأولى لكن المورد لم يسلم البضاعة في الموعد ولم ينفذ العقد.")
    assert route.primary_domain == "civil"
    assert "civil.contract_performance" in codes(case)
    assert any("العقد" in item for item in hypothesis(case, "civil.contract_performance").missing_elements)


def test_civil_loan_spots_debt_claim():
    case, route = analyze("أقرضت شخص 3000 دينار بتحويل بنكي وكان موعد السداد قبل شهر ولم يرجع المبلغ.")
    assert route.primary_domain == "civil"
    assert "civil.debt_claim" in codes(case)


def test_civil_debt_denial_is_kept_as_contradiction_not_resolved_fact():
    case, _ = analyze("لي عند شخص دين 2000 دينار وهو ينكر الدين وبيقول إنه دفعني كامل المبلغ.")
    issue = hypothesis(case, "civil.debt_claim")
    assert issue.contradictions
    assert issue.status == "needs_clarification"


def test_civil_nontraffic_damage_spots_compensation_without_traffic_issue():
    case, route = analyze("المقاول أتلف أرضية البيت أثناء العمل وسبب لي خسارة كبيرة وبدي أطالب بتعويض.")
    assert route.primary_domain == "civil"
    assert "civil.compensation_damage" in codes(case)
    assert not any(code.startswith("traffic.") for code in codes(case))


def test_personal_status_divorce_spots_divorce_path():
    case, route = analyze("أنا متزوجة وبدي أرفع قضية طلاق بسبب الخلافات المستمرة بيننا، شو المعلومات اللازمة؟")
    assert route.primary_domain == "personal_status"
    assert "personal_status.divorce_path" in codes(case)


def test_personal_status_maintenance_spots_support_issue():
    case, route = analyze("والد الأطفال ما بصرف عليهم من ستة أشهر وبدي أطالب بنفقة للأولاد.")
    assert route.primary_domain == "personal_status"
    assert "personal_status.maintenance" in codes(case)
    assert any("الفترة" in item for item in hypothesis(case, "personal_status.maintenance").missing_elements)


def test_personal_status_custody_access_is_not_theft_from_taking_children_language():
    case, route = analyze("الأب أخذ الأولاد ومنعني من رؤيتهم رغم وجود خلاف على الحضانة والمشاهدة.")
    assert route.primary_domain == "personal_status"
    assert "personal_status.custody_access" in codes(case)
    assert "criminal.theft" not in codes(case)


def test_personal_status_divorce_and_maintenance_can_coexist():
    case, route = analyze("بدي طلاق وكمان الزوج ما بصرف علي وعلى الأولاد من أشهر.")
    assert route.primary_domain == "personal_status"
    assert {"personal_status.divorce_path", "personal_status.maintenance"}.issubset(codes(case))


def test_company_signature_authority_is_commercial_issue():
    case, route = analyze("مدير بالشركة وقع عقد باسم الشركة لكن باقي الشركاء يقولوا إنه غير مفوض بالتوقيع على هذا النوع من العقود.")
    assert route.primary_domain == "commercial"
    assert "commercial.company_authority" in codes(case)
    assert any("المفوض" in item for item in hypothesis(case, "commercial.company_authority").missing_elements)


def test_company_money_withdrawal_is_not_automatically_theft():
    case, route = analyze("أحد الشركاء سحب من حساب الشركة وحول المبلغ لنفسه ويقول إن العملية كانت بدل مصاريف مستحقة له.")
    assert route.primary_domain == "commercial"
    assert "commercial.company_funds" in codes(case)
    # The facts may later support another route, but the company transaction itself must not be
    # converted into proven theft merely from the word 'سحب'.
    assert "criminal.theft" not in codes(case)


def test_share_transfer_dispute_spots_registry_question():
    case, route = analyze("أنا شريك بالشركة واكتشفت أن حصتي تغيرت بالسجل بعد تنازل عن الحصص وأنا أعترض على التنازل.")
    assert route.primary_domain == "commercial"
    assert "commercial.shareholding_dispute" in codes(case)


def test_online_blackmail_spots_cyber_issue_and_preserves_payment_question():
    case, route = analyze("شخص على واتساب هدد ينشر صوري الخاصة إذا ما دفعتله 500 دينار وأنا ما دفعت.")
    assert route.domains[:2] == ["cyber", "criminal"] or route.primary_domain == "cyber"
    assert "cyber.blackmail_threat" in codes(case)
    assert "cyber.private_data_misuse" in codes(case)
    assert any("دفع" in item for item in hypothesis(case, "cyber.blackmail_threat").missing_elements)


def test_hacked_account_spots_intrusion_without_blackmail_when_no_demand():
    case, route = analyze("انخترق حسابي على انستغرام وتغيرت كلمة السر وظهر تسجيل دخول من جهاز ما بعرفه.")
    assert route.primary_domain == "cyber"
    assert "cyber.account_intrusion" in codes(case)
    assert "cyber.blackmail_threat" not in codes(case)


def test_private_messages_disclosure_spots_data_misuse():
    case, route = analyze("شخص نشر محادثاتي الخاصة وصوري من حساب على فيسبوك بدون إذني.")
    assert route.primary_domain == "cyber"
    assert "cyber.private_data_misuse" in codes(case)


def test_service_dispute_spots_procedural_service_status():
    case, route = analyze("صدر حكم ضدي وأنا بقول إني ما تبلغت الحكم، والخصم يقول إن التبليغ تم على عنوان البيت.")
    assert route.primary_domain == "procedure"
    assert "procedure.service_status" in codes(case)
    assert hypothesis(case, "procedure.service_status").status == "needs_clarification"


def test_appeal_deadline_requires_judgment_and_service_facts_not_a_guessed_number():
    case, route = analyze("بدي أستأنف الحكم وخايف تكون فاتت مدة الاستئناف، ما بعرف إذا الحكم وجاهي ولا غيابي ولا متى تم التبليغ.")
    assert route.primary_domain == "procedure"
    assert {"procedure.appeal", "procedure.appeal_deadline_material"}.issubset(codes(case))
    missing = hypothesis(case, "procedure.appeal_deadline_material").missing_elements
    assert any("وصف الحكم" in item for item in missing)
    assert any("التبليغ" in item for item in missing)
