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
    return "unknown_object"


def build_case_graph(case: CaseModel) -> list[CaseRelation]:
    """Build a conservative graph of the *user's account* of the case.

    The graph separates alleged conduct, mental-state indicators, timeline order and
    evidence. It does not turn allegations into proven facts and never decides guilt.
    """
    relations: list[CaseRelation] = []
    action_map = {
        "entry": "entered",
        "breaking": "broke_or_forced",
        "taking": "took_property",
        "violence": "used_force",
        "death": "death_occurred",
        "termination": "terminated_employment",
        "judgment": "judgment_issued",
    }

    event_node_ids: list[str] = []
    for event in case.events:
        predicate = action_map.get(event.event_type)
        if not predicate:
            continue
        event_node = f"event:{event.order}"
        event_node_ids.append(event_node)
        subject = _find_actor_id(case, event.text)
        relations.append(CaseRelation(
            subject=subject or "unknown_actor",
            predicate=predicate,
            object=_object_for_event(event.event_type, event.text),
            source_text=event.text,
            confidence="high" if subject else "medium",
            inferred=subject is None,
        ))
        relations.append(CaseRelation(
            subject=event_node,
            predicate="event_type",
            object=event.event_type,
            source_text=event.text,
            confidence="high",
        ))

    # Preserve narrative order. This matters in self-defence, escape, entry and appeal facts.
    for left, right in zip(event_node_ids, event_node_ids[1:]):
        relations.append(CaseRelation(
            subject=left,
            predicate="occurred_before",
            object=right,
            source_text="ترتيب مستخلص من سرد المستخدم",
            confidence="medium",
            inferred=True,
        ))

    # Mental state stays a claim/indicator until legal analysis verifies its significance.
    marker = _intent_marker(case.raw_message)
    if marker:
        subject = _find_actor_id(case, case.raw_message) or "unknown_actor"
        relations.append(CaseRelation(
            subject=subject,
            predicate="mental_state_indicator",
            object=marker,
            source_text=case.raw_message,
            confidence="high",
            inferred=False,
        ))

    # Evidence is represented separately from conduct so an allegation is never silently
    # upgraded into a proven fact merely because evidence was mentioned.
    for index, evidence in enumerate(case.evidence, start=1):
        evidence_node = f"evidence:{index}"
        relations.append(CaseRelation(
            subject=evidence_node,
            predicate="evidence_kind",
            object=evidence.kind,
            source_text=evidence.description,
            confidence=evidence.reliability,
        ))
        if case.events:
            relations.append(CaseRelation(
                subject=evidence_node,
                predicate="may_support",
                object="event:1" if len(case.events) == 1 else "case_events",
                source_text=evidence.description,
                confidence="medium",
                inferred=True,
            ))

    return relations
