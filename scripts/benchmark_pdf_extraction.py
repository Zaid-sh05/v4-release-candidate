"""Benchmark pypdf vs. pdfplumber on a real, currently-failing official PDF.

Root cause found by scripts/diagnose_source_discovery.py against the Civil Code PDF
(moj.gov.jo): the document is genuinely complete (883,191 extracted chars; the PDF's own
metadata block states 1449 articles) and correctly classified (domain=civil, confidence 1.0),
but pypdf extracts Arabic text with MIRRORED character order per line (e.g. "المادة" comes out
as "ةداملا"), so the "المادة N" article-boundary regex never matches and quality_gate() rejects
it as no_statutory_article_structure. This is a PDF-extraction bug, not a missing-content or
classification problem.

Per policy: benchmark at least two extraction paths before switching libraries, measuring
readable-content/article-detection/processing-time — never switch based on one PDF alone
without a real measurement. Both pypdf (BSD-3) and pdfplumber (MIT, built on pdfminer.six,
MIT) are permissively licensed and zero-cost, consistent with the open-source-first policy.

Read-only: fetches the PDF bytes once and only runs extraction/regex logic locally. No writes.
"""
from __future__ import annotations

import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.legal_update_guard import _ARTICLE_STRUCTURE_RE, _GARBLED_MARKERS
from app.sync_engine import pdf_text as pypdf_extract
from app.sync_engine import safe_url, split_articles

TARGET_URL = os.environ.get("BENCHMARK_PDF_URL") or (
    "https://www.moj.gov.jo/ebv4.0/root_storage/ar/eb_list_page/"
    "%D8%A7%D9%84%D9%82%D8%A7%D9%86%D9%88%D9%86_%D8%A7%D9%84%D9%85%D8%AF%D9%86%D9%8A_"
    "%D8%B1%D9%82%D9%85_43_%D9%84%D8%B3%D9%86%D8%A9_1976.pdf"
)


def pdfplumber_extract(data: bytes) -> str:
    import io

    import pdfplumber

    out = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            out.append(page.extract_text() or "")
    return "\n".join(out)


def report(label: str, text: str, elapsed: float) -> None:
    forward_articles = _ARTICLE_STRUCTURE_RE.findall(text)
    pieces = split_articles(text)
    detected = [p for p in pieces if p[0] is not None]
    garbled_hits = sum(1 for m in _GARBLED_MARKERS if m in text.lower())
    print(f"\n-- {label} --")
    print(f"   extraction time: {elapsed:.2f}s")
    print(f"   total chars extracted: {len(text)}")
    print(f"   'المادة N' regex matches (forward/correct order): {len(forward_articles)}")
    print(f"   split_articles() pieces: {len(pieces)}, with detected article number: {len(detected)}")
    print(f"   garbled/boilerplate marker hits: {garbled_hits}")
    print(f"   would pass no_statutory_article_structure gate: {len(forward_articles) > 0}")
    print(f"   text sample (first 300 chars): {text[:300]!r}")


def main() -> int:
    if not safe_url(TARGET_URL):
        print("BLOCKED: target URL host is not in ALLOWED_HOSTS.")
        return 1
    print(f"Fetching (once, reused for both extractors): {TARGET_URL}")
    r = requests.get(TARGET_URL, timeout=60)
    r.raise_for_status()
    data = r.content
    print(f"Downloaded {len(data)} bytes.")

    t0 = time.monotonic()
    pypdf_text = pypdf_extract(data)
    report("pypdf (current production extractor)", pypdf_text, time.monotonic() - t0)

    try:
        t0 = time.monotonic()
        plumber_text = pdfplumber_extract(data)
        report("pdfplumber (candidate)", plumber_text, time.monotonic() - t0)
    except ImportError:
        print("\npdfplumber not installed in this environment — skipping candidate benchmark.")
        return 1

    print("\nDone. This script does not assert pass/fail or switch anything — it reports")
    print("measurements for a human/agent to decide the extraction-library question from.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
