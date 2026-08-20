"""Benchmark pypdf vs. pdfplumber vs. BiDi-reconstruction on a real, currently-failing
official Arabic statutory PDF.

Root cause chain found across two real documents (a Jordanian Civil Code PDF on moj.gov.jo,
and a Penal Code PDF on jiacc.gov.jo): both are genuinely complete, correctly-classified
statutory text, but both extractors -- pypdf AND pdfplumber -- read the PDF's glyph stream in
MIRRORED (visual, not logical) order, so "المادة" comes out as "ةداملا" and the article-boundary
regex never matches. This is NOT a pypdf-vs-pdfplumber problem (both fail identically); it is
a missing Unicode BiDi reordering step, which app.arabic_text_quality.
reconstruct_visual_order_arabic() performs. See that module's docstring for the algorithm and
its one documented residual limitation (an internal Lam+Alef ligature can end up with its two
letters transposed in a small fraction of words -- never affects numbers, years, article
numbers, or Latin tokens).

Per policy: benchmark real candidates before switching anything, measuring forward vs. reversed
marker counts, article detection, numeric/Latin-token preservation, and processing time --
never declare success just because "المادة" appears; check article sequence and count too.

Two independent input modes:
  BENCHMARK_PDF_FILE=/path/to/file.pdf   read local bytes, no network call at all (use this
                                          for a manually-provided PDF, e.g. the Civil Code,
                                          without any automated fetch to its source host).
  BENCHMARK_PDF_URL=https://...          fetch over the network (only ever used against an
                                          ALLOWED_HOSTS host that isn't under a cooldown).
If neither is set, defaults to the Civil Code URL below -- do not dispatch this against
moj.gov.jo while that host is under a cooldown; use BENCHMARK_PDF_FILE instead.

Read-only: no writes, no promotion.
"""
from __future__ import annotations

import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.arabic_text_quality import looks_like_reversed_arabic_reading_order, reconstruct_visual_order_arabic
from app.legal_update_guard import _ARTICLE_STRUCTURE_RE, _GARBLED_MARKERS
from app.sync_engine import pdf_text as pypdf_extract
from app.sync_engine import safe_url, split_articles

TARGET_FILE = os.environ.get("BENCHMARK_PDF_FILE") or None
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
    forward = text.count("المادة")
    reversed_count = text.count("المادة"[::-1])
    total_markers = forward + reversed_count
    readability = (forward / total_markers) if total_markers else None
    forward_articles = _ARTICLE_STRUCTURE_RE.findall(text)
    pieces = split_articles(text)
    detected = [p for p in pieces if p[0] is not None]
    nums = sorted({int(n) for n, _ in pieces if n is not None})
    garbled_hits = sum(1 for m in _GARBLED_MARKERS if m in text.lower())
    print(f"\n-- {label} --")
    print(f"   extraction/reconstruction time: {elapsed:.2f}s")
    print(f"   total chars: {len(text)}")
    print(f"   'المادة' occurrences: forward={forward} reversed={reversed_count} "
          f"(readability score: {readability if readability is not None else 'n/a'})")
    print(f"   'المادة N' regex matches (forward/correct order): {len(forward_articles)}")
    print(f"   split_articles() pieces: {len(pieces)}, with detected article number: {len(detected)}")
    if nums:
        print(f"   article-number range: {nums[0]}..{nums[-1]} ({len(nums)} distinct)")
    print(f"   garbled/boilerplate marker hits: {garbled_hits}")
    print(f"   would pass no_statutory_article_structure gate: {len(forward_articles) > 0}")
    print(f"   text sample (first 300 chars): {text[:300]!r}")


def main() -> int:
    if TARGET_FILE:
        print(f"Reading local file (no network call): {TARGET_FILE}")
        with open(TARGET_FILE, "rb") as fh:
            data = fh.read()
    else:
        if not safe_url(TARGET_URL):
            print("BLOCKED: target URL host is not in ALLOWED_HOSTS.")
            return 1
        print(f"Fetching (once, reused for all candidates): {TARGET_URL}")
        r = requests.get(TARGET_URL, timeout=60)
        r.raise_for_status()
        data = r.content
    print(f"{len(data)} bytes.")

    t0 = time.monotonic()
    pypdf_text = pypdf_extract(data)
    pypdf_elapsed = time.monotonic() - t0
    report("pypdf (current production extractor)", pypdf_text, pypdf_elapsed)

    t0 = time.monotonic()
    bidi_text = reconstruct_visual_order_arabic(pypdf_text)
    report("pypdf + BiDi reconstruction", bidi_text, time.monotonic() - t0)
    print(f"   was reading-order-corrupted before reconstruction: "
          f"{looks_like_reversed_arabic_reading_order(pypdf_text)}")

    try:
        t0 = time.monotonic()
        plumber_text = pdfplumber_extract(data)
        plumber_elapsed = time.monotonic() - t0
        report("pdfplumber (candidate)", plumber_text, plumber_elapsed)

        t0 = time.monotonic()
        plumber_bidi_text = reconstruct_visual_order_arabic(plumber_text)
        report("pdfplumber + BiDi reconstruction", plumber_bidi_text, time.monotonic() - t0)
    except ImportError:
        print("\npdfplumber not installed in this environment — skipping those two candidates.")

    print("\nDone. This script does not assert pass/fail or switch anything — it reports")
    print("measurements for a human/agent to decide the extraction architecture from.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
