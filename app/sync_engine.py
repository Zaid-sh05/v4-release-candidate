from __future__ import annotations
import io, re, time, zipfile, xml.etree.ElementTree as ET
from collections import deque
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from .config import settings
from .repository import repository
from .document_classifier import classify_document
from .legal_update_guard import legal_update_ledger
from .supabase_store import supabase_store
from .text import pretty_title
from .arabic_text_quality import looks_like_reversed_arabic_reading_order, reconstruct_visual_order_arabic

ALLOWED_HOSTS={
 'pm.gov.jo','www.pm.gov.jo','moj.gov.jo','www.moj.gov.jo','sjd.gov.jo','www.sjd.gov.jo',
 'mol.gov.jo','www.mol.gov.jo','psd.gov.jo','www.psd.gov.jo','ccd.gov.jo','www.ccd.gov.jo',
 'modee.gov.jo','www.modee.gov.jo','lob.gov.jo','www.lob.gov.jo',
 'moh.gov.jo','www.moh.gov.jo','mosd.gov.jo','www.mosd.gov.jo','mola.gov.jo','www.mola.gov.jo',
 'jiacc.gov.jo','www.jiacc.gov.jo',
}
LEGAL_HINTS=('قانون','قوانين','نظام','أنظمة','انظمة','تعليمات','تشريع','التشريعات','law','regulation','.pdf','.docx')


def safe_url(url:str)->bool:
    p=urlparse(url); return p.scheme in {'http','https'} and p.netloc.lower() in ALLOWED_HOSTS

def is_pdf(data:bytes)->bool: return bool(data and data.lstrip().startswith(b'%PDF-'))
def is_docx(data:bytes)->bool:
    if not data.startswith(b'PK'): return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z: return 'word/document.xml' in z.namelist()
    except Exception: return False

def pdf_text(data:bytes)->str:
    reader=PdfReader(io.BytesIO(data),strict=False); out=[]
    for p in reader.pages:
        try: out.append(p.extract_text(extraction_mode='layout') or p.extract_text() or '')
        except Exception:
            try: out.append(p.extract_text() or '')
            except Exception: pass
    return '\n'.join(out)

def pdfplumber_text(data:bytes)->str:
    import pdfplumber
    out=[]
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            out.append(page.extract_text() or '')
    return '\n'.join(out)

def _article_count(text:str)->int:
    return sum(1 for article,_ in split_articles(text) if article is not None)

def choose_pdf_extraction(primary_text:str,fallback_text:str|None)->str:
    """Pick between a primary extraction and a fallback, conservatively.

    Only switches away from the primary when it shows zero detected articles AND looks like
    the specific reversed-Arabic-reading-order failure (see app.arabic_text_quality) -- not
    just "this document happens to have no articles", e.g. a cover page or an FAQ -- and only
    when the fallback actually finds real article structure the primary didn't. This never
    downgrades a primary extraction that is already working.
    """
    primary_articles=_article_count(primary_text)
    if primary_articles>0 or fallback_text is None:
        return primary_text
    if not looks_like_reversed_arabic_reading_order(primary_text):
        return primary_text
    fallback_articles=_article_count(fallback_text)
    return fallback_text if fallback_articles>primary_articles else primary_text

def pdf_extraction_report(data:bytes)->dict:
    """Extract PDF text, escalating through a conservative repair/fallback chain only when
    the primary extraction looks reading-order-corrupted, and only ever switching away from
    a candidate that is strictly better (more detected articles) than what came before it:

      pypdf -> [corrupted?] -> BiDi reconstruction of pypdf's text
                             -> pdfplumber (alternate text-native extractor)
                             -> [still corrupted?] -> BiDi reconstruction of pdfplumber's text

    BiDi reconstruction is tried before switching extractors: real evidence (a Jordanian
    Penal Code PDF from jiacc.gov.jo) showed pdfplumber reads the exact same broken glyph
    order as pypdf -- this is not an extractor-choice problem, it is a missing Unicode BiDi
    reordering step (see app.arabic_text_quality). pdfplumber is still attempted afterward in
    case a different extractor's raw output responds differently.

    This is the single source of truth both the production crawler and the read-only
    diagnostic tooling call, so a diagnostic run always reflects exactly what a real sync
    would do. Returns full diagnostic detail (every candidate tried, article counts,
    timings) alongside the winning text.
    """
    t0=time.monotonic()
    primary=pdf_text(data)
    primary_time=time.monotonic()-t0
    primary_articles=_article_count(primary)
    primary_corrupted=looks_like_reversed_arabic_reading_order(primary)
    report={
        'primary_extractor':'pypdf','primary_text':primary,'primary_time_seconds':primary_time,
        'primary_article_count':primary_articles,'primary_looks_reversed':primary_corrupted,
        'bidi_attempted':False,'bidi_article_count':None,'bidi_time_seconds':None,
        'fallback_attempted':False,'fallback_extractor':None,'fallback_text':None,
        'fallback_time_seconds':None,'fallback_article_count':None,'fallback_error':None,
        'fallback_bidi_attempted':False,'fallback_bidi_article_count':None,
        'selected_extractor':'pypdf','selected_text':primary,
    }
    if primary_articles>0 or not primary_corrupted:
        return report

    best_label,best_text,best_articles='pypdf',primary,primary_articles

    t0=time.monotonic()
    bidi_primary=reconstruct_visual_order_arabic(primary)
    report['bidi_time_seconds']=time.monotonic()-t0
    report['bidi_attempted']=True
    bidi_primary_articles=_article_count(bidi_primary)
    report['bidi_article_count']=bidi_primary_articles
    if bidi_primary_articles>best_articles:
        best_label,best_text,best_articles='pypdf+bidi',bidi_primary,bidi_primary_articles

    report['fallback_attempted']=True
    report['fallback_extractor']='pdfplumber'
    try:
        t0=time.monotonic()
        fallback=pdfplumber_text(data)
        report['fallback_time_seconds']=time.monotonic()-t0
        report['fallback_text']=fallback
        fallback_articles=_article_count(fallback)
        report['fallback_article_count']=fallback_articles
        if fallback_articles>best_articles:
            best_label,best_text,best_articles='pdfplumber',fallback,fallback_articles
        if fallback_articles==0 and looks_like_reversed_arabic_reading_order(fallback):
            report['fallback_bidi_attempted']=True
            bidi_fallback=reconstruct_visual_order_arabic(fallback)
            bidi_fallback_articles=_article_count(bidi_fallback)
            report['fallback_bidi_article_count']=bidi_fallback_articles
            if bidi_fallback_articles>best_articles:
                best_label,best_text,best_articles='pdfplumber+bidi',bidi_fallback,bidi_fallback_articles
    except Exception as exc:
        report['fallback_error']=f'{type(exc).__name__}: {exc}'

    report['selected_extractor']=best_label
    report['selected_text']=best_text
    return report

def pdf_text_with_fallback(data:bytes)->str:
    return pdf_extraction_report(data)['selected_text']

def docx_text(data:bytes)->str:
    with zipfile.ZipFile(io.BytesIO(data)) as z: xml=z.read('word/document.xml')
    root=ET.fromstring(xml); ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}; paras=[]
    for p in root.findall('.//w:p',ns):
        x=''.join(t.text or '' for t in p.findall('.//w:t',ns));
        if x.strip(): paras.append(x)
    return '\n'.join(paras)

def clean_html(html:str):
    soup=BeautifulSoup(html,'html.parser'); links=[]
    for a in soup.find_all('a',href=True): links.append((a['href'],a.get_text(' ',strip=True)))
    for tag in soup(['script','style','nav','footer','header','noscript','svg']): tag.decompose()
    title=soup.title.get_text(' ',strip=True) if soup.title else ''
    text=re.sub(r'\s+',' ',soup.get_text(' ',strip=True)).strip()
    return title,text,links

def split_articles(text:str,max_chars:int=6500):
    t=(text or '').translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789')).replace('\r','\n')
    matches=list(re.finditer(r'(?:^|\n|\s)(?:المادة|مادة|article)\s*\(?\s*(\d{1,4})\s*\)?',t,re.I))
    if len(matches)>=3:
        out=[]
        for i,m in enumerate(matches):
            end=matches[i+1].start() if i+1<len(matches) else len(t); body=t[m.start():end].strip()
            if len(body)>45: out.append((m.group(1),body[:max_chars]))
        return out
    return [(None,t[i:i+max_chars].strip()) for i in range(0,len(t),max_chars) if len(t[i:i+max_chars].strip())>150]

def candidate(href:str,label:str)->bool:
    blob=f'{href} {label}'.lower(); return any(h.lower() in blob for h in LEGAL_HINTS)

def choose_domain(title:str,text:str,source:dict)->str:
    domain, _, _ = classify_document(title,text,source_domains=source.get('domains',[]),authority=source.get('authority',''))
    return domain

def sync_source(source_id:str,max_docs:int|None=None):
    source=next((s for s in repository.source_registry() if s['id']==source_id),None)
    if not source: raise ValueError(f'Unknown source: {source_id}')
    if source.get('sync_mode')=='reference':
        raise ValueError('This source is registered as a reference-only source and needs a dedicated connector.')
    if not safe_url(source['url']): raise ValueError('Source URL is outside the official allowlist.')
    max_docs=max_docs or settings.sync_max_docs_per_source
    q=deque([source['url']]); seen=set(); docs=0; inserted=0; cloud_inserted=0; errors=[]
    counters={'new':0,'changed':0,'unchanged':0,'rejected':0}
    session=requests.Session(); session.headers.update({'User-Agent':settings.sync_user_agent,'Accept':'text/html,application/xhtml+xml,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document;q=0.9,*/*;q=0.8'})
    while q and docs<max_docs:
        url=q.popleft()
        if url in seen or not safe_url(url): continue
        seen.add(url); docs+=1
        try:
            r=session.get(url,timeout=settings.sync_timeout_seconds,allow_redirects=True); r.raise_for_status(); ctype=(r.headers.get('content-type') or '').lower(); links=[]
            if not safe_url(r.url):
                raise ValueError('Redirected outside the official allowlist.')
            if is_pdf(r.content): raw_title=urlparse(r.url).path.rsplit('/',1)[-1]; text=pdf_text_with_fallback(r.content)
            elif is_docx(r.content): raw_title=urlparse(r.url).path.rsplit('/',1)[-1]; text=docx_text(r.content)
            elif 'html' in ctype or r.content.lstrip().startswith((b'<!DOCTYPE',b'<html',b'<HTML')):
                r.encoding=r.apparent_encoding or r.encoding; raw_title,text,links=clean_html(r.text)
            else: continue
            if len(text)<120: continue
            title=pretty_title(raw_title,text,source['authority']); domain=choose_domain(title,text,source); pieces=split_articles(text)
            plan=legal_update_ledger.plan(
                source_id=source_id,
                source_url=r.url,
                title=title,
                authority=source['authority'],
                domain=domain,
                text=text,
                chunks=pieces,
                source_domains=source.get('domains',[]),
            )
            counters[plan.action]+=1
            if plan.action=='rejected':
                legal_update_ledger.record(source_id=source_id,source_url=r.url,title=title,domain=domain,plan=plan,promoted=False)
            elif plan.action=='unchanged':
                legal_update_ledger.record(source_id=source_id,source_url=r.url,title=title,domain=domain,plan=plan,promoted=False)
            else:
                # Persistent cloud promotion comes first when configured. If it fails,
                # the fingerprint is not advanced and the next weekly run retries safely.
                cloud_count=0
                if supabase_store.configured:
                    cloud_count=supabase_store.replace_legal_document_chunks(
                        title=title,
                        authority=source['authority'],
                        domain=domain,
                        source_url=r.url,
                        chunks=pieces,
                        source_kind='official_sync',
                    )
                    cloud_inserted+=cloud_count
                chunk_count=repository.upsert_document_chunks(title=title,authority=source['authority'],domain=domain,source_url=r.url,chunks=pieces,source_kind='official_sync')
                inserted+=chunk_count
                legal_update_ledger.record(
                    source_id=source_id,
                    source_url=r.url,
                    title=title,
                    domain=domain,
                    plan=plan,
                    promoted=True,
                    details={'sqlite_chunks_upserted':chunk_count,'cloud_chunks_promoted':cloud_count},
                )
            for href,label in links:
                absolute=urljoin(r.url,href)
                if safe_url(absolute) and candidate(absolute,label) and absolute not in seen: q.append(absolute)
        except Exception as exc:
            errors.append(f'{url}: {type(exc).__name__}: {str(exc)[:150]}')
    promoted=counters['new']+counters['changed']
    status='ok' if promoted and not errors else ('partial' if promoted or errors else 'unchanged')
    repository.update_sync_status(source_id,f"{status}: {promoted} promoted, {counters['unchanged']} unchanged, {counters['rejected']} rejected")
    return {
        'source_id':source_id,
        'documents_visited':docs,
        'documents_new':counters['new'],
        'documents_changed':counters['changed'],
        'documents_unchanged':counters['unchanged'],
        'documents_rejected':counters['rejected'],
        'chunks_upserted':inserted,
        'cloud_chunks_promoted':cloud_inserted,
        'errors':errors[:15],
    }
