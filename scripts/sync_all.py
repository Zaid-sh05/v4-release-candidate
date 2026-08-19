import argparse
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app.repository import repository
from app.supabase_store import supabase_store
from app.sync_engine import sync_source


p=argparse.ArgumentParser()
p.add_argument('--source')
p.add_argument('--max-docs',type=int,default=None)
p.add_argument('--require-cloud',action='store_true',help='Fail unless the persistent Supabase updater schema is reachable.')
args=p.parse_args()

if args.require_cloud:
    if not supabase_store.configured:
        print('ERROR: Supabase is required for persistent weekly sync but is not configured.',file=sys.stderr)
        raise SystemExit(2)
    try:
        # A read-only sentinel lookup proves the persistent fingerprint table exists.
        supabase_store.get_legal_sync_fingerprint('__qanoni_updater_schema_probe__')
    except Exception as exc:
        print(f'ERROR: Supabase V4 updater migration is not ready: {type(exc).__name__}: {exc}',file=sys.stderr)
        raise SystemExit(3)

sources=repository.source_registry()
if args.source:
    sources=[s for s in sources if s['id']==args.source]

attempted=0
completed=0
hard_failures=[]
for s in sources:
    if s.get('sync_mode')=='reference':
        print(f"=== {s['id']} | reference only ===")
        continue
    attempted+=1
    print(f"\n=== {s['id']} | {s['authority']} ===")
    try:
        result=sync_source(s['id'],args.max_docs)
        print(result)
        completed+=1
        if result.get('documents_visited',0)==0 and result.get('errors'):
            hard_failures.append({'source_id':s['id'],'errors':result['errors']})
    except Exception as exc:
        failure={'source_id':s['id'],'error':f'{type(exc).__name__}: {exc}'}
        hard_failures.append(failure)
        print(failure)

print(f"\nSUMMARY: attempted={attempted} completed={completed} hard_failures={len(hard_failures)}")
if args.require_cloud and attempted and completed==0:
    print('ERROR: all scheduled crawl sources failed.',file=sys.stderr)
    raise SystemExit(4)
