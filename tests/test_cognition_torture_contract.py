from app.cognition import CaseCognitionEngine, CognitionEnrichment


class FakeEnricher:
    def __init__(self, enrichment: CognitionEnrichment):
        self.enrichment = enrichment

    def enrich(self, message: str, language: str = "ar"):
        return self.enrichment


def _issue_codes(case):
    return {h.code for h in case.hypotheses}


def test_rich_theft_scenario_keeps_distinct_conduct_and_evidence():
    case = CaseCognitionEngine(enable_llm=False).analyze(
        "دخل أحمد بيت خالد وكسر القفل وأخذ اللابتوب و500 دينار، وبعدها ضبطت الشرطة اللابتوب معه وكانت هناك كاميرا على الباب"
    )
    event_types = [e.event_type for e in case.events]
    assert {"entry", "breaking", "taking"}.issubset(event_types)
    assert {"camera", "physical"}.issubset({e.kind for e in case.evidence})
    assert {"criminal.theft", "criminal.aggravating_entry"}.issubset(_issue_codes(case))
    assert case.decision is not None
    assert case.decision.action == "retrieve"


def test_accidental_death_never_collapses_to_single_intentional_homicide_path():
    case = CaseCognitionEngine(enable_llm=False).analyze(
        "صدمت شخص بالسيارة بالغلط وتوفي، كنت مسرع بس ما كنت أقصد أضربه أو أقتله"
    )
    codes = _issue_codes(case)
    assert "criminal.unintentional_death" in codes
    assert "criminal.intentional_homicide" in codes
    accidental = next(h for h in case.hypotheses if h.code == "criminal.unintentional_death")
    intentional = next(h for h in case.hypotheses if h.code == "criminal.intentional_homicide")
    assert accidental.confidence > intentional.confidence
    assert case.decision is not None
    assert case.decision.action == "clarify"


def test_self_defense_remains_competing_hypothesis_not_guilt_finding():
    case = CaseCognitionEngine(enable_llm=False).analyze(
        "هاجمني شخص بسكين فضربته دفاعاً عن نفسي وتوفي"
    )
    codes = _issue_codes(case)
    assert "criminal.self_defense" in codes
    assert "criminal.intentional_homicide" in codes
    assert all(r.predicate != "guilty_of" for r in case.graph)
    assert case.decision is not None
    assert case.decision.action == "clarify"


def test_generic_appeal_question_is_blocked_until_material_procedure_facts_exist():
    case = CaseCognitionEngine(enable_llm=False).analyze("صدر الحكم وبدي أستأنف، كم معي وقت؟")
    assert "procedure.appeal" in _issue_codes(case)
    assert case.decision is not None
    assert case.decision.action == "clarify"
    assert "appeal_material_facts_missing" in case.decision.blockers


def test_unknown_actor_is_not_invented_from_ambiguous_burglary_story():
    case = CaseCognitionEngine(enable_llm=False).analyze(
        "حدا دخل البيت وإحنا مش عارفين مين، كسر الشباك وأخذ مصاري من الخزانة"
    )
    labels = {a.label for a in case.actors}
    assert "أحمد" not in labels
    assert "خالد" not in labels
    assert {"entry", "breaking", "taking"}.issubset({e.event_type for e in case.events})


def test_attached_preposition_pronouns_are_not_extracted_as_person_actors():
    # Real gap: the regex-based actor extractor captures whatever word follows a trigger verb
    # (أخذ, اتصل...), and attached preposition+pronoun objects ("from him", "with her") were not
    # in the non-person blocklist, so "أخذ منه القفل" invented a fake person actor "منه".
    case = CaseCognitionEngine(enable_llm=False).analyze("ذهب زيد لوالده وأخذ منه القفل")
    labels = {a.label for a in case.actors}
    assert "منه" not in labels
    assert "لوالده" not in labels


def test_llm_enrichment_cannot_create_unsupported_named_actor_or_event():
    message = "أحمد أخذ الحاسوب من المكتب"
    enrichment = CognitionEnrichment(
        actors=[
            {"label": "أحمد", "role": "person", "support_span": "أحمد"},
            {"label": "خالد", "role": "victim", "support_span": "خالد"},
        ],
        events=[
            {
                "event_type": "taking",
                "actor_label": "أحمد",
                "target": "الحاسوب",
                "intent": "unknown",
                "support_span": "أخذ الحاسوب",
            },
            {
                "event_type": "violence",
                "actor_label": "أحمد",
                "target": "خالد",
                "intent": "intentional",
                "support_span": "طعن خالد",
            },
        ],
        provider="fake",
        model="fake-model",
    )
    # Use the same grounding validator as the live provider would before merge.
    from app.cognition.llm_enricher import GroqCognitionEnricher

    validated = GroqCognitionEnricher(api_key="test-only")._validated_payload(
        message,
        {
            "language": "ar",
            "user_goal": "legal_analysis",
            "procedural_posture": "pre_case",
            "actors": enrichment.actors,
            "events": enrichment.events,
            "evidence": [],
            "semantic_signals": [],
            "ambiguities": [],
        },
    )
    case = CaseCognitionEngine(enricher=FakeEnricher(validated)).analyze(message)
    assert "خالد" not in {a.label for a in case.actors}
    assert not any(e.event_type == "violence" for e in case.events)
    assert any(e.event_type == "taking" for e in case.events)
