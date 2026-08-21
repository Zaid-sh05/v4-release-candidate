"""P0 regression: retrieved sources from an unrelated legal-issue family must never survive to
answer generation just because they share a broad domain label (or land in the miscellaneous
domain=general bucket) with the active case.

Two independent production failures motivated this file:

1. A theft/burglary case ("احمد دخل منزل خالد ليلا وكسر نافذة السيارة وسرقها"), followed by the
   short confirming message "سرق سيارة", surfaced Penal Code Article 282 (adultery) as the cited
   legal basis. Root cause: app.repository.search()'s "law_anchor"/"base" scoring bonuses matched
   on the LAW'S NAME being present in a candidate's title -- but every individually segmented
   article of a canonical law shares that law's name in its title by construction ("<law name>
   — المادة N"), so every single article became an automatic high-scoring "anchor" regardless of
   actual content relevance.

2. A cyber-threat scenario ("threatened via Telegram to publish private/nude images") surfaced
   Public Security Law and Associations Law content. Root cause: the router failed to classify
   the message (Telegram is a named-but-unlisted platform, not covered by the fixed platform
   list or the "unnamed generic medium" grammatical detector), leaving route.primary_domain as
   'general' -- and 'general' is a genuine miscellaneous bucket in this corpus (it is literally
   where Public Security Law and Associations Law are classified), which no gate in app.chat's
   _guard_sources rejected once a source's domain happened to be in route.domains.

Neither fix hardcodes the specific statute/article that leaked in production -- see
app/repository.py's law_anchor fix (gated on "does this candidate carry a specific article
number", not on any particular law) and app/chat.py's _source_issue_compatible (gated on the
coarse issue-family vocabulary in app.routing_guard.issue_signature(), not on any particular
title or domain name beyond the generic 'general' bucket rule).
"""
from __future__ import annotations

from app.chat_v4 import handle_chat
from app.models import ChatRequest
from app.repository import repository
from app.routing_guard import issue_signature


# ---------------------------------------------------------------------------
# Unit-level: the retrieval scoring fix (app.repository.search)
# ---------------------------------------------------------------------------

def test_unrelated_offense_article_never_appears_for_bare_theft_queries():
    # The exact reported production phrase, and near variants. A raw two-word query is not
    # expected to rank the ideal article at the top on lexical search alone (the full pipeline
    # escalates weak queries through cognition-driven adaptive search for that) -- what must
    # never happen at ANY layer is an unrelated offense article being treated as compatible.
    for query in ('سرق سيارة', 'سرق مركبة', 'اخذ سيارة بدون اذن'):
        results = repository.search(query, ['criminal'], 8)
        for r in results:
            hay = (r.title or '') + ' ' + (r.excerpt or '')
            assert 'الزاني' not in hay and 'الزانية' not in hay, (query, r.title)


def test_real_theft_article_is_retrievable_with_a_well_formed_query():
    # A generic whole-document "this is the right general law" reference entry legitimately
    # naming the correct statute is not the regression this fix targets (it is not topically
    # wrong, merely less specific) -- what matters is that the real article is still findable
    # at all, proving the law_anchor fix suppressed the false per-article anchor bonus without
    # breaking retrieval for the article that is actually correct.
    results = repository.search('سرقة مركبة', ['criminal'], 8)
    assert any(r.article == '407' for r in results), [r.article for r in results]


def test_whole_document_anchor_still_survives_with_a_poor_text_layer():
    # The mechanism this guards against being over-corrected: a whole-document reference entry
    # (no article number) representing a law whose PDF text layer is unusable must still be able
    # to serve as a general legal-basis anchor. Article 282 above must be rejected specifically
    # because it is a normally-segmented articled chunk, not because whole-document anchors were
    # disabled outright.
    results = repository.search('قانون الجرائم الالكترونية', ['cyber'], 8)
    assert any(not r.article for r in results), 'a whole-document anchor should still be retrievable'


# ---------------------------------------------------------------------------
# Unit-level: the issue-signature vocabulary itself
# ---------------------------------------------------------------------------

def test_issue_signature_distinguishes_property_crime_from_sexual_offense():
    theft_sig = issue_signature('احمد دخل منزل خالد ليلا وكسر نافذة السيارة وسرقها')
    adultery_sig = issue_signature('يعاقب الزاني والزانية برضاهما بالحبس من سنة الى ثلاث سنوات')
    assert 'property_crime' in theft_sig
    assert 'sexual_offense' in adultery_sig
    assert not (theft_sig & adultery_sig)


def test_issue_signature_recognizes_cyber_threat_from_telegram_image_disclosure():
    sig = issue_signature('قام رائد بتهديد سوسن عبر تيليجرام بأنه سوف ينشر لها صور وهي عارية')
    assert 'cyber_threat' in sig


def test_issue_signature_is_empty_for_ordinary_unrelated_text():
    # Silence (no tracked family detected) must not itself be treated as a conflict signal --
    # covered structurally by _source_issue_compatible's "empty source signature -> keep" rule,
    # asserted here at the signature level so a future change to the vocabulary that starts
    # over-firing on generic text is caught early.
    assert issue_signature('ما هي مواعيد العمل الرسمية في الوزارة؟') == frozenset()


# ---------------------------------------------------------------------------
# Integration-level: the full production path (both original P0 cases)
# ---------------------------------------------------------------------------

_THEFT_NARRATIVE = 'احمد دخل منزل خالد ليلا وكسر نافذة السيارة وسرقها'
_THEFT_FOLLOWUPS = [
    'سرق سيارة', 'سرق مركبة', 'اخذ سيارة بدون إذن', 'كسر قزاز السيارة وسرقها',
    'سرق سيارة بالليل', 'دخل الكراج وسرق المركبة', 'stole the car after breaking the window',
]


def test_theft_case_family_never_surfaces_a_sexual_offense_article():
    first = handle_chat(ChatRequest(message=_THEFT_NARRATIVE, language='ar'))
    for message in _THEFT_FOLLOWUPS:
        resp = handle_chat(ChatRequest(message=message, language='ar', conversation_id=first.conversation_id))
        for source in resp.sources:
            hay = (source.title or '') + ' ' + (source.excerpt or '')
            assert 'الزاني' not in hay and 'الزانية' not in hay, (message, source.title)


_CYBER_THREAT_VARIANTS = [
    'قام رائد بتهديد سوسن عبر تيليجرام بأنه سوف ينشر لها صور وهي عارية',
    'قام رائد بتهديد سوسن عبر تيليجرام بأنه سوف ينشر لها صور فاضحة ان لم تستجب لطلباته',
    'هددني حدا على سناب شات إنه رح ينشر صوري الشخصية',
    'threatened me on an unknown app to leak my private photos',
]

# Titles that must never appear as cited evidence for a cyber-threat case -- these are the
# exact families the production incident surfaced, kept here as permanent hard negatives, but
# the gate itself (domain='general' rejection + issue-family mismatch) is general-purpose and
# does not hardcode any of these specific titles.
_FORBIDDEN_UNRELATED_TITLE_FRAGMENTS = ('الامن العام', 'الجمعيات')


def test_cyber_threat_case_never_cites_unrelated_administrative_law():
    for message in _CYBER_THREAT_VARIANTS:
        resp = handle_chat(ChatRequest(message=message, language='ar'))
        for source in resp.sources:
            for fragment in _FORBIDDEN_UNRELATED_TITLE_FRAGMENTS:
                assert fragment not in (source.title or ''), (message, source.title)
        for fragment in _FORBIDDEN_UNRELATED_TITLE_FRAGMENTS:
            assert fragment not in resp.answer, (message, resp.answer)


def test_cyber_threat_case_routes_away_from_the_general_bucket():
    for message in _CYBER_THREAT_VARIANTS:
        resp = handle_chat(ChatRequest(message=message, language='ar'))
        assert resp.route.primary_domain != 'general', (message, resp.route.primary_domain)
