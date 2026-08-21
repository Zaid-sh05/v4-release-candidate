from __future__ import annotations

import re

from .answer_engine import generate_grounded_answer, insufficient_answer
from .case_analysis import generate_case_analysis_answer
from .cognition import CaseCognitionEngine
from .context import contextualize_message
from .diagnostics import RequestTrace
from .evaluator import evaluate_answer
from .llm import embed_query, generate_answer
from .models import ChatRequest, ChatResponse, RouteResult, SourceItem
from .repository import repository
from .router import DOMAIN_LABELS, analyze_query
from .routing_guard import issue_signature
from .runtime_store import runtime_store
from .supabase_store import supabase_store
from .text import looks_garbled_text, normalize_ar, strip_emoji_style

_CITATION_RE = re.compile(r'\[S(\d+)\]')

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


def _source_is_usable(source:SourceItem)->bool:
    excerpt=(source.excerpt or '').strip()
    return bool(
        excerpt
        and source.source_kind!='reference'
        and not _boilerplate_excerpt(excerpt)
        and not looks_garbled_text(excerpt)
    )


def _source_issue_compatible(query_signature:frozenset,source:SourceItem)->bool:
    """Reject a candidate that clearly belongs to a different legal-issue family than the query.

    Domain compatibility alone is not enough: an adultery article and a theft article are both
    domain=criminal, and Public Security Law / Associations Law both land in the miscellaneous
    domain=general bucket. This checks the issue family, not just the domain label.

    Two independent lines of defense, since the coarse issue vocabulary can never cover every
    legal topic and must not over-reject sources it simply has no vocabulary for:
    - domain='general' is treated as a genuine miscellaneous bucket -- once the query itself
      shows ANY positive issue signal, general-domain content is presumptively irrelevant to it,
      regardless of whether that specific source's own text happens to be silent or not.
    - within a domain, a source is only rejected on a DETECTED CONFLICT (its own text hits a
      *different* issue family than the query, with zero overlap) -- a source whose text is
      silent on every tracked family is kept rather than rejected, since silence is not evidence
      of irrelevance for the many legal topics this coarse vocabulary does not enumerate. A
      whole-document candidate (no specific article number) may still serve as a general
      legal-basis anchor even when its own excerpt does not lexically overlap.
    """
    if not query_signature:
        return True
    if source.domain=='general':
        return False
    if not source.article:
        return True
    source_signature=issue_signature(f'{source.title or ""} {source.excerpt or ""}')
    if not source_signature:
        return True
    return bool(query_signature & source_signature)


def _guard_sources(route:RouteResult,sources:list[SourceItem],trace:RequestTrace|None=None)->list[SourceItem]:
    """Keep only readable sources that belong to the active legal route AND issue family."""
    allowed=set(route.domains or [route.primary_domain])
    query_signature=issue_signature(route.normalized_text or '')
    cleaned=[]; seen=set()
    for source in sources:
        domain_ok=source.domain in allowed
        usable=_source_is_usable(source)
        if source.id in seen:
            continue
        if not domain_ok or not usable:
            if trace is not None:
                reason='wrong_domain' if not domain_ok else 'unusable_excerpt'
                trace.record_gate_decision(source,domain_compatible=domain_ok,issue_compatible=None,accepted=False,reason=reason)
            continue
        issue_ok=_source_issue_compatible(query_signature,source)
        if not issue_ok:
            if trace is not None:
                trace.record_gate_decision(source,domain_compatible=True,issue_compatible=False,accepted=False,reason='issue_family_mismatch')
            continue
        seen.add(source.id); cleaned.append(source)
        if trace is not None:
            trace.record_gate_decision(source,domain_compatible=True,issue_compatible=True,accepted=True,reason=None)

    strict_primary={'cyber','personal_status','labor','commercial'}
    if route.primary_domain in strict_primary:
        primary=[s for s in cleaned if s.domain==route.primary_domain]
        if primary:
            return primary
        return []
    return cleaned


def retrieval_fallback(message:str,route:RouteResult,sources:list[SourceItem])->str:
    sources=_guard_sources(route,sources)
    if not sources:
        return insufficient_answer(message,route,sources)
    preferred=[s for s in sources if s.source_kind in {'canonical_verified','verified_crosscheck','official_guidance','official_service','judicial_principle'}]
    substantive=(preferred or sources)
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


def _choose_grounded(message:str,route:RouteResult,sources:list[SourceItem],trace:RequestTrace|None=None):
    sources=_guard_sources(route,sources,trace)
    grounded=generate_grounded_answer(message,route,sources)
    if not grounded: return None,None
    evaluation=evaluate_answer(message,route,grounded.text,sources)
    return grounded,evaluation


def _apply_cognition_to_route(route:RouteResult, case, force_domain:str|None)->RouteResult:
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


def _needs_broad_synthesis(message:str,route:RouteResult)->bool:
    if route.intent in {'penalty','deadline','appeal_deadline','fees','judgment'}:
        return False
    if route.language=='en':
        low=(message or '').lower()
        return any(x in low for x in (
            'what are the cases','main cases','situations','types of','when is','when can','conditions',
            'exceptions','overview','explain the law','grounds for','examples of',
        ))
    n=normalize_ar(message or '')
    return any(normalize_ar(x) in n for x in (
        'حالات','ما هي الحالات','متى يعتبر','متى يكون','انواع','أنواع','شروط','استثناءات',
        'اشرح القانون','شرح القانون','نظرة عامة','اسباب','أسباب','صور الفصل','امثلة','أمثلة',
    ))


def _record_case_on_trace(trace:RequestTrace|None,case)->None:
    if trace is None or case is None:
        return
    trace.actors=[{'id':a.id,'label':a.label,'role':a.role} for a in getattr(case,'actors',[])]
    trace.events=[{'text':e.text,'event_type':e.event_type,'actors':e.actors} for e in getattr(case,'events',[])]
    trace.disputed_facts=[f.text for f in getattr(case,'facts',[]) if getattr(f,'disputed',False)]
    trace.cognition_warnings=list(getattr(case,'warnings',[]) or [])
    trace.cognition_ambiguities=list(getattr(case,'cognition_ambiguities',[]) or [])
    trace.legal_hypotheses=[
        {'code':h.code,'domain':h.domain,'confidence':h.confidence,'status':h.status}
        for h in getattr(case,'hypotheses',[])
    ]


def _cited_source_ids(answer:str,sources:list[SourceItem])->list[str]:
    """Best-effort mapping of "[S<n>]" inline citation markers back to source ids.

    This is a diagnostic approximation, not a guarantee the writer used the excerpt correctly --
    it only recovers WHICH of the sources handed to the writer were referenced by index, which is
    enough to distinguish "the right evidence never reached the writer" (evidence-selection layer)
    from "the right evidence was available but the final wording is wrong" (writer layer).
    """
    ids=[]
    for match in _CITATION_RE.finditer(answer or ''):
        idx=int(match.group(1))-1
        if 0<=idx<len(sources) and sources[idx].id not in ids:
            ids.append(sources[idx].id)
    return ids


def handle_chat(req:ChatRequest,trace:RequestTrace|None=None)->ChatResponse:
    """Run the real chat pipeline. `trace`, when supplied, is filled in as a diagnostic side
    record (see app.diagnostics.RequestTrace) -- it never changes what is retrieved, generated,
    or returned. The public HTTP layer never passes it; only test/admin callers do."""
    if trace is not None:
        trace.raw_input=req.message

    prior_history=[]
    if req.conversation_id:
        try:
            prior_history=runtime_store.history(req.conversation_id,8)
        except Exception:
            prior_history=[]

    initial_route=analyze_query(req.message,req.language,req.force_domain)
    effective_message,used_context=contextualize_message(req.message,prior_history,initial_route,trace)
    route=analyze_query(effective_message,req.language,req.force_domain) if used_context else initial_route

    if trace is not None:
        trace.normalized_input=route.normalized_text or ''
        trace.detected_language=route.language
        trace.detected_intent=route.intent
        trace.context_attachment_used=used_context

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
    _record_case_on_trace(trace,case)

    review_queries=_feedback_review_expansions(req.message,route.primary_domain) if route.intent!='smalltalk' else []
    cognition_queries=list(dict.fromkeys(cognition_queries+review_queries))[:10]
    broad_synthesis=_needs_broad_synthesis(effective_message,route)

    if trace is not None:
        trace.detected_domains=list(route.domains)
        trace.primary_domain=route.primary_domain
        trace.issue_signature=sorted(issue_signature(route.normalized_text or ''))

    cid=runtime_store.ensure_conversation(req.conversation_id,route.language)
    if trace is not None:
        trace.active_conversation_id=cid
    runtime_store.save_message(cid,'user',req.message,route.primary_domain,route.intent)
    if route.intent=='smalltalk':
        answer=strip_emoji_style(smalltalk(req.message,route.language))
        runtime_store.save_message(cid,'assistant',answer,'conversation','smalltalk')
        if trace is not None:
            trace.final_mode='conversation'
            trace.fallback_reason='smalltalk_intent'
        return ChatResponse(answer=answer,route=route,sources=[],mode='conversation',conversation_id=cid,disclaimer='')

    sources=[]
    emb=embed_query(effective_message)
    if emb:
        sources=_supabase_sources(supabase_store.hybrid_search(effective_message,emb,route.domains,8))
        if trace is not None: trace.record_candidates('hybrid',sources)
    if not sources and supabase_store.configured:
        sources=_cloud_keyword_sources([effective_message],route.domains,8)
        if trace is not None: trace.record_candidates('cloud_keyword',sources)
    if not sources:
        sources=repository.search(effective_message,route.domains,8)
        if trace is not None: trace.record_candidates('lexical',sources)
    if trace is not None:
        trace.retrieval_queries=[effective_message]
    sources=_guard_sources(route,sources,trace)

    if cognition_queries and (not sources or route.confidence < 0.8 or review_queries or broad_synthesis):
        if trace is not None:
            trace.retrieval_queries=list(dict.fromkeys(trace.retrieval_queries+cognition_queries))
        cognitive_sources=_cloud_keyword_sources([effective_message]+cognition_queries,route.domains,12)
        if not cognitive_sources:
            cognitive_sources=repository.adaptive_search(effective_message,route.domains,route.intent,12,cognition_queries)
        if trace is not None: trace.record_candidates('adaptive',cognitive_sources)
        cognitive_sources=_guard_sources(route,cognitive_sources,trace)
        if cognitive_sources:
            sources=cognitive_sources

    grounded,evaluation=_choose_grounded(effective_message,route,sources,trace)
    best_grounded=grounded
    best_eval=evaluation
    best_sources=sources
    used_adaptive=bool(review_queries)

    if broad_synthesis or grounded is None or grounded.strength!='strong' or (evaluation and evaluation.should_retry):
        evaluation_seed=evaluation or evaluate_answer(effective_message,route,'',sources)
        expansions=list(dict.fromkeys((evaluation_seed.expanded_queries or [])+cognition_queries))[:10]
        if trace is not None:
            trace.retrieval_queries=list(dict.fromkeys(trace.retrieval_queries+expansions))
        adaptive_sources=_cloud_keyword_sources([effective_message]+expansions,route.domains,12)
        if not adaptive_sources:
            adaptive_sources=repository.adaptive_search(effective_message,route.domains,route.intent,12,expansions)
        if trace is not None: trace.record_candidates('adaptive',adaptive_sources)
        adaptive_sources=_guard_sources(route,adaptive_sources,trace)
        if adaptive_sources:
            adaptive_grounded,adaptive_eval=_choose_grounded(effective_message,route,adaptive_sources,trace)
            if adaptive_grounded and (best_eval is None or adaptive_eval.score>=best_eval.score or broad_synthesis):
                best_grounded,best_eval,best_sources=adaptive_grounded,adaptive_eval,adaptive_sources
                used_adaptive=True

    best_sources=_guard_sources(route,best_sources,trace)
    if trace is not None:
        trace.accepted_source_ids=[s.id for s in best_sources]
    case_analysis=None
    case_analysis_eval=None
    if case and route.intent=='legal_question':
        case_analysis=generate_case_analysis_answer(effective_message,route,case,best_sources)
        if case_analysis:
            case_analysis_eval=evaluate_answer(effective_message,route,case_analysis.text,best_sources)

    history=runtime_store.history(cid,8)
    cognition_suffix='-cognition' if case and case.cognition_provider!='deterministic' else ''
    extractive_mode=('official-adaptive-extractive' if used_adaptive else 'official-self-checked-extractive')+cognition_suffix

    base_answer=None
    base_eval=best_eval
    base_mode=extractive_mode
    fallback_reason=''
    if case_analysis and case_analysis_eval and case_analysis_eval.passed:
        base_answer=case_analysis.text
        base_eval=case_analysis_eval
        base_mode='official-case-analysis'+cognition_suffix
    elif best_grounded and best_eval and best_eval.passed and (best_grounded.strength=='strong' or best_eval.score>=0.84):
        base_answer=best_grounded.text
    elif best_grounded:
        base_answer=best_grounded.text
        fallback_reason='grounded_answer_below_pass_threshold'
    else:
        critical={'penalty','deadline','appeal_deadline','fees','judgment','rights'}
        fallback_reason='no_grounded_answer'
        base_answer=insufficient_answer(effective_message,route,best_sources) if route.intent in critical else retrieval_fallback(effective_message,route,best_sources)
        base_eval=evaluate_answer(effective_message,route,base_answer,best_sources)

    answer=base_answer
    mode=base_mode

    llm_answer=generate_answer(
        effective_message,
        route,
        best_sources,
        history,
        draft_answer=base_answer,
        case=case,
    )
    if llm_answer:
        llm_eval=evaluate_answer(effective_message,route,llm_answer,best_sources)
        floor=max(0.62,(base_eval.score-0.15) if base_eval else 0.62)
        if llm_eval.passed and llm_eval.score>=floor:
            answer=llm_answer
            best_eval=llm_eval
            mode='official-openai-grounded-writer'+cognition_suffix
            fallback_reason=''

    answer=strip_emoji_style(answer or insufficient_answer(effective_message,route,best_sources))
    final_eval=evaluate_answer(effective_message,route,answer,best_sources)
    try:
        runtime_store.log_evaluation(cid,req.message,route.intent,route.primary_domain,final_eval.passed,final_eval.score,final_eval.reasons,mode)
    except Exception:
        pass
    runtime_store.save_message(cid,'assistant',answer,route.primary_domain,route.intent)
    if trace is not None:
        trace.final_mode=mode
        trace.final_cited_source_ids=_cited_source_ids(answer,best_sources)
        trace.fallback_reason=fallback_reason
    return ChatResponse(answer=answer,route=route,sources=best_sources,mode=mode,conversation_id=cid,disclaimer=AR_DISCLAIMER if route.language=='ar' else EN_DISCLAIMER)
