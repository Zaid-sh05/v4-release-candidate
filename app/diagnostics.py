"""First-class internal request tracing for localizing the first failing pipeline layer.

This module intentionally does NOT run a second, parallel pipeline. It only defines the
in-memory record shape that `app.chat.handle_chat` fills in as it executes the REAL production
path (see the `trace` parameter threaded through `handle_chat`/`_guard_sources`/`_choose_grounded`
etc. in `app/chat.py`). When `trace` is not supplied (the default, and the only mode the public
HTTP layer ever uses), instrumentation is a handful of `if trace is not None` checks -- no new
retrieval, no new LLM calls, no behavior change to the returned `ChatResponse`.

Tracing is opt-in and Python-only: there is no HTTP endpoint here, and nothing here is reachable
from the public chat API. Callers that want a trace (tests, an internal admin script run by a
developer) construct a `RequestTrace` and pass it into `handle_chat(req, trace=trace)` directly.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# The eight pipeline layers this module can attribute a failure to.
# ---------------------------------------------------------------------------
UNDERSTANDING_FAILURE = "UNDERSTANDING_FAILURE"
CONTEXT_FAILURE = "CONTEXT_FAILURE"
ISSUE_MAPPING_FAILURE = "ISSUE_MAPPING_FAILURE"
RETRIEVAL_PLAN_FAILURE = "RETRIEVAL_PLAN_FAILURE"
RETRIEVAL_RANKING_FAILURE = "RETRIEVAL_RANKING_FAILURE"
RELEVANCE_GATE_FAILURE = "RELEVANCE_GATE_FAILURE"
EVIDENCE_SELECTION_FAILURE = "EVIDENCE_SELECTION_FAILURE"
WRITER_FAILURE = "WRITER_FAILURE"
NO_FAILURE_DETECTED = "NO_FAILURE_DETECTED"

_LAYER_ORDER = (
    UNDERSTANDING_FAILURE,
    CONTEXT_FAILURE,
    ISSUE_MAPPING_FAILURE,
    RETRIEVAL_PLAN_FAILURE,
    RETRIEVAL_RANKING_FAILURE,
    RELEVANCE_GATE_FAILURE,
    EVIDENCE_SELECTION_FAILURE,
    WRITER_FAILURE,
)


@dataclass
class SourceTrace:
    """One retrieval candidate's journey through the gate, for the diagnostic trace only."""
    id: str
    title: str
    domain: str
    article: str | None
    score: float
    stage: str
    domain_compatible: bool | None = None
    issue_compatible: bool | None = None
    rejected_reason: str | None = None
    accepted: bool = False


@dataclass
class RequestTrace:
    """Structured, per-request diagnostic record. Never part of the public API response model."""
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    raw_input: str = ""
    normalized_input: str = ""
    detected_language: str = ""
    detected_intent: str = ""

    context_attachment_used: bool = False
    context_attachment_reason: str = ""
    active_conversation_id: str = ""

    actors: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    disputed_facts: list[str] = field(default_factory=list)
    cognition_warnings: list[str] = field(default_factory=list)
    cognition_ambiguities: list[dict] = field(default_factory=list)

    detected_domains: list[str] = field(default_factory=list)
    primary_domain: str = ""
    issue_signature: list[str] = field(default_factory=list)
    legal_hypotheses: list[dict] = field(default_factory=list)

    retrieval_queries: list[str] = field(default_factory=list)
    raw_candidates: list[SourceTrace] = field(default_factory=list)
    guarded_candidates: list[SourceTrace] = field(default_factory=list)
    rejected_candidates: list[SourceTrace] = field(default_factory=list)

    accepted_source_ids: list[str] = field(default_factory=list)
    final_mode: str = ""
    final_cited_source_ids: list[str] = field(default_factory=list)
    fallback_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # -- collection helpers used by app.chat; kept here so instrumentation call sites stay tiny --
    def record_candidates(self, stage: str, items: list, *, allowed_domains: set[str] | None = None) -> None:
        for item in items or []:
            self.raw_candidates.append(SourceTrace(
                id=getattr(item, "id", "") or "",
                title=getattr(item, "title", "") or "",
                domain=getattr(item, "domain", "") or "",
                article=getattr(item, "article", None),
                score=float(getattr(item, "score", 0) or 0),
                stage=stage,
            ))

    def record_gate_decision(self, item, *, domain_compatible: bool, issue_compatible: bool | None, accepted: bool, reason: str | None) -> None:
        entry = SourceTrace(
            id=getattr(item, "id", "") or "",
            title=getattr(item, "title", "") or "",
            domain=getattr(item, "domain", "") or "",
            article=getattr(item, "article", None),
            score=float(getattr(item, "score", 0) or 0),
            stage="gate",
            domain_compatible=domain_compatible,
            issue_compatible=issue_compatible,
            rejected_reason=reason,
            accepted=accepted,
        )
        if accepted:
            self.guarded_candidates.append(entry)
        else:
            self.rejected_candidates.append(entry)


# ---------------------------------------------------------------------------
# First-failure diagnosis.
#
# The trace alone cannot know what the CORRECT answer was -- only a caller (a test with a known
# regression fixture, or a developer investigating a specific reported case) knows that. This is
# why diagnosis takes an explicit `FailureExpectation`: the ground truth to check the trace
# against. Nothing here re-derives correctness on its own or claims certainty it does not have --
# any layer whose relevant expectation field was left unset is skipped, and if no layer could be
# confirmed either way, the result is `NO_FAILURE_DETECTED` with `diagnostic_status="uncertain"`.
# ---------------------------------------------------------------------------
@dataclass
class FailureExpectation:
    expected_actor_labels: list[str] | None = None
    expect_context_link: bool | None = None
    expected_primary_domain: str | None = None
    expected_issue_family: str | None = None
    forbidden_issue_families: list[str] | None = None
    expected_article: str | None = None
    forbidden_title_fragments: list[str] | None = None
    forbidden_domain: str | None = None
    forbidden_answer_fragments: list[str] | None = None
    required_answer_fragments: list[str] | None = None


@dataclass
class FirstFailureDiagnosis:
    layer: str
    status: Literal["confirmed", "uncertain"]
    detail: str


def classify_first_failure(trace: RequestTrace, expectation: FailureExpectation, final_answer: str = "") -> FirstFailureDiagnosis:
    """Walk the pipeline layers in order; return the first one a supplied expectation contradicts."""

    if expectation.expected_actor_labels:
        found = {a.get("label", "") for a in trace.actors}
        missing = [label for label in expectation.expected_actor_labels if label not in found]
        if missing:
            return FirstFailureDiagnosis(UNDERSTANDING_FAILURE, "confirmed", f"actors not extracted: {missing}")

    if expectation.expect_context_link is not None:
        if trace.context_attachment_used != expectation.expect_context_link:
            return FirstFailureDiagnosis(
                CONTEXT_FAILURE, "confirmed",
                f"expected context_attachment_used={expectation.expect_context_link}, got {trace.context_attachment_used}",
            )

    if expectation.expected_primary_domain and trace.primary_domain != expectation.expected_primary_domain:
        return FirstFailureDiagnosis(
            ISSUE_MAPPING_FAILURE, "confirmed",
            f"expected primary_domain={expectation.expected_primary_domain!r}, got {trace.primary_domain!r}",
        )
    if expectation.expected_issue_family and expectation.expected_issue_family not in trace.issue_signature:
        return FirstFailureDiagnosis(
            ISSUE_MAPPING_FAILURE, "confirmed",
            f"expected issue family {expectation.expected_issue_family!r} not in {trace.issue_signature}",
        )
    if expectation.forbidden_issue_families:
        hit = [f for f in expectation.forbidden_issue_families if f in trace.issue_signature]
        if hit:
            return FirstFailureDiagnosis(ISSUE_MAPPING_FAILURE, "confirmed", f"forbidden issue families present: {hit}")

    if expectation.expected_article or expectation.forbidden_domain or expectation.forbidden_title_fragments:
        if not trace.retrieval_queries:
            return FirstFailureDiagnosis(RETRIEVAL_PLAN_FAILURE, "confirmed", "no retrieval queries were generated")

    if expectation.expected_article:
        if not any(c.article == expectation.expected_article for c in trace.raw_candidates):
            return FirstFailureDiagnosis(
                RETRIEVAL_RANKING_FAILURE, "confirmed",
                f"article {expectation.expected_article!r} never appeared among raw retrieval candidates",
            )

    if expectation.forbidden_domain:
        leaked = [c for c in trace.guarded_candidates if c.domain == expectation.forbidden_domain]
        if leaked:
            return FirstFailureDiagnosis(RELEVANCE_GATE_FAILURE, "confirmed", f"forbidden domain {expectation.forbidden_domain!r} passed the gate")
    if expectation.forbidden_title_fragments:
        for candidate in trace.guarded_candidates:
            for fragment in expectation.forbidden_title_fragments:
                if fragment in (candidate.title or ""):
                    return FirstFailureDiagnosis(RELEVANCE_GATE_FAILURE, "confirmed", f"forbidden fragment {fragment!r} passed the gate ({candidate.title!r})")

    if expectation.expected_article:
        in_guarded = any(c.article == expectation.expected_article for c in trace.guarded_candidates)
        in_accepted = expectation.expected_article in [
            c.article for c in trace.guarded_candidates if c.id in trace.final_cited_source_ids
        ]
        if in_guarded and not in_accepted:
            return FirstFailureDiagnosis(
                EVIDENCE_SELECTION_FAILURE, "confirmed",
                f"article {expectation.expected_article!r} survived the gate but was not cited in the final answer",
            )

    if final_answer:
        if expectation.forbidden_answer_fragments:
            hit = [f for f in expectation.forbidden_answer_fragments if f in final_answer]
            if hit:
                return FirstFailureDiagnosis(WRITER_FAILURE, "confirmed", f"forbidden fragments in final answer: {hit}")
        if expectation.required_answer_fragments:
            missing = [f for f in expectation.required_answer_fragments if f not in final_answer]
            if missing:
                return FirstFailureDiagnosis(WRITER_FAILURE, "confirmed", f"required fragments missing from final answer: {missing}")

    any_expectation_set = any(
        v not in (None, [], "") for v in asdict(expectation).values()
    )
    if not any_expectation_set:
        return FirstFailureDiagnosis(NO_FAILURE_DETECTED, "uncertain", "no expectation fields supplied; nothing to check")
    return FirstFailureDiagnosis(NO_FAILURE_DETECTED, "confirmed", "all supplied expectations were satisfied")
