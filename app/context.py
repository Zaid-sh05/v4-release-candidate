from __future__ import annotations

import re

from .models import RouteResult
from .text import normalize_ar


def _recent_user_messages(history: list[dict], limit: int = 3) -> list[str]:
    msgs=[(m.get('content') or '').strip() for m in history if m.get('role')=='user' and (m.get('content') or '').strip()]
    return msgs[-limit:]


def _looks_like_independent_question(message: str) -> bool:
    n=normalize_ar(message)
    strong=(
        'ما عقوبه','شو عقوبه','ما العقوبه','شو العقوبه','ما هي عقوبه','ما هي العقوبه',
        'كيف اقدم','كيف ارفع','كم مده','كم رسوم','ما حكم','ما حقوق','شو حقوق',
        'قانون العمل','قانون السير','قانون العقوبات','القانون المدني','قانون الشركات',
        'قتل','سرقه','زنا','ابتزاز','اشاره حمراء','إشارة حمراء','طلاق','نفقه','حضانة',
    )
    return any(normalize_ar(x) in n for x in strong)


def _looks_like_followup_detail(message: str, route: RouteResult) -> bool:
    n=normalize_ar(message)
    tokens=[x for x in n.split() if x]
    detail_markers=(
        'عقدي','راتبي','اجري','أجري','صارلي','خدمتي','مده خدمتي','مدة خدمتي',
        'ما اعطوني','ما أعطوني','ما وصلني','ما استلمت','ما إستلمت','بدون انذار','بدون إنذار',
        'السبب','سبب الفصل','قالولي','حكولي','انه عقدي','إنه عقدي','غير محدد المده','غير محدد المدة',
        'محدد المده','محدد المدة','بالضبط','صحيح','من اربع سنوات','من 4 سنوات',
    )
    if n.strip() in {'نعم','لا','ايوه','أيوه','اه','آه'}:
        return True
    if any(normalize_ar(x) in n for x in detail_markers):
        return True
    # Very short factual replies are usually answers to a clarification question.
    if len(tokens) <= 12 and not any(x in n for x in ('شو','كيف','كم','هل','ما هي','ما هو','ليش','لماذا')):
        if re.search(r'\d', message) or route.primary_domain=='general' or route.confidence < 0.55:
            return True
    # If the current message has weak routing and the previous turn exists, context is safer than guessing.
    return route.primary_domain=='general' or route.confidence < 0.45


def contextualize_message(message: str, history: list[dict], route: RouteResult) -> tuple[str, bool]:
    """Return an effective query that carries recent user facts when this is a follow-up.

    We only contextualize likely follow-up details. A new, clearly independent legal question starts
    a fresh retrieval query even if it is sent in the same chat.
    """
    recent=_recent_user_messages(history,3)
    if not recent:
        return message, False
    if _looks_like_independent_question(message) and not _looks_like_followup_detail(message,route):
        return message, False
    if not _looks_like_followup_detail(message,route):
        return message, False
    context='\n'.join(recent)
    return f'{context}\nتفاصيل متابعة من المستخدم: {message}', True
