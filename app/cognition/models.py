from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Confidence = Literal["low", "medium", "high"]
DecisionAction = Literal["clarify", "retrieve", "answer"]


@dataclass
class Actor:
    id: str
    label: str
    role: str = "unknown"
    attributes: dict[str, str] = field(default_factory=dict)
    source: str = "deterministic"
    support_span: str | None = None


@dataclass
class Fact:
    text: str
    category: str
    source: str = "user"
    confidence: Confidence = "high"
    disputed: bool = False


@dataclass
class Event:
    order: int
    text: str
    event_type: str = "unknown"
    actors: list[str] = field(default_factory=list)
    target: str | None = None
    intent: str = "unknown"
    time_expression: str | None = None
    location: str | None = None
    source: str = "deterministic"
    support_span: str | None = None


@dataclass
class EvidenceItem:
    kind: str
    description: str
    supports: list[str] = field(default_factory=list)
    reliability: Confidence = "medium"
    source: str = "deterministic"
    support_span: str | None = None


@dataclass
class SemanticSignal:
    code: str
    support_span: str
    confidence: Confidence = "medium"
    source: str = "llm"


@dataclass
class CaseRelation:
    subject: str
    predicate: str
    object: str
    source_text: str
    confidence: Confidence = "medium"
    inferred: bool = False
    disputed: bool = False


@dataclass
class LegalHypothesis:
    code: str
    label_ar: str
    domain: str
    rationale: list[str] = field(default_factory=list)
    supporting_facts: list[str] = field(default_factory=list)
    missing_elements: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    confidence: float = 0.0
    status: Literal["candidate", "needs_clarification", "unlikely"] = "candidate"


@dataclass
class ClarifyingQuestion:
    id: str
    question_ar: str
    reason: str
    changes: list[str] = field(default_factory=list)
    priority: int = 50


@dataclass
class MaterialDecision:
    action: DecisionAction
    reason: str
    blockers: list[str] = field(default_factory=list)
    question_ids: list[str] = field(default_factory=list)
    safe_to_answer: bool = False


@dataclass
class CaseModel:
    raw_message: str
    language: str = "ar"
    user_goal: str = "legal_analysis"
    actors: list[Actor] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    semantic_signals: list[SemanticSignal] = field(default_factory=list)
    graph: list[CaseRelation] = field(default_factory=list)
    amounts: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    procedural_posture: str = "pre_case"
    domains: list[str] = field(default_factory=list)
    hypotheses: list[LegalHypothesis] = field(default_factory=list)
    clarifying_questions: list[ClarifyingQuestion] = field(default_factory=list)
    retrieval_queries: list[str] = field(default_factory=list)
    decision: MaterialDecision | None = None
    cognition_provider: str = "deterministic"
    cognition_model: str = ""
    cognition_ambiguities: list[dict[str, str | bool]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
