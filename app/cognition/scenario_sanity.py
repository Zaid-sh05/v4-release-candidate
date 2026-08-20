from __future__ import annotations

import re

from .language_match import contains_fuzzy, normalize_flexible
from .models import EvidenceItem, Event, Fact, SemanticSignal


_NON_PERSON_ACTOR_TERMS = {
    "اللابتوب", "لابتوب", "الحاسوب", "حاسوب", "الكمبيوتر", "كمبيوتر",
    "التلفون", "تلفون", "الهاتف", "هاتف", "الموبايل", "موبايل",
    "المصاري", "مصاري", "المال", "مال", "المبلغ", "مبلغ", "النقود", "نقود",
    "الدنانير", "دنانير", "القفل", "قفل", "الباب", "باب", "الشباك", "شباك",
    "السياره", "سياره", "السيارة", "المركبه", "مركبه", "المركبة",
    "السلاح", "سلاح", "السكين", "سكين", "المسدس", "مسدس",
    "البيت", "بيت", "المنزل", "منزل", "المكان", "مكان", "الارض", "الأرض",
    "العقد", "عقد", "الوثيقه", "وثيقه", "الوثيقة", "المستند", "مستند",
    "الكاميرا", "كاميرا", "التسجيل", "تسجيل", "الرساله", "رساله", "الرسالة",
    "ايضا", "أيضا", "انه", "إنه", "انها", "إنها", "اقواله", "أقواله", "اقوالها", "أقوالها",
    "شهادته", "شهادتها", "لاخبار", "لإخبار", "اخباره", "إخباره", "اخبار", "إخبار",
    "لاحقا", "لاحقاً", "مسرعا", "مسرعاً", "عندما", "بعدها", "قبلها", "المركز",
    "laptop", "computer", "phone", "mobile", "money", "cash", "amount",
    "lock", "door", "window", "car", "vehicle", "weapon", "knife", "gun",
    "house", "home", "property", "contract", "document", "camera", "cctv", "message",
    "then", "later", "there", "statement", "testimony",
}

_PAYMENT_CUES = (
    "دفع", "دفعت", "دفعه", "يدفع", "سدد", "سددت", "سداد",
    "حوّل", "حولت", "حوّلت", "تحويل", "تحويله", "حواله", "حوالة",
    "عربون", "دفعة", "دفعه مقدمة", "دفعه مقدمه",
    "paid", "pay", "payment", "transferred", "transfer", "bank transfer",
    "deposited", "deposit", "wired", "wire transfer",
)

_FALSE_TAKING_CONTEXTS = (
    "اخذ اقوال", "أخذ أقوال", "اخذ اقواله", "أخذ أقواله", "اخذ اقوالها", "أخذ أقوالها",
    "اخذ شهاده", "أخذ شهادة", "اخذ الشهاده", "أخذ الشهادة", "اخذ افاده", "أخذ إفادة",
    "taking a statement", "took his statement", "took her statement", "recorded his statement",
)

_EVENT_CUES: dict[str, tuple[str, ...]] = {
    "entry": ("دخل", "دخول", "تسلل", "اقتحم", "entered", "entry", "broke in", "broke into"),
    "breaking": ("كسر", "خلع", "حطم", "forced entry", "broke", "broke the lock", "broke the door"),
    "taking": ("أخذ", "اخذ", "اخد", "سرق", "استولى", "took", "stole", "stolen", "theft"),
    "violence": ("ضرب", "طعن", "اعتدى", "هاجم", "اطلق", "أطلق", "hit", "stabbed", "assaulted", "attacked", "shot"),
    "death": ("توفي", "توفى", "مات", "قتل", "وفاة", "died", "death", "killed"),
    "injury": ("اصيب", "أصيب", "انصاب", "جرح", "اصابة", "إصابة", "injured", "injury", "hurt"),
    "threat": ("هدد", "تهديد", "ابتزاز", "ابتز", "threatened", "threat", "blackmail", "extortion"),
    "termination": ("فصل", "طرد", "انهى عقد العمل", "أنهى عقد العمل", "فصلني", "fired", "dismissed", "terminated"),
    "judgment": ("صدر الحكم", "حكمت المحكمة", "الحكم", "judgment", "court ruled", "verdict"),
    "payment": _PAYMENT_CUES,
    "communication": ("قال", "قالت", "بحكي", "رسالة", "واتساب", "ابلغ", "أبلغ", "said", "told", "message", "whatsapp"),
    "driving": ("قاد", "يقود", "كان يقود", "بسوق", "قيادة", "سواقه", "سواقة", "driving", "drove", "was driving"),
    "collision": ("ارتطمت", "اصطدمت", "حادث سير", "تصادم", "صدم", "دهس", "crashed", "collision", "road accident", "hit the median"),
    "property_damage": ("تضررت", "تلفت", "اضرار", "أضرار", "عامود كهربائي", "عمود كهربائي", "damage", "damaged", "property damage"),
    "statement": ("اخبرهم", "أخبرهم", "اخذ اقوال", "أخذ أقوال", "اقواله", "أقواله", "شهاده", "شهادة", "شهد", "قال", "صرح", "statement", "testimony", "told police"),
    "money_demand": ("طلب مبلغ", "طلب منه مبلغ", "مقابل الشهاده", "مقابل الشهادة", "مقابل اقواله", "مقابل أقواله", "demanded money", "asked for money", "in exchange for testimony"),
}

_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u0600-\u06ff]+")


def _norm(value: str) -> str:
    return normalize_flexible(value or "").strip()


def _looks_like_non_person(label: str) -> bool:
    n = _norm(label)
    if not n:
        return True
    if n in {_norm(term) for term in _NON_PERSON_ACTOR_TERMS}:
        return True
    if n.replace(" ", "").isdigit():
        return True
    if any(token in n.split() for token in ("دينار", "دنانير", "jod", "jd")):
        return True
    return n in {"هو", "هي", "هم", "انا", "اني", "هذا", "هذه", "ذلك", "الذي", "التي"}


def prune_non_person_actors(case) -> bool:
    kept = []
    removed_ids: set[str] = set()
    for actor in getattr(case, "actors", []):
        role = getattr(actor, "role", "unknown")
        if role in {"person", "unknown", "other"} and _looks_like_non_person(getattr(actor, "label", "")):
            removed_ids.add(getattr(actor, "id", ""))
            continue
        kept.append(actor)
    if not removed_ids:
        return False
    case.actors = kept
    for event in getattr(case, "events", []):
        event.actors = [actor_id for actor_id in getattr(event, "actors", []) if actor_id not in removed_ids]
    return True


def prune_false_payment_events(case) -> bool:
    kept = []
    changed = False
    for event in getattr(case, "events", []):
        if event.event_type == "payment":
            span = (event.support_span or event.text or "").strip()
            if not span or not contains_fuzzy(span, *_PAYMENT_CUES):
                changed = True
                continue
        kept.append(event)
    if changed:
        case.events = kept
    return changed


def _is_false_taking_span(span: str) -> bool:
    return contains_fuzzy(span, *_FALSE_TAKING_CONTEXTS) and not contains_fuzzy(
        span, "سرق", "سرقه", "سرقة", "استولى", "stole", "theft", "stolen"
    )


def prune_false_taking_semantics(case) -> bool:
    changed = False
    kept_events = []
    for event in getattr(case, "events", []):
        if event.event_type == "taking" and _is_false_taking_span(event.support_span or event.text or ""):
            changed = True
            continue
        kept_events.append(event)
    if changed:
        case.events = kept_events

    residual = _norm(case.raw_message)
    for phrase in _FALSE_TAKING_CONTEXTS:
        residual = residual.replace(_norm(phrase), " ")
    property_taking_still_present = contains_fuzzy(
        residual, "سرق", "سرقه", "سرقة", "استولى", "اخذ", "أخذ", "اخد", "stole", "took", "theft"
    )
    if not property_taking_still_present:
        before = len(case.semantic_signals)
        case.semantic_signals = [signal for signal in case.semantic_signals if signal.code != "property.taking"]
        changed |= len(case.semantic_signals) != before
    return changed


def _token_windows_with_positions(text: str):
    matches = list(_TOKEN_RE.finditer(text or ""))
    for index, match in enumerate(matches):
        for width in range(1, 5):
            end = index + width
            if end > len(matches):
                break
            yield match.start(), (text or "")[match.start():matches[end - 1].end()]


def _event_type_position(message: str, event_type: str) -> int:
    cues = _EVENT_CUES.get(event_type)
    if not cues:
        return 10**9
    for position, window in _token_windows_with_positions(message):
        if contains_fuzzy(window, *cues):
            return position
    return 10**9


def _event_support_position(message: str, event) -> int:
    support = (event.support_span or "").strip()
    if support:
        direct = (message or "").find(support)
        if direct >= 0:
            relative = _event_type_position(support, event.event_type)
            return direct + relative if relative < 10**9 else direct
    return _event_type_position(message, event.event_type)


def reorder_events_by_narrative(case) -> bool:
    events = list(getattr(case, "events", []))
    if len(events) < 2:
        return False
    before = [(event.event_type, event.order) for event in events]
    events.sort(key=lambda event: (_event_support_position(case.raw_message, event), event.order))
    for index, event in enumerate(events, start=1):
        event.order = index
    case.events = events
    return before != [(event.event_type, event.order) for event in events]


def _clauses(text: str) -> list[str]:
    parts = re.split(r"[.!؟?؛،,\n\r]+|\s+(?:ثم|وبعدها|بعدها|لاحقا|لاحقاً)\s+", text or "")
    return [part.strip() for part in parts if len(part.strip()) >= 3]


def _has_event(case, event_type: str, support_span: str) -> bool:
    support_n = _norm(support_span)
    for event in getattr(case, "events", []):
        if event.event_type != event_type:
            continue
        existing = _norm(event.support_span or event.text)
        if support_n == existing or support_n in existing or existing in support_n:
            return True
    return False


def _add_event(case, event_type: str, span: str, *, intent: str = "unknown") -> bool:
    if not span or _has_event(case, event_type, span):
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
    case.semantic_signals.append(SemanticSignal(code=code, support_span=span, confidence=confidence, source="deterministic"))
    return True


def _add_evidence(case, kind: str, description: str, span: str) -> bool:
    key = (kind, _norm(span))
    if any((item.kind, _norm(item.support_span or item.description)) == key for item in case.evidence):
        return False
    case.evidence.append(EvidenceItem(
        kind=kind,
        description=description,
        source="deterministic",
        support_span=span,
        reliability="medium",
    ))
    return True


def _add_reported_fact(case, span: str) -> bool:
    n = _norm(span)
    if any(_norm(fact.text) == n for fact in case.facts):
        return False
    case.facts.append(Fact(text=span, category="statement", source="user", confidence="high", disputed=True))
    return True


def seed_lawyer_scenario_structure(case) -> bool:
    changed = False
    text = case.raw_message
    clauses = _clauses(text)

    for clause in clauses:
        if contains_fuzzy(clause, *_EVENT_CUES["collision"]):
            changed |= _add_event(case, "collision", clause, intent="accidental" if contains_fuzzy(clause, "بالغلط", "بالخطأ", "accidentally") else "unknown")
            changed |= _add_signal(case, "traffic.collision", clause)
        if contains_fuzzy(clause, *_EVENT_CUES["driving"]):
            changed |= _add_event(case, "driving", clause)
        if contains_fuzzy(clause, *_EVENT_CUES["property_damage"]):
            changed |= _add_event(case, "property_damage", clause)
            changed |= _add_evidence(case, "physical", "ضرر مادي مذكور في المركبة أو ممتلكات مرتبطة بالواقعة", clause)
        if contains_fuzzy(clause, *_EVENT_CUES["statement"]):
            changed |= _add_event(case, "statement", clause)
            changed |= _add_reported_fact(case, clause)
            if contains_fuzzy(clause, "الشرطه", "الشرطة", "المركز الامني", "المركز الأمني", "police"):
                changed |= _add_evidence(case, "official_record", "أقوال أو إفادة أمام الشرطة/المركز الأمني مذكورة في الرواية", clause)
            if contains_fuzzy(clause, "شهاده", "شهادة", "شهد", "testimony", "witness"):
                changed |= _add_evidence(case, "witness", "شهادة أو إفادة شخص مذكورة ضمن الوقائع", clause)
        if contains_fuzzy(clause, *_EVENT_CUES["money_demand"]):
            changed |= _add_event(case, "money_demand", clause)
            changed |= _add_signal(case, "statement.money_demand_link", clause)
            changed |= _add_reported_fact(case, clause)

    if contains_fuzzy(
        text,
        "لا يحمل رخصه", "لا يحمل رخصة", "لا يحمل اي منهما رخصه", "لا يحمل أي منهما رخصة",
        "بدون رخصه", "بدون رخصة", "ما معه رخصه", "ما معه رخصة", "unlicensed", "no driving licence", "no driving license",
    ):
        changed |= _add_signal(case, "traffic.unlicensed_status", "ذكر المستخدم عدم وجود رخصة قيادة")

    if contains_fuzzy(text, "تم اخذ اقوال", "تم أخذ أقوال", "اخذ اقواله", "أخذ أقواله", "police statement"):
        changed |= _add_signal(case, "procedure.police_statement", "ذكر المستخدم أخذ أقوال أمام الشرطة")

    recantation = contains_fuzzy(
        text,
        "شهادته الاولى", "شهادته الأولى", "اقواله الاولى", "أقواله الأولى", "غير اقواله", "غيّر أقواله",
        "رجع عن شهادته", "تراجع عن شهادته", "changed his statement", "recanted", "changed testimony",
    )
    coercion = contains_fuzzy(
        text,
        "تحت التهديد", "كان مهدد", "كان مهدداً", "اجبرني", "أجبرني", "بالاكراه", "بالإكراه",
        "under threat", "coerced", "forced to say",
    )
    if recantation or coercion:
        span = next((c for c in clauses if contains_fuzzy(c, "شهادته الاولى", "شهادته الأولى", "تحت التهديد", "غير اقواله", "رجع عن شهادته", "recanted", "coerced")), text[:500])
        changed |= _add_signal(case, "statement.changed_or_recanted", span)
        if coercion:
            changed |= _add_signal(case, "statement.coercion_claim", span)
        changed |= _add_reported_fact(case, span)

    driver_identity_statement = contains_fuzzy(
        text,
        "هو من كان يقود", "هو السائق", "كان يقود المركبه", "كان يقود المركبة",
        "كان السائق", "father was driving", "was the driver",
    )
    if driver_identity_statement and (recantation or coercion or contains_fuzzy(text, "شهاده", "شهادة", "اقوال", "أقوال")):
        changed |= _add_signal(case, "traffic.driver_identity_material", "هوية السائق محل أقوال متعارضة أو تحتاج تثبيت")

    return changed


def apply_scenario_sanity(case) -> bool:
    changed = False
    changed |= prune_non_person_actors(case)
    changed |= prune_false_payment_events(case)
    changed |= prune_false_taking_semantics(case)
    changed |= seed_lawyer_scenario_structure(case)
    changed |= reorder_events_by_narrative(case)
    return changed


__all__ = ["apply_scenario_sanity"]
