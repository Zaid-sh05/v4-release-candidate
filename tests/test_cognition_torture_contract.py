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


def test_plural_police_statement_is_not_misread_as_property_taking():
    # Same defect class the handoff explicitly forbids ("تم أخذ أقواله" must never become
    # theft), reappearing under plural conjugation: "أخذوا أقواله" (they took his statement,
    # plural) wasn't close enough to the singular "أخذ أقواله" blocklist entries for fuzzy
    # matching to bridge, so a false "taking" (property theft) event survived pruning.
    case = CaseCognitionEngine(enable_llm=False).analyze("رجال الشرطة أخذوا أقواله وسجلوا إفادته")
    event_types = {e.event_type for e in case.events}
    assert event_types == {"statement"}


def test_real_taking_survives_when_a_false_statement_context_shares_its_span():
    # Guards against over-correcting the fix above: a message with BOTH genuine property
    # taking and a later false-context statement mention must keep the real taking event.
    case = CaseCognitionEngine(enable_llm=False).analyze(
        "اقتحم المنزل واخذ الحاسوب، وبعدها اخذوا اقواله في المركز"
    )
    event_types = {e.event_type for e in case.events}
    assert "taking" in event_types
    assert "statement" in event_types


def test_named_parties_are_captured_in_verb_subject_narrative_order():
    # Phase 7 probe against the handoff's own reference complex scenario surfaced this: Arabic
    # narrative commonly puts the verb before the subject ("طلب عدي مبلغ", "أصيب عدي"), which the
    # original trigger-verb list never covered, silently dropping the story's central named party
    # from the actors list entirely (a false negative, not a false attribution, but it directly
    # weakens the "parties" section of any case analysis built from this fact pattern).
    case = CaseCognitionEngine(enable_llm=False).analyze(
        "أصيب عدي بجرح بسيط في الوجه. لاحقا طلب عدي مبلغ مالي مقابل الاستمرار على أقواله."
    )
    labels = {a.label for a in case.actors}
    assert "عدي" in labels


def test_unanchored_trigger_word_does_not_match_inside_a_longer_word():
    # Regression for a bug the fix above exposed: "بيت" (house) as a trigger word had no word
    # boundary, so it matched as a substring inside "البيت" (the house) and then captured
    # whatever word happened to follow it as a fake person actor.
    case = CaseCognitionEngine(enable_llm=False).analyze(
        "حدا دخل البيت وإحنا مش عارفين مين، كسر الشباك وأخذ مصاري من الخزانة"
    )
    labels = {a.label for a in case.actors}
    assert "وإحنا" not in labels
    assert "البيت" not in labels
    assert "مصاري" not in labels


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
