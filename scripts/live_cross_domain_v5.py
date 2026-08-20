from __future__ import annotations

import os
import sys
from typing import Any

import httpx

BASE_URL = os.getenv("QANONI_BASE_URL", "https://qanoni-alurdoni.up.railway.app").rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TIMEOUT = 45.0

created_conversations: list[str] = []


def fail(message: str) -> None:
    raise AssertionError(message)


def supabase_client():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        fail("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are required")
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


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


def post_chat(
    client: httpx.Client,
    message: str,
    *,
    language: str = "ar",
    conversation_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"message": message, "language": language}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    response = client.post(f"{BASE_URL}/api/chat", json=payload)
    if response.status_code != 200:
        fail(f"chat {response.status_code}: {response.text[:900]}")
    data = response.json()
    cid = data.get("conversation_id")
    if cid:
        created_conversations.append(cid)
    return data


def assert_no_garbled(text: str, label: str) -> None:
    presentation_forms = sum(
        1 for ch in text
        if 0xFB50 <= ord(ch) <= 0xFDFF or 0xFE70 <= ord(ch) <= 0xFEFF
    )
    known_bad = sum(text.count(marker) for marker in ("ᗷ", "ᣢ", "ᡧ", "ᝰ", "ᜮ"))
    if presentation_forms > max(6, len(text) // 20) or known_bad > 1:
        fail(f"{label}: garbled PDF/OCR text leaked into answer: {text[:1200]}")


def require_markers(text: str, markers: list[str], label: str) -> None:
    missing = [marker for marker in markers if marker not in text]
    if missing:
        fail(f"{label}: missing cognition markers {missing}; answer={text[:2200]}")


def assert_case(
    data: dict[str, Any],
    *,
    label: str,
    primary: str,
    markers: list[str],
    forbidden: list[str] | None = None,
) -> None:
    route = data.get("route") or {}
    domains = route.get("domains") or []
    answer = data.get("answer") or ""
    if route.get("primary_domain") != primary:
        fail(f"{label}: expected primary={primary}, got {route}")
    if primary not in domains:
        fail(f"{label}: primary domain missing from domains: {domains}")
    require_markers(answer, markers, label)
    for marker in forbidden or []:
        if marker in answer:
            fail(f"{label}: forbidden leakage/false issue {marker!r}; answer={answer[:1800]}")
    assert_no_garbled(answer, label)
    for source in data.get("sources") or []:
        if source.get("domain") not in domains:
            fail(f"{label}: source domain leak {source.get('domain')} vs {domains}")
        assert_no_garbled(source.get("excerpt") or "", f"{label} source")


def main() -> int:
    sb = supabase_client()
    client = httpx.Client(timeout=TIMEOUT, follow_redirects=True)
    try:
        health = client.get(f"{BASE_URL}/api/health")
        health.raise_for_status()
        h = health.json()
        if h.get("version") != "4.0.0-rc" or h.get("runtime_store") != "supabase":
            fail(f"unexpected production health: {h}")
        print("[PASS] production health")

        labor = post_chat(
            client,
            "أنا موظف بالشركة من سنتين، ما دفعوا راتبي عن آخر شهرين، وكمان بشتغل ساعتين أوفر تايم كل يوم بدون بدل. حلل الحالة قانونياً بدون افتراض النتيجة.",
        )
        assert_case(
            labor,
            label="labor wages + overtime",
            primary="labor",
            markers=["مطالبة محتملة بأجر/راتب غير مدفوع", "مطالبة محتملة ببدل عمل إضافي", "محاور البحث القانوني التالية"],
            forbidden=["سرقة محتملة", "قانون السير"],
        )
        print("[PASS] labor wage/overtime lawyer analysis")

        civil = post_chat(
            client,
            "وقعت عقد توريد ودفعت الدفعة الأولى، لكن المورد لم يسلم البضاعة في الموعد ولم ينفذ الالتزام وسبب لي خسارة. حلل عناصر النزاع التي يجب إثباتها.",
        )
        assert_case(
            civil,
            label="civil contract performance",
            primary="civil",
            markers=["نزاع عقدي حول التنفيذ/الإخلال", "نسخة العقد", "محاور البحث القانوني التالية"],
            forbidden=["قيادة دون رخصة", "سرقة محتملة"],
        )
        print("[PASS] civil contract lawyer analysis")

        family = post_chat(
            client,
            "الأب أخذ الأولاد ومنع الأم من رؤيتهم، ويوجد خلاف على الحضانة والمشاهدة ولا نعرف هل يوجد حكم سابق. حلل المسائل والوقائع الناقصة فقط.",
        )
        assert_case(
            family,
            label="personal status custody",
            primary="personal_status",
            markers=["نزاع محتمل حول الحضانة/المشاهدة", "أعمار الأطفال", "محاور البحث القانوني التالية"],
            forbidden=["سرقة محتملة", "أخذ أو استيلاء على مال/منقول"],
        )
        print("[PASS] custody-taking is not property theft")

        commercial = post_chat(
            client,
            "مدير في شركة وقع عقداً باسم الشركة، لكن الشركاء يقولون إنه غير مفوض بالتوقيع على هذا النوع من العقود. حلل ما الذي يجب فحصه قبل تقرير أثر العقد.",
        )
        assert_case(
            commercial,
            label="company signature authority",
            primary="commercial",
            markers=["مسألة صلاحية تمثيل/توقيع عن الشركة", "المفوضون بالتوقيع", "محاور البحث القانوني التالية"],
            forbidden=["سرقة محتملة", "قانون السير"],
        )
        print("[PASS] company authority lawyer analysis")

        cyber = post_chat(
            client,
            "تم اختراق حسابي على انستغرام وتغيير كلمة السر، وبعدها نشر الشخص بعض محادثاتي وصوري الخاصة من الحساب. حلل المسائل الرقمية والأدلة التي لازم أحافظ عليها.",
        )
        assert_case(
            cyber,
            label="cyber intrusion + private data",
            primary="cyber",
            markers=["دخول/اختراق غير مصرح به", "استعمال/كشف محتوى أو بيانات خاصة", "سجلات الدخول", "محاور البحث القانوني التالية"],
            forbidden=["الزنا", "المادة 282"],
        )
        print("[PASS] cyber intrusion/private-data lawyer analysis")

        procedure = post_chat(
            client,
            "صدر حكم ضدي وأريد الطعن، لكني أقول إنني لم أتبلغ الحكم والخصم يقول إن التبليغ تم على البيت، ولا أعرف هل الحكم وجاهي أم غيابي وهل فاتت مدة الاستئناف. حلل المسائل الإجرائية قبل تحديد أي مدة.",
        )
        assert_case(
            procedure,
            label="service + appeal deadline",
            primary="procedure",
            markers=["حالة/صحة التبليغ", "ميعاد الطعن/الاستئناف", "وصف الحكم", "النص الرسمي النافذ"],
            forbidden=["مدة الاستئناف: 30", "مدة الاستئناف: 15"],
        )
        print("[PASS] service/deadline lawyer analysis without guessed deadline")

        english = post_chat(
            client,
            "My employer has not paid my salary for two months and also requires two extra hours every day without overtime pay. Analyze the issues and missing facts before giving any final legal conclusion.",
            language="en",
        )
        assert_case(
            english,
            label="English labor analysis",
            primary="labor",
            markers=["possible unpaid wage/salary claim", "possible overtime-pay dispute", "Next legal research focus", "Grounding boundary"],
            forbidden=["Traffic law", "possible theft"],
        )
        print("[PASS] English labor lawyer analysis")

        # Same chat, genuinely new case: old labor context must not leak into the new company matter.
        switched = post_chat(
            client,
            "موضوع جديد: أنا شريك في شركة واكتشفت أن حصتي تغيرت في السجل بعد تنازل عن الحصص وأنا أعترض على هذا التنازل. حلل الملف الجديد فقط.",
            conversation_id=labor.get("conversation_id"),
        )
        assert_case(
            switched,
            label="labor -> commercial topic switch",
            primary="commercial",
            markers=["نزاع حصص/أسهم أو ملكية في شركة", "سجل الشركاء/المساهمين"],
            forbidden=["راتب غير مدفوع", "بدل عمل إضافي"],
        )
        if "labor" in ((switched.get("route") or {}).get("domains") or []):
            fail(f"labor -> commercial topic switch leaked prior labor domain: {switched.get('route')}")
        print("[PASS] cross-domain topic switch does not inherit old case")

        print("\nLIVE CROSS-DOMAIN LAWYER V5: PASS")
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
        print(f"\nLIVE CROSS-DOMAIN LAWYER V5: FAIL\n{type(exc).__name__}: {exc}", file=sys.stderr)
        raise
