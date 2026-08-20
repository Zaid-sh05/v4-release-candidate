from __future__ import annotations

from .answer_engine import generate_grounded_answer
from .cognition import CaseCognitionEngine
from .evaluator import evaluate_answer
from .models import SourceItem
from .repository import repository
from .routing_guard import apply_case_route, route_query
from .runtime_store import runtime_store
from .source_quality import looks_garbled_legal_text
from .supabase_store import supabase_store
from .text import normalize_ar


REVIEW_COGNITION=CaseCognitionEngine(enable_llm=False)


def _last_question_answer(history:list[dict])->tuple[str,str]:
    assistant_index=None
    for i in range(len(history)-1,-1,-1):
        if history[i].get('role')=='assistant' and (history[i].get('content') or '').strip():
            assistant_index=i; break
    if assistant_index is None: return '',''
    previous_answer=(history[assistant_index].get('content') or '').strip()
    for i in range(assistant_index-1,-1,-1):
        if history[i].get('role')=='user' and (history[i].get('content') or '').strip():
            return (history[i].get('content') or '').strip(),previous_answer
    return '',previous_answer


def _cloud_sources(queries:list[str],domains:list[str],limit:int=16)->list[SourceItem]:
    if not supabase_store.configured: return []
    allowed={d for d in domains if d not in {'general','conversation'}}
    out=[]; seen=set()
    for query in queries[:10]:
        q=' '.join((query or '').split()).strip()
        if len(q)<2: continue
        for row in supabase_store.keyword_search(q,domains,min(limit,20)):
            try: item=SourceItem(**row)
            except Exception: continue
            if allowed and item.domain not in allowed: continue
            if looks_garbled_legal_text(item.excerpt): continue
            if item.id in seen: continue
            seen.add(item.id); out.append(item)
            if len(out)>=limit: return out
    return out


def _merge_sources(*groups:list[SourceItem],limit:int=18)->list[SourceItem]:
    merged={}
    for group in groups:
        for source in group or []:
            if looks_garbled_legal_text(source.excerpt):
                continue
            current=merged.get(source.id)
            if current is None or source.score>current.score:
                merged[source.id]=source
    return sorted(
        merged.values(),
        key=lambda s:(
            s.source_kind in {'canonical_verified','verified_crosscheck'},
            s.source_kind in {'official_guidance','official_service','judicial_principle'},
            s.source_kind=='official_sync',
            s.score,
        ),
        reverse=True,
    )[:limit]


def _source_refs(sources:list[SourceItem])->list[dict]:
    return [{
        'id':s.id,'title':s.title,'authority':s.authority,'domain':s.domain,
        'source_url':s.source_url,'article':s.article,'verified_at':s.verified_at,
        'source_kind':s.source_kind,
    } for s in sources[:8]]


def _retrieval_hints(case,sources:list[SourceItem])->list[str]:
    hints=[]
    for query in case.retrieval_queries[:5]:
        q=' '.join((query or '').split()).strip()
        if q and q not in hints: hints.append(q)
    for source in sources[:5]:
        hint=' '.join(x for x in [source.title, f'المادة {source.article}' if source.article else ''] if x).strip()
        if hint and hint not in hints: hints.append(hint)
    return hints[:8]


def review_negative_feedback(*,feedback_id:str|None,conversation_id:str|None,note:str|None=None)->dict:
    """Re-check a disliked answer against official evidence without online weight training.

    User feedback is only a retrieval clue. It never becomes evidence and is never stored
    as a legal correction unless the re-check independently finds strong official support.
    """
    if not conversation_id:
        return {'status':'needs_review','reason':'missing_conversation','proposed_answer':None}
    history=runtime_store.history(conversation_id,12)
    question,previous_answer=_last_question_answer(history)
    if not question or not previous_answer:
        return {'status':'needs_review','reason':'missing_question_answer_pair','proposed_answer':None}

    route=route_query(question,'auto',None)
    try:
        case=REVIEW_COGNITION.analyze(question,route.language)
        route=apply_case_route(route,case,None)
    except Exception:
        case=None

    review_queries=[question]
    if case:
        review_queries.extend(case.retrieval_queries[:6])
    if note and len(note.strip())>=2:
        review_queries.append(note.strip()[:600])
    review_queries=list(dict.fromkeys(q for q in review_queries if q))[:10]

    cloud=_cloud_sources(review_queries,route.domains,16)
    expansions=(case.retrieval_queries[:8] if case else [])
    local=repository.adaptive_search(question,route.domains,route.intent,16,expansions)
    sources=_merge_sources(cloud,local,limit=18)

    old_eval=evaluate_answer(question,route,previous_answer,sources)
    grounded=generate_grounded_answer(question,route,sources) if sources else None
    new_eval=evaluate_answer(question,route,grounded.text,sources) if grounded else None

    auto_corrected=bool(
        grounded and new_eval and new_eval.passed and grounded.strength=='strong' and new_eval.score>=0.84
        and normalize_ar(grounded.text)!=normalize_ar(previous_answer)
    )
    if auto_corrected:
        status='auto_corrected'; reason='strong_official_recheck_passed'; proposed=grounded.text
    elif not sources:
        status='needs_review'; reason='no_official_sources_found'; proposed=None
    elif not grounded:
        status='needs_review'; reason='no_grounded_correction_generated'; proposed=None
    else:
        status='needs_review'; reason='official_recheck_not_strong_enough'; proposed=None

    hints=_retrieval_hints(case,sources) if case else []
    saved=runtime_store.save_feedback_review(
        feedback_id=feedback_id,
        conversation_id=conversation_id,
        question=question,
        previous_answer=previous_answer,
        feedback_note=note,
        primary_domain=route.primary_domain,
        status=status,
        old_score=float(old_eval.score) if old_eval else None,
        proposed_answer=proposed,
        new_score=float(new_eval.score) if new_eval else None,
        source_refs=_source_refs(sources),
        retrieval_hints=hints,
        review_reason=reason,
    )

    # A correction strong enough for automatic promotion becomes part of conversation
    # continuity immediately, so the user's next follow-up sees the corrected state.
    if auto_corrected:
        try:
            runtime_store.log_evaluation(
                conversation_id,question,route.intent,route.primary_domain,True,
                float(new_eval.score),new_eval.reasons,'feedback-auto-correction',
            )
            runtime_store.save_message(
                conversation_id,'assistant',proposed,route.primary_domain,'feedback_correction'
            )
        except Exception:
            pass

    return {
        'review_id':saved.get('id'),
        'status':status,
        'reason':reason,
        'old_score':float(old_eval.score) if old_eval else None,
        'new_score':float(new_eval.score) if new_eval else None,
        'proposed_answer':proposed,
        'sources':_source_refs(sources) if auto_corrected else [],
        'domain':route.primary_domain,
    }
