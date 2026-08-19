from app.cognition import CaseCognitionEngine, CognitionEnrichment, GroqCognitionEnricher


class FakeEnricher:
    def __init__(self, payload):
        self.payload = payload

    def enrich(self, message: str, language: str = "ar"):
        return self.payload


class OfflineEnricher:
    def enrich(self, message: str, language: str = "ar"):
        return None


def _codes(case):
    return {hypothesis.code for hypothesis in case.hypotheses}


def test_groq_payload_rejects_items_without_user_support_span():
    enricher = GroqCognitionEnricher(api_key="test-only")
    message = "أحمد أخذ الحاسوب من المنزل"
    result = enricher._validated_payload(
        message,
        {
            "language": "ar",
            "user_goal": "legal_analysis",
            "procedural_posture": "pre_case",
            "actors": [
                {"label": "أحمد", "role": "person", "support_span": "أحمد"},
                {"label": "خالد", "role": "person", "support_span": "خالد"},
            ],
            "events": [
                {"event_type": "taking", "support_span": "أخذ الحاسوب", "intent": "unknown"},
                {"event_type": "violence", "support_span": "هدده بسكين", "intent": "intentional"},
            ],
            "evidence": [],
            "semantic_signals": [],
            "ambiguities": [],
        },
    )
    assert [actor["label"] for actor in result.actors] == ["أحمد"]
    assert [event["event_type"] for event in result.events] == ["taking"]


def test_llm_semantic_event_can_route_language_deterministic_parser_does_not_know():
    enrichment = CognitionEnrichment(
        user_goal="rights",
        procedural_posture="pre_case",
        events=[
            {
                "event_type": "termination",
                "actor_label": "",
                "target": "employment relationship",
                "intent": "unknown",
                "time_expression": "yesterday",
                "location": "",
                "support_span": "They let me go from my job yesterday",
            }
        ],
        semantic_signals=[
            {
                "code": "employment.termination",
                "confidence": "high",
                "support_span": "let me go from my job",
            }
        ],
        provider="fake",
        model="fake-semantic-model",
    )
    case = CaseCognitionEngine(enricher=FakeEnricher(enrichment)).analyze(
        "They let me go from my job yesterday and I want to know my rights", language="en"
    )
    assert "labor.termination" in _codes(case)
    assert case.user_goal == "rights"
    assert case.cognition_provider == "fake"
    assert any(event.event_type == "termination" for event in case.events)


def test_llm_intent_enrichment_changes_case_graph_without_becoming_legal_truth():
    message = "السيارة ارتطمت بالمشاة دون أن أتعمد ذلك وتوفي الشخص"
    enrichment = CognitionEnrichment(
        events=[
            {
                "event_type": "death",
                "actor_label": "",
                "target": "الشخص",
                "intent": "accidental",
                "time_expression": "",
                "location": "",
                "support_span": "ارتطمت بالمشاة دون أن أتعمد ذلك وتوفي الشخص",
            }
        ],
        semantic_signals=[
            {
                "code": "intent.accidental",
                "confidence": "high",
                "support_span": "دون أن أتعمد ذلك",
            },
            {
                "code": "event.death",
                "confidence": "high",
                "support_span": "توفي الشخص",
            },
        ],
        provider="fake",
        model="fake-semantic-model",
    )
    case = CaseCognitionEngine(enricher=FakeEnricher(enrichment)).analyze(message)
    mental = [relation for relation in case.graph if relation.predicate == "mental_state_indicator"]
    assert any(relation.object == "unintentional" for relation in mental)
    accidental = next(h for h in case.hypotheses if h.code == "criminal.unintentional_death")
    intentional = next(h for h in case.hypotheses if h.code == "criminal.intentional_homicide")
    assert accidental.confidence > intentional.confidence
    assert all(relation.predicate != "guilty_of" for relation in case.graph)


def test_llm_failure_is_non_fatal_and_deterministic_cognition_continues():
    case = CaseCognitionEngine(enricher=OfflineEnricher()).analyze("فصلني صاحب العمل بدون إنذار")
    assert "labor.termination" in _codes(case)
    assert case.cognition_provider == "deterministic"
    assert case.decision is not None
