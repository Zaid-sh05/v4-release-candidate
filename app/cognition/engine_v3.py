from __future__ import annotations

import re

from .case_graph import build_case_graph
from .clarification import choose_questions
from .decision_gate import decide_next_action
from .engine_v21 import CaseCognitionEngine as BaseCaseCognitionEngine
from .issue_spotter import spot_issues
from .language_match import contains_fuzzy, normalize_flexible
from .models import EvidenceItem, Event, Fact, SemanticSignal
from .retrieval_planner import build_retrieval_queries


# Objects, filler words, pronouns and grammatical fragments that must never surface as people.
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


def _norm_label(value: str) -> str:
    return normalize_flexible(value or "").strip()


def _looks_like_non_person(label: str) -> bool:
    n = _norm_label(label)
    if not n:
        return True
    terms = {_norm_label(term) for term in _NON_PERSON_ACTOR_TERMS}
    if n in terms:
        return True
    if n.replace(" ", "").isdigit():
        return True
    if any(token in n.split() for token in ("دينار", "دنانير", "jod", "jd")):
        return True
    # Fragments produced by Arabic verb regexes are commonly pronouns/possessives rather than names.
    if n in {"هو", "هي", "هم", "انا", "اني", "إني", "هذا", "هذه", "ذلك", "الذي", "التي"}:
        return True
    return False


def _prune_non_person_actors(case) -> bool:
    kept = []
    removed_ids: set[str] = set()
    for actor in getattr(case, "actors", []):
        role = getattr(actor, "role", "unknown")
        label = getattr(actor, "label", "")
        if role in {"person", "unknown", "other"} and _looks_like_non_person(label):
            removed_ids.add(getattr(actor, "id", ""))
            continue
        kept.append(actor)

    if not removed_ids:
        return False

    case.actors = kept
    for event in getattr(case, "events", []):
        event.actors = [actor_id for actor_id in getattr(event, "actors", []) if actor_id not in removed_ids]
    return True


def _valid_payment_event(event) -> bool:
    span = (getattr(event, "support_span", None) or getattr(event, "text", "") or "").strip()
    return bool(span) and contains_fuzzy(span, *_PAYMENT_CUES)


def _prune_false_payment_events(case) -> bool:
    kept = []
    changed = False
    for event in getattr(case, "events", []):
        if getattr(event, "event_type", "") == "payment" and not _valid_payment_event(event):
            changed = True
            continue
        kept.append(event)
    if changed:
        case.events = kept
    return changed


def _token_windows_with_positions(text: str):
    matches = list(_TOKEN_RE.finditer(text or ""))
    for index, match in enumerate(matches):
        for width in range(1, 5):
            end = index + width
            if end > len(matches):
                break
            start_char = match.start()
            end_char = matches[end - 1].end()
            yield start_char, (text or "")[start_char:end_char]


def _event_type_position(message: str, event_type: str) -> int:
    cues = _EVENT_CUES.get(event_type)
    if not cues:
        return 10**9
    for position, window in _token_windows_with_positions(message):
        if contains_fuzzy(window, *cues):
            return position
    return 10**9


def _event_support_position(message: str, event) -> int:
    support = (getattr(event, "support_span", None) or "").strip()
    if support:
        direct = (message or "").find(support)
        if direct >= 0:
            relative = _event_type_position(support, getattr(event, "event_type", ""))
            if relative < 10**9:
                return direct + relative
            return direct
    return _event_type_position(message, getattr(event, "event_type", ""))


def _reorder_events_by_narrative(case) -> bool:
    events = list(getattr(case, "events", []))
    if len(events) < 2:
        return False
    before = [(getattr(event, "event_type", ""), getattr(event, "order", 0)) for event in events]
    events.sort(key=lambda event: (_event_support_position(case.raw_message, event), getattr(event, "order", 10**6)))
    for index, event in enumerate(events, start=1):
        event.order = index
    case.events = events
    after = [(getattr(event, "event_type", ""), getattr(event, "order", 0)) for event in events]
    return before != after


def _clauses(text: str) -> list[str]:
    parts = re.split(r"[.!؟?؛،,\n\r]+|\s+(?:ثم|وبعدها|بعدها|لاحقا|لاحقاً)\s+", text or "")
    return [part.strip() for part in parts if len(part.strip()) >= 3]


def _has_event(case, event_type: str, support_span: str) -> bool:
    support_n = normalize_flexible(support_span)
    return any(
        event.event_type == event_type
        and (
            support_n == normalize_flexible(event.support_span or event.text)
            or support_n in normalize_flexible(event.support_span or event.text)
            or normalize_flexible(event.support_span or event.text) in support_n
        )
        for event in getattr(case, "events", [])
    )


def _add_event(case, event_type: str, span: str, *, intent: str = "unknown") -> bool:
    if not span or _has_event(case, event_type, span):
        return False
    case.events.append(
        Event(
            order=len(case.events) + 1,
            text=span,
            event_type=event_type,
            intent=intent,
            source="deterministic",
            support_span=span,
        )
    )
    return True


def _add_signal(case, code: str, span: str, confidence: str = "high") -> bool:
    if any(signal.code == code for signal in getattr(case, "semantic_signals", [])):
        return False
    case.semantic_signals.append(
        SemanticSignal(code=code, support_span=span, confidence=confidence, source="deterministic")
    )
    return True


def _add_evidence(case, kind: str, description: str, span: str) -> bool:
    key = (kind, normalize_flexible(span))
    if any((item.kind, normalize_flexible(item.support_span or item.description)) == key for item in getattr(case, "evidence", [])):
        return False
    case.evidence.append(
        EvidenceItem(
            kind=kind,
            description=description,
            source="deterministic",
            support_span=span,
            reliability="medium",
        )
    )
    return True


def _add_reported_fact(case, span: str, *, disputed: bool = True) -> bool:
    n = normalize_flexible(span)
    if any(normalize_flexible(fact.text) == n for fact in getattr(case, "facts", [])):
        return False
    case.facts.append(Fact(text=span, category="statement", source="user", confidence="high", disputed=disputed))
    return True


def _seed_lawyer_scenario_structure(case) -> bool:
    """Add neutral, legally useful structure for complex real-world narratives.

    These are factual/semantic labels only. They deliberately avoid naming an offence or deciding
    whether a statement is true, false, admissible, voluntary, or legally sufficient.
    """
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
            changed |= _add_reported_fact(case, clause, disputed=True)
            if contains_fuzzy(clause, "الشرطه", "الشرطة", "المركز الامني", "المركز الأمني", "police"):
                changed |= _add_evidence(case, "official_record", "أقوال أو إفادة أمام الشرطة/المركز الأمني مذكورة في الرواية", clause)
            if contains_fuzzy(clause, "شهاده", "شهادة", "شهد", "testimony", "witness"):
                changed |= _add_evidence(case, "witness", "شهادة أو إفادة شخص مذكورة ضمن الوقائع", clause)
        if contains_fuzzy(clause, *_EVENT_CUES["money_demand"]):
            changed |= _add_event(case, "money_demand", clause)
            changed |= _add_signal(case, "statement.money_demand_link", clause)
            changed |= _add_reported_fact(case, clause, disputed=True)

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
        changed |= _add_reported_fact(case, span, disputed=True)

    if contains_fuzzy(text, "من كان يقود", "هو السائق", "كان يقود المركبه", "كان يقود المركبة", "السائق", "driver") and (
        recantation or contains_fuzzy(text, "والده انه هو من كان يقود", "والده أنه هو من كان يقود", "father was driving")
    ):
        changed |= _add_signal(case, "traffic.driver_identity_material", "هوية السائق محل أقوال مذكورة في الرواية", "high")

    return changed


def _recompute_case_reasoning(case) -> None:
    case.hypotheses = spot_issues(case)
    case.domains = list(dict.fromkeys(h.domain for h in case.hypotheses)) or ["general"]
    case.clarifying_questions = choose_questions(case)
    case.retrieval_queries = build_retrieval_queries(case)
    case.decision = decide_next_action(case)
    case.graph = build_case_graph(case)


class CaseCognitionEngine(BaseCaseCognitionEngine):
    """Scenario-fidelity layer for lawyer-oriented case analysis."""

    def analyze(self, message: str, language: str = "ar"):
        case = super().analyze(message, language)

        actors_changed = _prune_non_person_actors(case)
        payments_changed = _prune_false_payment_events(case)
        structure_changed = _seed_lawyer_scenario_structure(case)
        events_reordered = _reorder_events_by_narrative(case)

        if actors_changed or payments_changed or structure_changed or events_reordered:
            _recompute_case_reasoning(case)

        return case


__all__ = ["CaseCognitionEngine"]
