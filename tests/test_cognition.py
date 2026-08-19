from app.cognition import CaseCognitionEngine


def _codes(case):
    return {h.code for h in case.hypotheses}


def test_accidental_death_is_not_collapsed_into_intentional_homicide():
    case = CaseCognitionEngine().analyze("صدمت شخص بالسيارة بالغلط وتوفي، كنت ماشي بسرعة وما كنت أقصد أضربه")
    assert "criminal.unintentional_death" in _codes(case)
    accidental = next(h for h in case.hypotheses if h.code == "criminal.unintentional_death")
    intentional = next(h for h in case.hypotheses if h.code == "criminal.intentional_homicide")
    assert accidental.confidence > intentional.confidence
    assert "criminal" in case.domains


def test_premeditation_strengthens_intentional_homicide_hypothesis():
    case = CaseCognitionEngine().analyze("خطط أحمد قبل يومين لقتل خالد وانتظره ثم قتله")
    assert "criminal.intentional_homicide" in _codes(case)
    h = next(h for h in case.hypotheses if h.code == "criminal.intentional_homicide")
    assert h.confidence >= 0.70
    assert any(q.id == "homicide_intent" for q in case.clarifying_questions)


def test_complex_burglary_scenario_extracts_evidence_and_multiple_issues():
    text = (
        "قام أحمد بالدخول إلى منزل جاره خالد أثناء غيابه بعد أن كسر قفل الباب الخارجي، "
        "وأخذ جهاز حاسوب ومبلغاً نقدياً مقداره 500 دينار ثم غادر المكان. "
        "لاحقاً عثرت الشرطة على الحاسوب في منزل أحمد وأظهرت كاميرا مراقبة وجوده أمام منزل خالد وقت الحادث."
    )
    case = CaseCognitionEngine().analyze(text)
    codes = _codes(case)
    assert "criminal.theft" in codes
    assert "criminal.aggravating_entry" in codes
    assert any(e.kind == "camera" for e in case.evidence)
    assert any(e.kind == "physical" for e in case.evidence)
    assert any("500" in a for a in case.amounts)
    assert len(case.events) >= 2
    assert len(case.retrieval_queries) >= 2


def test_labor_case_asks_material_questions_not_generic_questions():
    case = CaseCognitionEngine().analyze("فصلني صاحب العمل اليوم بدون ما يشرحلي السبب، شو حقوقي؟")
    assert "labor.termination" in _codes(case)
    ids = {q.id for q in case.clarifying_questions}
    assert "labor_contract" in ids
    assert "labor_reason" in ids
    assert case.user_goal == "rights"


def test_appeal_case_requires_case_type_and_dates():
    case = CaseCognitionEngine().analyze("صدر الحكم وبدي أستأنف، كم معي وقت؟")
    assert "procedure.appeal" in _codes(case)
    ids = {q.id for q in case.clarifying_questions}
    assert "appeal_case_type" in ids
    assert "appeal_date" in ids
    assert case.procedural_posture == "post_judgment"


def test_self_defense_is_kept_as_competing_hypothesis():
    case = CaseCognitionEngine().analyze("هاجمني شخص بسكين فضربته دفاعاً عن نفسي وتوفي")
    assert "criminal.self_defense" in _codes(case)
    assert "criminal.intentional_homicide" in _codes(case)
    assert any(q.id == "defense_immediacy" for q in case.clarifying_questions)
