from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import RouteResult, SourceItem
from .text import normalize_ar


@dataclass
class AnswerEvaluation:
    passed: bool
    score: float
    reasons: list[str] = field(default_factory=list)
    should_retry: bool = False
    expanded_queries: list[str] = field(default_factory=list)


def _has_citation(answer: str) -> bool:
    return bool(re.search(r'\[S\d+\]', answer or ''))


def _has_duration(answer: str) -> bool:
    n = normalize_ar(answer or '')
    return bool(re.search(r'\b\d{1,3}\s*(?:يوم|يوما|يوماً|شهر|اشهر|أشهر|سنه|سنة|سنوات)\b', n)) or any(
        x in n for x in ('ثلاثون يوما','خمسه عشر يوما','خمسة عشر يوما','عشره ايام','عشرة ايام')
    )


def _query_expansions(message: str, route: RouteResult) -> list[str]:
    n = normalize_ar(message)
    out: list[str] = []
    if route.primary_domain == 'labor' and any(x in n for x in ('فصل','طرد','انهاء','إنهاء','انذار','إنذار')):
        out += [
            f'{message} فصل تعسفي بدل الإشعار حقوق العامل عقد غير محدد المدة',
            'فصل تعسفي بدل الإشعار نصف شهر عن كل سنة خدمة شهرين العامل صاحب العمل',
            'إعفاء العامل من العمل خلال فترة الإشعار بدل الإشعار',
        ]
    if route.intent == 'penalty':
        out += [f'{message} العقوبة المادة الحبس الغرامة', f'{message} النص القانوني المادة عقوبة']
    if route.intent in {'deadline','appeal_deadline'}:
        out += [f'{message} مدة الاستئناف تاريخ التبليغ الحكم وجاهي غيابي', f'{message} ميعاد الطعن التبليغ']
    if route.intent == 'fees':
        out += [f'{message} رسوم القيد دينار جدول رسوم المحاكم']
    if route.intent in {'procedure','appeal','complaint','enforcement'}:
        out += [f'{message} إجراءات تقديم لائحة قلم المحكمة الوثائق الرسوم', f'{message} خطوات الخدمة الرسمية']
    if route.intent == 'rights':
        out += [f'{message} الحقوق التعويض بدل الإشعار الأجر الإجازات الاستحقاقات']
    # preserve order while deduplicating
    return list(dict.fromkeys(x.strip() for x in out if x.strip()))[:4]


def evaluate_answer(message: str, route: RouteResult, answer: str, sources: list[SourceItem]) -> AnswerEvaluation:
    text = (answer or '').strip()
    n = normalize_ar(text)
    reasons: list[str] = []
    score = 1.0

    if not text:
        return AnswerEvaluation(False, 0.0, ['empty_answer'], True, _query_expansions(message, route))

    if sources and route.intent != 'smalltalk' and not _has_citation(text):
        score -= 0.22
        reasons.append('missing_source_citation')

    source_only_phrases = ('لقيت المرجع الرسمي','المصادر الظاهره تساعدك','وجدت المصادر','اقوى نص رسمي مسترجع')
    source_only = any(normalize_ar(x) in n for x in source_only_phrases)

    if route.intent == 'penalty':
        has_value = any(x in n for x in ('العقوبه:','الجزاء المروري المؤكد','الحبس','السجن','الاشغال','غرامه','نقاط مروريه'))
        if not has_value or source_only:
            score -= 0.55
            reasons.append('penalty_not_answered_directly')
    elif route.intent in {'deadline','appeal_deadline'}:
        clarification = any(x in n for x in ('لازم اعرف','حدد هل','ليست رقما واحدا','قد تختلف حسب'))
        if not ((_has_duration(text) and ('المده:' in n or 'مده الاستئناف' in n)) or clarification):
            score -= 0.5
            reasons.append('deadline_missing_duration_or_clarification')
        if _has_duration(text) and not any(x in n for x in ('تبليغ','صدور','اليوم التالي','من تاريخ')):
            score -= 0.12
            reasons.append('deadline_missing_start_trigger')
    elif route.intent == 'fees':
        if not ('الرسوم:' in n and ('دينار' in n or re.search(r'\b\d+(?:\.\d+)?\b', text))):
            score -= 0.5
            reasons.append('fee_not_answered_directly')
    elif route.intent in {'procedure','appeal','complaint','enforcement'}:
        action_words = ('الاجراء','1.','2.','تقدم','تقديم','راجع','مراجعه','احضر','إحضار','ابلاغ','إبلاغ','لائحه','قلم','المحكمه')
        if not any(normalize_ar(x) in n for x in action_words):
            score -= 0.42
            reasons.append('procedure_missing_actions')
    elif route.intent == 'rights':
        rights_terms = ('بدل الاشعار','تعويض','الفصل التعسفي','اجر','أجر','اجازه','إجازة','مكافاه','حقوقك','يستحق','استحقاق')
        has_right = any(normalize_ar(x) in n for x in rights_terms)
        if not has_right or source_only:
            score -= 0.5
            reasons.append('rights_not_stated_concretely')
        qn = normalize_ar(message)
        if route.primary_domain == 'labor' and any(x in qn for x in ('فصل','طرد','بدون انذار','بدون إنذار')):
            if 'بدل الاشعار' not in n:
                score -= 0.24
                reasons.append('labor_termination_missing_notice_pay')
            if 'الفصل التعسفي' not in n:
                score -= 0.15
                reasons.append('labor_termination_missing_arbitrary_dismissal')
    elif route.intent == 'law_overview':
        if 'قانون' not in n or len(text) < 70:
            score -= 0.35
            reasons.append('law_overview_too_thin')

    score = max(0.0, min(1.0, score))
    passed = score >= 0.62 and not any(r in reasons for r in (
        'penalty_not_answered_directly','fee_not_answered_directly','rights_not_stated_concretely'
    ))
    should_retry = (not passed or score < 0.78) and route.intent != 'smalltalk'
    return AnswerEvaluation(passed, round(score, 2), reasons, should_retry, _query_expansions(message, route))
