import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.repository import repository

s=repository.stats();print('Qanoni V3 corpus audit');print('='*22);print(f"Documents: {s['documents']}");print(f"Searchable chunks: {s['chunks']}");print(f"Registered official sources: {s['registered_official_sources']}");print('\nDomains:')
for d,n in s['domains'].items(): print(f'  {d:18} {n}')
print('\nCore-law coverage:')
for x in repository.coverage(): print(f"  {x['status']:14} {x['title']} | chunks={x['chunks']} articles={x['distinct_articles']}")
