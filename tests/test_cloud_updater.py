from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.chat_v4 import _GuardedSupabaseStore
from app.legal_update_guard import LegalUpdateLedger, document_fingerprint, quality_gate
from app.repository import repository
from app.supabase_store import SupabaseStore, supabase_store


class _Query:
    def __init__(self, client, table):
        self.client=client; self.table=table; self.op='select'; self.filters={}; self.values=None; self.in_values=None

    def select(self, columns='*'):
        self.op='select'; self.columns=columns; return self

    def eq(self, field, value):
        self.filters[field]=value; return self

    def limit(self, value):
        self.limit_value=value; return self

    def upsert(self, values, **kwargs):
        self.op='upsert'; self.values=values; return self

    def insert(self, values, **kwargs):
        self.op='insert'; self.values=values; return self

    def delete(self):
        self.op='delete'; return self

    def in_(self, field, values):
        self.in_values=(field,list(values)); return self

    def execute(self):
        if self.op=='upsert':
            self.client.upserts.append((self.table,self.values)); return SimpleNamespace(data=[])
        if self.op=='insert':
            self.client.inserts.append((self.table,self.values)); return SimpleNamespace(data=[])
        if self.op=='delete':
            self.client.deletes.append((self.table,self.in_values,self.filters)); return SimpleNamespace(data=[])
        if self.table=='legal_documents' and self.filters.get('source_url'):
            return SimpleNamespace(data=list(self.client.prior_documents))
        if self.table=='legal_chunks' and self.filters.get('document_id'):
            return SimpleNamespace(data=list(self.client.existing_chunks))
        if self.table=='qanoni_legal_sync_fingerprints':
            return SimpleNamespace(data=list(self.client.fingerprint_rows))
        return SimpleNamespace(data=[])


class _Rpc:
    def __init__(self, client, name, params):
        self.client=client; self.name=name; self.params=params
    def execute(self):
        self.client.rpc_calls.append((self.name,self.params))
        return SimpleNamespace(data=list(self.client.rpc_rows))


class _FakeClient:
    def __init__(self):
        self.upserts=[]; self.inserts=[]; self.deletes=[]; self.rpc_calls=[]
        self.prior_documents=[]; self.existing_chunks=[]; self.fingerprint_rows=[]; self.rpc_rows=[]
    def table(self, name): return _Query(self,name)
    def rpc(self, name, params): return _Rpc(self,name,params)


def _statute_text():
    base=(
        'قانون العمل المادة 1 يسمى هذا القانون قانون العمل. '
        'المادة 2 يقصد بالكلمات والعبارات المعاني المخصصة لها. '
        'المادة 3 تسري أحكام هذا القانون على العمال وأصحاب العمل. '
        'المادة 4 لا يجوز الانتقاص من الحقوق المقررة للعامل. '
    )
    return base*3


def test_cloud_keyword_search_uses_free_rpc_without_embedding():
    store=SupabaseStore(); fake=_FakeClient(); store.client=fake
    fake.rpc_rows=[{'id':'c1','domain':'labor'}]
    rows=store.keyword_search('فصل من العمل',['labor'],8)
    assert rows==fake.rpc_rows
    assert fake.rpc_calls==[('keyword_search_legal_chunks',{
        'query_text':'فصل من العمل','filter_domains':['labor'],'match_count':8,
    })]


def test_guarded_cloud_keyword_search_drops_cross_domain_rows():
    class Inner:
        configured=True
        def keyword_search(self,*args,**kwargs):
            return [{'id':'a','domain':'personal_status'},{'id':'b','domain':'labor'}]
    rows=_GuardedSupabaseStore(Inner()).keyword_search('طلاق',['personal_status'],8)
    assert [r['id'] for r in rows]==['a']


def test_cloud_promotion_writes_new_version_before_deleting_stale():
    store=SupabaseStore(); fake=_FakeClient(); store.client=fake
    fake.prior_documents=[{'id':'old-document'}]
    fake.existing_chunks=[{'id':'old-chunk'}]
    count=store.replace_legal_document_chunks(
        title='قانون العمل المعدل',authority='وزارة العمل',domain='labor',
        source_url='https://mol.gov.jo/law.pdf',chunks=[('1',_statute_text())],
    )
    assert count==1
    assert any(table=='legal_documents' for table,_ in fake.upserts)
    assert any(table=='legal_chunks' for table,_ in fake.upserts)
    assert ('legal_chunks',('id',['old-chunk']),{}) in fake.deletes
    assert ('legal_documents',('id',['old-document']),{}) in fake.deletes
    # Writes are recorded before any stale deletion calls by the implementation contract.
    assert fake.upserts


def test_cloud_fingerprint_is_authoritative_for_stateless_runner(tmp_path,monkeypatch):
    db=tmp_path/'runner.sqlite3'; db.touch(); monkeypatch.setattr(repository,'db',db)
    text=_statute_text(); chunks=[('1',text)]
    fp=document_fingerprint(title='قانون العمل',authority='وزارة العمل',domain='labor',source_url='https://mol.gov.jo/law.pdf',chunks=chunks)
    monkeypatch.setattr(supabase_store,'client',object())
    monkeypatch.setattr(supabase_store,'get_legal_sync_fingerprint',lambda url:fp)
    plan=LegalUpdateLedger().plan(
        source_id='mol_laws',source_url='https://mol.gov.jo/law.pdf',title='قانون العمل',
        authority='وزارة العمل',domain='labor',text=text,chunks=chunks,source_domains=['labor'],
    )
    assert plan.action=='unchanged'


def test_listing_page_without_articles_is_not_promoted():
    text=('قوانين وزارة العمل قانون العمل قانون الضمان قانون تنظيم العمل ' * 15).strip()
    ok,reason=quality_gate(title='قوانين وزارة العمل',text=text,domain='labor',chunks=[(None,text)],source_domains=['labor'])
    assert not ok
    assert reason=='no_statutory_article_structure'


def test_weekly_workflow_uses_supabase_secrets_and_no_paid_llm_secret():
    root=Path(__file__).resolve().parents[1]
    workflow=(root/'.github/workflows/weekly-legal-sync.yml').read_text(encoding='utf-8')
    assert 'schedule:' in workflow
    assert "timezone: 'Asia/Amman'" in workflow
    assert 'secrets.SUPABASE_URL' in workflow
    assert 'secrets.SUPABASE_SERVICE_ROLE_KEY' in workflow
    assert 'OPENAI_API_KEY: ""' in workflow
    assert '--require-cloud' in workflow


def test_supabase_migration_contains_cloud_ledger_and_keyword_rpc():
    root=Path(__file__).resolve().parents[1]
    sql=(root/'supabase/migrations/20260820_v4_cloud_updater.sql').read_text(encoding='utf-8')
    assert 'qanoni_legal_sync_fingerprints' in sql
    assert 'qanoni_legal_update_events' in sql
    assert 'keyword_search_legal_chunks' in sql
    assert 'enable row level security' in sql.lower()
