"""Explicit network check for OpenAI + Supabase.

This script never prints secrets. It is safe to run before deployment after
.env is configured.
"""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.config import settings

ok=True
print('Qanoni V3.6 integration check')
print('='*31)

if not settings.openai_api_key:
    print('OPENAI: NOT CONFIGURED')
    ok=False
else:
    try:
        from openai import OpenAI
        ai=OpenAI(api_key=settings.openai_api_key)
        model=ai.models.retrieve(settings.openai_model)
        e=ai.embeddings.create(model=settings.openai_embedding_model,input='قانوني integration check')
        dims=len(e.data[0].embedding)
        print(f'OPENAI: OK | model={model.id} | embedding_dims={dims}')
        if dims != 1536:
            print('OPENAI: ERROR expected 1536 embedding dimensions for current Supabase schema')
            ok=False
    except Exception as exc:
        print('OPENAI: ERROR',type(exc).__name__,str(exc)[:300])
        ok=False

if not settings.supabase_url or not settings.supabase_service_role_key:
    print('SUPABASE: NOT CONFIGURED')
    ok=False
else:
    try:
        from supabase import create_client
        sb=create_client(settings.supabase_url,settings.supabase_service_role_key)
        legal=sb.table('legal_chunks').select('id').limit(1).execute().data or []
        runtime=sb.table('qanoni_conversations').select('id').limit(1).execute().data or []
        print(f'SUPABASE: OK | legal_chunks reachable | runtime tables reachable')
        if not legal:
            print('SUPABASE: WARNING legal_chunks is empty; run scripts/push_to_supabase.py')
    except Exception as exc:
        print('SUPABASE: ERROR',type(exc).__name__,str(exc)[:300])
        ok=False

if ok and settings.openai_api_key and settings.supabase_url:
    try:
        from app.llm import embed_query
        from app.supabase_store import supabase_store
        emb=embed_query('ما عقوبة قطع الإشارة الحمراء؟')
        rows=supabase_store.hybrid_search('ما عقوبة قطع الإشارة الحمراء؟',emb,['traffic'],3) if emb else []
        print('HYBRID SEARCH:', 'OK' if rows else 'NO RESULTS', f'| results={len(rows)}')
        if not rows:
            print('Run scripts/embed_supabase.py after uploading the corpus.')
            ok=False
    except Exception as exc:
        print('HYBRID SEARCH: ERROR',type(exc).__name__,str(exc)[:300])
        ok=False

print('Result:', 'READY' if ok else 'CHECK REQUIRED')
raise SystemExit(0 if ok else 1)
