import sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.config import settings

if not settings.openai_api_key:
    raise SystemExit('Set OPENAI_API_KEY in .env first.')
if not settings.supabase_url or not settings.supabase_service_role_key:
    raise SystemExit('Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env first.')

from openai import OpenAI
from supabase import create_client

ai=OpenAI(api_key=settings.openai_api_key)
sb=create_client(settings.supabase_url,settings.supabase_service_role_key)
total=0

# Always read the first batch of rows still missing embeddings. Incrementing a
# page number here would skip rows because each update removes rows from the
# NULL result set.
while True:
    rows=sb.table('legal_chunks').select('id,title,body').is_('embedding','null').range(0,99).execute().data or []
    if not rows:
        break
    texts=[f"{r['title']}\n{r['body']}"[:12000] for r in rows]
    emb=ai.embeddings.create(model=settings.openai_embedding_model,input=texts)
    for r,e in zip(rows,emb.data):
        sb.table('legal_chunks').update({'embedding':e.embedding}).eq('id',r['id']).execute()
        total+=1
    print('Embedded',total)
    time.sleep(.1)
print('Embedding complete:',total)
