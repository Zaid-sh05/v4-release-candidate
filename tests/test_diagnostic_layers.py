"""Layer-specific diagnostic coverage (see app/diagnostics.py).

Each pipeline layer is tested in isolation where the real production code allows it (the
cognition engine, the retrieval planner, the retrieval gate) without going through the full
`handle_chat` pipeline, plus true end-to-end coverage of the three known-regression fixtures with
a `RequestTrace` attached so each layer's pass/fail state is individually inspectable -- not just
the final answer text. Nothing here duplicates production logic: every assertion reads a value the
real code already produced (a `CaseModel`, a `RouteResult`, a `RequestTrace`, a retrieval-planner
query list) rather than recomputing it.
"""
from __future__ import annotations

from app.chat import _guard_sources
from app.chat_v4 import handle_chat
from app.cognition.engine import CaseCognitionEngine
from app.cognition.models import CaseModel, LegalHypothesis
from app.cognition.retrieval_planner import build_retrieval_queries
from app.context import contextualize_message
from app.diagnostics import (
    CONTEXT_FAILURE,
    ISSUE_MAPPING_FAILURE,
    RELEVANCE_GATE_FAILURE,
    RETRIEVAL_RANKING_FAILURE,
    FailureExpectation,
    RequestTrace,
    classify_first_failure,
)
from app.models import ChatRequest, RouteResult, SourceItem
from app.repository import repository
from app.router import analyze_query

_ENGINE = CaseCognitionEngine()


# ---------------------------------------------------------------------------
# A. Semantic understanding: actors, events, evidence negation.
# ---------------------------------------------------------------------------

def test_semantic_understanding_extracts_actors_and_material_events():
    case = _ENGINE.analyze('احمد دخل منزل خالد ليلا وكسر نافذة السيارة وسرقها', 'ar')
    assert 'خالد' in [a.label for a in case.actors]
    event_types = {e.event_type for e in case.events}
    assert {'entry', 'breaking', 'taking'} <= event_types


def test_semantic_understanding_does_not_report_negated_evidence_as_present():
    case = _ENGINE.analyze('لم تعثر الشرطة على أي شيء في منزلي، ولم يحصل اي اعتداء', 'ar')
    assert case.evidence == []


# ---------------------------------------------------------------------------
# B. Context / threading.
# ---------------------------------------------------------------------------

def test_context_links_a_short_same_case_followup():
    history = [{'role': 'user', 'content': 'احمد دخل منزل خالد ليلا وكسر نافذة السيارة وسرقها'}]
    route = analyze_query('سرق سيارة', 'ar')
    trace = RequestTrace()
    effective, used = contextualize_message('سرق سيارة', history, route, trace)
    assert used is True
    assert trace.context_attachment_reason == 'same_domain_continuation'
    assert 'خالد' in effective


def test_context_does_not_link_an_explicit_new_case():
    history = [{'role': 'user', 'content': 'احمد دخل منزل خالد ليلا وكسر نافذة السيارة وسرقها'}]
    route = analyze_query('سؤال ثاني، ما هي عقوبة القتل؟', 'ar')
    trace = RequestTrace()
    _, used = contextualize_message('سؤال ثاني، ما هي عقوبة القتل؟', history, route, trace)
    assert used is False
    assert trace.context_attachment_reason == 'explicit_new_case_marker'


def test_context_does_not_contaminate_a_genuinely_new_unrelated_case():
    history = [{'role': 'user', 'content': 'تعرضت لابتزاز على فيسبوك، شو أعمل؟'}]
    route = analyze_query('صدمت سيارة وانا داخل بإشارة حمراء', 'ar')
    trace = RequestTrace()
    _, used = contextualize_message('صدمت سيارة وانا داخل بإشارة حمراء', history, route, trace)
    assert used is False


def test_context_links_an_answer_to_a_prior_clarifying_question():
    history = [
        {'role': 'user', 'content': 'قام أحمد بكسر قفل منزل جاره وأخذ حاسوبا محمولا'},
        {'role': 'assistant', 'content': 'قبل التكييف النهائي، هل كان الدخول دون إذن؟ هل وقع ليلاً؟'},
    ]
    route = analyze_query('من غير اذن، ووقع ليلا', 'ar')
    trace = RequestTrace()
    _, used = contextualize_message('من غير اذن، ووقع ليلا', history, route, trace)
    assert used is True
    assert trace.context_attachment_reason in {'answers_prior_clarification', 'followup_detail'}


def test_context_return_to_previous_topic_reactivates_it():
    history = [
        {'role': 'user', 'content': 'فصلني صاحب العمل بدون إنذار، شو حقوقي؟'},
        {'role': 'assistant', 'content': 'هذا سؤال عمالي.'},
        {'role': 'user', 'content': 'بالمناسبة، ما هي عقوبة السرقة؟'},
        {'role': 'assistant', 'content': 'هذا سؤال جزائي منفصل.'},
    ]
    route = analyze_query('خلينا نرجع لموضوع الفصل التعسفي', 'ar')
    trace = RequestTrace()
    effective, used = contextualize_message('خلينا نرجع لموضوع الفصل التعسفي', history, route, trace)
    assert used is True
    assert trace.context_attachment_reason == 'return_to_topic'
    assert 'فصلني' in effective


# ---------------------------------------------------------------------------
# C. Legal issue mapping (cognition, no retrieval involved).
# ---------------------------------------------------------------------------

def test_issue_mapping_classifies_theft_case_without_retrieval():
    case = _ENGINE.analyze('احمد دخل منزل خالد ليلا وكسر نافذة السيارة وسرقها', 'ar')
    assert 'criminal' in case.domains
    codes = {h.code for h in case.hypotheses}
    assert 'criminal.theft' in codes or 'criminal.aggravating_entry' in codes


def test_issue_mapping_distinguishes_cyber_threat_from_property_crime():
    # The deterministic cognition engine's own hypothesis vocabulary does not yet cover the
    # image-disclosure-threat family (a known, documented gap -- see app/routing_guard.py's
    # `_image_disclosure_threat_context`, which is what actually classifies this pattern in the
    # real pipeline via `route_query`/`issue_signature`). Issue mapping for this fixture is
    # therefore tested against the mechanism that actually performs it.
    from app.routing_guard import issue_signature, route_query
    theft_route = route_query('احمد دخل منزل خالد ليلا وكسر نافذة السيارة وسرقها', 'ar')
    cyber_route = route_query('قام رائد بتهديد سوسن عبر تيليجرام بأنه سوف ينشر لها صور وهي عارية', 'ar')
    assert theft_route.primary_domain == 'criminal'
    assert cyber_route.primary_domain == 'cyber'
    assert 'cyber_threat' in issue_signature(cyber_route.normalized_text)
    assert 'property_crime' in issue_signature(theft_route.normalized_text)


# ---------------------------------------------------------------------------
# D. Retrieval planner (issue codes fed in directly; query plan asserted).
# ---------------------------------------------------------------------------

def test_retrieval_planner_emits_theft_queries_for_the_theft_hypothesis():
    case = CaseModel(raw_message='x', hypotheses=[
        LegalHypothesis(code='criminal.theft', label_ar='', domain='criminal', confidence=0.6),
    ])
    queries = build_retrieval_queries(case)
    assert any('السرقة' in q for q in queries)


def test_retrieval_planner_emits_cyber_extortion_queries_for_the_blackmail_hypothesis():
    case = CaseModel(raw_message='x', hypotheses=[
        LegalHypothesis(code='cyber.blackmail_threat', label_ar='', domain='cyber', confidence=0.6),
    ])
    queries = build_retrieval_queries(case)
    assert any('الابتزاز' in q or 'الجرائم الإلكترونية' in q for q in queries)


# ---------------------------------------------------------------------------
# E. Retrieval ranking (controlled corpus query; correct source must be findable).
# ---------------------------------------------------------------------------

def test_retrieval_ranking_surfaces_the_real_theft_article():
    results = repository.search('سرقة مركبة', ['criminal'], 8)
    assert any(r.article == '407' for r in results)


def test_retrieval_ranking_never_surfaces_an_unrelated_offense_for_bare_theft_queries():
    results = repository.search('سرق سيارة', ['criminal'], 8)
    for r in results:
        hay = (r.title or '') + ' ' + (r.excerpt or '')
        assert 'الزاني' not in hay and 'الزانية' not in hay


# ---------------------------------------------------------------------------
# F. Relevance gate (mixed candidate set: correct / same-domain-wrong-topic / wrong-domain).
# ---------------------------------------------------------------------------

def _mk_source(id, title, domain, article, excerpt, score=5.0):
    return SourceItem(
        id=id, title=title, authority='جهة رسمية أردنية', domain=domain,
        source_url='https://example.gov.jo/x', article=article, excerpt=excerpt,
        source_kind='canonical_verified', score=score,
    )


def test_relevance_gate_rejects_same_domain_wrong_topic_and_wrong_domain_sources():
    route = RouteResult(
        language='ar', intent='legal_question', primary_domain='criminal',
        domains=['criminal', 'general'], confidence=0.9, normalized_text='سرق سيارة',
    )
    correct = _mk_source('407', 'قانون العقوبات — المادة 407', 'criminal', '407', 'نص السرقة أخذ مال منقول للغير خلسة')
    same_domain_wrong_topic = _mk_source('282', 'قانون العقوبات — المادة 282', 'criminal', '282', 'يعاقب الزاني والزانية برضاهما')
    wrong_domain = _mk_source('assoc1', 'قانون الجمعيات', 'general', None, 'نص إداري عن تسجيل الجمعيات')

    trace = RequestTrace()
    guarded = _guard_sources(route, [correct, same_domain_wrong_topic, wrong_domain], trace)

    assert [s.id for s in guarded] == ['407']
    rejected_ids = {c.id for c in trace.rejected_candidates}
    assert '282' in rejected_ids and 'assoc1' in rejected_ids


def test_relevance_gate_failure_is_detected_when_a_forbidden_source_is_deliberately_let_through():
    # Manufactured failure: simulate a gate that let the wrong-topic article through, and confirm
    # classify_first_failure correctly attributes it to RELEVANCE_GATE_FAILURE rather than a
    # later layer.
    trace = RequestTrace()
    trace.retrieval_queries = ['سرق سيارة']
    trace.raw_candidates = []
    same_domain_wrong_topic = _mk_source('282', 'قانون العقوبات — المادة 282', 'criminal', '282', 'يعاقب الزاني والزانية')
    trace.record_gate_decision(same_domain_wrong_topic, domain_compatible=True, issue_compatible=True, accepted=True, reason=None)

    diag = classify_first_failure(trace, FailureExpectation(forbidden_title_fragments=['المادة 282']))
    assert diag.layer == RELEVANCE_GATE_FAILURE


# ---------------------------------------------------------------------------
# G. Writer (known accepted evidence in; no unsupported source/article in the answer).
# ---------------------------------------------------------------------------

def test_writer_never_cites_an_article_outside_the_accepted_evidence_set():
    route = RouteResult(
        language='ar', intent='legal_question', primary_domain='criminal',
        domains=['criminal'], confidence=0.9, normalized_text='سرقة مركبة',
    )
    sources = [_mk_source('407', 'قانون العقوبات — المادة 407', 'criminal', '407', 'نص السرقة أخذ مال منقول للغير خلسة دون رضا مالكه', score=10.0)]
    from app.chat import _choose_grounded
    grounded, _evaluation = _choose_grounded('سرقة مركبة', route, sources)
    if grounded is not None:
        # The only article available to the writer was 407 -- no other article number may appear.
        import re
        cited_articles = set(re.findall(r'المادة\s+(\d+)', grounded.text))
        assert cited_articles <= {'407'}


# ---------------------------------------------------------------------------
# H. End-to-end: the three known-regression fixtures, with per-layer trace assertions.
# ---------------------------------------------------------------------------

def _assert_no_failure(trace: RequestTrace, expectation: FailureExpectation, answer: str) -> None:
    diag = classify_first_failure(trace, expectation, answer)
    assert diag.layer == 'NO_FAILURE_DETECTED', diag


def test_e2e_theft_followup_all_layers_pass():
    first = handle_chat(ChatRequest(message='احمد دخل منزل خالد ليلا وكسر نافذة السيارة وسرقها', language='ar'))
    trace = RequestTrace()
    followup = handle_chat(
        ChatRequest(message='سرق سيارة', language='ar', conversation_id=first.conversation_id),
        trace=trace,
    )
    # semantic understanding
    assert 'خالد' in followup.answer
    # context/threading
    assert trace.context_attachment_used is True
    # issue mapping
    assert trace.primary_domain == 'criminal'
    # retrieval + relevance gate + writer, via the shared diagnosis helper
    _assert_no_failure(
        trace,
        FailureExpectation(expected_primary_domain='criminal', forbidden_title_fragments=['المادة 282']),
        followup.answer,
    )


def test_e2e_telegram_image_threat_all_layers_pass():
    trace = RequestTrace()
    resp = handle_chat(
        ChatRequest(message='قام رائد بتهديد سوسن عبر تيليجرام بأنه سوف ينشر لها صور وهي عارية', language='ar'),
        trace=trace,
    )
    assert trace.primary_domain == 'cyber'
    assert 'cyber_threat' in trace.issue_signature
    _assert_no_failure(
        trace,
        FailureExpectation(
            expected_primary_domain='cyber',
            expected_issue_family='cyber_threat',
            forbidden_title_fragments=['الامن العام', 'الجمعيات'],
        ),
        resp.answer,
    )


def test_e2e_telegram_threat_conditioned_on_compliance_all_layers_pass():
    trace = RequestTrace()
    resp = handle_chat(
        ChatRequest(
            message='قام رائد بتهديد سوسن عبر تيليجرام بأنه سوف ينشر لها صور فاضحة ان لم تستجب لطلباته',
            language='ar',
        ),
        trace=trace,
    )
    assert trace.primary_domain == 'cyber'
    _assert_no_failure(
        trace,
        FailureExpectation(
            expected_primary_domain='cyber',
            forbidden_title_fragments=['الامن العام', 'الجمعيات'],
        ),
        resp.answer,
    )


def test_e2e_diagnosis_flags_uncertain_when_no_expectation_can_be_checked():
    trace = RequestTrace()
    handle_chat(ChatRequest(message='ما هي مواعيد العمل الرسمية؟', language='ar'), trace=trace)
    diag = classify_first_failure(trace, FailureExpectation())
    assert diag.status == 'uncertain'
