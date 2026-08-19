from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.repository import repository
from app.chat import handle_chat
from app.models import ChatRequest

CHECKS=[
 ('Personal Status','قانون الأحوال الشخصية رقم 15 لسنة 2019','personal_status',200),
 ('Companies','قانون الشركات رقم 22 لسنة 1997 وتعديلاته','commercial',150),
 ('Traffic','قانون السير رقم 49 لسنة 2008 وتعديلاته','traffic',30),
 ('Traffic Points','نظام النقاط المرورية لسنة 2024','traffic',10),
 ('Sharia Procedure','قانون أصول المحاكمات الشرعية وتعديلاته','procedure',50),
 ('Penal Code','قانون العقوبات رقم 16 لسنة 1960 وتعديلاته','criminal',80),
 ('Civil Code','القانون المدني رقم 43 لسنة 1976 وتعديلاته','civil',80),
 ('Criminal Procedure','قانون أصول المحاكمات الجزائية رقم 9 لسنة 1961 وتعديلاته','procedure',80),
 ('Civil Procedure','قانون أصول المحاكمات المدنية رقم 24 لسنة 1988 وتعديلاته','procedure',80),
]

def title_match(a,b):
 from app.text import normalize_ar
 a=normalize_ar(a);b=normalize_ar(b)
 return a==b or a in b or b in a

def count_articles(title,domain):
 with repository.connect() as con:
  docs=con.execute('select id,title_ar,source_kind from documents where domain=?',(domain,)).fetchall()
  ids=[d['id'] for d in docs if title_match(title,d['title_ar'])]
  arts=set();chunks=0;kinds=set()
  for did in ids:
   rows=con.execute('select article from chunks where document_id=?',(did,)).fetchall();chunks+=len(rows)
   arts.update(str(r['article']) for r in rows if r['article']);
   row=next(d for d in docs if d['id']==did);kinds.add(row['source_kind'])
 return chunks,len(arts),kinds

def main():
 print('Qanoni Pilot V3 readiness audit')
 print('='*32)
 print('Corpus:',repository.stats())
 print('\nCore legal texts')
 gaps=[]
 for label,title,domain,threshold in CHECKS:
  chunks,arts,kinds=count_articles(title,domain)
  ready=arts>=threshold
  status='READY' if ready else ('REFERENCE' if kinds and all(k=='reference' for k in kinds) else ('PARTIAL' if chunks else 'GAP'))
  if not ready:gaps.append(label)
  print(f'{label:20} {status:7} chunks={chunks:4} articles={arts:3} kinds={sorted(kinds)}')
 print('\nDirect-answer acceptance')
 cases=[
  ('Penalty','شو عقوبة الدائن اللي يطالب بدين وهمي بالإعسار؟','العقوبة:'),
  ('Sharia deadline','كم مدة الاستئناف بالحكم الشرعي الغيابي؟','المدة:'),
  ('Traffic points','قطعت إشارة حمراء شو العقوبة؟','6 نقاط'),
  ('Complaint','كيف أقدم شكوى عند المدعي العام؟','الإجراء:'),
  ('Criminal appeal fee','كم رسوم استئناف قضية جزائية؟','الرسوم:'),
 ]
 for label,q,needle in cases:
  a=handle_chat(ChatRequest(message=q,language='ar')).answer
  print(f'{label:20}', 'PASS' if needle in a else 'FAIL')
 print('\nHonest pilot status:')
 if gaps:
  print('Pilot-ready with explicit coverage gaps:',', '.join(gaps))
 else:
  print('All configured core thresholds passed.')
 print('Qanoni must refuse unsupported exact penalties/deadlines instead of guessing.')

if __name__=='__main__':main()
