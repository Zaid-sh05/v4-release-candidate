"""Read-only corpus/retrieval audit — Phase 2 (issue-aware retrieval) research.

Purpose: measure, rather than assume, whether the current `domain`-only chunk
tagging is fine-grained enough to keep a topically wrong same-domain statute
(e.g. a Penal Code adultery article) from outranking the correct statute
(e.g. a Cybercrime Law extortion/threat article) once routing has already
narrowed to the right domain set.

This script only performs `select` reads and calls the existing read-only
`keyword_search_legal_chunks` RPC — it never writes, upserts, or deletes.
It has no embedding access (OPENAI_API_KEY is not a CI secret), so it can
only exercise the lexical half of hybrid_search's RRF fusion; that is stated
explicitly in the output rather than presented as a full hybrid measurement.

Run via GitHub Actions (workflow_dispatch) where SUPABASE_URL /
SUPABASE_SERVICE_ROLE_KEY are already configured as repository secrets.
"""
from __future__ import annotations

import os
import sys
from collections import Counter

import httpx

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

# Probes: (label, query_text, filter_domains, what we're checking for)
HARD_NEGATIVE_PROBES = [
    (
        "cyber-extortion vs adultery",
        "شخص هدد بنشر صور فاضحة إذا لم يتم تحويل مبلغ مالي له عبر تطبيق",
        ["cyber", "criminal"],
        "expect a cybercrime extortion/threat article near top-1; watch for a "
        "Penal Code adultery/honor article (زنا) outranking it",
    ),
    (
        "labor termination vs unrelated criminal dismissal wording",
        "صاحب العمل أنهى عقد العمل بدون إنذار مسبق ولا تعويض",
        ["labor"],
        "expect a labor-law termination/notice article near top-1",
    ),
    (
        "burglary aggravation vs simple theft",
        "دخول منزل بكسر قفل الباب وأخذ مبلغ مالي وجهاز حاسوب",
        ["criminal"],
        "expect a break-and-enter aggravation article competitive with plain "
        "theft articles",
    ),
]

# Word-count-graduated diagnostic probes to isolate *why* the hard-negative probes above
# returned zero rows: websearch_to_tsquery ANDs bare words together, so a long natural
# sentence needs every single word to appear verbatim in a chunk. These probes strip a
# known-good phrase down word by word to find where the match count goes from >0 to 0.
LEXICAL_DIAGNOSTIC_PROBES = [
    ("cyber: 2-word statute-style phrase", "الجرائم الإلكترونية", ["cyber"]),
    ("cyber: 4-word legal phrase", "قانون الجرائم الإلكترونية الابتزاز", ["cyber"]),
    ("cyber: our retrieval_planner.py query (8 words)",
     "قانون الجرائم الإلكترونية الأردني الابتزاز الإلكتروني التهديد بنشر معلومات أو صور", ["cyber"]),
    ("cyber: single word", "ابتزاز", ["cyber"]),
    ("criminal: 2-word statute-style phrase", "كسر قفل", ["criminal"]),
    ("criminal: single word", "سرقة", ["criminal"]),
    ("labor: single word", "فصل", ["labor"]),
    ("labor: 2-word phrase", "إنهاء عقد", ["labor"]),
]


def rpc_keyword_search(query_text: str, filter_domains: list[str], match_count: int = 8) -> list[dict]:
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/rpc/keyword_search_legal_chunks",
        headers={**HEADERS, "Content-Type": "application/json"},
        json={"query_text": query_text, "filter_domains": filter_domains, "match_count": match_count},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def fetch_all_domains() -> Counter:
    domains: Counter = Counter()
    offset = 0
    page = 1000
    while True:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/legal_chunks",
            headers=HEADERS,
            params={"select": "domain", "offset": offset, "limit": page},
            timeout=30,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            break
        domains.update(row["domain"] for row in rows)
        offset += page
        if len(rows) < page:
            break
    return domains


def fetch_distinct_titles_for_domain(domain: str, limit: int = 30) -> list[str]:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/legal_chunks",
        headers=HEADERS,
        params={"select": "title", "domain": f"eq.{domain}", "limit": limit},
        timeout=30,
    )
    r.raise_for_status()
    return sorted({row["title"] for row in r.json() if row.get("title")})


def main() -> int:
    print("=" * 70)
    print("LEGAL CORPUS TOPIC AUDIT (read-only)")
    print("=" * 70)

    print("\n-- domain distribution (full table scan, count only) --")
    domains = fetch_all_domains()
    total = sum(domains.values())
    for domain, count in domains.most_common():
        print(f"  {domain:20s} {count:5d}  ({100 * count / total:.1f}%)")
    print(f"  TOTAL: {total}")

    print("\n-- distinct source-law titles per domain (up to 30 sampled rows) --")
    print("   (this is the only existing signal finer than `domain`; if a domain's")
    print("    titles already cleanly separate by statute, that may be usable as a")
    print("    cheap topic proxy without a new taxonomy column)")
    for domain in domains:
        titles = fetch_distinct_titles_for_domain(domain)
        print(f"\n  domain={domain} ({len(titles)} distinct titles in sample):")
        for t in titles:
            print(f"    - {t}")

    print("\n" + "=" * 70)
    print("HARD-NEGATIVE LEXICAL RETRIEVAL PROBES")
    print("(keyword_search_legal_chunks only — no embedding access in CI, so this")
    print(" measures the lexical half of hybrid_search's RRF fusion, not the full")
    print(" hybrid score. Treat results as a lower bound / directional signal.)")
    print("=" * 70)
    exit_code = 0
    for label, query_text, filter_domains, expectation in HARD_NEGATIVE_PROBES:
        print(f"\n-- probe: {label} --")
        print(f"   query: {query_text!r}")
        print(f"   filter_domains: {filter_domains}")
        print(f"   expectation: {expectation}")
        try:
            rows = rpc_keyword_search(query_text, filter_domains, 8)
        except Exception as exc:
            print(f"   ERROR calling RPC: {type(exc).__name__}: {exc}")
            exit_code = 1
            continue
        if not rows:
            print("   (no lexical matches at all — websearch_to_tsquery may have found nothing)")
            continue
        for i, row in enumerate(rows, 1):
            excerpt = " ".join((row.get("excerpt") or "").split())[:140]
            print(
                f"   [{i}] score={row.get('score'):.4f} domain={row.get('domain')} "
                f"article={row.get('article')} title={row.get('title')[:60]!r}"
            )
            print(f"        excerpt: {excerpt}")

    print("\n" + "=" * 70)
    print("LEXICAL DIAGNOSTIC PROBES (word-count graduated)")
    print("Isolating whether AND-semantics over long sentences is why the hard-negative")
    print("probes above returned zero rows.")
    print("=" * 70)
    for label, query_text, filter_domains in LEXICAL_DIAGNOSTIC_PROBES:
        print(f"\n-- {label} --")
        print(f"   query: {query_text!r}  filter_domains: {filter_domains}")
        try:
            rows = rpc_keyword_search(query_text, filter_domains, 5)
        except Exception as exc:
            print(f"   ERROR calling RPC: {type(exc).__name__}: {exc}")
            exit_code = 1
            continue
        if not rows:
            print("   -> 0 matches")
            continue
        print(f"   -> {len(rows)} matches, top: score={rows[0].get('score'):.4f} title={rows[0].get('title')[:60]!r}")

    print("\nDone. This script does not assert pass/fail — it reports measurements")
    print("for a human/agent to read and decide the Phase 2 architecture from.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
