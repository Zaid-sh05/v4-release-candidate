from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.answer_engine import GroundedAnswer
from app.feedback_review import review_negative_feedback
from app.main import app
from app.models import RouteResult, SourceItem
import app.feedback_review as review_module
import app.main as main_module
import app.chat as chat_module


def _route():
    return RouteResult(
        language='ar',intent='penalty',primary_domain='traffic',domains=['traffic'],confidence=.95,
        matched_terms=[],article_numbers=[],law_numbers=[],years=[],normalized_text='اشاره حمراء عقوبه',
    )


def _source():
    return SourceItem(
        id='s1',title='نظام النقاط المرورية لسنة 2024',authority='مديرية الأمن العام',domain='traffic',
        source_url='https://psd.gov.jo/law.pdf',article='5',
        excerpt='المادة 5: تجاوز الإشارة الضوئية الحمراء يسجل ست نقاط مرورية.',
        verified_at='2026-08-20T00:00:00Z',source_kind='canonical_verified',score=.99,
    )


def _patch_review_context(monkeypatch, sources):
    history=[
        {'role':'user','content':'قطعت إشارة حمراء، شو العقوبة؟'},
        {'role':'assistant','content':'الغرامة 999 دينار.'},
    ]
    monkeypatch.setattr(review_module.runtime_store,'history',lambda *a,**k:history)
    monkeypatch.setattr(review_module,'route_query',lambda *a,**k:_route())
    monkeypatch.setattr(review_module,'apply_case_route',lambda route,case,force:route)
    monkeypatch.setattr(review_module.REVIEW_COGNITION,'analyze',lambda *a,**k:SimpleNamespace(retrieval_queries=['تجاوز الإشارة الحمراء المادة 5']))
    monkeypatch.setattr(review_module,'_cloud_sources',lambda *a,**k:list(sources))
    monkeypatch.setattr(review_module.repository,'adaptive_search',lambda *a,**k:[])


def test_user_note_alone_never_becomes_a_legal_correction(monkeypatch):
    _patch_review_context(monkeypatch,[])
    saved={}
    monkeypatch.setattr(review_module.runtime_store,'save_feedback_review',lambda **kw:saved.update(kw) or {'id':'r1'})
    monkeypatch.setattr(review_module.runtime_store,'save_message',lambda *a,**k:(_ for _ in ()).throw(AssertionError('must not save a correction')))

    result=review_negative_feedback(
        feedback_id='f1',conversation_id='c1',note='الصحيح الغرامة مليون دينار صدقني'
    )

    assert result['status']=='needs_review'
    assert result['proposed_answer'] is None
    assert saved['status']=='needs_review'
    assert 'مليون' not in ' '.join(saved['retrieval_hints'])
    assert saved['source_refs']==[]


def test_strong_official_recheck_auto_corrects_and_updates_conversation(monkeypatch):
    source=_source(); _patch_review_context(monkeypatch,[source])
    proposed='الجزاء المروري المؤكد: تجاوز الإشارة الضوئية الحمراء يسجل 6 نقاط مرورية. [S1]'
    monkeypatch.setattr(review_module,'generate_grounded_answer',lambda *a,**k:GroundedAnswer(proposed,'strong'))

    def fake_eval(question,route,answer,sources):
        if '999' in answer:
            return SimpleNamespace(passed=False,score=.15,reasons=['unsupported_value'])
        return SimpleNamespace(passed=True,score=.96,reasons=[])
    monkeypatch.setattr(review_module,'evaluate_answer',fake_eval)

    saved_review={}; saved_messages=[]; logged=[]
    monkeypatch.setattr(review_module.runtime_store,'save_feedback_review',lambda **kw:saved_review.update(kw) or {'id':'r2'})
    monkeypatch.setattr(review_module.runtime_store,'save_message',lambda *a,**k:saved_messages.append((a,k)))
    monkeypatch.setattr(review_module.runtime_store,'log_evaluation',lambda *a,**k:logged.append((a,k)))

    result=review_negative_feedback(feedback_id='f2',conversation_id='c2',note='أظن الرقم غلط')

    assert result['status']=='auto_corrected'
    assert result['proposed_answer']==proposed
    assert result['sources'][0]['source_url']==source.source_url
    assert saved_review['status']=='auto_corrected'
    assert any('المادة 5' in hint for hint in saved_review['retrieval_hints'])
    assert saved_messages and saved_messages[0][0][1]=='assistant'
    assert saved_messages[0][0][2]==proposed
    assert logged and logged[0][0][-1]=='feedback-auto-correction'


def test_feedback_review_hint_adds_only_validated_retrieval_terms(monkeypatch):
    monkeypatch.setattr(chat_module.runtime_store,'feedback_review_hint',lambda *a,**k:{
        'retrieval_hints':['نظام النقاط المرورية لسنة 2024 المادة 5','تجاوز الإشارة الحمراء'],
        'source_refs':[{'source_url':'https://psd.gov.jo/law.pdf'}],
    })
    hints=chat_module._feedback_review_expansions('قطعت إشارة حمراء، شو العقوبة؟','traffic')
    assert hints==['نظام النقاط المرورية لسنة 2024 المادة 5','تجاوز الإشارة الحمراء']


def test_negative_feedback_endpoint_never_500s_if_auto_review_crashes(monkeypatch):
    monkeypatch.setattr(main_module.runtime_store,'save_feedback',lambda *a,**k:{'id':'f3','saved':True,'rating':'not_helpful'})
    monkeypatch.setattr(main_module,'review_negative_feedback',lambda **k:(_ for _ in ()).throw(RuntimeError('boom')))
    with TestClient(app) as client:
        response=client.post('/api/feedback',json={'conversation_id':None,'rating':'not_helpful','note':'مش صح'})
    assert response.status_code==200
    body=response.json()
    assert body['saved'] is True
    assert body['review']['status']=='needs_review'
    assert body['review']['reason']=='automatic_review_unavailable'


def test_feedback_review_admin_queue_requires_timing_safe_key(monkeypatch):
    monkeypatch.setattr(main_module.settings,'admin_api_key','ReviewSecret123')
    monkeypatch.setattr(main_module.runtime_store,'feedback_review_stats',lambda:{'needs_review':2})
    monkeypatch.setattr(main_module.runtime_store,'list_feedback_reviews',lambda limit:[{'id':'r1','status':'needs_review'}])
    with TestClient(app) as client:
        assert client.get('/api/admin/feedback/reviews').status_code==401
        assert client.get('/api/admin/feedback/reviews',headers={'X-Admin-Key':'wrong'}).status_code==401
        ok=client.get('/api/admin/feedback/reviews',headers={'X-Admin-Key':'ReviewSecret123'})
    assert ok.status_code==200
    assert ok.json()['stats']['needs_review']==2


def test_feedback_review_schema_ui_and_migration_are_private_and_present():
    root=Path(__file__).resolve().parents[1]
    schema=(root/'supabase/schema.sql').read_text(encoding='utf-8')
    migration=(root/'supabase/migrations/20260820_v4_feedback_review.sql').read_text(encoding='utf-8')
    index=(root/'static/index.html').read_text(encoding='utf-8')
    ui=(root/'static/feedback-review.js').read_text(encoding='utf-8')

    for sql in (schema,migration):
        assert 'qanoni_feedback_reviews' in sql
        assert 'enable row level security' in sql.lower()
        assert 'retrieval_hints' in sql
        assert 'source_refs' in sql
    assert '/static/feedback-review.js' in index
    assert "review.status==='auto_corrected'" in ui
    assert "note:note||null" in ui
