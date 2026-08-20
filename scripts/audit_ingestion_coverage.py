"""Read-only ingestion/coverage audit — Legal Knowledge Program research.

Answers, from real production telemetry (never assumption): for every configured official
source, what got discovered/ingested/rejected and why; and for the highest-value Jordanian
statutes, how complete is article-level coverage in the corpus right now.

Strictly read-only: only `select` against Supabase tables/views already written by
app/legal_update_guard.py (qanoni_legal_update_events, qanoni_legal_sync_fingerprints) and
app/supabase_store.py (legal_chunks). No writes, no schema changes, no ingestion triggered.

Run via GitHub Actions (workflow_dispatch) where SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are
already configured as repository secrets.
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter, defaultdict

import httpx

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

# Mirrors app/repository.py's local source_registry seed (data/qanoni.sqlite3) as of this
# audit. This is static config, not live data — paired below with real cloud telemetry by
# source_id to build the coverage matrix.
SOURCE_REGISTRY = [
    ("jc_labor_principles", "المجلس القضائي الأردني", ["labor"], "reference"),
    ("sjd_courts", "دائرة قاضي القضاة", ["procedure", "personal_status"], "reference"),
    ("sjd_laws", "دائرة قاضي القضاة", ["personal_status", "procedure"], "crawl"),
    ("ccd_laws", "دائرة مراقبة الشركات", ["commercial"], "crawl"),
    ("lob_legislation", "ديوان التشريع والرأي", ["general", "civil", "criminal", "procedure",
     "traffic", "commercial", "labor", "cyber", "administrative", "real_estate",
     "constitutional", "tax_finance", "personal_status"], "reference"),
    ("pm_official_gazette", "رئاسة الوزراء الأردنية", ["general", "constitutional", "civil",
     "criminal", "procedure", "traffic", "commercial", "labor", "cyber", "tax_finance",
     "administrative", "real_estate", "personal_status"], "crawl"),
    ("psd_laws", "مديرية الأمن العام", ["traffic", "cyber", "criminal"], "crawl"),
    ("psd_traffic", "مديرية الأمن العام - المعهد المروري الأردني", ["traffic"], "crawl"),
    ("mola_laws", "وزارة الإدارة المحلية", ["civil", "real_estate", "labor", "administrative", "general"], "crawl"),
    ("modee_privacy", "وزارة الاقتصاد الرقمي والريادة", ["cyber"], "crawl"),
    ("mosd_laws", "وزارة التنمية الاجتماعية", ["criminal", "general"], "crawl"),
    ("moh_core_laws", "وزارة الصحة الأردنية", ["general", "civil", "criminal", "labor"], "crawl"),
    ("moj_systems", "وزارة العدل الأردنية", ["civil", "criminal", "procedure", "administrative", "general"], "crawl"),
    ("moj_penal_context", "وزارة العدل الأردنية", ["criminal"], "crawl"),
    ("moj_laws", "وزارة العدل الأردنية", ["civil", "criminal", "procedure", "administrative", "general"], "crawl"),
    ("moj_court_services", "وزارة العدل الأردنية", ["procedure", "criminal", "civil"], "reference"),
    ("mol_laws", "وزارة العمل الأردنية", ["labor"], "crawl"),
    ("mol_faq", "وزارة العمل الأردنية", ["labor"], "reference"),
    ("mol_labor_termination_guidance", "وزارة العمل الأردنية", ["labor"], "reference"),
]

# High-value laws to prioritize, matched against `title` by substring (Arabic, normalized by
# stripping diacritics is not needed here — titles in the corpus are already plain text).
TARGET_LAWS = [
    ("Civil Code / القانون المدني", "القانون المدني"),
    ("Labour Law / قانون العمل", "قانون العمل"),
    ("Penal Code / قانون العقوبات", "قانون العقوبات"),
    ("Cybercrime Law / قانون الجرائم الإلكترونية", "الجرائم الالكترونية"),
    ("Traffic Law / قانون السير", "قانون السير"),
    ("Civil Procedure / أصول المحاكمات المدنية", "أصول المحاكمات المدنية"),
    ("Criminal Procedure / أصول المحاكمات الجزائية", "أصول المحاكمات الجزائية"),
    ("Evidence Law / قانون البينات", "قانون البينات"),
    ("Personal Status Law / قانون الأحوال الشخصية", "الأحوال الشخصية"),
    ("Companies Law / قانون الشركات", "قانون الشركات"),
    ("Personal Data Protection Law / قانون حماية البيانات الشخصية", "حماية البيانات الشخصية"),
]

_ARTICLE_NUM_RE = re.compile(r"\d+")


def fetch_all(table: str, select: str, params: dict | None = None) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    page = 1000
    base_params = dict(params or {})
    while True:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=HEADERS,
            params={**base_params, "select": select, "offset": offset, "limit": page},
            timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return rows


def main() -> int:
    print("=" * 70)
    print("INGESTION / COVERAGE AUDIT (read-only)")
    print("=" * 70)

    # ------------------------------------------------------------------
    # 1) Real sync telemetry: what did the crawler actually do, per source?
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("SYNC TELEMETRY: qanoni_legal_update_events (every crawl decision ever recorded)")
    print("=" * 70)
    events = fetch_all("qanoni_legal_update_events", "source_id,action,reason,domain,created_at")
    if not events:
        print("  NO ROWS AT ALL — the weekly-sync workflow has never successfully recorded a")
        print("  single crawl decision against this Supabase project. This is the most direct")
        print("  possible evidence of a root cause: either the workflow never ran end-to-end,")
        print("  or every source's very first document failed before reaching record().")
    else:
        by_source: dict[str, Counter] = defaultdict(Counter)
        reasons_by_source: dict[str, Counter] = defaultdict(Counter)
        for e in events:
            by_source[e["source_id"]][e["action"]] += 1
            if e["action"] == "rejected":
                reasons_by_source[e["source_id"]][e.get("reason") or "unknown"] += 1
        print(f"  total events: {len(events)} across {len(by_source)} source_ids\n")
        for source_id, counts in sorted(by_source.items()):
            print(f"  source_id={source_id}: {dict(counts)}")
            if reasons_by_source[source_id]:
                print(f"      rejection reasons: {dict(reasons_by_source[source_id])}")

    seen_source_ids = {e["source_id"] for e in events} if events else set()
    print("\n  -- sources with ZERO recorded events (never ran, or crawler never reached a")
    print("     single record() call — e.g. discovery/allowlist/timeout failure before any")
    print("     document was even classified) --")
    for source_id, authority, domains, mode in SOURCE_REGISTRY:
        if mode == "reference":
            continue
        if source_id not in seen_source_ids:
            print(f"    - {source_id} ({authority}, expected domains={domains})")

    # ------------------------------------------------------------------
    # 2) What actually got promoted, per source?
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("PROMOTED DOCUMENTS: qanoni_legal_sync_fingerprints (currently-live promoted set)")
    print("=" * 70)
    fingerprints = fetch_all("qanoni_legal_sync_fingerprints", "source_id,source_url,title,domain,promoted_at")
    by_source_fp: dict[str, list[dict]] = defaultdict(list)
    for f in fingerprints:
        by_source_fp[f["source_id"]].append(f)
    print(f"  total promoted documents: {len(fingerprints)}\n")
    for source_id, authority, domains, mode in SOURCE_REGISTRY:
        docs = by_source_fp.get(source_id, [])
        tag = "REFERENCE-ONLY (no crawl expected)" if mode == "reference" else f"{len(docs)} promoted"
        print(f"  {source_id:32s} | {authority[:28]:28s} | {tag}")
        for d in docs[:8]:
            print(f"      - {d['title'][:80]}")
        if len(docs) > 8:
            print(f"      ... and {len(docs) - 8} more")

    # ------------------------------------------------------------------
    # 3) Thin-domain deep dive: everything actually stored under civil/tax_finance/cyber.
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("THIN-DOMAIN DEEP DIVE (full row listing, not a sample)")
    print("=" * 70)
    for domain in ("civil", "tax_finance", "cyber"):
        rows = fetch_all("legal_chunks", "title,article,body,source_url", {"domain": f"eq.{domain}"})
        print(f"\n  domain={domain}: {len(rows)} total chunks")
        by_title: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by_title[r["title"]].append(r)
        for title, chunks in by_title.items():
            body_chars = sum(len(c.get("body") or "") for c in chunks)
            articles = sorted({c["article"] for c in chunks if c.get("article")})
            print(f"    - {title[:70]!r}: {len(chunks)} chunks, {body_chars} total body chars, "
                  f"articles={articles[:15]}{'...' if len(articles) > 15 else ''}")

    # ------------------------------------------------------------------
    # 4) High-value law coverage matrix: article-level completeness where determinable.
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("HIGH-VALUE LAW COVERAGE MATRIX")
    print("=" * 70)
    for label, needle in TARGET_LAWS:
        rows = fetch_all("legal_chunks", "title,article,body,domain,verified_at", {"title": f"ilike.*{needle}*"})
        print(f"\n-- {label} --")
        if not rows:
            print(f"    ZERO chunks with title containing {needle!r} — NOT PRESENT in the corpus at all.")
            continue
        by_title: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by_title[r["title"]].append(r)
        for title, chunks in by_title.items():
            body_chars = sum(len(c.get("body") or "") for c in chunks)
            article_nums = []
            for c in chunks:
                m = _ARTICLE_NUM_RE.search(c.get("article") or "")
                if m:
                    article_nums.append(int(m.group()))
            article_nums = sorted(set(article_nums))
            gaps = []
            for i in range(len(article_nums) - 1):
                if article_nums[i + 1] - article_nums[i] > 1:
                    gaps.append((article_nums[i], article_nums[i + 1]))
            print(f"    title={title[:70]!r} domain={chunks[0].get('domain')}")
            print(f"      chunks={len(chunks)} body_chars={body_chars} "
                  f"article_range={article_nums[:1]}..{article_nums[-1:]} distinct_articles={len(article_nums)}")
            if gaps:
                print(f"      POSSIBLE GAPS in article numbering (may be repealed/renumbered, "
                      f"or missing): {gaps[:10]}")
            if body_chars < 3000:
                print(f"      WARNING: very little text ({body_chars} chars total) for a named "
                      f"statute — likely an index/summary page was promoted, not the full text.")

    print("\nDone. This script does not assert pass/fail — it reports measurements for a")
    print("human/agent to read and decide the Legal Knowledge Program roadmap from.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
