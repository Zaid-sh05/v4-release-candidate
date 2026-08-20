from __future__ import annotations
import hmac
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.routing import Mount
from .config import ROOT, settings
from .models import ChatRequest, ChatResponse, FeedbackRequest
from .chat_v4 import handle_chat
from .feedback_review import review_negative_feedback
from .observability import ai_runtime_status, effective_corpus_stats
from .repository import repository
from .router import DOMAIN_LABELS
from .mcp_runtime import build_mcp_servers
from .supabase_store import supabase_store
from .sync_engine import sync_source
from .runtime_store import runtime_store

STATIC=ROOT/'static'
MCP_SERVERS=build_mcp_servers()
MCP_APPS={name:server.streamable_http_app(stateless_http=True,json_response=True) for name,server in MCP_SERVERS.items()}
MCP_DOMAINS=tuple(MCP_SERVERS)


def _replace_mcp_mount_apps(app:FastAPI, fresh_apps:dict[str,object])->None:
    """Point stable /mcp mounts at freshly-created MCP ASGI apps.

    StreamableHTTPSessionManager.run() is intentionally single-use. FastAPI's app
    object, however, can be started more than once in tests and some process managers.
    Rebuilding the MCP server instances per lifespan prevents a completed manager from
    being reused while keeping the public mount paths stable.
    """
    for route in app.routes:
        if not isinstance(route,Mount) or not route.path.startswith('/mcp/'):
            continue
        domain=route.path.removeprefix('/mcp/')
        fresh=fresh_apps.get(domain)
        if fresh is not None:
            route.app=fresh


@asynccontextmanager
async def lifespan(app:FastAPI)->AsyncIterator[None]:
    # Never reuse the module-level MCP session managers: the MCP SDK guarantees that
    # each StreamableHTTPSessionManager.run() instance is entered at most once.
    active_servers=build_mcp_servers()
    active_apps={name:server.streamable_http_app(stateless_http=True,json_response=True) for name,server in active_servers.items()}
    _replace_mcp_mount_apps(app,active_apps)
    app.state.mcp_servers=active_servers
    async with AsyncExitStack() as stack:
        for server in active_servers.values():
            await stack.enter_async_context(server.session_manager.run())
        try:
            yield
        finally:
            app.state.mcp_servers={}

app=FastAPI(title='Qanoni | قانوني Pilot API',version=settings.app_version,docs_url='/api/docs',redoc_url=None,lifespan=lifespan)
app.mount('/static',StaticFiles(directory=STATIC),name='static')
for domain,mcp_app in MCP_APPS.items(): app.mount(f'/mcp/{domain}',mcp_app)


def _require_admin(value:str|None)->None:
    if not settings.admin_api_key:
        raise HTTPException(status_code=403,detail='Admin API is disabled.')
    if not value or not hmac.compare_digest(value,settings.admin_api_key):
        raise HTTPException(status_code=401,detail='Invalid admin key.')


@app.get('/',include_in_schema=False)
def home(): return FileResponse(STATIC/'index.html')
@app.get('/favicon.ico',include_in_schema=False)
def favicon(): return FileResponse(STATIC/'favicon.svg',media_type='image/svg+xml')
@app.get('/manifest.webmanifest',include_in_schema=False)
def manifest(): return FileResponse(STATIC/'manifest.webmanifest',media_type='application/manifest+json')
@app.get('/sw.js',include_in_schema=False)
def sw(): return FileResponse(STATIC/'sw.js',media_type='application/javascript')

@app.get('/api/health')
def health():
    ai=ai_runtime_status()
    any_llm=bool(ai['answer_generation']['configured'] or ai['cognition']['configured'])
    return {
        'status':'ok',
        'app':settings.app_name,
        'version':settings.app_version,
        'environment':settings.app_env,
        'llm':'configured' if any_llm else 'deterministic_only',
        'ai':ai,
        'supabase':supabase_store.health(),
        'runtime_store':runtime_store.active_name,
        'admin_sync_enabled':bool(settings.admin_api_key),
        'mcp':{'enabled':bool(MCP_DOMAINS),'servers':list(MCP_DOMAINS)},
        'corpus':effective_corpus_stats(),
    }

@app.get('/api/domains')
def domains(): return [{'id':d,'label_ar':x['ar'],'label_en':x['en'],'tools':['search_official_law','get_article','list_official_sources']} for d,x in DOMAIN_LABELS.items()]
@app.get('/api/sources')
def sources(): return repository.source_registry()
@app.get('/api/coverage')
def coverage(): return repository.coverage()
@app.get('/api/stats')
def stats(): return effective_corpus_stats()
@app.get('/api/search')
def search(q:str=Query(min_length=2),domain:str='general',limit:int=8): return {'query':q,'domain':domain,'results':repository.search(q,[domain],min(max(limit,1),20))}
@app.post('/api/chat',response_model=ChatResponse)
def chat(req:ChatRequest): return handle_chat(req)

@app.post('/api/feedback')
def feedback(req:FeedbackRequest):
    try:
        result=runtime_store.save_feedback(req.conversation_id,req.rating,req.note)
    except ValueError as exc:
        raise HTTPException(status_code=400,detail=str(exc)) from exc
    if req.rating=='not_helpful':
        try:
            result['review']=review_negative_feedback(
                feedback_id=result.get('id'),
                conversation_id=req.conversation_id,
                note=req.note,
            )
        except Exception:
            # The original feedback remains durably saved even if automatic review hits
            # a transient retrieval/storage problem. Never turn a dislike click into 500.
            result['review']={'status':'needs_review','reason':'automatic_review_unavailable','proposed_answer':None}
    return result

@app.get('/api/feedback/stats')
def feedback_stats(): return runtime_store.feedback_stats()

@app.get('/api/admin/feedback/reviews')
def feedback_reviews(limit:int=50,x_admin_key:str|None=Header(default=None,alias='X-Admin-Key')):
    _require_admin(x_admin_key)
    return {'stats':runtime_store.feedback_review_stats(),'reviews':runtime_store.list_feedback_reviews(limit)}

@app.post('/api/admin/sync/{source_id}')
def sync_one(source_id:str,max_docs:int|None=None,x_admin_key:str|None=Header(default=None,alias='X-Admin-Key')):
    _require_admin(x_admin_key)
    try: return sync_source(source_id,max_docs)
    except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
    except Exception as exc: raise HTTPException(status_code=502,detail=f'Sync failed: {type(exc).__name__}: {str(exc)[:240]}') from exc
