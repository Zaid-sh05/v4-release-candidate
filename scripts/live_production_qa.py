from __future__ import annotations

import os
import re
import sys
import uuid
from typing import Any
from urllib.parse import unquote

import httpx

BASE_URL = os.getenv("QANONI_BASE_URL", "https://qanoni-alurdoni.up.railway.app").rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TIMEOUT = 35.0
EMOJI = re.compile(r"[\U0001F1E6-\U0001FAFF\u2600-\u27BF]+")

created_conversations: list[str] = []


def fail(message: str) -> None:
    raise AssertionError(message)


def canonical_url(value: str | None) -> str:
    return unquote((value or "").strip()).rstrip("/")


def post_chat(client: httpx.Client, message: str, *, language: str = "ar", force_domain: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"message": message, "language": language}
    if force_domain:
        payload["force_domain"] = force_domain
    r = client.post(f"{BASE_URL}/api/chat", json=payload)
    if r.status_code != 200:
        fail(f"chat {r.status_code}: {message!r}: {r.text[:500]}")
    data = r.json()
    cid = data.get("conversation_id")
    if cid:
        created_conversations.append(cid)
    if EMOJI.search(data.get("answer") or ""):
        fail(f"emoji leaked into answer for {message!r}")
    for src in data.get("sources") or []:
        if src.get("domain") not in (data.get("route") or {}).get("domains", []):
            fail(f"cross-domain source leak for {message!r}: {src.get('domain')} vs {data['route']['domains']}")
    return data


def assert_prefix(actual: list[str], expected: list[str], label: str) -> None:
    if actual[: len(expected)] != expected:
        fail(f"{label}: expected prefix {expected}, got {actual}")


def supabase_client():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        fail("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are required for production QA")
    from supabase import create_client

    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def newest_promoted_probe(sb) -> dict[str, str]:
    promoted = (
        sb.table("qanoni_legal_sync_fingerprints")
        .select("source_url,source_id,domain,title,promoted_at")
        .in_("source_id", ["ccd_laws", "mol_laws"])
        .order("promoted_at", desc=True)
        .limit(5)
        .execute()
        .data
        or []
    )
    if not promoted:
        fail("no promoted weekly-sync documents found in Supabase")
    for doc in promoted:
        rows = (
            sb.table("legal_chunks")
            .select("source_url,domain,title,article,body")
            .eq("source_url", doc["source_url"])
            .limit(5)
            .execute()
            .data
            or []
        )
        for row in rows:
            body = " ".join((row.get("body") or "").split())
            words = body.split()
            if len(words) >= 12:
                phrase = " ".join(words[2:12])
                return {
                    "source_url": row["source_url"],
                    "domain": row.get("domain") or doc.get("domain") or "general",
                    "phrase": phrase,
                    "title": row.get("title") or doc.get("title") or "",
                }
    fail("promoted weekly-sync documents contained no usable cloud chunk")


def cleanup(sb) -> None:
    for cid in dict.fromkeys(created_conversations):
        for table in [
            "qanoni_feedback_reviews",
            "qanoni_feedback",
            "qanoni_answer_evaluations",
            "qanoni_messages",
        ]:
            try:
                sb.table(table).delete().eq("conversation_id", cid).execute()
            except Exception as exc:
                print(f"cleanup warning: {table} {cid}: {type(exc).__name__}: {exc}")
        try:
            sb.table("qanoni_conversations").delete().eq("id", cid).execute()
        except Exception as exc:
            print(f"cleanup warning: conversation {cid}: {type(exc).__name__}: {exc}")


def main() -> int:
    sb = supabase_client()
    qa_tag = f"qa-{uuid.uuid4().hex[:8]}"
    client = httpx.Client(timeout=TIMEOUT, follow_redirects=True)
    try:
        health = client.get(f"{BASE_URL}/api/health")
        if health.status_code != 200:
            fail(f"health {health.status_code}: {health.text[:500]}")
        h = health.json()
        assert h.get("version") == "4.0.0-rc", h
        assert h.get("runtime_store") == "supabase", h
        assert (h.get("supabase") or {}).get("reachable") is True, h
        assert ((h.get("ai") or {}).get("cognition") or {}).get("configured") is True, h
        assert (h.get("corpus") or {}).get("store") == "supabase", h
        assert int((h.get("corpus") or {}).get("chunks") or 0) >= 4118, h
        print(f"[PASS] health / cloud corpus: {(h.get('corpus') or {}).get('chunks')} chunks")

        cases = [
            ("هلو", ["conversation"]),
            ("ما هي اجراءات الطلاق؟", ["personal_status"]),
            ("فصلني صاحب العمل بدون إنذار، شو حقوقي؟", ["labor"]),
            ("واحد ببتزني على واتساب وهدد ينشر صوري إذا ما دفعتله", ["cyber", "criminal"]),
            ("بدي أستأنف حكم بقضية سرقة، شو المعلومات اللي لازم أحددها؟", ["procedure", "criminal"]),
            ("كنت بسوق ودهست شخص بالغلط وتوفى", ["traffic", "criminal"]),
            ("خطط شخص مسبقاً لقتل خالد وانتظره ثم قتله عمداً", ["criminal"]),
        ]
        for message, expected in cases:
            data = post_chat(client, message)
            domains = data["route"]["domains"]
            assert_prefix(domains, expected, message)
            if "الطلاق" in message:
                answer = data.get("answer") or ""
                if "تزويد طالبي الخدمة" in answer or "العمال الأردنيين" in answer:
                    fail(f"divorce answer leaked labor corpus: {answer[:500]}")
            print(f"[PASS] route {message!r} -> {domains}")

        english = post_chat(client, "Hello", language="en")
        assert_prefix(english["route"]["domains"], ["conversation"], "English smalltalk")
        print("[PASS] English smalltalk")

        probe = newest_promoted_probe(sb)
        probe_message = f"ما هو النص المتعلق بعبارة: {probe['phrase']}"
        cloud = post_chat(client, probe_message, force_domain=probe["domain"])
        returned_urls = {canonical_url(s.get("source_url")) for s in cloud.get("sources") or []}
        expected_url = canonical_url(probe["source_url"])
        if expected_url not in returned_urls:
            fail(
                "live chat did not retrieve the promoted weekly-sync cloud document; "
                f"expected={expected_url}, got={list(returned_urls)[:8]}"
            )
        print(f"[PASS] weekly-sync cloud retrieval -> {probe['title'][:100]}")

        feedback_case = post_chat(client, "قطعت إشارة حمراء، شو العقوبة؟")
        cid = feedback_case["conversation_id"]
        feedback = client.post(
            f"{BASE_URL}/api/feedback",
            json={
                "conversation_id": cid,
                "rating": "not_helpful",
                "note": f"Automated production QA {qa_tag}: verify grounded self-correction pipeline.",
            },
        )
        if feedback.status_code != 200:
            fail(f"feedback endpoint {feedback.status_code}: {feedback.text[:500]}")
        f = feedback.json()
        if f.get("store") != "supabase" or not f.get("saved"):
            fail(f"feedback was not persisted to Supabase: {f}")
        review = f.get("review") or {}
        if review.get("status") not in {"auto_corrected", "needs_review"}:
            fail(f"unexpected feedback review state: {review}")
        persisted = (
            sb.table("qanoni_feedback_reviews")
            .select("id,status,conversation_id")
            .eq("conversation_id", cid)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not persisted:
            fail("feedback self-correction review was not persisted in Supabase")
        print(f"[PASS] feedback self-correction persisted -> {persisted[0]['status']}")

        print("\nLIVE PRODUCTION QA: PASS")
        return 0
    finally:
        try:
            cleanup(sb)
        finally:
            client.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nLIVE PRODUCTION QA: FAIL\n{type(exc).__name__}: {exc}", file=sys.stderr)
        raise
