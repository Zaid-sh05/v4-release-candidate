from app.cognition import CaseCognitionEngine, CognitionEnrichment
from app.routing_guard import apply_case_route, route_query


class FakeEnricher:
    def __init__(self, enrichment):
        self.enrichment = enrichment

    def enrich(self, message: str, language: str = "ar"):
        return self.enrichment


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


def test_short_ambiguous_gate_survives_llm_enrichment():
    enrichment = CognitionEnrichment(
        user_goal="rights",
        events=[{
            "event_type": "taking",
            "actor_label": "",
            "target": "المصاري",
            "intent": "intentional",
            "time_expression": "",
            "location": "",
            "support_span": "أخذ المصاري",
        }],
        semantic_signals=[{
            "code": "intent.intentional",
            "confidence": "high",
            "support_span": "أخذ المصاري",
        }],
        provider="fake",
        model="fake",
    )
    case = CaseCognitionEngine(enricher=FakeEnricher(enrichment)).analyze("أخذ المصاري ومشي")
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


def test_attached_waw_injury_adds_civil_to_traffic_route():
    text = "صار حادث بين سيارتي وسيارة ثانية وانصاب السائق الثاني ونقلوه عالمستشفى"
    case = CaseCognitionEngine(enable_llm=False).analyze(text)
    route = apply_case_route(route_query(text, "auto", None), case, None)
    assert route.domains[:2] == ["traffic", "civil"]


def test_fatal_traffic_case_prioritizes_criminal_before_civil():
    text = "صدمت شخص بالسيارة بالغلط وتوفي، كنت مسرع بس ما كنت أقصد أضربه أو أقتله"
    case = CaseCognitionEngine(enable_llm=False).analyze(text)
    route = apply_case_route(route_query(text, "auto", None), case, None)
    assert route.domains[:3] == ["traffic", "criminal", "civil"]


def test_attached_waw_taking_makes_burglary_primary_criminal():
    text = "دخل أحمد بيت خالد بالليل وكسر القفل وأخذ اللابتوب و500 دينار، وبعدها ضبطت الشرطة اللابتوب معه"
    case = CaseCognitionEngine(enable_llm=False).analyze(text)
    route = apply_case_route(route_query(text, "auto", None), case, None)
    assert route.primary_domain == "criminal"
    assert route.domains[0] == "criminal"


def test_llm_taking_label_is_rejected_for_hospital_transport_text():
    message = "صار حادث وانصاب السائق الثاني ونقلوه عالمستشفى"
    enrichment = CognitionEnrichment(
        events=[{
            "event_type": "taking",
            "actor_label": "",
            "target": "المستشفى",
            "intent": "unknown",
            "time_expression": "",
            "location": "",
            "support_span": "نقلوه عالمستشفى",
        }],
        provider="fake",
        model="fake",
    )
    case = CaseCognitionEngine(enricher=FakeEnricher(enrichment)).analyze(message)
    assert all(event.event_type != "taking" for event in case.events)


def test_llm_breaking_label_is_rejected_for_cancelled_sale_text():
    message = "دفعت عربون 2000 دينار على شقة والبائع رجع عن البيع"
    enrichment = CognitionEnrichment(
        events=[{
            "event_type": "breaking",
            "actor_label": "",
            "target": "العربون",
            "intent": "intentional",
            "time_expression": "",
            "location": "",
            "support_span": "البائع رجع عن البيع",
        }],
        provider="fake",
        model="fake",
    )
    case = CaseCognitionEngine(enricher=FakeEnricher(enrichment)).analyze(message)
    assert all(event.event_type != "breaking" for event in case.events)


def test_police_allegation_with_denial_marks_fact_disputed():
    message = "الشرطة بتقول إني سرقت التلفون بس أنا بنكر، والدليل الوحيد شاهد بحكي إنه شافني قريب من المكان"
    case = CaseCognitionEngine(enable_llm=False).analyze(message)
    assert any(fact.disputed for fact in case.facts)
    assert "criminal.theft" in _codes(case)
