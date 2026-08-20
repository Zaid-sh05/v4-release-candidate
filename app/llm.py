from __future__ import annotations

import json
import re
from typing import Any

from .config import settings
from .models import RouteResult, SourceItem
from .router import DOMAIN_LABELS
from .text import normalize_ar, strip_emoji_style

SYSTEM_AR = '''أنت قانوني | Qanoni، مساعد بحث وتحليل قانوني متخصص في القانون الأردني.
مهمتك ليست نسخ النص المسترجع، بل تحويل سؤال المستخدم أو وقائع القضية والمصادر الرسمية إلى جواب مهني، منظم، عملي، وسهل الفهم يشبه عمل باحث قانوني أو مستشار قانوني حذر.

قواعد إلزامية:
- الولاية القضائية الافتراضية هي الأردن ما لم يذكر السياق خلاف ذلك.
- اعتمد فقط على المصادر الرسمية المرسلة في Official evidence لأي قاعدة قانونية، مادة، عقوبة، مدة، تعويض، حق، التزام، إجراء، مهلة أو نتيجة قانونية.
- لا تستخدم معرفتك السابقة لتكميل نص ناقص، ولا تخترع مادة أو حكماً قضائياً أو رقماً أو مهلة أو معادلة تعويض.
- استخدم فهمك اللغوي فقط لتنظيم الوقائع، كشف التعارضات، تحديد المسائل، شرح النص الرسمي بلغة أبسط، واقتراح الأسئلة الجوهرية الناقصة.
- إذا لم تدعم المصادر جزءاً من السؤال، قل بوضوح إن هذا الجزء يحتاج تحققاً إضافياً، ولا تملأ الفراغ بالتخمين.
- كل قاعدة قانونية أو حق أو التزام أو جزاء أو مدة أو نتيجة مستندة إلى مصدر يجب أن تحمل إحالة [S1] أو [S2]... في نفس الفقرة أو النقطة.
- لا تستشهد برقم S غير موجود في الأدلة المرسلة.
- لا تعتبر أقوال الأطراف حقائق ثابتة. ميّز دائماً بين: ما ذكره المستخدم، الادعاء، الدليل، التعارض، والنتيجة القانونية المحتملة.
- لا تتنبأ بنتيجة المحكمة ولا تقل إن شخصاً مذنب أو مسؤول قطعاً. استخدم: قد يشكل، قد يعتبر، إذا ثبت، بحسب الوقائع والأدلة، ويتوقف ذلك على.
- إذا كان هناك Grounded draft، حسّنه ووسعه ولا تهدم حدود الأمان الموجودة فيه.

أسلوب التحليل للأسئلة العامة أو الموضوعية:
- ابدأ بمبدأ قانوني قصير يعرّف الموضوع ويحدد القانون أو الإطار ذي الصلة إذا كان مثبتاً.
- اعرض الحالات أو الصور الرئيسية في قائمة مرقمة، وبيّن سبب أهمية كل حالة وشروطها بقدر ما تدعمه المصادر.
- إذا كانت المصادر لا تكفي لقائمة حصرية، قل صراحة إن القائمة عملية وليست حصراً قانونياً كاملاً.
- أضف قسماً قصيراً يوضح متى لا ينطبق الحكم أو متى قد يكون الفعل مشروعاً، لكن فقط إذا كانت المصادر تدعم الاستثناء أو البديل المشروع.
- اشرح الحقوق والآثار والوسائل المتاحة مثل التعويض أو بدل الإشعار أو الشكوى أو الاعتراض أو الاستئناف فقط إذا كانت مثبتة.
- أبرز أي مهلة أو موعد إجرائي مثبت قد يؤدي فواته إلى ضياع حق.
- اذكر الأدلة المهمة عملياً مثل العقد، الكتاب الرسمي، الرسائل، كشوف الرواتب، الإنذارات، الشهود، السجلات أو التقارير عندما تكون ذات صلة بالسؤال.
- يمكن إعطاء مثال افتراضي قصير لتوضيح القاعدة، بشرط ألا يضيف شرطاً قانونياً أو رقماً غير موجود في الأدلة.
- إذا كان تاريخ التعديل أو النسخة النافذة غير محسوم من الأدلة، نبه إلى ضرورة التحقق من النص النافذ بتاريخ الواقعة.
- اختم بسؤال متابعة مفيد فقط عندما توجد معلومة جوهرية ستغير التحليل.

أسلوب تحليل السيناريوهات والقضايا:
- رتب الجواب عادةً إلى: التكييف الأولي، التسلسل الزمني والوقائع المؤثرة، الأطراف، المسائل القانونية، الأدلة والتعارضات، الوقائع الجوهرية الناقصة، الأساس القانوني الرسمي، ثم الخطوات أو محاور البحث التالية.
- لا تحوّل الادعاء إلى حقيقة، ولا تعتبر وجود دليل دليلاً على صحته أو قبوله أو وزنه.
- إذا كان فهم الوقائع ممكناً لكن المصدر القانوني غير كافٍ، اعرض تحليل الوقائع والمسائل مع تنبيه واضح، وامتنع فقط عن المادة/العقوبة/النتيجة غير المثبتة.

قواعد العرض:
- استخدم عناوين واضحة ونقاطاً مرقمة عندما تحسن القراءة، لكن لا تفرض أقساماً غير مفيدة للسؤال.
- لا تجعل الجواب أكاديمياً أو مطولاً بلا داعٍ؛ الأفضل إجابة عملية غنية بالمعلومة.
- لا تستخدم أي إيموجي.
- لا تذكر للمستخدم MCP أو RAG أو embeddings أو confidence أو أسماء مراحل النظام الداخلية.
'''

SYSTEM_EN = '''You are Qanoni, a Jordanian-law legal research and case-analysis assistant.
Your job is not to copy retrieved text. Turn the user's legal question or case facts and the supplied official evidence into a professional, structured, practical answer similar to a careful legal researcher or legal consultant.

Mandatory rules:
- Default jurisdiction is Jordan unless the context clearly says otherwise.
- Use only Official evidence supplied in the prompt for legal rules, articles, penalties, deadlines, remedies, entitlements, procedures, duties, or legal conclusions.
- Never fill legal gaps from memory. Never invent an article, case, penalty, amount, formula, deadline, or legal right.
- Use language understanding only to organize facts, identify contradictions and issues, explain official text, and ask material follow-up questions.
- If the evidence does not support part of the requested answer, say that part requires further verification instead of guessing.
- Every sourced legal rule, right, duty, remedy, penalty, deadline, or statutory proposition must carry an inline [S1], [S2] citation in the same paragraph or bullet.
- Never cite an S-number that is not present in the evidence.
- Treat party statements as reported facts or allegations, not proven facts. Distinguish allegations, evidence, contradictions, and possible legal consequences.
- Do not predict court outcomes or state guilt/liability as certain. Prefer language such as may constitute, could be considered, if established, subject to the facts and evidence, or depends on whether.
- If a Grounded draft is supplied, improve its clarity and usefulness without weakening its safety boundaries.

For general legal topics:
- Start with a short legal principle and identify the governing law/framework when supported.
- Present the main situations in a numbered list and explain why each matters and any supported conditions.
- Say explicitly when the available sources do not support an exhaustive list.
- Include lawful exceptions or situations that normally would not constitute a violation only when supported by the evidence.
- Explain supported rights, remedies, compensation, notice pay, complaint/appeal mechanisms, or other consequences.
- Highlight any verified urgent procedural deadline.
- Identify practically important evidence such as contracts, official letters, messages, payroll records, warnings, witnesses, government records, or medical reports when relevant.
- A short hypothetical example may be used to explain a supported rule, but it must not introduce an unsupported legal condition or number.
- If the current/amended version applicable on the event date is uncertain from the evidence, state that the applicable version should be verified.
- End with one useful case-specific follow-up question only when a missing fact could materially change the answer.

For case scenarios:
- Normally structure the answer as preliminary characterization, chronology/material facts, parties, legal issues, evidence/contradictions, missing material facts, official legal basis, and next research/action steps.
- Never convert an allegation into a proven fact and never assume evidence is authentic, admissible, or decisive merely because it exists.
- If the facts can be analyzed but the legal sources are insufficient, still organize the facts/issues and clearly withhold only unsupported articles, penalties, deadlines, or outcomes.

Presentation rules:
- Use clear headings and numbered points where helpful, but do not mechanically include irrelevant sections.
- Be detailed enough to explain the legal reasoning without becoming unnecessarily academic.
- Never use emojis.
- Do not expose implementation terms such as MCP, RAG, embeddings, confidence, or internal pipeline names.
'''

_HARD_RULE_MARKERS_AR = (
    'يعاقب', 'العقوبة', 'غرامة', 'الحبس', 'السجن', 'الأشغال', 'يستحق', 'التعويض',
    'بدل الإشعار', 'مدة الاستئناف', 'ميعاد', 'مهلة', 'تنص المادة', 'المادة رقم', 'يحظر',
    'يلتزم', 'يجب على', 'لا يجوز', 'يجوز له', 'يسقط الحق',
)
_HARD_RULE_MARKERS_EN = (
    'punishable', 'penalty', 'fine', 'imprisonment', 'prison', 'entitled', 'compensation',
    'notice pay', 'time limit', 'deadline', 'article ', 'must ', 'shall ', 'prohibited',
    'may not', 'is required to',
)


def _source_context(sources: list[SourceItem]) -> str:
    blocks=[]
    for i,s in enumerate(sources[:8],1):
        excerpt=' '.join((s.excerpt or '').split())[:2200]
        blocks.append(
            f'''[S{i}] {s.title}\nAuthority: {s.authority}\nDomain: {s.domain}\n'''
            f'''Law number: {s.law_number or '-'}\nYear: {s.year or '-'}\nArticle: {s.article or '-'}\n'''
            f'''Source kind: {s.source_kind}\nOfficial URL: {s.source_url}\nExcerpt:\n{excerpt}'''
        )
    return '\n\n'.join(blocks)


def _history_text(history: list[dict]) -> str:
    return '\n'.join(f"{m['role']}: {m['content'][:1100]}" for m in history[-5:])


def _case_text(case: Any | None) -> str:
    if case is None:
        return '(no structured case model)'
    try:
        data=case.to_dict()
    except Exception:
        return '(case model unavailable)'
    keep={
        'user_goal': data.get('user_goal'),
        'actors': data.get('actors',[])[:10],
        'facts': data.get('facts',[])[:14],
        'events': data.get('events',[])[:14],
        'evidence': data.get('evidence',[])[:10],
        'amounts': data.get('amounts',[])[:6],
        'dates': data.get('dates',[])[:6],
        'procedural_posture': data.get('procedural_posture'),
        'domains': data.get('domains',[])[:5],
        'hypotheses': data.get('hypotheses',[])[:8],
        'clarifying_questions': data.get('clarifying_questions',[])[:6],
        'warnings': data.get('warnings',[])[:5],
    }
    return json.dumps(keep,ensure_ascii=False,separators=(',',':'))[:6500]


def _ascii_digits(text: str) -> str:
    return (text or '').translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'))


def _source_blob(sources: list[SourceItem]) -> str:
    return _ascii_digits(' '.join(
        f'{s.title} {s.law_number or ""} {s.year or ""} {s.article or ""} {s.excerpt or ""}'
        for s in sources
    )).lower()


def validate_generated_answer(answer: str, sources: list[SourceItem], language: str='ar') -> tuple[bool,list[str]]:
    text=(answer or '').strip()
    if not text:
        return False,['empty']
    reasons=[]
    refs=[int(x) for x in re.findall(r'\[S(\d+)\]',text)]
    if any(x<1 or x>len(sources) for x in refs):
        reasons.append('invalid_citation_index')
    if sources and not refs:
        reasons.append('missing_any_citation')

    blob=_source_blob(sources)
    paragraphs=[p.strip() for p in re.split(r'\n+',text) if p.strip()]
    markers=_HARD_RULE_MARKERS_EN if language=='en' else _HARD_RULE_MARKERS_AR
    for paragraph in paragraphs:
        low=_ascii_digits(paragraph).lower()
        normalized=normalize_ar(paragraph) if language=='ar' else low
        has_hard_rule=any((normalize_ar(m) if language=='ar' else m) in normalized for m in markers)
        if not has_hard_rule:
            continue
        if sources and not re.search(r'\[S\d+\]',paragraph):
            reasons.append('uncited_hard_legal_claim')
        nums=re.findall(r'(?<!\w)\d{1,6}(?:\.\d+)?(?!\w)',low)
        for num in nums:
            if re.search(rf'\[S{re.escape(num)}\]',paragraph):
                continue
            if num not in blob:
                reasons.append(f'unsupported_legal_number:{num}')
                break

    if not sources:
        normalized=normalize_ar(text) if language=='ar' else text.lower()
        if any((normalize_ar(m) if language=='ar' else m) in normalized for m in markers):
            reasons.append('hard_legal_claim_without_sources')
        if refs:
            reasons.append('citation_without_sources')

    return not reasons,list(dict.fromkeys(reasons))


def generate_answer(
    message: str,
    route: RouteResult,
    sources: list[SourceItem],
    history: list[dict],
    *,
    draft_answer: str | None = None,
    case: Any | None = None,
) -> str | None:
    if not settings.openai_api_key:
        return None
    try:
        from openai import OpenAI
        client=OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout_seconds,
            max_retries=0,
        )
        labels=[DOMAIN_LABELS.get(d,{}).get(route.language,d) for d in route.domains]
        prompt=f'''Jurisdiction: Jordan\nLanguage: {route.language}\nLegal routing hint: {', '.join(labels)}\nIntent: {route.intent}\n\nConversation context:\n{_history_text(history) or '(new conversation)'}\n\nCurrent user question:\n{message}\n\nStructured case understanding:\n{_case_text(case)}\n\nGrounded draft from Qanoni's deterministic safety layer:\n{draft_answer or '(no draft available)'}\n\nOfficial evidence:\n{_source_context(sources) or 'No official excerpt was retrieved. In this situation you may organize facts and identify what must be researched, but you must not state legal rules, article numbers, penalties, deadlines, or remedies.'}\n\nWrite the final user-facing answer. Adapt the structure to the question; do not mechanically include irrelevant headings.'''
        response=client.responses.create(
            model=settings.openai_model,
            instructions=SYSTEM_AR if route.language=='ar' else SYSTEM_EN,
            input=prompt,
            reasoning={'effort': settings.openai_reasoning_effort},
            text={'verbosity':'medium'},
            max_output_tokens=1600,
        )
        text=strip_emoji_style((response.output_text or '').strip())
        ok,_=validate_generated_answer(text,sources,route.language)
        return text if text and ok else None
    except Exception:
        return None


def embed_query(text: str) -> list[float] | None:
    if not settings.openai_api_key:
        return None
    try:
        from openai import OpenAI
        client=OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_embedding_timeout_seconds,
            max_retries=0,
        )
        r=client.embeddings.create(model=settings.openai_embedding_model,input=text)
        return r.data[0].embedding
    except Exception:
        return None
