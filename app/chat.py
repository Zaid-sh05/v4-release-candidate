from __future__ import annotations

from .answer_engine import generate_grounded_answer, insufficient_answer
from .case_analysis import generate_case_analysis_answer
from .cognition import CaseCognitionEngine
from .context import contextualize_message
from .evaluator import evaluate_answer
from .llm import embed_query, generate_answer
from .models import ChatRequest, ChatResponse, RouteResult, SourceItem
from .repository import repository
from .router import DOMAIN_LABELS, analyze_query
from .runtime_store import runtime_store
from .supabase_store import supabase_store
from .text import normalize_ar, strip_emoji_style

AR_DISCLAIMER='معلومات قانونية عامة مستندة إلى مصادر رسمية، ولا تغني عن استشارة محامٍ مرخص أو قرار الجهة المختصة.'
EN_DISCLAIMER='General legal information grounded in official sources; it is not a substitute for advice from a licensed lawyer or the competent authority.'

COGNITION_ENGINE = CaseCognitionEngine()


def smalltalk(text:str,lang:str)->str:
    n=normalize_ar(text)
    if lang=='en':
        if 'who are you' in text.lower():
            return 'I am Qanoni, a legal AI assistant focused on Jordanian law and official Jordanian legal sources. Tell me the situation in ordinary language and I will help you identify the relevant legal area.'
        if 'what can you do' in text.lower() or 'help me' in text.lower():
            return 'I can help you research Jordanian traffic, labor, civil, criminal, personal-status, company, cybercrime, data-protection and court-procedure questions, while showing the official sources used.'
        if 'thank' in text.lower(): return 'You are welcome. Send me the next question whenever you are ready.'
        return 'Hello. I am Qanoni. Tell me what happened in your own words and I will help you work through the legal issue.'
    if 'مين انت' in n or 'عرفني' in n:
        return 'أنا قانوني، مساعد قانوني ذكي متخصص في القانون الأردني والمصادر الرسمية. احكيلي الحالة بطريقتك العادية، وأنا أرتب المسألة وأبحث في المجال القانوني المناسب.'
    if 'شو بتقدر تعمل' in n or 'ساعدني' in n:
        return 'أقدر أساعدك في مسائل السير والعمل والمدني والجزائي والأحوال الشخصية والشركات والجرائم الإلكترونية وحماية البيانات وإجراءات المحاكم، مع إظهار العقوبة أو المدة أو الإجراء مباشرة عندما يكون النص الرسمي المسترجع كافياً.'
    if 'شكرا' in n or 'يسلمو' in n:
        return 'العفو. ابعثلي سؤالك التالي وقت ما بدك.'
    if 'كيفك' in n or 'شو اخبارك' in n:
        return 'بخير، وجاهز أساعدك. احكيلي الموضوع اللي بدك نفهمه قانونياً.'
    return 'أهلاً. أنا قانوني. احكيلي شو صار معك بطريقتك العادية، وبساعدك نحدد المسار القانوني المناسب.'


def _boilerplate_excerpt(text:str)->bool:
    n=normalize_ar(text or '')
    bad=('english search english','يرجى الانتظار','اسم الملف','عرض وتحميل','كيف تقيم محتوى الصفحه','ساعات العمل','وسائل التواصل الاجتماعي')
    return sum(1 for x in bad if normalize_ar(x) in n)>=2


def retrieval_fallback(message:str,route:RouteResult,sources:list[SourceItem])->str:
    if not sources or all(s.source_kind=='reference' for s in sources):
        return insufficient_answer(message,route,sources)
    usable=[s for s in sources if s.excerpt and s.source_kind!='reference' and not _boilerplate_excerpt(s.excerpt)]
    preferred=[s for s in usable if s.source_kind in {'canonical_verified','verified_crosscheck','official_guidance','official_service','judicial_principle'}]
    substantive=(preferred or usable)
    if not substantive: return insufficient_answer(message,route,sources)
    substantive=sorted(substantive,key=lambda s:(s.source_kind in {'canonical_verified','verified_crosscheck'},s.source_kind in {'official_guidance','official_service','judicial_principle'},s.score),reverse=True)[0]
    excerpt=' '.join((substantive.excerpt or '').split())
    excerpt=excerpt[:760].rsplit(' ',1)[0] + ('…' if len(excerpt)>760 else '')
    if route.language=='en':
        art=f', Article {substantive.article}' if substantive.article else ''
        return f'The strongest verified text I found is: {excerpt} [S1]\n\nLegal basis: {substantive.title}{art}. [S1]'
    art=f'، المادة {substantive.article}' if substantive.article else ''
    return f'الخلاصة من أقوى نص موثوق مسترجع: {excerpt} [S1]\n\nالأساس القانوني: {substantive.title}{art}. [S1]'


def _supabase_sources(rows:list[dict]) -> list[SourceItem]:
    out=[]
    for r in rows:
        try: out.append(SourceItem(**r))
        except Exception: pass
    return out


def _cloud_keyword_sources(queries:list[str],domains:list[str],limit:int=12)->list[SourceItem]:
    """Bounded multi-query cloud retrieval with no embedding provider required."""
    if not supabase_store.configured:
        return []
    out=[]; seen=set()
    for query in queries[:8]:
        q=' '.join((query or '').split()).strip()
        if len(q)<2: continue
        for item in _supabase_sources(supabase_store.keyword_search(q,domains,limit)):
            if item.id in seen: continue
            seen.add(item.id); out.append(item)
            if len(out)>=limit: return out
    return out


def _choose_grounded(message:str,route:RouteResult,sources:list[SourceItem]):
    grounded=generate_grounded_answer(message,route,sources)
    if not grounded: return None,None
    evaluation=evaluate_answer(message,route,grounded.text,sources)
    return grounded,evaluation


def _apply_cognition_to_route(route:RouteResult, case, force_domain:str|None)->RouteResult:
    """Use cognition as a routing hint, never as legal authority."""
    if force_domain:
        return route

    cognition_domains=[d for d in case.domains if d in DOMAIN_LABELS and d!='general']
    if cognition_domains:
        existing=[d for d in route.domains if d not in {'general','conversation'}]
        if route.primary_domain in {'general','conversation'} or route.confidence < 0.62:
            route.primary_domain=cognition_domains[0]
            route.domains=list(dict.fromkeys(cognition_domains+existing))[:4]
            route.confidence=max(route.confidence,0.72 if case.cognition_provider!='deterministic' else 0.62)
        else:
            route.domains=list(dict.fromkeys(route.domains+cognition_domains))[:4]

    if route.intent=='legal_question':
        mapped={
            'penalty':'penalty',
            'rights':'rights',
            'appeal':'appeal',
            'procedure':'procedure',
        }.get(case.user_goal)
        if mapped:
            route.intent=mapped

    return route


def _cognition_expansions(case)->list[str]:
    out=[]
    for query in case.retrieval_queries:
        q=' '.join((query or '').split()).strip()
        if q and q not in out:
            out.append(q)
        if len(out)>=6:
            break
    return out


def _feedback_review_expansions(message:str,primary_domain:str)->list[str]:
    """Reuse only official-source-derived hints from a previously validated correction."""
    try:
        hint=runtime_store.feedback_review_hint(message,primary_domain)
    except Exception:
        return []
    if not hint:
        return []
    out=[]
    for query in hint.get('retrieval_hints') or []:
        q=' '.join((query or '').split()).strip()
        if q and q not in out:
            out.append(q)
        if len(out)>=6: break
    return out


def handle_chat(req:ChatRequest)->ChatResponse:
    prior_history=[]
    if req.conversation_id:
        try:
            prior_history=runtime_store.history(req.conversation_id,8)
        except Exception:
            prior_history=[]

    initial_route=analyze_query(req.message,req.language,req.force_domain)
    effective_message,used_context=contextualize_message(req.message,prior_history,initial_route)
    route=analyze_query(effective_message,req.language,req.force_domain) if used_context else initial_route

    if route.intent!='smalltalk':
        try:
            case=COGNITION_ENGINE.analyze(effective_message,route.language)
            route=_apply_cognition_to_route(route,case,req.force_domain)
            cognition_queries=_cognition_expansions(case)
        except Exception:
            case=None
            cognition_queries=[]
    else:
        case=None
        cognition_queries=[]

    review_queries=_feedback_review_expansions(req.message,route.primary_domain) if route.intent!='smalltalk' else []
    cognition_queries=list(dict.fromkeys(cognition_queries+review_queries))[:10]

    cid=runtime_store.ensure_conversation(req.conversation_id,route.language)
    runtime_store.save_message(cid,'user',req.message,route.primary_domain,route.intent)
    if route.intent=='smalltalk':
        answer=strip_emoji_style(smalltalk(req.message,route.language))
        runtime_store.save_message(cid,'assistant',answer,'conversation','smalltalk')
        return ChatResponse(answer=answer,route=route,sources=[],mode='conversation',conversation_id=cid,disclaimer='')

    sources=[]
    emb=embed_query(effective_message)
    if emb:
        sources=_supabase_sources(supabase_store.hybrid_search(effective_message,emb,route.domains,8))
    if not sources and supabase_store.configured:
        sources=_cloud_keyword_sources([effective_message],route.domains,8)
    if not sources:
        sources=repository.search(effective_message,route.domains,8)

    if cognition_queries and (not sources or route.confidence < 0.8 or review_queries):
        cognitive_sources=_cloud_keyword_sources([effective_message]+cognition_queries,route.domains,12)
        if not cognitive_sources:
            cognitive_sources=repository.adaptive_search(
                effective_message,route.domains,route.intent,12,cognition_queries
            )
        if cognitive_sources:
            sources=cognitive_sources

    grounded,evaluation=_choose_grounded(effective_message,route,sources)
    best_grounded=grounded
    best_eval=evaluation
    best_sources=sources
    used_adaptive=bool(review_queries)

    if grounded is None or grounded.strength!='strong' or (evaluation and evaluation.should_retry):
        evaluation_seed=evaluation or evaluate_answer(effective_message,route,'',sources)
        expansions=list(dict.fromkeys((evaluation_seed.expanded_queries or [])+cognition_queries))[:10]
        adaptive_sources=_cloud_keyword_sources([effective_message]+expansions,route.domains,12)
        if not adaptive_sources:
            adaptive_sources=repository.adaptive_search(effective_message,route.domains,route.intent,12,expansions)
        if adaptive_sources:
            adaptive_grounded,adaptive_eval=_choose_grounded(effective_message,route,adaptive_sources)
            if adaptive_grounded and (best_eval is None or adaptive_eval.score>=best_eval.score):
                best_grounded,best_eval,best_sources=adaptive_grounded,adaptive_eval,adaptive_sources
                used_adaptive=True

    case_analysis=None
    case_analysis_eval=None
    if case and route.intent=='legal_question':
        case_analysis=generate_case_analysis_answer(effective_message,route,case,best_sources)
        if case_analysis:
            case_analysis_eval=evaluate_answer(effective_message,route,case_analysis.text,best_sources)

    history=runtime_store.history(cid,8)
    answer=None
    cognition_suffix='-cognition' if case and case.cognition_provider!='deterministic' else ''
    mode=('official-adaptive-extractive' if used_adaptive else 'official-self-checked-extractive')+cognition_suffix

    if case_analysis and case_analysis_eval and case_analysis_eval.passed:
        answer=case_analysis.text
        best_eval=case_analysis_eval
        mode='official-case-analysis'+cognition_suffix
    elif best_grounded and best_eval and best_eval.passed and (best_grounded.strength=='strong' or best_eval.score>=0.84):
        answer=best_grounded.text
    else:
        llm_answer=generate_answer(effective_message,route,best_sources,history)
        if llm_answer:
            llm_eval=evaluate_answer(effective_message,route,llm_answer,best_sources)
            if llm_eval.passed and (best_eval is None or llm_eval.score>=best_eval.score):
                answer=llm_answer
                best_eval=llm_eval
                mode='official-self-checked-hybrid-rag'+cognition_suffix
        if not answer and best_grounded:
            answer=best_grounded.text
        if not answer:
            critical={'penalty','deadline','appeal_deadline','fees','judgment','rights'}
            answer=insufficient_answer(effective_message,route,best_sources) if route.intent in critical else retrieval_fallback(effective_message,route,best_sources)

    answer=strip_emoji_style(answer or insufficient_answer(effective_message,route,best_sources))
    final_eval=evaluate_answer(effective_message,route,answer,best_sources)
    try:
        runtime_store.log_evaluation(cid,req.message,route.intent,route.primary_domain,final_eval.passed,final_eval.score,final_eval.reasons,mode)
    except Exception:
        pass
    runtime_store.save_message(cid,'assistant',answer,route.primary_domain,route.intent)
    return ChatResponse(answer=answer,route=route,sources=best_sources,mode=mode,conversation_id=cid,disclaimer=AR_DISCLAIMER if route.language=='ar' else EN_DISCLAIMER)
