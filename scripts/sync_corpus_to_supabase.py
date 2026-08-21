"""Idempotent promotion of this session's locally-validated corpus additions into production
Supabase, plus a targeted repair of known-corrupted Traffic Law chunks there.

Scope (exactly, no more):
  1. The 41 documents / 2930 chunks this session added to data/qanoni.sqlite3 under
     PR #55 (Civil Code, Penal Code) and PR #56 (the 39-law Master Corpus package),
     identified unambiguously by their source_url prefix ('user-supplied-paste://') --
     never by title, to avoid any fuzzy-matching risk. Excludes, by construction (they were
     simply never ingested locally), the 5 QUALITY_BLOCKED OCR laws.
  2. A mirror of PR #58's local Traffic Law chunk repair, applied to Supabase's own copy of
     "قانون السير رقم 49 لسنة 2008 وتعديلاته" (confirmed by a prior read-only audit to have
     the same 61-chunk/55-article/article-range-1..343 fingerprint as the corrupted local
     document before PR #58) -- ONLY for articles where Supabase has exactly one corrupted
     chunk under that article number (an unambiguous match). Articles with more than one
     chunk sharing a label (3 and 17 locally) are reported, never auto-replaced, since
     resolving which chunk matches which clean text requires the same by-hand content
     verification PR #58 did locally, not something this script can safely automate blind.

DRY RUN BY DEFAULT. Requires --live to write anything. Dry run performs every read/comparison
and prints the exact plan -- zero Supabase writes -- so the plan can be reviewed before anyone
approves --live.

Reuses app.supabase_store.SupabaseStore.replace_legal_document_chunks(), the existing
production write path (same sha1/sha256 id scheme as the local sqlite side; idempotent
per-document upsert that only touches rows sharing that exact document's own source_url, so
running this twice, or running it alongside unrelated existing Supabase content, cannot
duplicate or clobber anything outside its own 41 documents).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.repository import repository
from app.supabase_store import SupabaseStore
from app.text import normalize_ar

TRAFFIC_LAW_TITLE = "قانون السير رقم 49 لسنة 2008 وتعديلاته"
TRAFFIC_LAW_DOMAIN = "traffic"

# (article, clean_text) -- identical to the PR #58 local fix; same manually-verified,
# boundary-truncated text sourced from the master-corpus LAW13 supplement.
TRAFFIC_LAW_CLEAN_ARTICLES: dict[str, str] = {}


def _is_corrupted(body: str) -> bool:
    return any(0xFB50 <= ord(c) <= 0xFDFF or 0xFE70 <= ord(c) <= 0xFEFF for c in (body or ""))


def load_traffic_clean_articles() -> None:
    """Recompute the exact 6 verified clean replacement texts from the local PR #56 chunks
    that PR #58 used, by reading them back out of data/qanoni.sqlite3 (the LOCAL Traffic Law
    supplement document, already fixed/validated -- not re-deriving from raw source text)."""
    con = repository.connect()
    # the LOCAL traffic canonical document, PR #58 already fixed these 6 chunks
    row = con.execute(
        "select id from documents where domain='traffic' and title_ar=? and source_kind='canonical_official'",
        (TRAFFIC_LAW_TITLE,),
    ).fetchone()
    if row is None:
        raise SystemExit("local canonical Traffic Law document not found -- aborting")
    doc_id = row["id"]
    for art in ("3", "17", "27", "30", "32", "343"):
        chunks = con.execute(
            "select body from chunks where document_id=? and article=?", (doc_id, art)
        ).fetchall()
        clean = [c["body"] for c in chunks if not _is_corrupted(c["body"])]
        if len(clean) == 1:
            TRAFFIC_LAW_CLEAN_ARTICLES[art] = clean[0]
        # if 0 or >1 clean candidates locally, leave unset -- article 3 and 17 locally have a
        # second, DIFFERENT-topic chunk that stays corrupted (no source), so len(clean)==1 is
        # exactly the expected/verified case for all 6 target articles.
    con.close()


def plan_document_promotion() -> list[dict]:
    con = repository.connect()
    docs = con.execute(
        "select id, title_ar, authority, domain, source_url, source_kind, verified_at "
        "from documents where source_url like 'user-supplied-paste://%' order by domain, title_ar"
    ).fetchall()
    plan = []
    for d in docs:
        chunks = con.execute(
            "select article, body from chunks where document_id=? order by chunk_index", (d["id"],)
        ).fetchall()
        plan.append({
            "title": d["title_ar"], "authority": d["authority"], "domain": d["domain"],
            "source_url": d["source_url"], "source_kind": d["source_kind"],
            "verified_at": d["verified_at"],
            "chunks": [(c["article"], c["body"]) for c in chunks],
        })
    con.close()
    return plan


def plan_traffic_repair(store: SupabaseStore) -> tuple[list[dict], list[dict]]:
    """Returns (applicable_fixes, skipped_ambiguous)."""
    rows = (
        store.client.table("legal_chunks")
        .select("id,article,body")
        .eq("title", TRAFFIC_LAW_TITLE)
        .eq("domain", TRAFFIC_LAW_DOMAIN)
        .execute()
        .data
        or []
    )
    by_article: dict[str, list[dict]] = {}
    for r in rows:
        by_article.setdefault(r.get("article") or "", []).append(r)

    applicable, skipped = [], []
    for art, clean_text in TRAFFIC_LAW_CLEAN_ARTICLES.items():
        candidates = by_article.get(art, [])
        corrupt = [r for r in candidates if _is_corrupted(r["body"])]
        if len(candidates) == 0:
            skipped.append({"article": art, "reason": "not_found_in_supabase"})
        elif len(corrupt) == 0:
            skipped.append({"article": art, "reason": "already_clean_in_supabase", "n_candidates": len(candidates)})
        elif len(candidates) > 1:
            skipped.append({
                "article": art, "reason": "ambiguous_multiple_chunks_same_article",
                "n_candidates": len(candidates), "n_corrupt": len(corrupt),
            })
        else:
            applicable.append({
                "article": art, "chunk_id": corrupt[0]["id"],
                "old_preview": corrupt[0]["body"][:60], "new_text": clean_text,
            })
    return applicable, skipped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="actually write to Supabase (default: dry run)")
    args = ap.parse_args()

    store = SupabaseStore()
    if not store.configured:
        raise SystemExit(f"Supabase not configured: {store.last_error or 'no credentials'}")

    print("=" * 70)
    print(f"SUPABASE CORPUS SYNC -- {'LIVE' if args.live else 'DRY RUN'}")
    print("=" * 70)

    before = store.client.table("legal_chunks").select("id", count="exact").execute()
    before_docs = store.client.table("legal_documents").select("id", count="exact").execute()
    print(f"\nBEFORE: documents={before_docs.count} chunks={before.count}")

    # --- 1. document promotion plan --------------------------------------------------------
    doc_plan = plan_document_promotion()
    total_chunks = sum(len(d["chunks"]) for d in doc_plan)
    print(f"\n{len(doc_plan)} documents / {total_chunks} chunks to promote (source_url-identified, this session's work only):")
    for d in doc_plan:
        print(f"  [{d['domain']:15s}] {d['source_kind']:15s} chunks={len(d['chunks']):5d}  {d['title'][:55]}")

    results = {"documents_written": 0, "chunks_written": 0, "traffic_fixed": 0, "traffic_skipped": []}

    if args.live:
        for d in doc_plan:
            n = store.replace_legal_document_chunks(
                title=d["title"], authority=d["authority"], domain=d["domain"],
                source_url=d["source_url"], chunks=d["chunks"],
                source_kind=d["source_kind"], verified_at=d["verified_at"],
            )
            results["documents_written"] += 1
            results["chunks_written"] += n
            print(f"  WROTE {d['title'][:50]:50s} -> {n} chunks")

    # --- 2. traffic-law repair plan ----------------------------------------------------------
    load_traffic_clean_articles()
    applicable, skipped = plan_traffic_repair(store)
    print(f"\nTraffic Law repair: {len(applicable)} applicable fixes, {len(skipped)} skipped (see reasons)")
    for a in applicable:
        print(f"  article {a['article']}: chunk {a['chunk_id'][:12]} old={a['old_preview']!r} -> new_len={len(a['new_text'])}")
    for s in skipped:
        print(f"  SKIP article {s['article']}: {s['reason']} {s}")

    if args.live:
        for a in applicable:
            new_hash = hashlib.sha256(normalize_ar(a["new_text"]).encode()).hexdigest()
            store.client.table("legal_chunks").update({
                "body": a["new_text"],
            }).eq("id", a["chunk_id"]).execute()
            results["traffic_fixed"] += 1
            print(f"  FIXED article {a['article']} (chunk {a['chunk_id'][:12]})")
        results["traffic_skipped"] = skipped

    after = store.client.table("legal_chunks").select("id", count="exact").execute()
    after_docs = store.client.table("legal_documents").select("id", count="exact").execute()
    print(f"\nAFTER: documents={after_docs.count} chunks={after.count}")
    print(f"DELTA: documents={(after_docs.count or 0)-(before_docs.count or 0):+d} chunks={(after.count or 0)-(before.count or 0):+d}")

    print("\n" + "=" * 70)
    print("OBSERVABILITY SUMMARY")
    print("=" * 70)
    print(json.dumps({
        "mode": "live" if args.live else "dry_run",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "documents_planned": len(doc_plan),
        "chunks_planned": total_chunks,
        "traffic_applicable": len(applicable),
        "traffic_skipped": len(skipped),
        **results,
    }, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
