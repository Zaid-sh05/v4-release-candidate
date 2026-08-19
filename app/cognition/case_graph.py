from __future__ import annotations

import re

from .models import CaseModel, CaseRelation


def _actor_ids(case: CaseModel) -> dict[str, str]:
    return {a.label: a.id for a in case.actors}


def _find_actor_id(case: CaseModel, text: str) -> str | None:
    actor_ids = _actor_ids(case)
    for label in sorted(actor_ids, key=len, reverse=True):
        if label and label in text:
            return actor_ids[label]
    return None


def _intent_marker(text: str) -> str | None:
    low = text.lower()
    if any(x in low for x in ["بالغلط", "دون قصد", "غير مقصود", "ما كنت أقصد", "ما كنت اقصد", "خطأ", "خطا"]):
        return "unintentional"
    if any(x in low for x in ["سبق الإصرار", "سبق الاصرار", "خطط", "انتظره", "حضّر", "حضر له"]):
        return "premeditated"
    if any(x in low for x in ["عمداً", "عمدا", "قصداً", "قصدا", "متعمد", "تعمد"]):
        return "intentional"
    if any(x in low for x in ["دفاعاً عن نفسي", "دفاعا عن نفسي", "دفاع شرعي", "هاجمني"]):
        return "self_defense_claim"
    return None


def _object_for_event(event_type: str, text: str) -> str:
    if event_type == "taking":
        m = re.search(r"(?:أخذ|اخذ|سرق)\s+([^،.]+)", text)
        return m.group(1).strip() if m else "property"
    if event_type == "violence":
        m = re.search(r"(?:ضرب|طعن|هاجم|أطلق النار على|اطلق النار على)\s+([^،.]+)", text)
        return m.group(1).strip() if m else "person"
    if event_type == "entry":
        m = re.search(r"(?:دخل|الدخول إلى|الدخول الى|دخول)\s+([^،.]+)", text)
        return m.group(1).strip() if m else "place"
    if event_type == "breaking":
        m = re.search(r"(?:كسر|خلع)\s+([^،.]+)", text)
        return m.group(1).strip() if m else "barrier_or_lock"
    if event_type == "termination":
        return "employment_relationship"
    if event_type == "judgment":
        return "judgment"
    if event_type == "death":
        return "person_death"
    if event_type == "injury":
        return "person_injury"
    if event_type == "threat":
        return "person_or_interest"
    if event_type == "payment":
        return "payment"
    if event_type == "communication":
        return "communication"
    return "unknown_object"


def build_case_graph(case: CaseModel) -> list[CaseRelation]:
    """Build a conservative graph of the user's account of the case.

    LLM-enriched fields are accepted only after grounding against the user's original
    message. The graph is descriptive, not a finding of guilt, liability, or law.
    """
    relations: list[CaseRelation] = []
    action_map = {
        "entry": "entered",
        "breaking": "broke_or_forced",
        "taking": "took_property",
        "violence": "used_force",
        "death": "death_occurred",
        "injury": "injury_occurred",
        "threat": "threatened",
        "termination": "terminated_employment",
        "judgment": "judgment_issued",
        "payment": "payment_occurred",
        "communication": "communicated",
    }

    event_node_ids: list[str] = []
    for event in case.events:
        predicate = action_map.get(event.event_type)
        if not predicate:
            continue
        event_node = f"event:{event.order}"
        event_node_ids.append(event_node)
        subject = event.actors[0] if event.actors else _find_actor_id(case, event.text)
        object_value = event.target or _object_for_event(event.event_type, event.text)
        relations.append(CaseRelation(
            subject=subject or "unknown_actor",
            predicate=predicate,
            object=object_value,
            source_text=event.support_span or event.text,
            confidence="high" if subject else "medium",
            inferred=subject is None,
        ))
        relations.append(CaseRelation(
            subject=event_node,
            predicate="event_type",
            object=event.event_type,
            source_text=event.support_span or event.text,
            confidence="high",
        ))
        intent = event.intent if event.intent != "unknown" else _intent_marker(event.text)
        if intent == "accidental":
            intent = "unintentional"
        if intent:
            relations.append(CaseRelation(
                subject=event_node,
                predicate="mental_state_indicator",
                object=intent,
                source_text=event.support_span or event.text,
                confidence="high" if event.intent != "unknown" else "medium",
                inferred=event.intent == "unknown",
            ))
        if event.location:
            relations.append(CaseRelation(
                subject=event_node,
                predicate="location",
                object=event.location,
                source_text=event.support_span or event.text,
                confidence="medium",
            ))
        if event.time_expression:
            relations.append(CaseRelation(
                subject=event_node,
                predicate="time_expression",
                object=event.time_expression,
                source_text=event.support_span or event.text,
                confidence="medium",
            ))

    for left, right in zip(event_node_ids, event_node_ids[1:]):
        relations.append(CaseRelation(
            subject=left,
            predicate="occurred_before",
            object=right,
            source_text="ترتيب مستخلص من سرد المستخدم",
            confidence="medium",
            inferred=True,
        ))

    marker = _intent_marker(case.raw_message)
    if marker and not any(r.predicate == "mental_state_indicator" and r.object == marker for r in relations):
        subject = _find_actor_id(case, case.raw_message) or "unknown_actor"
        relations.append(CaseRelation(
            subject=subject,
            predicate="mental_state_indicator",
            object=marker,
            source_text=case.raw_message,
            confidence="high",
            inferred=False,
        ))

    for index, evidence in enumerate(case.evidence, start=1):
        evidence_node = f"evidence:{index}"
        relations.append(CaseRelation(
            subject=evidence_node,
            predicate="evidence_kind",
            object=evidence.kind,
            source_text=evidence.support_span or evidence.description,
            confidence=evidence.reliability,
        ))
        if case.events:
            relations.append(CaseRelation(
                subject=evidence_node,
                predicate="may_support",
                object="event:1" if len(case.events) == 1 else "case_events",
                source_text=evidence.support_span or evidence.description,
                confidence="medium",
                inferred=True,
            ))

    return relations
