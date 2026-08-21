from __future__ import annotations

import re

from .cognition.language_match import contains_fuzzy
from .models import RouteResult
from .router import DOMAIN_LABELS, analyze_query
from .text import normalize_ar


_SMALLTALK_ONLY = {
    "مرحبا", "اهلا", "هلا", "هلو", "هلوو", "هاي", "السلام عليكم",
    "صباح الخير", "مساء الخير", "كيفك", "شو اخبارك", "مين انت", "عرفني عن حالك",
    "شو بتقدر تعمل", "ساعدني", "شكرا", "يسلمو", "تمام", "اوكي",
    "hi", "hello", "hey", "hi there", "hello there", "hey there",
    "good morning", "good evening", "how are you", "hello how are you",
    "who are you", "what can you do", "help me", "thanks", "thank you", "okay", "ok",
}

_TOKEN_EDGE_RE = re.compile(r"^[\s\.,،؛:!?؟()\[\]{}\"'«»]+|[\s\.,،؛:!?؟()\[\]{}\"'«»]+$")
_SHORT_WAW_VERB_STEMS = {
    "اخذ", "اخد", "كسر", "دخل", "ضرب", "قتل", "سرق", "طعن", "مات",
}


def _canonical_token(token: str) -> str:
    """Normalize one token without creating Arabic substring false positives."""
    token = _TOKEN_EDGE_RE.sub("", normalize_ar(token or "")).strip()
    if not token:
        return ""

    for prefix in ("وال", "فال", "بال", "كال", "لل", "ال"):
        if token.startswith(prefix) and len(token) > len(prefix) + 2:
            token = token[len(prefix):]
            break
    return token


def _token_variants(token: str) -> set[str]:
    """Return conservative spoken-Arabic clitic variants for exact routing guards."""
    variants = {token}
    if token.startswith("و"):
        stem = token[1:]
        if len(token) > 4 or stem in _SHORT_WAW_VERB_STEMS:
            variants.add(stem)
    if token.startswith("عال") and len(token) > 5:
        variants.add(token[3:])
    if token.startswith("وعال") and len(token) > 6:
        variants.add(token[4:])
    return {v for v in variants if v}


def _tokens(text: str) -> list[str]:
    return [tok for raw in normalize_ar(text).lower().split() if (tok := _canonical_token(raw))]


def _phrase_tokens(text: str) -> list[str]:
    return _tokens(text)


def _has(text: str, *phrases: str) -> bool:
    """Token/phrase-aware exact Arabic/English matching; never raw substring matching."""
    words = _tokens(text)
    variants = [_token_variants(word) for word in words]
    normalized = " ".join(words)
    for phrase in phrases:
        pwords = _phrase_tokens(phrase)
        if not pwords:
            continue
        if len(pwords) == 1:
            if any(pwords[0] in options for options in variants):
                return True
        else:
            width = len(pwords)
            if any(
                all(pwords[offset] in variants[i + offset] for offset in range(width))
                for i in range(len(words) - width + 1)
            ):
                return True
        p = " ".join(pwords)
        if all(ord(ch) < 128 for ch in p) and f" {p} " in f" {normalized} ":
            return True
    return False


def _smalltalk_only_message(text: str) -> bool:
    """Recognize conversation-only messages by the whole message, never a substring.

    The legacy router historically treated ``hi`` inside ``him`` as a greeting. For a
    legal assistant this is dangerous because a typo-rich English fact pattern may have
    no exact legal lexicon hit and can be discarded before cognition sees it. Whole-message
    matching preserves greetings while guaranteeing substantive narratives reach cognition.
    """
    signature = " ".join(_tokens(text))
    allowed = {" ".join(_tokens(item)) for item in _SMALLTALK_ONLY}
    return bool(signature) and signature in allowed


def _traffic_context(text: str) -> bool:
    """Require actual driving/road conduct; Arabic حادث alone also means 'incident'."""
    terms = (
        "اشارة حمراء", "إشارة حمراء", "حادث سير", "حادث مروري", "مخالفة سير",
        "صدمت", "دهست", "تصادم", "سائق", "قيادة", "بسوق", "يقود", "مسرع",
        "سرعة زائدة", "رادار", "red light", "road accident", "traffic accident",
        "speeding", "driver", "driving",
    )
    return _has(text, *terms) or contains_fuzzy(text, *terms)


def _property_crime_context(text: str) -> bool:
    """Recognize a property-crime fact pattern despite ordinary Arabic/English typos.

    This only chooses the retrieval domain. It never determines the offence, article or
    penalty; those still require cognition plus grounded official legal text.
    """
    theft_terms = ("سرقة", "سرقت", "سرق", "theft", "stole", "stolen")
    taking_terms = ("أخذ", "اخذ", "اخد", "أخذت", "اخذت", "استولى", "took", "stole")
    intrusion_terms = (
        "كسر", "كسر قفل", "كسر الباب", "خلع", "دخل البيت", "دخل المنزل",
        "الدخول إلى منزل", "الدخول الى منزل", "تسلل", "اقتحم", "forced entry",
        "broke into", "broke the lock", "broke the door", "entered the house", "entered the home",
    )
    theft_word = _has(text, *theft_terms) or contains_fuzzy(text, *theft_terms)
    taking = _has(text, *taking_terms) or contains_fuzzy(text, *taking_terms)
    intrusion = _has(text, *intrusion_terms) or contains_fuzzy(text, *intrusion_terms)
    return theft_word or (taking and intrusion)


_DIGITAL_MEDIUM_PREPOSITIONS = ("عبر", "من خلال", "بواسطة", "خلال", "via", "through")
_DIGITAL_MEDIUM_NOUN_TOKENS = {
    "تطبيق", "تطبيقات", "منصه", "منصات", "موقع", "مواقع", "برنامج", "برامج",
    "حساب", "حسابات", "رسائل", "رساله", "شات", "النت", "الانترنت",
    "app", "apps", "platform", "account", "website", "chat", "messages", "online",
}


def _digital_medium_context(text: str) -> bool:
    """Recognize an unnamed digital communication channel by its grammatical construction.

    A Jordanian narrative routinely describes a threat "through an app" or "via a
    platform" without ever naming the product. A fixed platform-name list cannot
    generalize to that, so this looks for the preposition + medium-noun construction
    itself (e.g. "عبر تطبيق", "من خلال حساب") instead of any specific product name.
    """
    words = _tokens(text)
    for prep in _DIGITAL_MEDIUM_PREPOSITIONS:
        prep_tokens = _phrase_tokens(prep)
        width = len(prep_tokens)
        if not width or width > len(words):
            continue
        for i in range(len(words) - width + 1):
            if not all(prep_tokens[o] in _token_variants(words[i + o]) for o in range(width)):
                continue
            for j in range(i + width, min(i + width + 4, len(words))):
                if _DIGITAL_MEDIUM_NOUN_TOKENS & _token_variants(words[j]):
                    return True
    return False


_IMAGE_OR_MEDIA_TERMS = (
    "صور", "صورة", "صوره", "فيديو", "مقطع", "مقاطع", "مواد",
    # Common possessive-suffixed forms ("my/her/your photos"): _has()/contains_fuzzy() match
    # whole tokens and do not strip noun possessive suffixes (only a few verb-object suffixes
    # and prefixes are handled), so "صوري" never reduces to "صور" on its own. Someone describing
    # a threat to expose THEIR OWN photos is an extremely common, natural phrasing.
    "صوري", "صورها", "صورك", "صورتي", "صورته", "صورتها", "صورتك",
    "photos", "photo", "pictures", "images", "video", "videos", "clips",
)
_DISCLOSURE_VERB_TERMS = (
    "نشر", "ينشر", "تنشر", "بنشر", "فضح", "يفضح", "تفضح", "تسريب", "يسرب", "تسرب", "سرب",
    "publish", "leak", "leaked", "expose", "share", "shares",
)
_PRIVATE_CONTENT_QUALIFIER_TERMS = (
    "عارية", "عاريه", "عاري", "فاضحة", "فاضحه", "خاصة", "خاصه", "حميمية", "حميميه",
    "شخصية", "شخصيه", "خصوصية", "خصوصيه",
    "private", "nude", "naked", "intimate", "explicit", "personal",
)


def _image_disclosure_threat_context(text: str) -> bool:
    """Recognize "threatens to expose private images/content" independently of the medium.

    A threat to publish someone's intimate/private photos or material is the legally
    determinative conduct here -- the electronic-extortion family this maps to does not
    turn on which specific app carried the threat, or whether that app is even named at
    all. Gating cyber routing on a closed platform-name list (or even the "unnamed medium"
    grammatical detector, which only recognizes generic nouns like "app"/"platform") misses
    a named-but-unlisted platform (e.g. Telegram) used without a generic noun alongside it,
    and misses cases where no medium is mentioned at all. This checks the conduct directly.
    """
    has_media = _has(text, *_IMAGE_OR_MEDIA_TERMS) or contains_fuzzy(text, *_IMAGE_OR_MEDIA_TERMS)
    if not has_media:
        return False
    has_disclosure_verb = _has(text, *_DISCLOSURE_VERB_TERMS) or contains_fuzzy(text, *_DISCLOSURE_VERB_TERMS)
    has_private_qualifier = _has(text, *_PRIVATE_CONTENT_QUALIFIER_TERMS) or contains_fuzzy(text, *_PRIVATE_CONTENT_QUALIFIER_TERMS)
    return has_disclosure_verb or has_private_qualifier


_PERSONAL_TERMS = (
    "طلاق", "أطلق", "اطلق", "خلع", "نفقة", "حضانة", "زواج", "مطلقة", "طليقي", "محكمة شرعية",
    "اشوف ولادي", "يشوف ولاده", "رؤية الأولاد", "رؤية الاولاد", "مشاهدة الأولاد", "مشاهدة الاولاد",
    "divorce", "custody", "alimony", "visitation",
)
_LABOR_TERMS = ("فصلني", "طردني", "الفصل", "سبب الفصل", "صاحب العمل", "عقد عمل", "الشغل", "راتب", "اجر", "إنذار مكتوب", "انذار مكتوب", "ضعف الاداء", "employer", "fired", "dismissed")
_CYBER_TERMS = (
    "واتساب", "انستغرام", "فيسبوك", "ابتزاز", "ابتزني", "ببتزني", "يبتزني",
    "اختراق", "تهكير", "whatsapp", "online blackmail", "cybercrime",
)
_THREAT_TERMS = (
    "هدد", "هددني", "يهددني", "بهددني", "بتهددني", "تهديد",
    "ابتزاز", "ابتزني", "ببتزني", "يبتزني", "مبتزني",
    # English inflected forms: the fuzzy-match threshold does not bridge "threatened" -> "threat"
    # (SequenceMatcher ratio ~0.75, below the 0.84 floor), so the conjugated forms are listed
    # explicitly -- the same approach already used for the Arabic conjugations above.
    "threat", "threatened", "threatens", "threatening", "blackmail", "blackmailed", "extortion",
)
_VIOLENCE_TERMS = ("قتل", "قتله", "اعتداء", "ضرب", "ضربني", "طعن", "هاجمني", "سلاح", "سرقة", "سرقت", "سرق", "murder", "assault", "theft")
# A distinct family from violence/property crime: unrelated but still domain=criminal offense
# families must not be treated as evidence for each other (e.g. an adultery article is not a
# valid source for a theft query merely because both live under the Penal Code).
_SEXUAL_OFFENSE_TERMS = (
    "زنا", "الزاني", "الزانية", "زانية", "زان", "اغتصاب", "هتك عرض", "هتك العرض",
    "فعل فاحش", "افعال فاحشة", "أفعال فاحشة", "فحشاء",
    "adultery", "rape", "sexual assault", "indecent assault",
)


def _matches_terms(text: str, *phrases: str) -> bool:
    return _has(text, *phrases) or contains_fuzzy(text, *phrases)


def issue_signature(text: str) -> frozenset[str]:
    """Which coarse legal-issue families are lexically present in this text.

    Used for BOTH the active query/case text and a retrieval candidate's own title+excerpt,
    so a candidate can be checked for issue-level compatibility with the query -- not just
    domain membership. Domain membership alone is not enough: an adultery article and a theft
    article are both domain=criminal but describe unrelated offense families, and this is the
    shared vocabulary that lets that specific kind of mismatch be detected as a real conflict
    rather than silently passed through.
    """
    signature: set[str] = set()
    if _property_crime_context(text):
        signature.add("property_crime")
    if _traffic_context(text):
        signature.add("traffic")
    if _matches_terms(text, *_PERSONAL_TERMS):
        signature.add("personal_status")
    if _matches_terms(text, *_LABOR_TERMS):
        signature.add("labor")
    threat_hit = _matches_terms(text, *_THREAT_TERMS)
    if _matches_terms(text, *_CYBER_TERMS) or (threat_hit and (_digital_medium_context(text) or _image_disclosure_threat_context(text))):
        signature.add("cyber_threat")
    if _matches_terms(text, *_VIOLENCE_TERMS):
        signature.add("violence")
    if _matches_terms(text, *_SEXUAL_OFFENSE_TERMS):
        signature.add("sexual_offense")
    return frozenset(signature)


def _set_primary(route: RouteResult, primary: str, extras: list[str] | None = None, confidence: float = 0.9) -> RouteResult:
    domains = [primary]
    for domain in extras or []:
        if domain in DOMAIN_LABELS and domain not in domains:
            domains.append(domain)
    route.primary_domain = primary
    route.domains = domains[:4]
    route.confidence = max(route.confidence, confidence)
    # Defense in depth: a substantive V4 guard must always rescue a false legacy
    # smalltalk classification so cognition and grounded retrieval are allowed to run.
    if route.intent == "smalltalk":
        route.intent = "legal_question"
    return route


def route_query(text: str, requested_language: str = "auto", force_domain: str | None = None) -> RouteResult:
    """Run the legacy lexical router, then apply conservative V4 semantic guards."""
    route = analyze_query(text, requested_language, force_domain)
    if force_domain:
        return route

    if _smalltalk_only_message(text):
        return RouteResult(
            language=route.language,
            intent="smalltalk",
            primary_domain="conversation",
            domains=["conversation"],
            confidence=1.0,
            matched_terms=[],
            article_numbers=route.article_numbers,
            law_numbers=route.law_numbers,
            years=route.years,
            normalized_text=route.normalized_text,
        )

    # If the legacy router found a greeting only because a short token occurred inside
    # another English word (e.g. ``hi`` in ``him``), do not terminate the legal pipeline.
    # Reset to a low-confidence general legal route and let the semantic guards/cognition
    # determine the subject from the full narrative.
    if route.intent == "smalltalk":
        route.intent = "legal_question"
        route.primary_domain = "general"
        route.domains = ["general"]
        route.confidence = 0.32

    appeal = _has(text, "استئناف", "استأنف", "استانف", "تمييز", "طعن", "appeal", "cassation")
    complaint = _has(text, "شكوى", "المدعي العام", "مدعي عام", "نيابة عامة", "ادعاء عام", "complaint", "prosecutor")
    personal_terms = _PERSONAL_TERMS
    labor_terms = _LABOR_TERMS
    cyber_terms = _CYBER_TERMS
    threat_terms = _THREAT_TERMS
    violence_terms = _VIOLENCE_TERMS
    taking_terms = ("أخذ", "اخذ", "اخد", "أخذت", "اخذت", "سرق", "سرقت", "استولى", "took", "stole")
    forced_entry_terms = ("كسر", "كسر قفل", "خلع", "دخل البيت", "دخل المنزل", "تسلل", "اقتحم", "forced entry")
    self_defense_terms = ("دفاع عن نفسي", "دفاعا عن نفسي", "هاجمني", "self defense", "self-defense")
    injury_terms = ("اصابة", "إصابة", "انصاب", "اصيب", "أصيب", "جرح", "المستشفى", "injury", "injured", "hospital")
    death_terms = ("وفاة", "توفي", "توفى", "مات", "قتل", "death", "died", "killed")
    # Decomposed termination concept (verb-class + employment-object-class) alongside the fixed
    # phrases in labor_terms: "أنهت الشركة خدماتي" (ended my services) never says "فصلني"/"طردني"
    # literally, but is the same underlying event as long as a termination verb and an
    # employment object co-occur, regardless of which specific paraphrase or conjugation was used.
    termination_verb_terms = ("فصل", "طرد", "انه", "سرح", "استغنى", "terminated", "let go")
    employment_object_terms = (
        "خدماتي", "خدمتي", "عقدي", "عقد العمل", "وظيفتي", "عملي", "شغلي",
        "my job", "my contract", "my employment",
    )

    # Dialect/typo tolerance must be applied uniformly across every domain guard, not only
    # traffic/property-crime, otherwise personal-status, labor and cyber routing silently
    # loses the same conservative fuzzy matching the rest of the router already relies on.
    def _matches(*phrases: str) -> bool:
        return _has(text, *phrases) or contains_fuzzy(text, *phrases)

    personal = _matches(*personal_terms)
    termination_verb = _matches(*termination_verb_terms)
    employment_object = _matches(*employment_object_terms)
    labor = _matches(*labor_terms) or (termination_verb and employment_object)
    traffic = _traffic_context(text)
    property_crime = _property_crime_context(text)
    threat = _matches(*threat_terms)
    # An unnamed/unseen digital medium ("عبر تطبيق ما بعرفه") plus threat language is the same
    # underlying cyber-extortion narrative as a named platform, so it must route the same way.
    # Likewise, a threat to expose private images/material is itself sufficient regardless of
    # whether any medium is named at all, or is named but not in the fixed platform list.
    cyber = (
        _matches(*cyber_terms)
        or (threat and _digital_medium_context(text))
        or (threat and _image_disclosure_threat_context(text))
    )
    violence = _matches(*violence_terms)
    taking = _matches(*taking_terms)
    forced_entry = _matches(*forced_entry_terms)
    self_defense = _matches(*self_defense_terms)
    injury = _matches(*injury_terms)
    death = _matches(*death_terms)

    if appeal:
        extras: list[str] = []
        if personal:
            extras.append("personal_status")
        if violence or taking:
            extras.append("criminal")
        _set_primary(route, "procedure", extras, 0.94)
    elif complaint:
        _set_primary(route, "procedure", ["criminal"], 0.94)
    elif property_crime:
        _set_primary(route, "criminal", [], 0.94)
    elif traffic:
        extras = []
        if death:
            extras.append("criminal")
        if injury or death:
            extras.append("civil")
        _set_primary(route, "traffic", extras, 0.91)
    elif cyber:
        _set_primary(route, "cyber", ["criminal"] if threat else [], 0.91)
    elif labor:
        _set_primary(route, "labor", [], 0.92)
    elif self_defense or violence or (taking and forced_entry):
        _set_primary(route, "criminal", [], 0.9)
    elif personal:
        _set_primary(route, "personal_status", [], 0.92)

    if personal and _has(text, "اجراءات", "إجراءات", "شو الخطوات", "procedure", "how do i") and not appeal:
        route.intent = "procedure"

    return route


def apply_case_route(route: RouteResult, case, force_domain: str | None = None) -> RouteResult:
    """Fuse grounded cognition with lexical routing without letting either layer dominate blindly."""
    if force_domain:
        return route

    case_domains = [d for d in case.domains if d in DOMAIN_LABELS and d != "general"]
    strong_domains: list[str] = []
    for hypothesis in case.hypotheses:
        if hypothesis.confidence >= 0.75 and hypothesis.domain in DOMAIN_LABELS and hypothesis.domain not in strong_domains:
            strong_domains.append(hypothesis.domain)

    existing = [d for d in route.domains if d not in {"general", "conversation"}]

    semantic_text = route.normalized_text or ""
    property_case = _property_crime_context(semantic_text)
    if property_case and not _traffic_context(semantic_text):
        case_domains = [d for d in case_domains if d != "traffic"]
        strong_domains = [d for d in strong_domains if d != "traffic"]
        existing = [d for d in existing if d != "traffic"]
        if route.primary_domain == "traffic":
            route.primary_domain = "criminal"

    # A pair of grounded material events (taking + entry/breaking) is enough to correct
    # an unrelated lexical domain, even though the legal theft hypotheses intentionally
    # remain below 0.75 until ownership/consent/intent facts are confirmed. This is a
    # routing correction, not a finding that theft is legally established.
    event_types = {getattr(event, "event_type", "") for event in getattr(case, "events", [])}
    material_property_events = "taking" in event_types and bool({"entry", "breaking"} & event_types)
    if material_property_events and "criminal" in case_domains and route.primary_domain not in {"procedure", "traffic", "cyber", "criminal"}:
        route.primary_domain = "criminal"
        existing = [d for d in existing if d != "personal_status"]

    if route.primary_domain in {"general", "conversation"} and case_domains:
        route.primary_domain = case_domains[0]
    elif strong_domains and route.primary_domain not in strong_domains and route.primary_domain not in {"procedure", "traffic", "cyber"}:
        route.primary_domain = strong_domains[0]

    route.domains = list(dict.fromkeys(([route.primary_domain] if route.primary_domain not in {"general", "conversation"} else []) + existing + case_domains))[:4]
    if not route.domains:
        route.domains = ["general"]
    route.confidence = max(route.confidence, 0.74 if case.cognition_provider != "deterministic" else 0.64)

    if route.intent == "legal_question":
        mapped = {"penalty": "penalty", "rights": "rights", "appeal": "appeal", "procedure": "procedure"}.get(case.user_goal)
        if mapped:
            route.intent = mapped
    return route
