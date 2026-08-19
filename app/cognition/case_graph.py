from __future__ import annotations

import re

from .models import CaseModel, CaseRelation


def _actor_ids(case: CaseModel) -> dict[str, str]:
    return {a.label: a.id for a in case.actors}


def _find_actor_id(case: CaseModel, text: str) -> str | None:
    labels = sorted(_actor_ids(case), key=len, reverse=True)
    for label in labels:
        if label and label in text:
            return _actor_ids(case)[label]
    return None


def build_case_graph(case: CaseModel) -> list[CaseRelation]:
    """Build conservative subject-action-object relations from extracted events.

    This graph does not decide legal guilt or liability. It gives later cognition stages
    a structured description of what the user claims happened, who appears involved,
    and which relations are only inferred rather than explicitly stated.
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

    for event in case.events:
        predicate = action_map.get(event.event_type)
        if not predicate:
            continue

        subject = _find_actor_id(case, event.text)
        relation = CaseRelation(
            subject=subject or "unknown_actor",
            predicate=predicate,
            object="unknown_object",
            source_text=event.text,
            confidence="high" if subject else "medium",
            inferred=subject is None,
        )

        if event.event_type == "taking":
            m = re.search(r"(?:أخذ|اخذ|سرق)\s+([^،.]+)", event.text)
            if m:
                relation.object = m.group(1).strip()
        elif event.event_type == "violence":
            m = re.search(r"(?:ضرب|طعن|هاجم)\s+([^،.]+)", event.text)
            if m:
                relation.object = m.group(1).strip()
        elif event.event_type == "termination":
            relation.object = "employment_relationship"
        elif event.event_type == "judgment":
            relation.object = "judgment"
        elif event.event_type == "death":
            relation.object = "person_death"

        relations.append(relation)

    # Evidence relations are represented separately so reasoning can distinguish
    # an alleged event from a fact that is supported by a stated source of evidence.
    for evidence in case.evidence:
        relations.append(CaseRelation(
            subject="evidence",
            predicate="supports_or_relates_to",
            object=evidence.kind,
            source_text=evidence.description,
            confidence=evidence.reliability,
            inferred=False,
        ))

    return relations
