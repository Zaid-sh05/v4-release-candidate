from __future__ import annotations

import os
import sys
from typing import Any

import httpx

BASE_URL = os.getenv("QANONI_BASE_URL", "https://qanoni-alurdoni.up.railway.app").rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TIMEOUT = 40.0

created_conversations: list[str] = []

COMPLEX_TRAFFIC = (
    "خرج شابان ليلا في سيارة والد أحدهما وكان كلاهما لا يحمل رخصة قيادة. أثناء السير ارتطمت السيارة "
    "بالجزيرة الوسطية وتضررت المركبة واصطدمت أيضا بعمود كهربائي. لم يصب الأول بشيء وجرح وجه الثاني "
    "جرحا صغيرا. بعد ذلك عاد الأول مع والده إلى موقع الحادث مع وصول الشرطة، وأخبرهم الأب أنه هو من كان "
    "يقود المركبة، وتم أخذ أقواله وشهد المصاب أن الأب هو السائق. بعد يوم طلب المصاب مبلغا ماليا من الأب "
    "مقابل الشهادة فرفض الأب، ثم ذهب المصاب إلى المركز الأمني وقال إن شهادته الأولى كانت تحت التهديد."
)

BURGLARY = (
    "دخل شخص منزل جاره أثناء غيابه بعد أن كسر قفل الباب، وأخذ حاسوبا و500 دينار. لاحقا عثرت الشرطة "
    "على الحاسوب لديه وظهرت كاميرا مراقبة وجوده قرب المنزل وقت الواقعة."
)

BURGLARY_FOLLOWUP = (
    "الدخول كان من غير إذن، ولم يقع ليلا، والمكان مسكون لكن أهله كانوا خارج المنزل، والمال لصاحب المنزل، "
    "والمالك لم يوافق على أخذه."
)

CYBER_CASE = "تعرضت لابتزاز على فيسبوك وهددني شخص بنشر صوري إذا لم أدفع له مبلغا ماليا، شو أعمل؟"
TRAFFIC_SWITCH = "كنت بسوق وصار حادث وانصاب شخص كان راكب معي وانا لا احمل رخصة، شو وضعي؟"

ENGLISH_COMPLEX = (
    "Two cousins were in a car at night and neither had a driving license. The car crashed into the median, "
    "one passenger was injured and the car was damaged. At the police station the father said he was driving. "
    "The passenger first supported that statement, later changed his statement, claimed he was under threat, "
    "and had asked the father for money in exchange for keeping the testimony."
)


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
        fail(f"chat {response.status_code}: {response.text[:700]}")
    data = response.json()
    cid = data.get("conversation_id")
    if cid:
        created_conversations.append(cid)
    return data


def assert_no_garbled(text: str, label: str) -> None:
    bad_ranges = sum(
        1 for ch in text
        if 0xFB50 <= ord(ch) <= 0xFDFF or 0xFE70 <= ord(ch) <= 0xFEFF
    )
    exotic = sum(1 for ch in text if 0x1400 <= ord(ch) <= 0x2DFF)
    if bad_ranges > max(5, len(text) // 25) or exotic > 4:
        fail(f"{label}: garbled OCR leaked into answer: {text[:1000]}")


def require_contains(text: str, markers: list[str], label: str) -> None:
    missing = [marker for marker in markers if marker not in text]
    if missing:
        fail(f"{label}: missing {missing}; answer={text[:1800]}")


def assert_complex_traffic(data: dict[str, Any]) -> None:
    route = data.get("route") or {}
    domains = route.get("domains") or []
    answer = data.get("answer") or ""
    if route.get("primary_domain") != "traffic":
        fail(f"complex traffic: primary domain must be traffic, got {route}")
    expected = ["traffic", "procedure", "criminal", "civil"]
    if domains[:4] != expected:
        fail(f"complex traffic: expected domains {expected}, got {domains}")
    require_contains(
        answer,
        [
            "مرحلة تحقيق/استدلال",
            "قيادة دون رخصة",
            "تعارض أو تغير في الأقوال",
            "ادعاء إكراه/تهديد",
            "طلب منفعة مالية",
            "محاور البحث القانوني التالية",
            "حدود الاستناد",
        ],
        "complex traffic",
    )
    forbidden = [
        "سرقة محتملة",
        "أخذ أو استيلاء على مال/منقول",
        "ايضا — شخص",
        "أيضا — شخص",
        "اقواله — شخص",
        "أقواله — شخص",
        "شهادته — شخص",
        "لاخبار — شخص",
    ]
    for marker in forbidden:
        if marker in answer:
            fail(f"complex traffic: forbidden false interpretation {marker!r}; answer={answer[:1800]}")
    assert_no_garbled(answer, "complex traffic")
    for source in data.get("sources") or []:
        if source.get("domain") not in domains:
            fail(f"complex traffic: cross-domain source {source.get('domain')} vs {domains}")
        assert_no_garbled(source.get("excerpt") or "", "complex traffic source")


def assert_followup_keeps_case(first: dict[str, Any], second: dict[str, Any]) -> None:
    if first.get("conversation_id") != second.get("conversation_id"):
        fail("burglary follow-up did not stay in the same conversation")
    route = second.get("route") or {}
    answer = second.get("answer") or ""
    if route.get("primary_domain") != "criminal":
        fail(f"burglary follow-up lost criminal case context: {route}")
    if "القانون المدني" in answer and "القانون الجزائي" not in answer:
        fail(f"burglary follow-up drifted to civil: {answer[:1400]}")
    if "المادة الرسمية المسترجعة غير كافية" in answer and route.get("primary_domain") == "civil":
        fail(f"burglary follow-up was treated as a new civil query: {answer[:1400]}")
    assert_no_garbled(answer, "burglary follow-up")


def assert_topic_switch(first: dict[str, Any], second: dict[str, Any]) -> None:
    if first.get("conversation_id") != second.get("conversation_id"):
        fail("topic switch should remain in the same chat conversation id")
    domains = (second.get("route") or {}).get("domains") or []
    if not domains or domains[0] != "traffic":
        fail(f"cyber -> traffic topic switch inherited old case: {domains}")
    if "cyber" in domains:
        fail(f"cyber context leaked into new traffic case: {domains}")
    answer = second.get("answer") or ""
    if "فيسبوك" in answer or "الجرائم الإلكترونية" in answer:
        fail(f"old cyber case leaked into traffic answer: {answer[:1400]}")
    assert_no_garbled(answer, "traffic topic switch")


def assert_cyber(data: dict[str, Any]) -> None:
    domains = (data.get("route") or {}).get("domains") or []
    answer = data.get("answer") or ""
    if domains[:2] != ["cyber", "criminal"]:
        fail(f"cyber blackmail route wrong: {domains}")
    if "المادة 282" in answer or "الزنا" in answer:
        fail(f"cyber case leaked unrelated penal/adultery answer: {answer[:1400]}")
    for source in data.get("sources") or []:
        if source.get("domain") not in domains:
            fail(f"cyber source leak: {source}")
    assert_no_garbled(answer, "cyber blackmail")


def assert_english_complex(data: dict[str, Any]) -> None:
    route = data.get("route") or {}
    answer = data.get("answer") or ""
    if route.get("primary_domain") != "traffic":
        fail(f"English complex route wrong: {route}")
    lower = answer.lower()
    required = [
        "unlicensed driving",
        "conflicting or changed statements",
        "threat or coercion",
        "grounding boundary",
    ]
    missing = [marker for marker in required if marker not in lower]
    if missing:
        fail(f"English complex missing {missing}: {answer[:1800]}")
    damaged_words = [" hef ", " aking ", " he main legal", " importan "]
    padded = f" {lower} "
    for marker in damaged_words:
        if marker in padded:
            fail(f"English text post-processing corruption returned: {marker!r}: {answer[:1200]}")


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

        complex_case = post_chat(client, COMPLEX_TRAFFIC)
        assert_complex_traffic(complex_case)
        print("[PASS] complex traffic / statements / money-demand case")

        burglary = post_chat(client, BURGLARY)
        burglary_followup = post_chat(
            client,
            BURGLARY_FOLLOWUP,
            conversation_id=burglary.get("conversation_id"),
        )
        assert_followup_keeps_case(burglary, burglary_followup)
        print("[PASS] clarification facts remain attached to burglary case")

        cyber = post_chat(client, CYBER_CASE)
        assert_cyber(cyber)
        switched = post_chat(client, TRAFFIC_SWITCH, conversation_id=cyber.get("conversation_id"))
        assert_topic_switch(cyber, switched)
        print("[PASS] same chat can start a new traffic case without cyber leakage")

        english = post_chat(client, ENGLISH_COMPLEX, language="en")
        assert_english_complex(english)
        print("[PASS] English complex lawyer analysis")

        print("\nLIVE LAWYER TORTURE: PASS")
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
        print(f"\nLIVE LAWYER TORTURE: FAIL\n{type(exc).__name__}: {exc}", file=sys.stderr)
        raise
