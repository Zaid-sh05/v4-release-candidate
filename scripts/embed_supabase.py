import sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.config import settings

if not settings.openai_api_key:
    raise SystemExit('Set OPENAI_API_KEY in .env first.')
if not settings.supabase_url or not settings.supabase_service_role_key:
    raise SystemExit('Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env first.')

from openai import OpenAI, BadRequestError
from supabase import create_client

ai=OpenAI(api_key=settings.openai_api_key)
sb=create_client(settings.supabase_url,settings.supabase_service_role_key)
total=0

# A plain character cap is only an approximation of the embedding model's 8192-token limit --
# Arabic legal text (with diacritics, numbering, and mixed digits) can run well over 1
# token/char, so a naive 12000-char cap was overshooting the real token budget for some
# chunks. 6000 chars is a conservative first-pass cap; on a real BadRequestError the
# offending text is re-embedded alone with a much harder cap, so one oversized chunk never
# blocks the rest of a batch.
def embed_one(text: str, cap: int):
    return ai.embeddings.create(model=settings.openai_embedding_model, input=[text[:cap]]).data[0]

# Always read the first batch of rows still missing embeddings. Incrementing a
# page number here would skip rows because each update removes rows from the
# NULL result set.
while True:
    rows=sb.table('legal_chunks').select('id,title,body').is_('embedding','null').range(0,99).execute().data or []
    if not rows:
        break
    texts=[f"{r['title']}\n{r['body']}"[:6000] for r in rows]
    try:
        emb=ai.embeddings.create(model=settings.openai_embedding_model,input=texts).data
    except BadRequestError:
        emb=[]
        for r,t in zip(rows,texts):
            try:
                emb.append(embed_one(t,6000))
            except BadRequestError:
                emb.append(embed_one(t,1500))
    for r,e in zip(rows,emb):
        sb.table('legal_chunks').update({'embedding':e.embedding}).eq('id',r['id']).execute()
        total+=1
    print('Embedded',total)
    time.sleep(.1)
print('Embedding complete:',total)
