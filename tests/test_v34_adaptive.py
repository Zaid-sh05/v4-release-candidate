import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from app.main import app
from app.chat import handle_chat
from app.models import ChatRequest
from app.evaluator import evaluate_answer
from app.repository import repository


def main():
    r=handle_chat(ChatRequest(message='فصلني صاحب العمل بدون إنذار شو حقوقي؟',language='ar'))
    assert r.route.primary_domain=='labor'
    for x in ('بدل الإشعار','الفصل التعسفي','نصف شهر','شهرين','محدد المدة'):
        assert x in r.answer,(x,r.answer)
    assert 'المادة 31' not in r.answer,r.answer
    ev=evaluate_answer('فصلني صاحب العمل بدون إنذار شو حقوقي؟',r.route,r.answer,r.sources)
    assert ev.passed,(ev,r.answer)

    r2=handle_chat(ChatRequest(message='صاحب العمل قال لا تداوم خلال شهر الإنذار، شو حقي؟',language='ar'))
    assert 'بدل الإشعار' in r2.answer,r2.answer

    bad=evaluate_answer('ما عقوبة السرقة؟',r.route,'وجدت المصادر الرسمية التالية',r.sources)
    assert not bad.passed and bad.should_retry,bad

    with TestClient(app) as c:
        rr=c.post('/api/feedback',json={'conversation_id':r.conversation_id,'rating':'helpful'})
        assert rr.status_code==200,rr.text
        st=c.get('/api/feedback/stats')
        assert st.status_code==200 and st.json().get('helpful',0)>=1,st.text

    # runtime tables should exist and be writable
    with repository.connect() as con:
        assert con.execute("select name from sqlite_master where type='table' and name='answer_evaluations'").fetchone()
        assert con.execute("select name from sqlite_master where type='table' and name='feedback'").fetchone()
    print('V3.4 adaptive/self-evaluation tests: OK')

if __name__=='__main__': main()
