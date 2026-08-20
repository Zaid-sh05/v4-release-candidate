from __future__ import annotations

import re

from .case_graph import build_case_graph
from .engine_v21 import CaseCognitionEngine as BaseCaseCognitionEngine
from .language_match import contains_fuzzy, normalize_flexible


# Things that can legitimately be a target/evidence/property in a legal narrative but
# must never be surfaced as a human actor merely because they follow an Arabic verb.
# This is deliberately a semantic sanity list, not a legal classification list.
_NON_PERSON_ACTOR_TERMS = {
    "اللابتوب", "لابتوب", "الحاسوب", "حاسوب", "الكمبيوتر", "كمبيوتر",
    "التلفون", "تلفون", "الهاتف", "هاتف", "الموبايل", "موبايل",
    "المصاري", "مصاري", "المال", "مال", "المبلغ", "مبلغ", "النقود", "نقود",
    "الدنانير", "دنانير", "القفل", "قفل", "الباب", "باب", "الشباك", "شباك",
    "السياره", "سياره", "السيارة", "المركبه", "مركبه", "المركبة",
    "السلاح", "سلاح", "السكين", "سكين", "المسدس", "مسدس",
    "البيت", "بيت", "المنزل", "منزل", "المكان", "مكان",
    "العقد", "عقد", "الوثيقه", "وثيقه", "الوثيقة", "المستند", "مستند",
    "الكاميرا", "كاميرا", "التسجيل", "تسجيل", "الرساله", "رساله", "الرسالة",
    "laptop", "computer", "phone", "mobile", "money", "cash", "amount",
    "lock", "door", "window", "car", "vehicle", "weapon", "knife", "gun",
    "house", "home", "property", "contract", "document", "camera", "cctv", "message",
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
    # Currency/value expressions are objects/amounts, never people.
    if any(token in n.split() for token in ("دينار", "دنانير", "jod", "jd")):
        return True
    return False


def _prune_non_person_actors(case) -> bool:
    """Reject obvious objects accidentally extracted as human actors.

    Role-bearing institutions/people recognized as police, employer, worker, prosecutor,
    court, victim or suspect are preserved. The guard is aimed at generic ``person``
    extractions such as "أخذ اللابتوب" -> actor="اللابتوب".
    """
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
    # Currency or a bare amount is a fact/value. It becomes a payment event only if
    # the user's own text contains a payment/transfer act.
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
        # Up to four tokens covers the longest event cues while keeping fuzzy matching
        # bounded and deterministic.
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
            # A long support span may be an entire sentence containing several events.
            # Add the position of this event's own cue inside that sentence when possible.
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


class CaseCognitionEngine(BaseCaseCognitionEngine):
    """Cognition V3 scenario-fidelity layer for lawyer-oriented case analysis.

    The upstream cognition engine remains responsible for language understanding and issue
    spotting. This layer performs deterministic semantic sanity checks after optional LLM
    enrichment so objects do not become people, amounts do not become payments, and the
    event sequence follows the user's narrative as closely as the grounded text permits.
    """

    def analyze(self, message: str, language: str = "ar"):
        case = super().analyze(message, language)

        actors_changed = _prune_non_person_actors(case)
        payments_changed = _prune_false_payment_events(case)
        events_reordered = _reorder_events_by_narrative(case)

        if actors_changed or payments_changed or events_reordered:
            # Relations depend on actor/event identity and order. Rebuild only the graph;
            # the legal hypotheses themselves are intentionally not recomputed from these
            # presentation-level sanity fixes, avoiding accidental changes to safety gates.
            case.graph = build_case_graph(case)

        return case


__all__ = ["CaseCognitionEngine"]
