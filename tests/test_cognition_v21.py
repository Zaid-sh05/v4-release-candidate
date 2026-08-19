from app.cognition import CaseCognitionEngine
from app.routing_guard import apply_case_route, route_query


def _codes(case):
    return {h.code for h in case.hypotheses}


def _signals(case):
    return {s.code for s in case.semantic_signals}


def test_accidental_signal_does_not_depend_on_llm():
    case = CaseCognitionEngine(enable_llm=False).analyze(
        "صدمت شخص بالسيارة بالغلط وتوفي، وما كنت أقصد أضربه أو أقتله"
    )
    assert "intent.accidental" in _signals(case)
    assert "event.death" in _signals(case)
    assert "criminal.unintentional_death" in _codes(case)


def test_appeal_goal_signal_does_not_depend_on_llm():
    case = CaseCognitionEngine(enable_llm=False).analyze("صدر الحكم وبدي أستأنف، كم معي وقت؟")
    assert "goal.appeal" in _signals(case)
    assert "procedure.appeal" in _codes(case)
    assert case.decision.action == "clarify"


def test_short_ambiguous_taking_requires_clarification():
    case = CaseCognitionEngine(enable_llm=False).analyze("أخذ المصاري ومشي")
    assert any(e.event_type == "taking" for e in case.events)
    assert case.decision.action == "clarify"
    assert "short_ambiguous_prompt" in case.decision.blockers


def test_live_route_fusion_for_self_defense_is_criminal():
    text = "هاجمني واحد بسكين وضربني، فدفعت عنه وضربته دفاعاً عن نفسي وبعدها توفى"
    case = CaseCognitionEngine(enable_llm=False).analyze(text)
    route = apply_case_route(route_query(text, "auto", None), case, None)
    assert "criminal" in route.domains
    assert "criminal.self_defense" in _codes(case)


def test_live_route_fusion_for_cyber_extortion_keeps_criminal_domain():
    text = "واحد على واتساب هدد ينشر صوري إذا ما حولتله 1000 دينار، شو أعمل؟"
    case = CaseCognitionEngine(enable_llm=False).analyze(text)
    route = apply_case_route(route_query(text, "auto", None), case, None)
    assert route.domains[:2] == ["cyber", "criminal"]
    assert "event.threat" in _signals(case)
