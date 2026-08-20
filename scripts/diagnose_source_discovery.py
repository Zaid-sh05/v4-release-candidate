"""Live network diagnostic for the official legal-source crawler — read-only, no writes.

Reuses app.sync_engine's exact fetch/extract/classify/quality-gate functions in dry-run mode.
It never calls supabase_store.replace_legal_document_chunks or legal_update_ledger.record —
nothing is promoted, nothing is written anywhere. This only talks to real gov.jo sites over
plain HTTP(S) requests (no JS execution), so it must run somewhere with real internet egress
(GitHub Actions), not the dev sandbox (blocked by org egress policy).

Two independent modes, selected by which env vars are set:

  DIAG_SOURCES=psd_laws,psd_traffic,moj_laws     (comma-separated source_ids from source_registry)
      For each source's seed URL: fetch it, report status/content-type/text length, and list
      every discovered link plus whether it passes candidate() — this is how you find both
      "why does this source discover nothing" (zero links, or all links filtered out) and
      "what is the real URL for law X" (read the candidate-link labels).

  DIAG_URLS=https://...,https://...              (comma-separated explicit URLs)
      For each URL: full extraction diagnostic — format (pdf/docx/html), raw text length and a
      readable sample, how many "المادة N" article markers were found, how many pieces
      split_articles() produced, and the exact quality_gate() verdict/reason a real sync would
      apply. This is how you confirm whether a specific candidate URL is the real full statute
      text before pointing production at it.

Both env vars may be set at once; both sections run.
"""
from __future__ import annotations

import os
import sys
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.document_classifier import classify_document
from app.legal_update_guard import quality_gate
from app.repository import repository
from app.sync_engine import (
    ALLOWED_HOSTS,
    candidate,
    clean_html,
    docx_text,
    is_docx,
    is_pdf,
    pdf_text,
    safe_url,
    split_articles,
)
from app.text import pretty_title

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": settings.sync_user_agent,
    "Accept": "text/html,application/xhtml+xml,application/pdf,"
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document;q=0.9,*/*;q=0.8",
})

# Labels/URLs matching any of these keyword groups get called out explicitly, regardless of
# how many total candidates a page has — a raw sample can silently omit a match past its cap.
TARGET_LAW_KEYWORDS = {
    "Civil Code": ("القانون المدني", "قانون مدني"),
    "Evidence Law": ("قانون البينات", "البينات"),
    "Criminal Procedure": ("أصول المحاكمات الجزائية", "المحاكمات الجزائية"),
    "Civil Procedure": ("أصول المحاكمات المدنية", "المحاكمات المدنية"),
    "Penal Code (base, not amendment)": ("قانون العقوبات",),
}


def _retry_get(url: str, *, attempts: int = 3, **kwargs):
    """Retry with short backoff so a persistent block is distinguishable from a transient blip."""
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return SESSION.get(url, **kwargs)
        except Exception as exc:  # noqa: BLE001 - reporting the raw exception is the point here
            last_exc = exc
            print(f"    attempt {attempt}/{attempts} failed: {type(exc).__name__}: {exc}")
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise last_exc


def _flag_target_law_matches(candidates: list[tuple[str, str]], base_url: str) -> None:
    flagged = False
    for law, keywords in TARGET_LAW_KEYWORDS.items():
        matches = [
            (href, label) for href, label in candidates
            if any(k in href or k in label for k in keywords)
            and "معدل" not in href and "معدل" not in label  # exclude amendment laws
        ]
        if matches:
            flagged = True
            print(f"  *** TARGET LAW MATCH: {law} ***")
            for href, label in matches:
                absolute = urljoin(base_url, href)
                print(f"      [{'OK' if safe_url(absolute) else 'OUT-OF-ALLOWLIST'}] {absolute}")
                print(f"          label: {label!r}")
    if not flagged:
        print(f"  (no target-law keyword match among all {len(candidates)} candidates on this page)")


def probe_sitemap_and_robots(seed_url: str) -> None:
    """For JS-shell pages, check whether robots.txt/sitemap.xml exposes real content URLs that
    bypass the client-rendered shell entirely — the lightest possible fix, tried before any
    browser-automation dependency."""
    parsed = urlparse(seed_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    for path in ("/robots.txt", "/sitemap.xml", "/sitemap_index.xml"):
        url = origin + path
        try:
            r = SESSION.get(url, timeout=15)
        except Exception as exc:
            print(f"  {path}: REQUEST FAILED: {type(exc).__name__}: {exc}")
            continue
        print(f"  {path}: status={r.status_code} content-length={len(r.content)}")
        if r.status_code == 200 and r.content:
            sample = r.text[:500].replace("\n", " ")
            print(f"      sample: {sample!r}")


def diagnose_source(source_id: str) -> None:
    sources = {s["id"]: s for s in repository.source_registry()}
    source = sources.get(source_id)
    print(f"\n{'=' * 70}\nSOURCE DISCOVERY DIAGNOSTIC: {source_id}\n{'=' * 70}")
    if not source:
        print(f"  UNKNOWN source_id (not in source_registry): {source_id!r}")
        return
    print(f"  authority: {source['authority']}")
    print(f"  seed url:  {source['url']}")
    print(f"  domains:   {source.get('domains')}")
    print(f"  sync_mode: {source.get('sync_mode')}")
    host = urlparse(source["url"]).netloc.lower()
    print(f"  host {host!r} in ALLOWED_HOSTS: {host in ALLOWED_HOSTS}")
    if not safe_url(source["url"]):
        print("  BLOCKED by safe_url() before any request is made — fix ALLOWED_HOSTS or the URL.")
        return

    try:
        r = _retry_get(source["url"], timeout=settings.sync_timeout_seconds, allow_redirects=True)
    except Exception as exc:
        print(f"  REQUEST FAILED after retries: {type(exc).__name__}: {exc}")
        print("  -> persistent network-level failure (timeout, DNS, TLS, connection refused),")
        print("     not a one-off blip. This alone fully explains a source with zero recorded")
        print("     events: sync_source() never reaches its while-loop body's try block far")
        print("     enough to call record(). Probing robots.txt/sitemap.xml as a cheap secondary")
        print("     signal (a reachable robots.txt on the same host would suggest this specific")
        print("     path/endpoint is blocked rather than the whole host):")
        probe_sitemap_and_robots(source["url"])
        return

    print(f"  final url after redirects: {r.url}")
    print(f"  status: {r.status_code}")
    ctype = (r.headers.get("content-type") or "").lower()
    print(f"  content-type: {ctype!r}")
    print(f"  content length: {len(r.content)} bytes")
    if not safe_url(r.url):
        print("  REDIRECTED outside the allowlist — sync_engine would abort here (ValueError).")
        return
    if r.status_code != 200:
        print("  Non-200 status — sync_engine's r.raise_for_status() would abort here, and the")
        print("  exception is caught and appended to errors[], but the loop continues to the")
        print("  next queued URL (there may be none, since no links were harvested yet).")
        return

    if is_pdf(r.content):
        print("  format: PDF")
    elif is_docx(r.content):
        print("  format: DOCX")
    elif "html" in ctype or r.content.lstrip().startswith((b"<!DOCTYPE", b"<html", b"<HTML")):
        print("  format: HTML")
        r.encoding = r.apparent_encoding or r.encoding
        title, text, links = clean_html(r.text)
        print(f"  page title: {title!r}")
        print(f"  visible text length: {len(text)} chars")
        print(f"  visible text sample: {text[:300]!r}")
        if len(text) < 300:
            print("  -> very little visible text. If the real content is injected by JavaScript")
            print("     after page load, a plain requests.get() will only ever see this shell.")
            print("     Probing robots.txt/sitemap.xml for a JS-bypass path:")
            probe_sitemap_and_robots(r.url)
        print(f"  raw <a href> links found: {len(links)}")
        candidates = [(href, label) for href, label in links if candidate(href, label)]
        print(f"  links passing candidate() legal-hint filter: {len(candidates)}")
        if not links:
            print("  -> ZERO links at all on this page. Either the page is genuinely a dead end,")
            print("     or (again) real navigation is JS-rendered and invisible to BeautifulSoup.")
        elif not candidates:
            print("  -> links exist but NONE match LEGAL_HINTS keywords — candidate() filter may")
            print("     be too strict for this site's link text/URL structure, or this really is")
            print("     an unrelated page.")
        _flag_target_law_matches(candidates, r.url)
        print("  sample of candidate links (href -> label), first 25 of "
              f"{len(candidates)}:")
        for href, label in candidates[:25]:
            absolute = urljoin(r.url, href)
            in_scope = safe_url(absolute)
            print(f"    [{'OK' if in_scope else 'OUT-OF-ALLOWLIST'}] {absolute}")
            print(f"        label: {label!r}")
    else:
        print(f"  format: UNRECOGNIZED (not PDF/DOCX/HTML, content-type={ctype!r})")
        print("  -> sync_engine's `else: continue` silently skips this with no error recorded.")


def diagnose_url(url: str) -> None:
    print(f"\n{'=' * 70}\nEXTRACTION DIAGNOSTIC: {url}\n{'=' * 70}")
    if not safe_url(url):
        print("  BLOCKED by safe_url() — host not in ALLOWED_HOSTS, or not http(s).")
        return
    try:
        r = _retry_get(url, timeout=settings.sync_timeout_seconds, allow_redirects=True)
        r.raise_for_status()
    except Exception as exc:
        print(f"  REQUEST FAILED after retries: {type(exc).__name__}: {exc}")
        return
    if not safe_url(r.url):
        print(f"  REDIRECTED outside allowlist to {r.url!r}")
        return

    ctype = (r.headers.get("content-type") or "").lower()
    if is_pdf(r.content):
        fmt = "pdf"
        raw_title = urlparse(r.url).path.rsplit("/", 1)[-1]
        text = pdf_text(r.content)
    elif is_docx(r.content):
        fmt = "docx"
        raw_title = urlparse(r.url).path.rsplit("/", 1)[-1]
        text = docx_text(r.content)
    elif "html" in ctype or r.content.lstrip().startswith((b"<!DOCTYPE", b"<html", b"<HTML")):
        fmt = "html"
        r.encoding = r.apparent_encoding or r.encoding
        raw_title, text, links = clean_html(r.text)
        candidates = [(href, label) for href, label in links if candidate(href, label)]
        print(f"  raw <a href> links found: {len(links)} | candidates: {len(candidates)}")
        _flag_target_law_matches(candidates, r.url)
        if len(text) < 300:
            print("     Probing robots.txt/sitemap.xml for a JS-bypass path:")
            probe_sitemap_and_robots(r.url)
        print(f"  sample of candidate links, first 25 of {len(candidates)}:")
        for href, label in candidates[:25]:
            absolute = urljoin(r.url, href)
            print(f"    [{'OK' if safe_url(absolute) else 'OUT-OF-ALLOWLIST'}] {absolute}")
            print(f"        label: {label!r}")
    else:
        print(f"  UNRECOGNIZED format, content-type={ctype!r} — sync_engine would skip silently.")
        return

    print(f"  format: {fmt}")
    print(f"  raw extracted text length: {len(text)} chars")
    print(f"  text sample (first 400 chars): {text[:400]!r}")
    print(f"  text sample (chars 2000-2400, if present): {text[2000:2400]!r}")
    if len(text) < 120:
        print("  -> sync_engine's `if len(text) < 120: continue` would DROP this silently before")
        print("     any quality_gate() call — not even recorded as rejected.")
        return

    title = pretty_title(raw_title, text, "diagnostic")
    domain, conf, reasons = classify_document(title, text, source_domains=None, authority="diagnostic")
    print(f"  pretty_title: {title!r}")
    print(f"  classified domain: {domain} (confidence={conf}, reasons={reasons})")

    pieces = split_articles(text)
    article_pieces = [p for p in pieces if p[0] is not None]
    print(f"  split_articles(): {len(pieces)} pieces total, {len(article_pieces)} with a detected")
    print(f"    article number (real 'المادة N' structure found: {len(article_pieces) >= 3 or (len(pieces) > 0 and pieces[0][0] is not None)})")
    if article_pieces:
        nums = [p[0] for p in article_pieces]
        print(f"    article numbers found (first 20): {nums[:20]}")

    accepted, reason = quality_gate(title=title, text=text, domain=domain, chunks=pieces, source_domains=None)
    print(f"  quality_gate() verdict: {'ACCEPTED' if accepted else 'REJECTED'} (reason={reason})")


def main() -> int:
    sources = [s.strip() for s in (os.environ.get("DIAG_SOURCES") or "").split(",") if s.strip()]
    urls = [u.strip() for u in (os.environ.get("DIAG_URLS") or "").split(",") if u.strip()]
    if not sources and not urls:
        print("Set DIAG_SOURCES and/or DIAG_URLS env vars. Nothing to do.")
        return 1
    for source_id in sources:
        diagnose_source(source_id)
    for url in urls:
        diagnose_url(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
