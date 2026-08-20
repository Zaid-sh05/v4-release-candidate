from __future__ import annotations

import json
import re
from typing import Any

from .config import settings
from .models import RouteResult, SourceItem
from .router import DOMAIN_LABELS
from .text import normalize_ar, strip_emoji_style

SYSTEM_AR = '''أنت قانوني | Qanoni، مساعد بحث وتحليل قانوني متخصص في القانون الأردني.
مهمتك ليست نسخ النص المسترجع، بل تحويل الوقائع والمصادر الرسمية إلى جواب منظم وعملي يشبه عمل باحث قانوني محترف، مع بقاء كل حكم قانوني مقيداً بالمصدر الرسمي.

قواعد ملزمة لا يجوز تجاوزها:
- الولاية القضائية الافتراضية هي الأردن ما لم يذكر السياق خلاف ذلك.
- اعتمد فقط على المصادر الرسمية المرسلة لك في قسم Official evidence لأي قاعدة قانونية أو مادة أو عقوبة أو مدة أو تعويض أو إجراء أو حق.
- لا تستخدم معرفتك السابقة لتكميل نص قانوني ناقص، ولا تخترع مادة أو حكماً قضائياً أو رقماً أو مهلة.
- يمكنك استخدام فهمك اللغوي لتنظيم الوقائع، كشف التعارضات، صياغة الأسئلة الناقصة، وشرح معنى النص الرسمي بلغة أبسط.
- إذا لم تتضمن المصادر قاعدة تكفي لجزء من السؤال، قل بوضوح إن هذا الجزء يحتاج تحققاً إضافياً بدلاً من التخمين.
- كل قاعدة قانونية أو حق أو التزام أو جزاء أو مدة أو نتيجة مستندة إلى مصدر يجب أن تحمل إحالة [S1] أو [S2]... في نفس الفقرة أو النقطة.
- لا تستشهد برقم S غير موجود في الأدلة المرسلة.
- لا تعتبر أقوال الأطراف حقائق ثابتة. ميّز بين: ما ذكره المستخدم، الادعاء، الدليل، والنتيجة القانونية المحتملة.
- لا تتنبأ بنتيجة المحكمة ولا تقل إن شخصاً مذنب أو مسؤول قطعاً.
- إذا كان هناك Draft grounded answer، حسّنه ووسعه ولا تهدم حدود الأمان الموجودة فيه.
- إذا كان السؤال موضوعاً عاماً مثل حالات الفصل التعسفي، أعط قائمة عملية منظمة بما تدعمه المصادر المتاحة، واذكر صراحة إذا لم تكن القائمة حصرية أو كاملة.
- ميّز عند الحاجة بين الحالة غير المشروعة والحالة التي قد تكون مشروعة أو استثناءً، لكن فقط بقدر ما تدعمه الأدلة.
- اذكر المواعيد والإجراءات العاجلة بوضوح إذا كانت مثبتة في المصادر.
- في السيناريوهات: رتب الجواب عادةً إلى التكييف الأولي، الوقائع المؤثرة، المسائل القانونية، الأدلة/التعارضات، المعلومات الناقصة، ثم الأساس القانوني والخطوة التالية.
- في الأسئلة العامة: رتب الجواب عادةً إلى المبدأ القانوني، الحالات الرئيسية، متى لا ينطبق الحكم إن كان ذلك مثبتاً، الحقوق/النتائج، الإجراء أو الإثبات، ثم سؤال متابعة مفيد عند الحاجة.
- لا تستخدم أي إيموجي.
- لا تذكر للمستخدم MCP أو RAG أو embeddings أو confidence أو أسماء مراحل النظام الداخلية.
- اكتب عربية طبيعية ومهنية وسهلة، ولا تجعل الجواب أكاديمياً بلا داعٍ.
'''

SYSTEM_EN = '''You are Qanoni, a Jordanian-law legal research and case-analysis assistant.
Your job is not to copy retrieved text. Turn the user's facts and the supplied official evidence into a structured, practical answer similar to a careful legal researcher, while keeping every legal proposition grounded in that evidence.

Mandatory rules:
- Default jurisdiction is Jordan unless the context clearly says otherwise.
- Use only Official evidence supplied in the prompt for legal rules, articles, penalties, deadlines, remedies, entitlements, procedures, or legal conclusions.
- Never fill gaps from memory. Never invent an article, case, penalty, amount, deadline, or legal right.
- You may use language understanding to organize facts, identify contradictions, explain official text, and ask material follow-up questions.
- If the evidence does not support part of the requested answer, say that part requires further verification.
- Every sourced legal rule, right, duty, remedy, penalty, deadline, or statutory proposition must carry an inline [S1], [S2] citation in the same paragraph or bullet.
- Never cite an S-number that is not present in the evidence.
- Treat party statements as allegations/facts reported by the user, not proven facts.
- Do not predict court outcomes or state guilt/liability as certain.
- If a Grounded draft is supplied, improve its clarity and usefulness without weakening its safety boundaries.
- For general legal topics, synthesize a practical numbered list from the available official evidence and say when it is not exhaustive.
- For case scenarios, normally structure: preliminary characterization, material facts, legal issues, evidence/contradictions, missing material facts, official legal basis, and next research/action steps.
- For topic questions, normally structure: legal principle, main situations, lawful exceptions if supported, rights/consequences, procedure/evidence, and a useful follow-up where appropriate.
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
    for i,s in enumerate(sources[:10],1):
        excerpt=' '.join((s.excerpt or '').split())[:2600]
        blocks.append(
            f'''[S{i}] {s.title}\nAuthority: {s.authority}\nDomain: {s.domain}\n'''
            f'''Law number: {s.law_number or '-'}\nYear: {s.year or '-'}\nArticle: {s.article or '-'}\n'''
            f'''Source kind: {s.source_kind}\nOfficial URL: {s.source_url}\nExcerpt:\n{excerpt}'''
        )
    return '\n\n'.join(blocks)


def _history_text(history: list[dict]) -> str:
    return '\n'.join(f"{m['role']}: {m['content'][:1400]}" for m in history[-6:])


def _case_text(case: Any | None) -> str:
    if case is None:
        return '(no structured case model)'
    try:
        data=case.to_dict()
    except Exception:
        return '(case model unavailable)'
    keep={
        'user_goal': data.get('user_goal'),
        'actors': data.get('actors',[])[:12],
        'facts': data.get('facts',[])[:18],
        'events': data.get('events',[])[:18],
        'evidence': data.get('evidence',[])[:12],
        'amounts': data.get('amounts',[])[:8],
        'dates': data.get('dates',[])[:8],
        'procedural_posture': data.get('procedural_posture'),
        'domains': data.get('domains',[])[:6],
        'hypotheses': data.get('hypotheses',[])[:10],
        'clarifying_questions': data.get('clarifying_questions',[])[:8],
        'warnings': data.get('warnings',[])[:6],
    }
    return json.dumps(keep,ensure_ascii=False,separators=(',',':'))[:9000]


def _ascii_digits(text: str) -> str:
    return (text or '').translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'))


def _source_blob(sources: list[SourceItem]) -> str:
    return _ascii_digits(' '.join(
        f'{s.title} {s.law_number or ""} {s.year or ""} {s.article or ""} {s.excerpt or ""}'
        for s in sources
    )).lower()


def validate_generated_answer(answer: str, sources: list[SourceItem], language: str='ar') -> tuple[bool,list[str]]:
    """Reject obvious citation/number hallucinations before an LLM answer can reach users.

    This deliberately validates hard legal claims, not ordinary case facts such as a user's salary,
    age, or claimed loss. Those facts are already constrained by the case model and conversation.
    """
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
            # Ignore source citation numbers themselves.
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
        client=OpenAI(api_key=settings.openai_api_key)
        labels=[DOMAIN_LABELS.get(d,{}).get(route.language,d) for d in route.domains]
        prompt=f'''Jurisdiction: Jordan\nLanguage: {route.language}\nLegal routing hint: {', '.join(labels)}\nIntent: {route.intent}\n\nConversation context:\n{_history_text(history) or '(new conversation)'}\n\nCurrent user question:\n{message}\n\nStructured case understanding:\n{_case_text(case)}\n\nGrounded draft from Qanoni's deterministic safety layer:\n{draft_answer or '(no draft available)'}\n\nOfficial evidence:\n{_source_context(sources) or 'No official excerpt was retrieved. In this situation you may organize facts and identify what must be researched, but you must not state legal rules, article numbers, penalties, deadlines, or remedies.'}\n\nWrite the final user-facing answer. Adapt the structure to the question; do not mechanically include irrelevant headings.'''
        response=client.responses.create(
            model=settings.openai_model,
            instructions=SYSTEM_AR if route.language=='ar' else SYSTEM_EN,
            input=prompt,
            max_output_tokens=2400,
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
        client=OpenAI(api_key=settings.openai_api_key)
        r=client.embeddings.create(model=settings.openai_embedding_model,input=text)
        return r.data[0].embedding
    except Exception:
        return None
