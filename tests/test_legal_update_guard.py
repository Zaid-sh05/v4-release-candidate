from __future__ import annotations

from types import SimpleNamespace

from app.legal_update_guard import LegalUpdateLedger, document_fingerprint, quality_gate
from app.repository import repository
from app import sync_engine


def _law_text(extra: str = '') -> str:
    body = (
        'قانون العمل الأردني المادة 1 يسمى هذا القانون قانون العمل. '
        'المادة 2 يقصد بالكلمات والعبارات المعاني المخصصة لها في هذا القانون. '
        'المادة 3 تسري أحكام هذا القانون على العمال وأصحاب العمل ضمن الحدود المقررة قانوناً. '
        'المادة 4 لا يجوز الانتقاص من الحقوق المقررة للعامل بموجب أحكام هذا القانون. '
    )
    return (body * 3) + extra


def test_fingerprint_is_stable_and_changes_with_content():
    chunks=[('1',_law_text())]
    a=document_fingerprint(title='قانون العمل',authority='وزارة العمل',domain='labor',source_url='https://mol.gov.jo/law.pdf',chunks=chunks)
    b=document_fingerprint(title='قانون العمل',authority='وزارة العمل',domain='labor',source_url='https://mol.gov.jo/law.pdf',chunks=chunks)
    c=document_fingerprint(title='قانون العمل',authority='وزارة العمل',domain='labor',source_url='https://mol.gov.jo/law.pdf',chunks=[('1',_law_text(' تعديل'))])
    assert a == b
    assert a != c


def test_quality_gate_rejects_short_and_cross_domain_content():
    ok, reason=quality_gate(title='قانون العمل',text='قانون قصير',domain='labor',chunks=[('1','قانون قصير')],source_domains=['labor'])
    assert not ok and reason == 'text_too_short'

    text=_law_text()
    ok, reason=quality_gate(title='قانون العمل',text=text,domain='criminal',chunks=[('1',text)],source_domains=['labor'])
    assert not ok and reason == 'domain_outside_source_scope'


def test_ledger_classifies_new_unchanged_and_changed(tmp_path, monkeypatch):
    db=tmp_path/'ledger.sqlite3'; db.touch()
    monkeypatch.setattr(repository,'db',db)
    ledger=LegalUpdateLedger()
    text=_law_text(); chunks=[('1',text)]
    kwargs=dict(source_id='mol_laws',source_url='https://mol.gov.jo/law.pdf',title='قانون العمل',authority='وزارة العمل',domain='labor',text=text,chunks=chunks,source_domains=['labor'])

    first=ledger.plan(**kwargs)
    assert first.action == 'new'
    ledger.record(source_id=kwargs['source_id'],source_url=kwargs['source_url'],title=kwargs['title'],domain=kwargs['domain'],plan=first,promoted=True)

    second=ledger.plan(**kwargs)
    assert second.action == 'unchanged'

    changed_kwargs={**kwargs,'text':text+' تعديل رسمي جديد','chunks':[('1',text+' تعديل رسمي جديد')]}
    third=ledger.plan(**changed_kwargs)
    assert third.action == 'changed'


def test_sync_source_promotes_once_then_skips_unchanged(tmp_path, monkeypatch):
    db=tmp_path/'sync.sqlite3'; db.touch()
    monkeypatch.setattr(repository,'db',db)

    source={
        'id':'mol_laws','authority':'وزارة العمل الأردنية','url':'https://mol.gov.jo/AR/List/laws',
        'sync_mode':'crawl','domains':['labor'],
    }
    monkeypatch.setattr(sync_engine.repository,'source_registry',lambda:[source])
    monkeypatch.setattr(sync_engine.repository,'update_sync_status',lambda *a,**k:None)
    inserted=[]
    monkeypatch.setattr(sync_engine.repository,'upsert_document_chunks',lambda **kwargs: inserted.append(kwargs) or len(kwargs['chunks']))
    monkeypatch.setattr(sync_engine,'choose_domain',lambda title,text,source:'labor')

    html=f'<html><head><title>قانون العمل</title></head><body>{_law_text()}</body></html>'.encode('utf-8')

    class FakeResponse:
        def __init__(self):
            self.content=html; self.url=source['url']; self.headers={'content-type':'text/html; charset=utf-8'}; self.encoding='utf-8'; self.apparent_encoding='utf-8'
        @property
        def text(self): return self.content.decode('utf-8')
        def raise_for_status(self): return None

    class FakeSession:
        def __init__(self): self.headers={}
        def get(self,*a,**k): return FakeResponse()

    monkeypatch.setattr(sync_engine.requests,'Session',FakeSession)

    first=sync_engine.sync_source('mol_laws',max_docs=1)
    second=sync_engine.sync_source('mol_laws',max_docs=1)

    assert first['documents_new'] == 1
    assert first['chunks_upserted'] > 0
    assert second['documents_unchanged'] == 1
    assert second['chunks_upserted'] == 0
    assert len(inserted) == 1
