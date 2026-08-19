from __future__ import annotations
import io, re, zipfile, xml.etree.ElementTree as ET
from collections import deque
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from .config import settings
from .repository import repository
from .document_classifier import classify_document
from .legal_update_guard import legal_update_ledger
from .text import pretty_title

ALLOWED_HOSTS={
 'pm.gov.jo','www.pm.gov.jo','moj.gov.jo','www.moj.gov.jo','sjd.gov.jo','www.sjd.gov.jo',
 'mol.gov.jo','www.mol.gov.jo','psd.gov.jo','www.psd.gov.jo','ccd.gov.jo','www.ccd.gov.jo',
 'modee.gov.jo','www.modee.gov.jo','lob.gov.jo','www.lob.gov.jo',
 'moh.gov.jo','www.moh.gov.jo','mosd.gov.jo','www.mosd.gov.jo','mola.gov.jo','www.mola.gov.jo'
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
    # Whole-document classification only. A document is never split across legal domains.
    domain, _, _ = classify_document(title,text,source_domains=source.get('domains',[]),authority=source.get('authority',''))
    return domain

def sync_source(source_id:str,max_docs:int|None=None):
    source=next((s for s in repository.source_registry() if s['id']==source_id),None)
    if not source: raise ValueError(f'Unknown source: {source_id}')
    if source.get('sync_mode')=='reference':
        raise ValueError('This source is registered as a reference-only source and needs a dedicated connector.')
    if not safe_url(source['url']): raise ValueError('Source URL is outside the official allowlist.')
    max_docs=max_docs or settings.sync_max_docs_per_source
    q=deque([source['url']]); seen=set(); docs=0; inserted=0; errors=[]
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
            if is_pdf(r.content): raw_title=urlparse(r.url).path.rsplit('/',1)[-1]; text=pdf_text(r.content)
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
                # Record the event for audit visibility, but do not rewrite the corpus.
                legal_update_ledger.record(source_id=source_id,source_url=r.url,title=title,domain=domain,plan=plan,promoted=False)
            else:
                chunk_count=repository.upsert_document_chunks(title=title,authority=source['authority'],domain=domain,source_url=r.url,chunks=pieces,source_kind='official_sync')
                inserted+=chunk_count
                legal_update_ledger.record(
                    source_id=source_id,
                    source_url=r.url,
                    title=title,
                    domain=domain,
                    plan=plan,
                    promoted=True,
                    details={'chunks_upserted':chunk_count},
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
        'errors':errors[:15],
    }
