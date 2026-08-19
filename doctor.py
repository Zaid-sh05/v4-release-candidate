import importlib,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
mods=['fastapi','uvicorn','pydantic','pydantic_settings','requests','bs4','pypdf']
optional=['mcp','openai','supabase']
print('Qanoni Pilot V3.6 FINAL doctor');print('='*31)
print('Python:',sys.version.split()[0])
if sys.version_info < (3,11): print('ERROR: Python 3.11+ required');raise SystemExit(1)
ok=True
for m in mods:
    try: importlib.import_module(m);print('OK ',m)
    except Exception as e: print('MISSING ',m,':',e);ok=False
for m in optional:
    try: importlib.import_module(m);print('OK optional ',m)
    except Exception: print('OPTIONAL/MISSING ',m)
db=ROOT/'data/qanoni.sqlite3';print('Database:',db,'exists=',db.exists())
if not db.exists(): ok=False
else:
    con=sqlite3.connect(db)
    chunks=con.execute('select count(*) from chunks').fetchone()[0]
    docs=con.execute('select count(*) from documents').fetchone()[0]
    sources=con.execute('select count(*) from source_registry').fetchone()[0]
    con.close();print(f'Corpus: {chunks} chunks | {docs} documents | {sources} sources')
try:
    from app.chat import handle_chat
    from app.models import ChatRequest
    checks=[('penalty','شو عقوبة الدائن اللي يطالب بدين وهمي بالإعسار؟','العقوبة:'),('deadline','كم مدة الاستئناف بالحكم الشرعي الغيابي؟','المدة:'),('fees','كم رسوم استئناف قضية جزائية؟','الرسوم:')]
    for name,q,needle in checks:
        ans=handle_chat(ChatRequest(message=q,language='ar')).answer
        passed=needle in ans;print('Answer engine',name,':','OK' if passed else 'FAIL');ok &= passed
except Exception as e:
    print('Answer engine ERROR:',e);ok=False

try:
    from app.config import settings
    print('OpenAI configured:', bool(settings.openai_api_key))
    print('Supabase configured:', bool(settings.supabase_url and settings.supabase_service_role_key))
    print('Runtime store:', settings.runtime_store)
except Exception:
    pass
print('Doctor finished:', 'OK' if ok else 'CHECK FAILED')
raise SystemExit(0 if ok else 1)
