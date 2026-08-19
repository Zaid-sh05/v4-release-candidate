from __future__ import annotations
import json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.repository import repository

VERIFIED='2026-08-19T10:30:00+00:00'

FACTS=[
    {
        'title':'مبدأ قضائي حديث: الفصل التعسفي وبدل الإشعار - المجلس القضائي الأردني',
        'authority':'المجلس القضائي الأردني',
        'domain':'labor',
        'url':'https://www.jc.jo/AR/ListDetails/%D9%85%D8%A8%D8%A7%D8%AF%D8%A6_%D9%88%D8%AF%D8%B1%D8%A7%D8%B3%D8%A7%D8%AA_%D8%A7%D9%84%D9%85%D9%83%D8%AA%D8%A8/1187/4360',
        'kind':'judicial_principle',
        'chunks':[
            (None,'مبدأ قضائي منشور من المجلس القضائي الأردني بعنوان قانون العمل / فصل تعسفي / عبء الإثبات / إعفاء العامل من العمل خلال فترة الإشعار، تمييز حقوق هيئة عامة رقم 6719/2024. يقرر أن إعفاء صاحب العمل للعامل من العمل خلال فترة الإشعار يلزم صاحب العمل بدفع بدل الإشعار للعامل. كما يوضح أن عبء إثبات الفصل التعسفي يقع ابتداء على العامل، وينتقل إلى صاحب العمل لإثبات مشروعية الإنهاء إذا دفع بأن الإنهاء كان بسبب إخلال العامل بالتزاماته.'),
        ],
    },
    {
        'title':'توضيح رسمي لوزارة العمل بشأن الفصل التعسفي واستحقاق العامل',
        'authority':'وزارة العمل الأردنية',
        'domain':'labor',
        'url':'https://www.mol.gov.jo/Ar/NewsDetails/%D8%A7%D8%AA%D9%81%D8%A7%D9%82_%D8%A8%D8%AE%D8%B5%D9%88%D8%B5_%D8%A7%D8%AD%D8%AF_%D9%85%D8%B5%D8%A7%D9%86%D8%B9_%D8%A7%D9%84%D8%A3%D9%84%D8%A8%D8%B3%D8%A9_%D8%A7%D9%84%D9%85%D9%87%D8%AF%D8%AF_%D8%A8%D8%A7%D9%84%D8%A5%D8%BA%D9%84%D8%A7%D9%82_%D9%81%D9%8A_%D8%A7%D9%84%D9%83%D8%B1%D9%83_%D8%A8%D8%B9%D8%AF_%D8%AA%D9%88%D9%81%D9%8A%D8%B1_%D8%A7%D8%B3%D8%AA%D8%AB%D9%85%D8%A7%D8%B1_%D8%AC%D8%AF%D9%8A%D8%AF_%D9%88%D9%81%D8%B1%D8%B5_%D8%B9%D9%85%D9%84_%D8%AC%D8%AF%D9%8A%D8%AF_%D9%88%D8%A7%D9%84%D8%AD%D9%81%D8%A7%D8%B8_%D8%B9%D9%84%D9%89_700%E2%80%AA_%D9%81%D8%B1%D8%B5%D8%A9_%D8%B9%D9%85%D9%84',
        'kind':'official_guidance',
        'chunks':[
            (None,'في توضيح رسمي منشور على موقع وزارة العمل بشأن حقوق عمال مصنع، ذكرت الوزارة أن قانون العمل ينص على منح العامل نصف شهر عن كل سنة خدمة بما لا يقل عن أجر شهرين إذا تبين أن العامل فصل فصلاً تعسفياً. هذا المصدر توضيح رسمي تطبيقي، ويجب عند حساب استحقاق حالة فردية التحقق من النص النافذ ونوع العقد وسبب الإنهاء ومدة الخدمة.'),
        ],
    },
    {
        'title':'قانون العمل رقم 8 لسنة 1996 وتعديلاته وملحقاته - صفحة القوانين الحالية',
        'authority':'وزارة العمل الأردنية',
        'domain':'labor',
        'url':'https://mol.gov.jo/AR/List/%D8%A7%D9%84%D9%82%D9%88%D8%A7%D9%86%D9%8A%D9%86',
        'kind':'official_guidance',
        'chunks':[
            (None,'تعرض صفحة القوانين الحالية في وزارة العمل الأردنية قانون العمل رقم 8 لسنة 1996 وتعديلاته وملحقاته بوصفه التشريع الأساسي المنشور لدى الوزارة لمسائل العمل. يجب ربط أي احتساب نهائي للحقوق بالنص النافذ للحالة، مع مراعاة نوع العقد وسبب الإنهاء والتعديلات ذات الصلة.'),
        ],
    },
]

REGISTRY=[
    ('jc_labor_principles','المجلس القضائي - مبادئ قانون العمل','Judicial Council - Labour Principles','المجلس القضائي الأردني','https://www.jc.jo/AR/List/%D9%85%D8%A8%D8%A7%D8%AF%D8%A6_%D9%88%D8%AF%D8%B1%D8%A7%D8%B3%D8%A7%D8%AA_%D8%A7%D9%84%D9%85%D9%83%D8%AA%D8%A8',['labor'],'reference','مبادئ قضائية رسمية منشورة، تستخدم لفهم تطبيق قواعد العمل دون تعديل النص التشريعي.'),
    ('mol_labor_termination_guidance','وزارة العمل - توضيحات إنهاء العمل','Ministry of Labour - Termination Guidance','وزارة العمل الأردنية','https://www.mol.gov.jo/AR/Modules/FAQ',['labor'],'reference','مصادر وتوضيحات رسمية مساعدة في مسائل إنهاء العمل والنزاعات العمالية.'),
]

def reset_fact(d):
    import hashlib
    doc_id=hashlib.sha1(f"{d['url']}|{d['title']}|{d['domain']}".encode()).hexdigest()
    with repository.connect() as con:
        con.execute('delete from chunks where document_id=?',(doc_id,))
        con.execute('delete from documents where id=?',(doc_id,))

def seed_registry():
    with repository.connect() as con:
        for rid,ar,en,authority,url,domains,mode,notes in REGISTRY:
            con.execute('''insert into source_registry(id,name_ar,name_en,authority,url,domains_json,sync_mode,notes,last_sync_at,last_sync_status)
                values(?,?,?,?,?,?,?,?,?,?)
                on conflict(id) do update set name_ar=excluded.name_ar,name_en=excluded.name_en,authority=excluded.authority,url=excluded.url,domains_json=excluded.domains_json,sync_mode=excluded.sync_mode,notes=excluded.notes,last_sync_at=excluded.last_sync_at,last_sync_status=excluded.last_sync_status''',
                (rid,ar,en,authority,url,json.dumps(domains,ensure_ascii=False),mode,notes,VERIFIED,'verified'))

def main():
    seed_registry();total=0
    for d in FACTS:
        reset_fact(d)
        total+=repository.upsert_document_chunks(title=d['title'],authority=d['authority'],domain=d['domain'],source_url=d['url'],chunks=d['chunks'],source_kind=d['kind'],verified_at=VERIFIED)
    with repository.connect() as con:
        con.execute("insert into chunk_fts(chunk_fts) values('delete-all')")
        rows=con.execute('select c.rowid,d.title_ar,c.body from chunks c join documents d on d.id=c.document_id').fetchall()
        con.executemany('insert into chunk_fts(rowid,title,body) values(?,?,?)',[(r['rowid'],r['title_ar'],r['body']) for r in rows])
    print('V3.4 legal-depth facts:',total)
    print(repository.stats())

if __name__=='__main__': main()
