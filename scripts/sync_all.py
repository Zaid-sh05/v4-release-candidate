import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.repository import repository
from app.sync_engine import sync_source

p=argparse.ArgumentParser();p.add_argument('--source');p.add_argument('--max-docs',type=int,default=None);args=p.parse_args()
sources=repository.source_registry()
if args.source: sources=[s for s in sources if s['id']==args.source]
for s in sources:
    if s.get('sync_mode')=='reference':
        print(f"=== {s['id']} | reference only ===");continue
    print(f"\n=== {s['id']} | {s['authority']} ===")
    try: print(sync_source(s['id'],args.max_docs))
    except Exception as e: print({'source_id':s['id'],'error':f'{type(e).__name__}: {e}'})
