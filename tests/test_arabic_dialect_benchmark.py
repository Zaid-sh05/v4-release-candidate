from __future__ import annotations

"""Permanent, numerically-scored Jordanian Arabic dialect/typo routing benchmark.

Each case is (message, expected_primary_domain). This is deliberately separate from
the existing typo-tolerance tests in test_case_analysis_bilingual.py, which cover
theft/entry scenario fidelity; this file tracks routing accuracy across the full
domain set for clean MSA, Jordanian dialect, typos, missing hamza and mixed
Arabic/English phrasing, so future language-pipeline changes cannot silently
regress dialect coverage without moving this score.
"""

from app.routing_guard import route_query

CASES: tuple[tuple[str, str], ...] = (
    # Clean MSA baseline
    ("ما هي إجراءات الطلاق؟", "personal_status"),
    ("فصلني صاحب العمل بدون إنذار مكتوب", "labor"),
    ("تعرضت لابتزاز على واتساب", "cyber"),
    ("كنت أقود السيارة وصدمت شخصاً", "traffic"),
    ("اقتحم شخص منزلي وسرق أغراضي", "criminal"),
    # Jordanian dialect verb/conjugation variants
    ("بدي أطلق زوجتي، شو الطريقة القانونية؟", "personal_status"),
    ("شو حقوقي اذا فصلوني من الشغل بدون سبب؟", "labor"),
    ("واحد ببتزني على انستغرام وهدد ينشر صوري", "cyber"),
    ("كنت بسوق وما معي رخصة وصدمت واحد وانجرح", "traffic"),
    ("انصاب واحد بحادث سيارة وانا السايق", "traffic"),
    ("معي رخصة بس صدمت شخص بالغلط", "traffic"),
    # Typos / doubled letters / missing hamza
    ("حدا كسسر قفل بيتي وسرق اغراضي", "criminal"),
    ("واحد سررقني من البيت وهرب", "criminal"),
    ("صاحب الشغل طردني بدون سبب وما اعطاني اجري", "labor"),
    ("زوجي بدو ياخذ الاولاد ومانع عني الحضانه", "personal_status"),
    ("زوجي ما بيسمحلي اشوف ولادي", "personal_status"),
    # Mixed Arabic/English
    ("فصلني manager بدون warning", "labor"),
    ("he brok القفل and stol laptop", "criminal"),
    # Clean English baseline
    ("what are the cases of arbitrary dismissal?", "labor"),
    ("he broke into my house and stole my laptop", "criminal"),
    ("i was driving and hit a pedestrian by accident", "traffic"),
)

# Below this pass rate, dialect/typo routing has materially regressed.
MIN_PASS_RATE = 0.85


def test_arabic_dialect_routing_benchmark_meets_pass_rate():
    failures = []
    for message, expected in CASES:
        route = route_query(message, "auto", None)
        if route.primary_domain != expected:
            failures.append((message, expected, route.primary_domain))

    passed = len(CASES) - len(failures)
    rate = passed / len(CASES)
    detail = "\n".join(f"  expected={exp!r} got={got!r} :: {msg!r}" for msg, exp, got in failures)
    assert rate >= MIN_PASS_RATE, (
        f"dialect routing benchmark {passed}/{len(CASES)} ({rate:.0%}) below floor "
        f"{MIN_PASS_RATE:.0%}:\n{detail}"
    )


def test_jordanian_dialect_verb_conjugation_variants_route_correctly():
    # Locks in the fix for a real gap: colloquial conjugations (فصلوني vs فصلني) and verb
    # forms (أطلق vs طلاق) were previously invisible to domain routing because only
    # traffic/property-crime checks used fuzzy matching; every domain guard does now.
    assert route_query("بدي أطلق زوجتي، شو الطريقة القانونية؟", "ar", None).primary_domain == "personal_status"
    assert route_query("شو حقوقي اذا فصلوني من الشغل بدون سبب؟", "ar", None).primary_domain == "labor"


def test_custody_visitation_dialect_phrasing_routes_to_personal_status():
    # "اشوف ولادي" (see my kids) has no lexical overlap with "حضانة"/"طلاق" so fuzzy
    # matching alone can't bridge it; this is a real keyword-list gap, not a typo.
    assert route_query("زوجي ما بيسمحلي اشوف ولادي", "ar", None).primary_domain == "personal_status"
