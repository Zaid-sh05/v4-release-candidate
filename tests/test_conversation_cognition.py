from app.cognition.conversation import ConversationCaseState


def _codes(case):
    return {h.code for h in case.hypotheses}


def test_labor_followup_is_added_to_same_case():
    state = ConversationCaseState()
    first, continued = state.ingest("فصلني صاحب العمل بدون إنذار، شو حقوقي؟")
    assert continued is False
    second, continued = state.ingest("عقدي غير محدد المدة وصارلي 4 سنوات")
    assert continued is True
    assert "labor.termination" in _codes(second)
    assert "4 سنوات" in second.raw_message


def test_short_salary_reply_keeps_labor_context():
    state = ConversationCaseState()
    state.ingest("فصلني صاحب العمل بدون إنذار، شو حقوقي؟")
    state.ingest("عقدي غير محدد المدة وصارلي 4 سنوات")
    case, continued = state.ingest("راتبي 500 دينار")
    assert continued is True
    assert "labor.termination" in _codes(case)
    assert any("500" in amount for amount in case.amounts)


def test_new_explicit_penalty_question_starts_new_case():
    state = ConversationCaseState()
    state.ingest("فصلني صاحب العمل بدون إنذار، شو حقوقي؟")
    case, continued = state.ingest("شو عقوبة السرقة؟")
    assert continued is False
    assert "criminal.theft" in _codes(case)
    assert "labor.termination" not in _codes(case)


def test_intent_clarification_updates_homicide_hypothesis():
    state = ConversationCaseState()
    state.ingest("صار حادث ومات شخص")
    case, continued = state.ingest("كان بالغلط وما كنت أقصد أضربه")
    assert continued is True
    accidental = next(h for h in case.hypotheses if h.code == "criminal.unintentional_death")
    intentional = next(h for h in case.hypotheses if h.code == "criminal.intentional_homicide")
    assert accidental.confidence > intentional.confidence
