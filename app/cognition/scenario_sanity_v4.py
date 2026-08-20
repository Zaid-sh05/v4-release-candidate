from __future__ import annotations

import re

from .language_match import normalize_flexible
from .models import EvidenceItem, Event, Fact, SemanticSignal
from .scenario_sanity import apply_scenario_sanity as base_apply_scenario_sanity


def _n(text: str) -> str:
    return normalize_flexible(text or "")


def _has_fragment(text: str, *fragments: str) -> bool:
    n = _n(text)
    return any(_n(fragment) in n for fragment in fragments if fragment)


def _clauses(text: str) -> list[str]:
    parts = re.split(r"[.!؟?؛،,\n\r]+|\s+(?:ثم|وبعدها|بعدها|لاحقا|لاحقاً|later|then)\s+", text or "", flags=re.IGNORECASE)
    return [part.strip() for part in parts if len(part.strip()) >= 3]


def _find_clause(text: str, *fragments: str) -> str:
    for clause in _clauses(text):
        if _has_fragment(clause, *fragments):
            return clause
    return (text or "").strip()[:600]


def _has_event(case, event_type: str) -> bool:
    return any(event.event_type == event_type for event in case.events)


def _add_event(case, event_type: str, span: str, *, intent: str = "unknown") -> bool:
    if not span or _has_event(case, event_type):
        return False
    case.events.append(Event(
        order=len(case.events) + 1,
        text=span,
        event_type=event_type,
        intent=intent,
        source="deterministic",
        support_span=span,
    ))
    return True


def _add_signal(case, code: str, span: str, confidence: str = "high") -> bool:
    if any(signal.code == code for signal in case.semantic_signals):
        return False
    case.semantic_signals.append(SemanticSignal(
        code=code,
        support_span=span,
        confidence=confidence,
        source="deterministic",
    ))
    return True


def _add_evidence(case, kind: str, description: str, span: str) -> bool:
    key = (kind, _n(span))
    if any((item.kind, _n(item.support_span or item.description)) == key for item in case.evidence):
        return False
    case.evidence.append(EvidenceItem(
        kind=kind,
        description=description,
        reliability="medium",
        source="deterministic",
        support_span=span,
    ))
    return True


def _add_disputed_fact(case, span: str) -> bool:
    if not span:
        return False
    key = _n(span)
    for fact in case.facts:
        if _n(fact.text) == key:
            if not fact.disputed:
                fact.disputed = True
                return True
            return False
    case.facts.append(Fact(text=span, category="statement", source="user", confidence="high", disputed=True))
    return True


def _remove_negated_payment_events(case) -> bool:
    """A refusal/denial to pay is not a completed payment event."""
    changed = False
    kept = []
    positive_markers = (
        "دفعت له", "دفعت المبلغ", "حولت له", "حوّلت له", "تم التحويل", "سددت له",
        "i paid", "paid him", "transferred", "wired", "sent the money",
    )
    negative_markers = (
        "لم ادفع", "لم أدفع", "ما دفعت", "رفضت الدفع", "رفض اعطاؤه", "رفض إعطاؤه",
        "لم يحول", "لم أحول", "did not pay", "didn't pay", "refused to pay", "no money was paid",
    )
    for event in case.events:
        if event.event_type != "payment":
            kept.append(event)
            continue
        span = event.support_span or event.text or ""
        has_positive = _has_fragment(span, *positive_markers)
        has_negative = _has_fragment(span, *negative_markers)
        if has_negative and not has_positive:
            changed = True
            continue
        kept.append(event)
    if changed:
        case.events = kept
    return changed


def _seed_inflected_core_events(case) -> bool:
    text = case.raw_message
    changed = False

    if not _has_event(case, "collision") and _has_fragment(
        text, "ارتطم", "اصطدم", "صدمت", "صدم", "دهس", "حادث سير", "حادث مروري",
        "crashed", "collision", "road accident", "traffic accident", "hit the median", "hit the curb",
    ):
        span = _find_clause(text, "ارتطم", "اصطدم", "صدمت", "صدم", "دهس", "crashed", "collision", "hit the")
        changed |= _add_event(case, "collision", span)
        changed |= _add_signal(case, "traffic.collision", span)

    if not _has_event(case, "injury") and _has_fragment(
        text, "انصاب", "اصيب", "أصيب", "جرح", "اصابه", "إصابة", "نزف", "injured", "injury", "hurt", "wound",
    ):
        span = _find_clause(text, "انصاب", "اصيب", "أصيب", "جرح", "اصابه", "إصابة", "injured", "hurt", "wound")
        changed |= _add_event(case, "injury", span)
        changed |= _add_signal(case, "event.injury", span)

    if not _has_event(case, "threat") and _has_fragment(
        text, "هدد", "تهديد", "ابتز", "ابتزاز", "تحت التهديد", "threat", "threatened", "blackmail", "extortion",
    ):
        span = _find_clause(text, "هدد", "تهديد", "ابتز", "ابتزاز", "تحت التهديد", "threat", "threatened")
        changed |= _add_event(case, "threat", span)
        changed |= _add_signal(case, "event.threat", span)

    if not _has_event(case, "property_damage") and _has_fragment(
        text, "تضرر", "تلف", "اضرار", "أضرار", "عمود كهرب", "عامود كهرب", "damaged", "damage", "property damage",
    ):
        span = _find_clause(text, "تضرر", "تلف", "اضرار", "أضرار", "عمود كهرب", "عامود كهرب", "damaged", "damage")
        changed |= _add_event(case, "property_damage", span)
        changed |= _add_evidence(case, "physical", "ضرر مادي مذكور ضمن الرواية", span)

    if not _has_event(case, "driving") and _has_fragment(
        text, "بسوق", "يقود", "قاد", "قياد", "سواق", "driving", "drove", "was driving", "driver",
    ):
        span = _find_clause(text, "بسوق", "يقود", "قاد", "قياد", "سواق", "driving", "drove", "was driving")
        changed |= _add_event(case, "driving", span)

    return changed


def _seed_unlicensed_status(case) -> bool:
    text = case.raw_message
    markers = (
        "بدون رخصه", "بدون رخصة", "لا يحمل رخصه", "لا يحمل رخصة", "لا يحمل اي منهما رخصه",
        "لا يحمل أي منهما رخصة", "ما معه رخصه", "ما معه رخصة", "غير مرخص للقياده", "غير مرخص للقيادة",
        "unlicensed", "no driving license", "no driving licence", "without a driving license", "without a driving licence",
        "did not have a driving license", "did not have a driving licence", "neither had a driving license", "neither had a driving licence",
        "neither had a license", "neither had a licence",
    )
    if not _has_fragment(text, *markers):
        return False
    return _add_signal(case, "traffic.unlicensed_status", _find_clause(text, *markers))


def _seed_statement_procedure(case) -> bool:
    text = case.raw_message
    changed = False
    police = _has_fragment(text, "الشرطه", "الشرطة", "المركز الامني", "المركز الأمني", "police", "police station")
    statement = _has_fragment(
        text, "اقوال", "أقوال", "اقوالي", "أقوالي", "افاده", "إفادة", "شهاده", "شهادة", "شهد",
        "statement", "testimony", "told police", "said he was driving",
    )
    if police and statement:
        span = _find_clause(text, "اقوال", "أقوال", "اقوالي", "أقوالي", "افاده", "إفادة", "شهاده", "شهادة", "statement", "testimony", "police")
        changed |= _add_signal(case, "procedure.police_statement", span)
        changed |= _add_evidence(case, "official_record", "أقوال أو إفادة أمام الشرطة/المركز الأمني مذكورة في الرواية", span)
        if not _has_event(case, "statement"):
            changed |= _add_event(case, "statement", span)

    changed_statement = _has_fragment(
        text, "رجع عن شهاد", "تراجع عن شهاد", "غير اقوال", "غيّر أقوال", "غير شهاد", "غيّر شهاد",
        "شهادته الاولى", "شهادته الأولى", "اقواله الاولى", "أقواله الأولى",
        "changed his statement", "changed her statement", "changed the statement", "recanted", "later changed his statement",
    )
    if changed_statement:
        span = _find_clause(text, "رجع عن شهاد", "تراجع عن شهاد", "غير اقوال", "غير شهاد", "شهادته الاولى", "شهادته الأولى", "changed his statement", "recanted")
        changed |= _add_signal(case, "statement.changed_or_recanted", span)
        changed |= _add_disputed_fact(case, span)

    coercion = _has_fragment(
        text, "تحت التهديد", "بالاكراه", "بالإكراه", "اجبر", "أجبر", "مهدد", "under threat", "coerced", "forced to say",
    )
    if coercion:
        span = _find_clause(text, "تحت التهديد", "بالاكراه", "بالإكراه", "اجبر", "أجبر", "under threat", "coerced", "forced to say")
        changed |= _add_signal(case, "statement.coercion_claim", span)
        changed |= _add_disputed_fact(case, span)

    driver_identity = _has_fragment(
        text, "هو من كان يقود", "هو السائق", "كان السائق", "كان يقود المركبه", "كان يقود المركبة",
        "was driving", "was the driver", "father said he was driving",
    )
    if driver_identity and (changed_statement or coercion or statement):
        changed |= _add_signal(case, "traffic.driver_identity_material", _find_clause(text, "هو من كان يقود", "هو السائق", "كان يقود", "was driving", "was the driver"))

    return changed


def _seed_testimony_money_demand(case) -> bool:
    text = case.raw_message
    request = _has_fragment(text, "طلب", "طالب", "asked", "demanded")
    money = _has_fragment(text, "مبلغ", "دينار", "مال", "مصاري", "money", "cash", "payment", "benefit")
    testimony = _has_fragment(text, "شهاده", "شهادة", "اقوال", "أقوال", "افاده", "إفادة", "testimony", "statement")
    exchange = _has_fragment(text, "مقابل", "نظير", "in exchange", "for keeping", "to keep", "لتغيير", "حتى يغير", "حتى يثبت")
    if not (request and money and testimony and exchange):
        return False

    span = _find_clause(text, "طلب", "asked", "demanded", "مقابل", "in exchange")
    changed = _add_event(case, "money_demand", span)
    changed |= _add_signal(case, "statement.money_demand_link", span)
    changed |= _add_disputed_fact(case, span)
    return changed


def apply_scenario_sanity(case) -> bool:
    changed = base_apply_scenario_sanity(case)
    changed |= _remove_negated_payment_events(case)
    changed |= _seed_inflected_core_events(case)
    changed |= _seed_unlicensed_status(case)
    changed |= _seed_statement_procedure(case)
    changed |= _seed_testimony_money_demand(case)

    # Restore chronological order after supplemental events are added.
    if changed:
        raw = case.raw_message
        def position(event):
            span = event.support_span or event.text or ""
            pos = raw.find(span)
            return pos if pos >= 0 else 10**9
        case.events.sort(key=lambda event: (position(event), event.order))
        for index, event in enumerate(case.events, start=1):
            event.order = index
    return changed


__all__ = ["apply_scenario_sanity"]
