"""Regression: the retrieval-query planner must not silently no-op for issues it already spots.

`build_retrieval_queries` is the existing issue-aware retrieval mechanism: when route confidence
is low or the initial source set is weak, `app/chat.py` replaces the retrieved sources with a
re-query built from these targeted strings (see `cognition_queries` in `handle_chat`). Before this
fix, the cyber.* hypothesis codes (`cyber.blackmail_threat`, `cyber.account_intrusion`,
`cyber.private_data_misuse`) had no branch here, so a correctly-spotted cyber issue produced an
empty retrieval-query list and the re-query fallback never fired for it — leaving the primary,
generic-message-only search as the only signal, with no legal-topic-specific query to disambiguate
a Cybercrime Law provision from a same-domain but unrelated Penal Code provision.

Query strings are kept short (<=4 words) deliberately: a read-only production audit
(scripts/audit_legal_corpus_topics.py) confirmed Postgres' `simple` FTS config does no Arabic
stemming/prefix-stripping and `websearch_to_tsquery` ANDs bare words together, so a long
descriptive sentence matches zero corpus rows while a 2-4 word phrase using the corpus' own
vocabulary (e.g. "قانون الجرائم الإلكترونية الابتزاز") reliably hits the right article.
"""
from __future__ import annotations

from app.cognition.models import CaseModel, LegalHypothesis
from app.cognition.retrieval_planner import build_retrieval_queries


def _case_with(code: str, domain: str) -> CaseModel:
    case = CaseModel(raw_message="irrelevant for this planner")
    case.hypotheses = [LegalHypothesis(code=code, label_ar="x", domain=domain)]
    return case


def test_blackmail_threat_hypothesis_yields_cybercrime_law_queries():
    queries = build_retrieval_queries(_case_with("cyber.blackmail_threat", "cyber"))
    assert queries, "cyber.blackmail_threat must not silently produce zero retrieval queries"
    assert any("الجرائم الإلكترونية" in q for q in queries)
    assert any("ابتزاز" in q for q in queries)


def test_account_intrusion_hypothesis_yields_cybercrime_law_query():
    queries = build_retrieval_queries(_case_with("cyber.account_intrusion", "cyber"))
    assert queries
    assert any("الدخول غير المصرح" in q for q in queries)


def test_private_data_misuse_hypothesis_yields_cybercrime_law_query():
    queries = build_retrieval_queries(_case_with("cyber.private_data_misuse", "cyber"))
    assert queries
    assert any("حماية البيانات" in q for q in queries)


def test_unrelated_hypothesis_code_still_yields_empty_list_not_a_crash():
    queries = build_retrieval_queries(_case_with("personal_status.divorce_path", "personal_status"))
    assert queries == []


def test_cyber_queries_stay_short_enough_for_and_semantics_lexical_search():
    """websearch_to_tsquery ANDs bare words together; a long sentence matches nothing against
    literal statute text (confirmed empirically — see module docstring). Keep every generated
    cyber query at or under 4 words so it stays usable by the lexical half of hybrid_search.
    """
    for code in ("cyber.blackmail_threat", "cyber.account_intrusion", "cyber.private_data_misuse"):
        for q in build_retrieval_queries(_case_with(code, "cyber")):
            assert len(q.split()) <= 4, f"{code!r} query too long for AND-semantics lexical search: {q!r}"
