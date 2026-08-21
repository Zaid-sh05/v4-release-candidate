"""Generative semantic-generalization benchmark for cyber-extortion narratives.

Per the standing architecture directive: language understanding must be entity-agnostic and
wording-agnostic. A person's name, a platform's name, dialect, word order, and gender/subject
conjugation are attributes of the surface text, not the legal concept. This file does not
memorize fixture sentences; it assembles probes from independent axes (actor name, medium,
threatened material, phrasing) and asserts that the STRUCTURAL routing/issue-spotting outcome
stays invariant across the swap.

Scope, stated honestly rather than implied: this benchmark currently exercises Properties
A (name invariance), B/C (known vs. unseen-named vs. unnamed-generic medium invariance), and
D (formal vs. dialect phrasing). It does NOT yet exercise Properties E-I (payment-vs-demand-only
distinction, sensitive-material-type invariance, full negation/allegation-status invariance) —
the current `Event`/`CaseModel` schema has no structured field separating a "demand" from a
"disclosure threat" as independent facts, so those properties cannot be asserted precisely yet.
That is a real, tracked gap, not a hidden one; closing it is a schema-level follow-up.
"""
from __future__ import annotations

from app.routing_guard import route_query
from app.cognition import CaseCognitionEngine


# Deliberately not reused from any other fixture in this suite, so a future implementer
# cannot make this file pass by special-casing the exact strings used here.
_NAMES = ["سامر", "لينا", "وسيم", "دانا"]

_MEDIA = [
    ("عبر واتساب", "known_platform"),
    ("عبر انستغرام", "known_platform"),
    ("عبر تطبيق زمرة", "unseen_named_platform"),
    ("من خلال منصة نبضة", "unseen_named_platform"),
    ("عبر تطبيق ما حدا بعرفه", "unnamed_generic_medium"),
    ("من خلال حساب ع موقع غريب", "unnamed_generic_medium"),
]

_MATERIAL = ["صوري الخاصة", "محادثاتي الخاصة", "معلوماتي المالية"]

_THREAT_VERBS = ["هددني", "هددتني"]  # gender-varied subject conjugation


def _formal_sentence(name: str, medium: str, verb: str, material: str) -> str:
    return f"{name} {verb} {medium} إنه سينشر {material} إذا لم أحوّل له مبلغاً من المال"


def _dialect_sentence(name: str, medium: str, verb: str, material: str) -> str:
    return f"{name} {verb} {medium} إنه رح ينشر {material} إذا ما حولتله مصاري"


def _generate_cases():
    cases = []
    for i, medium_pair in enumerate(_MEDIA):
        medium, medium_class = medium_pair
        name = _NAMES[i % len(_NAMES)]
        verb = _THREAT_VERBS[i % len(_THREAT_VERBS)]
        material = _MATERIAL[i % len(_MATERIAL)]
        builder = _formal_sentence if i % 2 == 0 else _dialect_sentence
        cases.append((builder(name, medium, verb, material), medium_class))
    return cases


def _issue_codes(message: str) -> set[str]:
    case = CaseCognitionEngine(enable_llm=False).analyze(message)
    return {h.code for h in case.hypotheses}


def test_medium_and_name_invariant_routing_across_generated_cyber_extortion_probes():
    """Property B/C: routing to cyber must not depend on a fixed platform-name whitelist."""
    cases = _generate_cases()
    assert len(cases) >= 6

    failures = []
    for message, medium_class in cases:
        route = route_query(message)
        if not ("cyber" in route.domains or route.primary_domain == "cyber"):
            failures.append((medium_class, message, route.primary_domain))

    pass_rate = 1 - len(failures) / len(cases)
    assert pass_rate >= 0.90, f"generalization regression: {failures}"


def test_medium_and_name_invariant_issue_spotting_across_generated_cyber_extortion_probes():
    """Property A/B/C combined: the same legal issue must be spotted regardless of the actor's
    name or whether the platform is known, an unseen product name, or an unnamed generic medium.
    """
    cases = _generate_cases()

    failures = []
    for message, medium_class in cases:
        codes = _issue_codes(message)
        if "cyber.blackmail_threat" not in codes:
            failures.append((medium_class, message, codes))

    pass_rate = 1 - len(failures) / len(cases)
    assert pass_rate >= 0.90, f"generalization regression: {failures}"


def test_unnamed_generic_medium_alone_is_sufficient_no_named_platform_required():
    # The literal case the architecture directive calls out: an unseen/unnamed product must
    # not break understanding when the grammatical medium construction is present.
    message = "رامي هددني من خلال تطبيق ما بعرفه حدا إنه رح ينشر فيديو خاص فيني إذا ما دفعتله فلوس"
    route = route_query(message)
    assert "cyber" in route.domains or route.primary_domain == "cyber"
    assert "cyber.blackmail_threat" in _issue_codes(message)


def test_no_threat_no_digital_medium_does_not_spuriously_classify_as_cyber_blackmail():
    # Negative control: ordinary account/app vocabulary without a threat must not fire.
    message = "فتحت حساب جديد على تطبيق للتواصل مع أصدقائي بعد ما ضاع القديم"
    assert "cyber.blackmail_threat" not in _issue_codes(message)


def test_gender_varied_subject_conjugation_does_not_break_threat_detection():
    # Property D-adjacent: "هددني" (he threatened me) vs "هددتني" (she threatened me) must
    # resolve to the same routing outcome; this was a real, reproduced gap (see routing_guard
    # digital-medium generalization fix), not a hypothetical.
    male = route_query("سامر هددني عبر تطبيق غير معروف إنه رح ينشر صوري إذا ما دفعتله")
    female = route_query("هبة هددتني عبر تطبيق غير معروف إنها رح تنشر صوري إذا ما دفعتلها")
    assert male.primary_domain == female.primary_domain == "cyber"


def test_employment_termination_paraphrase_is_not_dependent_on_fixed_phrase():
    # A sibling gap in the same class: labor routing required the literal "فصلني"/"طردني", so
    # "أنهت الشركة خدماتي" (the company ended my services) fell through to a different domain
    # despite describing the same underlying event. Decomposed into termination-verb +
    # employment-object components instead of enumerating every paraphrase.
    cases = [
        "أنهت الشركة خدماتي بدون سبب واضح ولا عطتني تعويض",
        "انهى صاحب العمل عقدي فجأة بدون انذار",
        "سرحوني من شغلي من غير سبب",
    ]
    for message in cases:
        route = route_query(message)
        assert route.primary_domain == "labor", (message, route.primary_domain)


def test_unrelated_use_of_the_termination_verb_root_does_not_misfire_into_labor():
    # Negative control: the termination-verb component alone must not be sufficient; it needs
    # an employment-object co-occurring, or an unrelated "انهى" (a judge ending a session) would
    # falsely classify as a labor dispute.
    route = route_query("انهى القاضي الجلسة وقال بيصدر الحكم لاحقا")
    assert route.primary_domain != "labor"


# P0 regression: "عبر تيليجرام" (via Telegram) fell through both the fixed platform-name list
# AND the "unnamed medium" grammatical detector, because Telegram IS named but the token after
# the preposition is a specific product name, not one of the generic nouns ("app"/"platform")
# that detector requires. Real production impact: the query fell all the way through to
# domain=general, which -- before the app.chat._guard_sources issue-compatibility fix -- let
# completely unrelated official documents (Public Security Law, Associations Law) answer a
# cyber-threat scenario. This class of gap is intentionally not closed by adding "تيليجرام" to
# a list: it is closed by recognizing the underlying threatened conduct (image/material
# disclosure) directly, so it also covers platforms never enumerated anywhere in this file.
_NAMED_BUT_UNLISTED_PLATFORMS = ["تيليجرام", "سناب شات", "تيك توك", "ماسنجر", "سيجنال", "تويتر"]


def test_named_but_unlisted_platform_still_routes_to_cyber_via_image_disclosure_threat():
    for platform in _NAMED_BUT_UNLISTED_PLATFORMS:
        message = f"قام رائد بتهديد سوسن عبر {platform} بأنه سوف ينشر لها صور وهي عارية"
        route = route_query(message)
        assert "cyber" in route.domains or route.primary_domain == "cyber", (platform, route.primary_domain)


_DISCLOSURE_MATERIAL_PHRASES = [
    "صور عارية", "صور خاصة", "صور شخصية", "مواد خاصة", "فيديو خاص", "صور فاضحة",
]


def test_private_material_disclosure_threat_routes_to_cyber_regardless_of_wording():
    """Property E (material-type invariance): the threatened material's exact description
    must not gate routing -- "صور عارية" and "مواد خاصة" describe the same underlying
    disclosure-threat conduct even though they share no common substring.
    """
    for material in _DISCLOSURE_MATERIAL_PHRASES:
        message = f"هدد شخص آخر عبر إحدى منصات التواصل بأنه سينشر {material} الخاصة به"
        route = route_query(message)
        assert "cyber" in route.domains or route.primary_domain == "cyber", (material, route.primary_domain)


def test_disclosure_threat_with_and_without_an_explicit_demand_both_route_to_cyber():
    """Property F (demand-vs-no-demand invariance): a conditional demand ("ان لم تستجب
    لطلباته") must not be required for cyber routing -- an unconditional disclosure threat is
    the same underlying conduct as one with a stated condition attached.
    """
    no_demand = route_query("قام رائد بتهديد سوسن عبر تيليجرام بأنه سوف ينشر لها صور وهي عارية")
    non_money_demand = route_query(
        "قام رائد بتهديد سوسن عبر تيليجرام بأنه سوف ينشر لها صور فاضحة ان لم تستجب لطلباته"
    )
    money_demand = route_query(
        "قام رائد بتهديد سوسن عبر تيليجرام بأنه سوف ينشر لها صور فاضحة ان لم تحول له مبلغاً من المال"
    )
    for route, label in ((no_demand, "no_demand"), (non_money_demand, "non_money_demand"), (money_demand, "money_demand")):
        assert "cyber" in route.domains or route.primary_domain == "cyber", (label, route.primary_domain)


def test_unnamed_and_named_disclosure_threats_do_not_infer_unstated_facts():
    """The routing signal must come from the stated conduct only -- it must not require or
    imply payment, sexual conduct, or any concept beyond threat + private-material disclosure.
    """
    route = route_query("قام رائد بتهديد سوسن عبر تيليجرام بأنه سوف ينشر لها صور وهي عارية")
    assert route.primary_domain == "cyber"
    assert "personal_status" not in route.domains  # must not be inferred as a family/marriage matter
