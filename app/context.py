from __future__ import annotations

import re

from .models import RouteResult
from .text import normalize_ar


_SMALLTALK = {
    'مرحبا', 'مرحبا بك', 'اهلا', 'هلا', 'كيفك', 'شكرا', 'يسلمو', 'تمام', 'اوكي',
    'hi', 'hello', 'hey', 'thanks', 'thank you', 'ok', 'okay',
}

_CORRECTION_MARKERS = (
    'قصدي', 'اقصد', 'أقصد', 'انا بسال عن', 'أنا بسأل عن', 'انا بسأل عن', 'مش عن',
    'المقصود', 'تصحيح', 'صحح', 'خليني اوضح', 'خليني أوضح',
    'i mean', 'what i mean', 'i am asking about', "i'm asking about", 'correction',
)

_EXPLICIT_NEW_CASE_MARKERS = (
    'سؤال ثاني', 'سؤال اخر', 'سؤال آخر', 'موضوع ثاني', 'موضوع اخر', 'موضوع آخر',
    'حالة ثانية', 'حاله ثانيه', 'حالة اخرى', 'حالة أخرى', 'مثال ثاني', 'مثال اخر', 'مثال آخر',
    'قضية ثانية', 'قضيه ثانيه', 'new question', 'another question', 'new case', 'another case',
)

# Deliberately specific topic cues. They are used only to decide whether a message starts a
# different conversation thread; they are never used as legal authority or legal classification.
_TOPIC_CUES: dict[str, tuple[str, ...]] = {
    'traffic': (
        'حادث سير', 'كنت بسوق', 'بسوق', 'دهست', 'تصادم', 'سياره', 'سيارة', 'مركبه', 'مركبة',
        'رخصه', 'رخصة', 'اشاره حمراء', 'إشارة حمراء', 'road accident', 'driving', 'driver', 'vehicle',
    ),
    'cyber': (
        'جرائم الكترونيه', 'جرائم إلكترونية', 'ابتزاز الكتروني', 'ابتزاز إلكتروني', 'فيسبوك',
        'واتساب', 'انستغرام', 'منصه تواصل', 'منصة تواصل', 'نشر صور', 'حساب', 'facebook',
        'whatsapp', 'instagram', 'online blackmail', 'cybercrime', 'social media',
    ),
    'labor': (
        'فصلني', 'صاحب العمل', 'عقد عمل', 'راتب', 'اجري', 'أجري', 'موظف', 'عامل',
        'fired', 'employer', 'employee', 'employment', 'salary',
    ),
    'personal_status': (
        'طلاق', 'زواج', 'نفقه', 'نفقة', 'حضانه', 'حضانة', 'مهر', 'محكمه شرعيه', 'محكمة شرعية',
        'divorce', 'marriage', 'custody', 'alimony', 'sharia',
    ),
    'commercial': (
        'شركه', 'شركة', 'مساهم', 'حصص', 'سجل تجاري', 'company', 'shareholder', 'llc',
    ),
    'criminal': (
        'سرقه', 'سرقة', 'كسر قفل', 'اقتحم', 'قتل', 'طعن', 'ضرب', 'اعتداء', 'theft', 'stole',
        'broke into', 'murder', 'assault',
    ),
}

_CLARIFICATION_CONCEPTS: dict[str, tuple[str, ...]] = {
    'permission': ('اذن', 'إذن', 'موافقه', 'موافقة', 'رضا', 'consent', 'permission'),
    'night': ('ليلا', 'ليلاً', 'ليل', 'نهارا', 'نهار', 'night', 'daytime'),
    'occupancy': ('مسكون', 'مأهول', 'اهله', 'أهله', 'occupied', 'residential'),
    'ownership': ('ملكيه', 'ملكية', 'المال ل', 'المالك', 'ملكه', 'ملكه', 'owned', 'ownership'),
    'employment_reason': ('سبب الفصل', 'السبب', 'انذار', 'إنذار', 'notice', 'reason for termination'),
    'dates': ('تاريخ', 'متى', 'يوم', 'شهر', 'date', 'when'),
    'injury': ('اصابه', 'إصابة', 'انصاب', 'مستشفى', 'injured', 'hospital'),
    'licence': ('رخصه', 'رخصة', 'ترخيص', 'licence', 'license'),
}


def _n(text: str) -> str:
    return normalize_ar(text or '')


def _is_smalltalk_message(message: str) -> bool:
    value = _n(message).strip()
    return value in {_n(x) for x in _SMALLTALK}


def _recent_user_messages(history: list[dict], limit: int = 5) -> list[str]:
    msgs = [
        (m.get('content') or '').strip()
        for m in history
        if m.get('role') == 'user' and (m.get('content') or '').strip()
    ]
    substantive = [m for m in msgs if not _is_smalltalk_message(m)]
    return substantive[-limit:]


def _last_assistant_message(history: list[dict]) -> str:
    for item in reversed(history):
        if item.get('role') == 'assistant' and (item.get('content') or '').strip():
            return (item.get('content') or '').strip()
    return ''


def _contains_any(message: str, values: tuple[str, ...]) -> bool:
    n = _n(message)
    return any(_n(value) in n for value in values)


def _topic_scores(message: str) -> dict[str, int]:
    n = _n(message)
    scores: dict[str, int] = {}
    for domain, cues in _TOPIC_CUES.items():
        score = sum(1 for cue in cues if _n(cue) in n)
        if score:
            scores[domain] = score
    return scores


def _dominant_topic(message: str) -> str | None:
    scores = _topic_scores(message)
    if not scores:
        return None
    return max(scores, key=lambda key: scores[key])


def _looks_like_correction(message: str) -> bool:
    return _contains_any(message, _CORRECTION_MARKERS)


def _looks_like_explicit_new_case(message: str) -> bool:
    return _contains_any(message, _EXPLICIT_NEW_CASE_MARKERS)


def _answers_prior_clarification(message: str, last_assistant: str) -> bool:
    """Detect replies that resolve facts the assistant just asked the user to clarify."""
    if not last_assistant:
        return False
    assistant_n = _n(last_assistant)
    message_n = _n(message)
    overlap = 0
    for cues in _CLARIFICATION_CONCEPTS.values():
        assistant_has = any(_n(cue) in assistant_n for cue in cues)
        message_has = any(_n(cue) in message_n for cue in cues)
        if assistant_has and message_has:
            overlap += 1
    if overlap:
        return True

    # A list of factual yes/no/negative statements immediately after a clarification-heavy answer
    # is normally a reply to that answer even when the wording does not repeat the exact question.
    clarification_language = (
        'يلزم حسم', 'قد يلزم حسم', 'ما يزال', 'قبل التكييف', 'هل كان', 'هل وقع',
        'still material', 'still to resolve', 'before a final classification',
    )
    answer_shaped = (
        message_n.startswith('نعم') or message_n.startswith('لا ') or ' لم ' in f' {message_n} '
        or ' من غير ' in f' {message_n} ' or '\n' in message
    )
    return any(_n(x) in assistant_n for x in clarification_language) and answer_shaped


def _looks_like_followup_detail(message: str, route: RouteResult, last_assistant: str = '') -> bool:
    n = _n(message)
    tokens = [x for x in n.split() if x]
    detail_markers = (
        'بدون اذن', 'من غير اذن', 'باذن', 'بإذن', 'لم يوافق', 'وافق', 'المالك', 'المال ل',
        'لم يقع ليلا', 'وقع ليلا', 'مسكون', 'غير مسكون', 'اهله', 'أهله',
        'عقدي', 'راتبي', 'اجري', 'أجري', 'صارلي', 'خدمتي', 'سبب الفصل', 'بدون انذار', 'بدون إنذار',
        'بالضبط', 'صحيح', 'لا احمل رخصه', 'لا أحمل رخصة', 'معي رخصه', 'معي رخصة',
        'without permission', 'with permission', 'not at night', 'at night', 'occupied',
        'the owner did not consent', 'owner consented', 'it belongs to', 'my contract', 'my salary',
    )
    if _answers_prior_clarification(message, last_assistant):
        return True
    if n.strip() in {_n(x) for x in ('نعم', 'لا', 'ايوه', 'أيوه', 'اه', 'آه', 'yes', 'no')}:
        return True
    if any(_n(x) in n for x in detail_markers):
        return True
    if len(tokens) <= 14 and not any(x in n for x in ('شو', 'كيف', 'كم', 'هل', 'ما هي', 'ما هو', 'ليش', 'لماذا', 'what', 'how', 'why')):
        if re.search(r'\d', message) or route.primary_domain == 'general' or route.confidence < 0.55:
            return True
    return route.primary_domain == 'general' or route.confidence < 0.42


def _strong_topic_switch(message: str, route: RouteResult, recent_users: list[str]) -> bool:
    if not recent_users or _looks_like_correction(message):
        return False
    current = route.primary_domain if route.primary_domain not in {'general', 'conversation'} else _dominant_topic(message)
    previous = _dominant_topic(recent_users[-1])
    if not current or not previous or current == previous:
        return False
    current_scores = _topic_scores(message)
    # Require a real topical signal so a weak router guess cannot erase an active case thread.
    return current_scores.get(current, 0) >= 1 and route.confidence >= 0.58


def contextualize_message(message: str, history: list[dict], route: RouteResult) -> tuple[str, bool]:
    """Carry forward the active case only when the new turn genuinely belongs to it.

    The conversation may contain multiple legal matters. Follow-up facts, answers to clarifying
    questions, and explicit corrections inherit the recent case facts. A clear topic switch starts
    a fresh case thread even when the user keeps the same conversation_id.
    """
    recent = _recent_user_messages(history, 5)
    if not recent:
        return message, False

    if _looks_like_explicit_new_case(message):
        return message, False

    last_assistant = _last_assistant_message(history)
    if _strong_topic_switch(message, route, recent):
        return message, False

    should_link = (
        _looks_like_correction(message)
        or _answers_prior_clarification(message, last_assistant)
        or _looks_like_followup_detail(message, route, last_assistant)
    )
    if not should_link:
        return message, False

    # Keep only the last two substantive user turns from the active thread. This gives cognition
    # enough facts to resolve a clarification without dragging unrelated older matters into retrieval.
    prior = recent[-2:]
    if route.language == 'en':
        context = '\n'.join(prior)
        return f'Previous facts from the same case:\n{context}\nNew follow-up facts or correction:\n{message}', True

    context = '\n'.join(prior)
    return f'وقائع سابقة من نفس القضية:\n{context}\nتفاصيل متابعة أو تصحيح جديد من المستخدم:\n{message}', True
