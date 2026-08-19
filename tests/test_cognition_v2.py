from app.cognition import CaseCognitionEngine


def _predicates(case):
    return {r.predicate for r in case.graph}


def test_case_graph_separates_actions_timeline_and_evidence():
    text = (
        "قام أحمد بالدخول إلى منزل جاره خالد بعد أن كسر قفل الباب، "
        "وأخذ جهاز حاسوب ومبلغ 500 دينار. لاحقاً عثرت الشرطة على الحاسوب "
        "وأظهرت كاميرا مراقبة وجود أحمد أمام المنزل."
    )
    case = CaseCognitionEngine().analyze(text)
    predicates = _predicates(case)
    assert "entered" in predicates
    assert "broke_or_forced" in predicates
    assert "took_property" in predicates
    assert "occurred_before" in predicates
    assert "evidence_kind" in predicates
    assert case.decision is not None
    assert case.decision.action == "retrieve"
    assert case.decision.safe_to_answer is False


def test_accidental_death_records_mental_state_and_blocks_final_classification():
    case = CaseCognitionEngine().analyze(
        "صدمت شخص بالسيارة بالغلط وتوفي، كنت مسرع وما كنت أقصد أضربه"
    )
    mental = [r for r in case.graph if r.predicate == "mental_state_indicator"]
    assert mental
    assert mental[0].object == "unintentional"
    assert case.decision is not None
    assert case.decision.action == "clarify"
    assert "material_competing_hypotheses" in case.decision.blockers


def test_premeditation_is_preserved_as_fact_indicator_not_legal_conclusion():
    case = CaseCognitionEngine().analyze(
        "خطط أحمد قبل يومين لقتل خالد وانتظره ثم قتله"
    )
    mental = [r for r in case.graph if r.predicate == "mental_state_indicator"]
    assert mental
    assert mental[0].object == "premeditated"
    assert mental[0].predicate != "guilty_of"


def test_appeal_deadline_stops_for_material_procedural_facts():
    case = CaseCognitionEngine().analyze("صدر الحكم وبدي أستأنف، كم معي وقت؟")
    assert case.decision is not None
    assert case.decision.action == "clarify"
    assert "appeal_material_facts_missing" in case.decision.blockers
    assert "appeal_case_type" in case.decision.question_ids


def test_rich_scenario_does_not_dead_end_on_clarification_only():
    case = CaseCognitionEngine().analyze(
        "دخل أحمد بيت خالد وكسر القفل وأخذ اللابتوب. لاحقاً ضبطت الشرطة اللابتوب معه وكانت هناك كاميرا على الباب."
    )
    assert len(case.events) >= 3
    assert case.retrieval_queries
    assert case.decision is not None
    assert case.decision.action == "retrieve"
    # Questions may remain, but they should accompany preliminary research instead of blocking it.
    assert case.decision.question_ids
