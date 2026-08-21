from __future__ import annotations
import json, re, sqlite3, uuid
from datetime import datetime, timezone
from .config import settings
from .models import SourceItem
from .text import normalize_ar


def now_iso():
    return datetime.now(timezone.utc).isoformat()

class LegalRepository:
    def __init__(self):
        self.db = settings.sqlite_file
        if not self.db.exists():
            raise RuntimeError(f'Qanoni database not found: {self.db}')

    def connect(self):
        con=sqlite3.connect(self.db, timeout=15)
        con.row_factory=sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        return con

    def stats(self):
        with self.connect() as con:
            chunks=con.execute('select count(*) c from chunks').fetchone()['c']
            docs=con.execute('select count(*) c from documents').fetchone()['c']
            sources=con.execute('select count(*) c from source_registry').fetchone()['c']
            domains=con.execute('select d.domain,count(*) c from chunks c join documents d on d.id=c.document_id group by d.domain order by c desc').fetchall()
            canonical=con.execute("select count(*) c from documents where source_kind like 'canonical%'").fetchone()['c']
        return {'chunks':chunks,'documents':docs,'registered_official_sources':sources,'canonical_documents':canonical,'domains':{r['domain']:r['c'] for r in domains}}

    def coverage(self):
        core=[
            ('قانون الأحوال الشخصية رقم 15 لسنة 2019','personal_status'),
            ('قانون الشركات رقم 22 لسنة 1997 وتعديلاته','commercial'),
            ('قانون السير رقم 49 لسنة 2008 وتعديلاته','traffic'),
            ('نظام النقاط المرورية لسنة 2024','traffic'),
            ('قانون الجرائم الإلكترونية رقم 17 لسنة 2023','cyber'),
            ('قانون العمل رقم 8 لسنة 1996 وتعديلاته','labor'),
            ('قانون أصول المحاكمات الشرعية وتعديلاته','personal_status'),
            ('قانون العقوبات رقم 16 لسنة 1960 وتعديلاته','criminal'),
            ('القانون المدني رقم 43 لسنة 1976 وتعديلاته','civil'),
            ('قانون أصول المحاكمات الجزائية رقم 9 لسنة 1961 وتعديلاته','procedure'),
            ('قانون أصول المحاكمات المدنية رقم 24 لسنة 1988 وتعديلاته','procedure'),
        ]
        result=[]
        with self.connect() as con:
            for title,domain in core:
                ntitle=normalize_ar(title)
                docs=con.execute('select id,title_ar,source_url,source_kind from documents where domain=?',(domain,)).fetchall()
                matches=[d for d in docs if normalize_ar(d['title_ar'])==ntitle or ntitle in normalize_ar(d['title_ar']) or normalize_ar(d['title_ar']) in ntitle]
                chunk_count=0; articles=set(); urls=[]; kinds=set()
                for d in matches:
                    rows=con.execute('select article from chunks where document_id=?',(d['id'],)).fetchall()
                    chunk_count+=len(rows); articles.update(str(r['article']) for r in rows if r['article']); urls.append(d['source_url']); kinds.add(d['source_kind'])
                status='canonical' if any(k.startswith('canonical') for k in kinds) else ('reference_only' if kinds and all(k=='reference' for k in kinds) else ('partial' if chunk_count else 'reference_only'))
                result.append({'title':title,'domain':domain,'status':status,'chunks':chunk_count,'distinct_articles':len(articles),'source_urls':list(dict.fromkeys(urls))[:3]})
        return result

    def source_registry(self):
        with self.connect() as con:
            rows=con.execute('select * from source_registry order by authority,name_ar').fetchall()
        out=[]
        for r in rows:
            x=dict(r); x['domains']=json.loads(x.pop('domains_json')); out.append(x)
        return out

    def update_sync_status(self, source_id: str, status: str):
        with self.connect() as con:
            con.execute('update source_registry set last_sync_at=?,last_sync_status=? where id=?',(now_iso(),status,source_id))

    def ensure_conversation(self, conversation_id: str|None, language: str) -> str:
        cid=conversation_id or str(uuid.uuid4()); now=now_iso()
        with self.connect() as con:
            row=con.execute('select 1 from conversations where id=?',(cid,)).fetchone()
            if row: con.execute('update conversations set language=?,updated_at=? where id=?',(language,now,cid))
            else: con.execute('insert into conversations values(?,?,?,?)',(cid,language,now,now))
        return cid

    def save_message(self,cid:str,role:str,content:str,domain:str|None=None,intent:str|None=None):
        with self.connect() as con:
            con.execute('insert into messages values(?,?,?,?,?,?,?)',(str(uuid.uuid4()),cid,role,content,domain,intent,now_iso()))
            con.execute('update conversations set updated_at=? where id=?',(now_iso(),cid))

    def history(self,cid:str,limit:int=8):
        with self.connect() as con:
            rows=con.execute('select role,content from messages where conversation_id=? order by created_at desc limit ?',(cid,limit)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def _candidate_rows(self, domains:list[str], max_rows:int=2600):
        with self.connect() as con:
            if domains and 'general' not in domains:
                qs=','.join('?' for _ in domains)
                return con.execute(f'''select c.rowid as rowid,c.id,c.article,c.body,d.id document_id,d.title_ar,d.authority,d.domain,d.source_url,d.law_number,d.year,d.source_kind,d.verified_at
                    from chunks c join documents d on d.id=c.document_id where d.domain in ({qs}) limit ?''',(*domains,max_rows)).fetchall()
            return con.execute('''select c.rowid as rowid,c.id,c.article,c.body,d.id document_id,d.title_ar,d.authority,d.domain,d.source_url,d.law_number,d.year,d.source_kind,d.verified_at
                    from chunks c join documents d on d.id=c.document_id limit ?''',(max_rows,)).fetchall()

    def _wordset(self, normalized: str) -> set[str]:
        out=set()
        for raw in (normalized or '').split():
            w=raw.strip('؟?!.,،؛:()[]{}\"\'')
            if not w: continue
            out.add(w)
            # Definite article / simple clitics make Arabic retrieval less brittle.
            for prefix in ('وال','بال','كال','فال','لل','ال','و','ب','ف'):
                if w.startswith(prefix) and len(w) > len(prefix)+2:
                    out.add(w[len(prefix):])
        return out

    def _search_terms(self, query:str, domains:list[str]) -> tuple[list[str],list[str]]:
        qn=normalize_ar(query)
        qwords=self._wordset(qn)

        def _core_word(w:str) -> str:
            w=(w or '').strip('؟?!.,،؛:()[]{}\"\'')
            for prefix in ('وال','فال','بال','كال'):
                if w.startswith(prefix) and len(w)>len(prefix)+2:
                    w=w[len(prefix):]; break
            if w.startswith('ال') and len(w)>4:
                w=w[2:]
            return w

        def qhas(*xs:str) -> bool:
            for x in xs:
                if not x: continue
                nx=normalize_ar(x)
                if nx in qn:
                    return True
                parts=[_core_word(w) for w in nx.split() if _core_word(w)]
                if len(parts)>=2 and all(w in qwords for w in parts):
                    return True
            return False
        stop={
            'شو','كيف','بدي','عندي','على','من','في','الى','الي','عن','مع','بدون','واحد','وحده','انا','هو','هي',
            'قانون','القانون','الاردني','اردني','قضيه','قضية','حكم','سوال','سؤال','رقم','لسنه','سنة','ما','هل','لو',
            'عقوبه','عقوبة','حقوقي','حقي','حق','اجراءات','إجراءات','the','what','how','and','law','jordan','jordanian','case',
        }
        raw=[]
        for original in qn.split():
            candidates=[original,*sorted(self._wordset(original),key=len)]
            for w in candidates:
                if len(w)>1 and w not in stop and w not in raw:
                    raw.append(w)
        terms=list(dict.fromkeys(raw)); phrases=[]

        def add_term(*xs):
            for x in xs:
                nx=normalize_ar(x)
                if ' ' in nx:
                    if nx not in phrases: phrases.append(nx)
                elif nx and nx not in terms: terms.append(nx)

        if qhas('فصلني','طردني','فصل من العمل','انهاء عقد','dismissed','fired','wrongful dismissal'):
            add_term('انهاء','اشعار','انذار','صاحب العمل','عقد العمل','العامل','تعويض','فصل تعسفي','نزاع عمالي','شكوى عمالية','080022208')
        if qhas('راتب','اجر','أجر','overtime','عمل اضافي','عمل إضافي'):
            add_term('اجر','ساعات العمل','عمل اضافي','بدل اجر')
        if qhas('اجازه','إجازة','leave'):
            add_term('اجازة سنوية','اجازة مرضية','اجر كامل')
        if qhas('اشاره حمراء','إشارة حمراء','red light'):
            add_term('اشارة','حمراء','اشارة ضوئية','تجاوز الاشارة','النقاط المرورية')
        if qhas('سرعه','سرعة','رادار','speeding'):
            add_term('سرعة','رادار','تجاوز السرعة')
        if qhas('ابتزاز','ابتزني','ببتزني','يبتزني','blackmail','extortion'):
            add_term('ابتزاز','ابتز','هدد','تهديد','جرائم الكترونية','نظام معلومات','شبكة معلوماتية')
            if qhas('شو اعمل','شو أعمل','ماذا افعل','ماذا أفعل','تعرضت','بلاغ','ابلاغ','إبلاغ','report'):
                add_term('وحدة مكافحة الجرائم الالكترونية','التواصل','الابلاغ','الرقم المجاني','عدم تحويل مبالغ')
        if qhas('استئناف','استأنف','استانف','استاناف','appeal'):
            add_term('استئناف','لائحة الاستئناف','مدة الاستئناف','ميعاد الاستئناف','تبليغ الحكم','وجاهي','غيابي','طعن','تمييز')
        if qhas('شرعي','شرعية','محكمة شرعية','sharia'):
            add_term('شرعي','شرعية','أصول المحاكمات الشرعية','محكمة الاستئناف الشرعية','وجاهي','غيابي','تدقيق','تبليغ')
        if qhas('كم يوم','قديش','كم مده','كم مدة','خلال كم','مهله','مهلة','ميعاد','deadline','time limit'):
            add_term('مدة','خلال','يوما','يوم','تاريخ التبليغ','تاريخ صدور الحكم')
        if qhas('حكم قطعي','الحكم القطعي','متى يصبح الحكم','final judgment'):
            add_term('قطعي','اكتساب الدرجة القطعية','الطعن','الاستئناف','التبليغ')
        if qhas('شكوى','اشتكي','أشتكي','مدعي عام','المدعي العام','نيابة عامة','النيابة العامة','ادعاء عام','الادعاء العام','complaint','prosecutor'):
            add_term('شكوى','المدعي العام','النيابة العامة','الادعاء العام','تقديم الشكوى')
        if qhas('تنفيذ الحكم','انفذ الحكم','أنفذ الحكم','enforce judgment'):
            add_term('تنفيذ الحكم','دائرة التنفيذ','المحكوم له','المحكوم عليه','حجز')
        if qhas('رسوم','كم بدفع','fees','fee'):
            add_term('رسوم','الرسم','دينار','امر قبض')
        if qhas('جزائي','جزائية','جنائي','جنائية','criminal case'):
            add_term('جزائي','جزائية','قضايا جزائية','الشق الجزائي','استئناف القرارات الصادرة بالقضايا الجزائية')
        if qhas('اعسار','إعسار','insolvency'):
            add_term('الاعسار','قانون الاعسار','دائن','مدين','ديون','ذمة الاعسار')
        if qhas('دين وهمي','ديون وهمية','وهمي'):
            add_term('ديون وهمية','طالب بديون وهمية','دائن')
        if qhas('زنا','adultery'): add_term('زنا')
        if qhas('سرقه','سرقة','theft'): add_term('سرقة')
        if qhas('قتل','قتل قصد','قتل عمد','murder','homicide'):
            add_term('قتل','القتل القصد','المادة 326','قصد احتمالي','عشرين سنة')
        if qhas('طلاق','divorce'): add_term('طلاق','تفريق')
        if qhas('حضانة','حضانه','custody'): add_term('حضانة')
        if qhas('نفقه','نفقة','alimony','maintenance'): add_term('نفقة')
        if qhas('عقوبه','عقوبة','غرامه','غرامة','حبس','سجن','penalty','fine'):
            add_term('يعاقب','الحبس','غرامة','العقوبة')
        return terms[:26],phrases[:14]

    def _focused_excerpt(self, body:str, terms:list[str], phrases:list[str], max_chars:int=1450) -> str:
        body=(body or '').strip()
        if len(body)<=max_chars: return body
        nbody=normalize_ar(body)
        needles=[normalize_ar(x) for x in phrases+terms if x]
        positions=[]
        for needle in needles:
            p=nbody.find(needle)
            if p>=0: positions.append(p)
        if not positions: return body[:max_chars]
        # normalized Arabic has roughly the same character order/length for our purpose.
        center=min(positions)
        start=max(0,center-max_chars//3)
        end=min(len(body),start+max_chars)
        start=max(0,end-max_chars)
        if start>0:
            b=max(body.rfind('\n',0,start),body.rfind('.',0,start),body.rfind('؛',0,start))
            if b>start-220: start=b+1
        if end<len(body):
            e_candidates=[x for x in (body.find('\n',end),body.find('.',end),body.find('؛',end)) if x!=-1]
            if e_candidates and min(e_candidates)<end+220: end=min(e_candidates)+1
        return body[start:end].strip()

    def search(self, query:str, domains:list[str]|str, limit:int=8) -> list[SourceItem]:
        if isinstance(domains,str): domains=[domains]
        qn=normalize_ar(query)
        terms,phrases=self._search_terms(query,domains)
        candidates=self._candidate_rows(domains)
        article_match=re.search(r'(?:الماده|المادة|مادة|article)\s*(\d{1,4})',qn,re.I)
        requested_article=article_match.group(1) if article_match else None
        exact_law_nums=set(re.findall(r'\b\d{1,4}\b',query.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'))))
        scored=[]
        for r in candidates:
            title_n=normalize_ar(r['title_ar']); body_n=normalize_ar(r['body'][:9000])
            tw=self._wordset(title_n); bw=self._wordset(body_n)
            # Listing/index pages are discovery material, not substantive legal evidence.
            generic_index = (
                r['source_kind']=='official_sync' and not r['article'] and
                (title_n.startswith('القوانين والانظمه') or title_n.startswith('القوانين وزاره') or
                 title_n.startswith('القوانين دائره') or title_n.startswith('التشريعات الاردنيه'))
            )
            if generic_index:
                continue
            # Do not mix Sharia procedure into ordinary civil/criminal appeals.
            if r['domain']=='procedure' and 'personal_status' not in domains and 'شرعي' in title_n:
                continue
            if r['domain']=='procedure' and 'criminal' in domains and 'civil' not in domains and 'مدني' in title_n:
                continue
            if r['domain']=='procedure' and 'civil' in domains and 'criminal' not in domains and 'جزاي' in title_n:
                continue
            # For a named offence/conduct, do not surface an unrelated amendment merely because
            # it contains generic words such as imprisonment or fine. The base-law reference may
            # remain as a verification anchor when the consolidated offence text is missing.
            conduct_terms=[normalize_ar(x) for x in ('زنا','سرقة','احتيال','تزوير','قتل','رشوة','اختلاس','اغتصاب') if normalize_ar(x) in qn]
            if normalize_ar('ابتزاز') in qn:
                conduct_terms.extend([normalize_ar('ابتزاز'),normalize_ar('ابتز')])
            if conduct_terms and not any(t in title_n or t in body_n for t in conduct_terms):
                base_reference=(r['source_kind']=='reference' and ('قانون العقوبات' in title_n or 'قانون الجرائم الالكترونيه' in title_n))
                if not base_reference:
                    continue
            score=0.0; content_hits=0
            for tok in terms:
                hit_title=tok in tw
                hit_body=tok in bw
                if hit_title: score+=3.0; content_hits+=1
                if hit_body: score+=1.35; content_hits+=1
            for phrase in phrases:
                if phrase in title_n: score+=4.5; content_hits+=2
                if phrase in body_n: score+=2.4; content_hits+=2
            exact_meta=False
            if requested_article and str(r['article'] or '')==requested_article:
                score+=6.0; exact_meta=True
            if r['law_number'] and str(r['law_number']) in exact_law_nums:
                score+=5.0; exact_meta=True
            if r['year'] and str(r['year']) in exact_law_nums:
                score+=2.0; exact_meta=True

            primary_domain=domains[0] if domains else 'general'
            is_primary=r['domain']==primary_domain
            if any(normalize_ar(x) in qn for x in ['شرعي','شرعية','sharia']) and 'شرعي' in title_n:
                score += 7.0
            if ('غيابي' in qn or 'غيابيا' in qn) and str(r['article'] or '')=='112' and 'اصول المحاكمات الشرعيه' in title_n:
                score += 22.0
            if any(normalize_ar(x) in qn for x in ['شكوى','مدعي عام','المدعي العام','ادعاء عام','الادعاء العام','complaint','prosecutor']) and ('شكوى' in title_n or 'ادعاء' in title_n):
                score += 8.0
            if any(normalize_ar(x) in qn for x in ['رسوم','كم بدفع','fees','fee']) and r['source_kind']=='official_service':
                score += 3.0
            base_titles={
                'labor':'قانون العمل رقم 8','traffic':'قانون السير رقم 49','cyber':'قانون الجرائم الالكترونية رقم 17',
                'commercial':'قانون الشركات رقم 22','personal_status':'قانون الاحوال الشخصية رقم 15',
                'criminal':'قانون العقوبات رقم 16','civil':'القانون المدني رقم 43',
            }
            if r['domain']=='procedure':
                if 'criminal' in domains:
                    base_for_doc='قانون اصول المحاكمات الجزائية رقم 9'
                elif 'civil' in domains:
                    base_for_doc='قانون اصول المحاكمات المدنية رقم 24'
                else:
                    base_for_doc=None
            else:
                base_for_doc=base_titles.get(r['domain'])
            # A law-name match is only meaningful "this is generally the right base statute"
            # evidence for a whole-document candidate (no article number -- e.g. a reference-only
            # row standing in for a law whose PDF text layer is unusable). Every properly
            # segmented article chunk's title also contains the law's own name by construction
            # ("<law name> — المادة N"), so applying this to articled rows made every single
            # article of a canonical law an automatic anchor regardless of actual relevance --
            # letting e.g. an unrelated adultery article outscore the real theft article for a
            # theft query purely because both share the same law name in their title.
            law_anchor=bool(base_for_doc and normalize_ar(base_for_doc) in title_n and r['domain'] in domains and not r['article'])
            canonical_anchor=r['source_kind'].startswith('canonical') and is_primary

            # Do not manufacture relevance merely because a document lives in the same domain.
            # Canonical/base statutes may appear as law anchors even when a PDF text layer is poor.
            if content_hits==0 and not exact_meta and not canonical_anchor and not law_anchor:
                continue

            if law_anchor:
                score+=2.6 if is_primary else 1.7
            if r['source_kind'].startswith('canonical'): score+=3.2
            elif r['source_kind']=='official_sync': score+=1.0
            elif r['source_kind']=='official_service': score+=2.2
            elif r['source_kind']=='official_guidance': score+=1.8
            elif r['source_kind']=='judicial_principle': score+=2.8
            elif r['source_kind']=='verified_crosscheck': score+=3.0
            elif r['source_kind']=='reference': score-=0.2
            score += 1.7 if is_primary else 0.25

            # Context-aware procedural ranking: ordinary criminal appeals should not be led by Sharia procedure.
            if primary_domain=='procedure' and 'criminal' in domains:
                if 'جزاي' in title_n or 'العقوبات' in title_n: score+=4.5
                if any(normalize_ar(x) in qn for x in ('جزائي','جزائية','جنائي','جنائية')) and ('جزاي' in title_n or 'جزائي' in title_n): score+=7.0
                if any(normalize_ar(x) in qn for x in ('شكوى','مدعي عام','المدعي العام','ادعاء عام','الادعاء العام')) and ('شكوى' in title_n or 'ادعاء' in title_n): score+=8.0
                if 'شرعي' in title_n: score-=4.0
            if primary_domain=='procedure' and 'civil' in domains:
                if 'مدني' in title_n: score+=4.0
                if 'شرعي' in title_n: score-=3.0
            if primary_domain=='cyber':
                if r['domain']=='cyber': score+=2.0
                elif r['domain']=='criminal': score-=0.5

            # Common-language bridge for the insolvency offence of claiming fictitious debt.
            if any(normalize_ar(x) in qn for x in ('دين وهمي','ديون وهمية','مطالبة بدين وهمي')):
                if 'اعسار' in title_n: score+=12.0
                if 'ديون وهميه' in body_n or ('دائن' in body_n and 'وهم' in body_n): score+=8.0

            # Base statutes should generally outrank implementing instructions for broad rights
            # questions -- but again, only as a whole-document signal (see law_anchor above),
            # never as a per-article bonus every article of the base law would equally receive.
            base=base_titles.get(primary_domain)
            if base and normalize_ar(base) in title_n and not r['article']: score+=3.0

            if any(x in title_n for x in ['القوانين وزاره','القوانين دائره','التشريعات الاردنيه','وثيقه قانونيه رسميه','التقرير السنوي','الكتاب السنوي']): score-=4.0
            if score>1.0: scored.append((score,r,content_hits))

        scored.sort(key=lambda x:(x[0],x[2]),reverse=True)
        top_score=scored[0][0] if scored else 0.0
        min_keep=max(2.2, top_score*0.34) if top_score else 2.2
        out=[]; seen=set()
        for score,r,_ in scored:
            if score < min_keep:
                continue
            key=(normalize_ar(r['title_ar']),str(r['article'] or ''))
            if key in seen: continue
            seen.add(key)
            excerpt=self._focused_excerpt(r['body'],terms,phrases)
            # Some official PDFs expose a broken Arabic text layer. Keep the official law as an
            # anchor, but never feed unreadable extraction to the user or language model as evidence.
            if (r['source_kind'].startswith('canonical') and
                normalize_ar('قانون الجرائم الإلكترونية رقم 17') in normalize_ar(r['title_ar']) and
                not r['article']):
                excerpt='سجل مرجعي رسمي لقانون الجرائم الإلكترونية رقم 17 لسنة 2023. لم يعتمد قانوني النص المستخرج من ملف PDF في هذه النسخة بسبب جودة طبقة النص؛ يجب فتح المصدر الرسمي للتحقق من المادة الدقيقة.'
            out.append(SourceItem(id=r['id'],title=r['title_ar'],authority=r['authority'],domain=r['domain'],source_url=r['source_url'],law_number=r['law_number'],year=r['year'],article=r['article'],excerpt=excerpt,verified_at=r['verified_at'],source_kind=r['source_kind'],score=round(score,2)))
            if len(out)>=limit: break
        return out

    def adaptive_search(self, query:str, domains:list[str]|str, intent:str, limit:int=12, expansions:list[str]|None=None) -> list[SourceItem]:
        """Run conservative multi-query retrieval and merge evidence without changing legal facts."""
        if isinstance(domains,str): domains=[domains]
        queries=[query]
        for q in (expansions or []):
            if q and q not in queries: queries.append(q)
        merged={}
        for qi,q in enumerate(queries[:5]):
            rows=self.search(q,domains,max(limit,10))
            for rank,item in enumerate(rows):
                bonus=max(0.0,2.4-qi*0.45-rank*0.05)
                candidate=item.model_copy(update={'score':round(float(item.score)+bonus,2)})
                prev=merged.get(item.id)
                if prev is None or candidate.score>prev.score:
                    merged[item.id]=candidate
        out=sorted(merged.values(),key=lambda x:(x.source_kind in {'canonical_verified','verified_crosscheck'},x.source_kind in {'official_guidance','official_service','judicial_principle'},x.score),reverse=True)
        return out[:limit]

    def _ensure_runtime_tables(self, con):
        con.execute("create table if not exists answer_evaluations(id text primary key, conversation_id text, message text not null, intent text, primary_domain text, passed integer not null, score real not null, reasons_json text not null, mode text, created_at text not null)")
        con.execute("create table if not exists feedback(id text primary key, conversation_id text, rating text not null, note text, created_at text not null)")

    def log_evaluation(self, cid:str, message:str, intent:str, primary_domain:str, passed:bool, score:float, reasons:list[str], mode:str):
        with self.connect() as con:
            self._ensure_runtime_tables(con)
            con.execute('insert into answer_evaluations values(?,?,?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),cid,message,intent,primary_domain,1 if passed else 0,float(score),json.dumps(reasons,ensure_ascii=False),mode,now_iso()))

    def save_feedback(self, cid:str|None, rating:str, note:str|None=None) -> dict:
        if rating not in {'helpful','not_helpful'}:
            raise ValueError('rating must be helpful or not_helpful')
        with self.connect() as con:
            self._ensure_runtime_tables(con)
            fid=str(uuid.uuid4())
            con.execute('insert into feedback values(?,?,?,?,?)',(fid,cid,rating,(note or '')[:1200],now_iso()))
        return {'id':fid,'saved':True,'rating':rating}

    def feedback_stats(self) -> dict:
        with self.connect() as con:
            self._ensure_runtime_tables(con)
            rows=con.execute('select rating,count(*) c from feedback group by rating').fetchall()
        return {r['rating']:r['c'] for r in rows}

    def upsert_document_chunks(self, *, title:str, authority:str, domain:str, source_url:str, chunks:list[tuple[str|None,str]], source_kind:str='official_sync', verified_at:str|None=None) -> int:
        import hashlib
        doc_id=hashlib.sha1(f'{source_url}|{title}|{domain}'.encode()).hexdigest()
        with self.connect() as con:
            con.execute('''insert into documents(id,title_ar,authority,domain,source_url,source_kind,verified_at,created_at) values(?,?,?,?,?,?,?,?)
                on conflict(id) do update set title_ar=excluded.title_ar,authority=excluded.authority,domain=excluded.domain,verified_at=excluded.verified_at,source_kind=excluded.source_kind''',(doc_id,title,authority,domain,source_url,source_kind,verified_at or now_iso(),now_iso()))
            n=0
            for idx,(article,body) in enumerate(chunks):
                body=(body or '').strip()
                if len(body)<40: continue
                h=hashlib.sha256(normalize_ar(body).encode()).hexdigest(); cid=hashlib.sha1(f'{doc_id}|{article or ""}|{h}'.encode()).hexdigest()
                try:
                    con.execute('insert into chunks(id,document_id,article,chunk_index,body,body_normalized,content_hash) values(?,?,?,?,?,?,?)',(cid,doc_id,article,idx,body,normalize_ar(body),h))
                    rowid=con.execute('select rowid from chunks where id=?',(cid,)).fetchone()[0]
                    con.execute('insert into chunk_fts(rowid,title,body) values(?,?,?)',(rowid,title,body)); n+=1
                except sqlite3.IntegrityError:
                    pass
            return n

repository=LegalRepository()
