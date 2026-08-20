from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_ARABIC_DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_TOKEN_RE = re.compile(r"[a-z0-9\u0600-\u06ff]+", re.IGNORECASE)
_REPEAT_RE = re.compile(r"(.)\1{2,}", re.IGNORECASE)
_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06ff]")


def normalize_flexible(text: str) -> str:
    """Normalize Arabic/English user text for tolerant *linguistic* matching.

    This helper is deliberately used only to understand what the user appears to be
    talking about. It must never be used to invent a legal rule, article, penalty or
    deadline. Arabic hamza/yaa/taa-marbuta variants, tatweel, diacritics and noisy
    repeated letters are normalized; English is lower-cased and punctuation is ignored.
    """
    value = unicodedata.normalize("NFKC", text or "").lower()
    value = _ARABIC_DIACRITICS_RE.sub("", value).replace("ـ", "")
    value = (
        value.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ٱ", "ا")
        .replace("ى", "ي")
        .replace("ؤ", "و")
        .replace("ئ", "ي")
        .replace("ة", "ه")
        .replace("’", "'")
        .replace("`", "'")
    )
    # Users often stretch a letter for emphasis (هلووو / hellooo). Keeping at most
    # two copies avoids destroying legitimate doubled English letters.
    value = _REPEAT_RE.sub(r"\1\1", value)
    return " ".join(_TOKEN_RE.findall(value))


def tokens(text: str) -> list[str]:
    return normalize_flexible(text).split()


def _arabic_dedup_variant(token: str) -> str | None:
    if not _ARABIC_CHAR_RE.search(token):
        return None
    # Arabic users frequently double a letter by mistake (كسسر/سررقة). Arabic spelling
    # normally represents gemination with shadda, so exposing a collapsed variant is
    # considerably safer here than doing the same globally for English words.
    collapsed = re.sub(r"(.)\1+", r"\1", token)
    return collapsed if collapsed != token else None


def _token_variants(token: str) -> set[str]:
    variants = {token}
    if not token:
        return variants

    collapsed = _arabic_dedup_variant(token)
    if collapsed:
        variants.add(collapsed)

    # Conservative Arabic clitics: expose matching alternatives rather than mutating
    # the original token. Do not strip a bare leading waw from short words.
    snapshot = list(variants)
    for current in snapshot:
        for prefix in ("وال", "فال", "بال", "كال", "لل", "ال"):
            if current.startswith(prefix) and len(current) >= len(prefix) + 3:
                variants.add(current[len(prefix):])
        if current.startswith("و") and len(current) >= 5:
            variants.add(current[1:])
        if current.startswith("ف") and len(current) >= 5:
            variants.add(current[1:])
    return {v for v in variants if v}


def _ascii_word(value: str) -> bool:
    return bool(value) and all("a" <= ch <= "z" for ch in value)


def _similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0
    # Short Arabic cues remain exact-only because collisions are common. For English,
    # allow a 3↔4 character one-letter typo such as lok/lock when the target cue itself
    # is at least four characters.
    if min(len(left), len(right)) <= 3:
        if _ascii_word(left) and _ascii_word(right) and max(len(left), len(right)) >= 4:
            return SequenceMatcher(None, left, right).ratio()
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _token_matches(actual: str, expected: str, threshold: float) -> bool:
    for a in _token_variants(actual):
        for e in _token_variants(expected):
            if a == e:
                return True
            if min(len(a), len(e)) <= 3 and _ascii_word(a) and _ascii_word(e):
                floor = 0.85
            else:
                floor = max(threshold, 0.88 if min(len(a), len(e)) <= 5 else threshold)
            if _similarity(a, e) >= floor:
                return True
    return False


def contains_fuzzy(text: str, *phrases: str, threshold: float = 0.84) -> bool:
    """Token-aware Arabic/English phrase matching with conservative typo tolerance."""
    actual = tokens(text)
    if not actual:
        return False

    normalized_text = " ".join(actual)
    for phrase in phrases:
        expected = tokens(phrase)
        if not expected:
            continue

        exact_phrase = " ".join(expected)
        if f" {exact_phrase} " in f" {normalized_text} ":
            return True

        if len(expected) == 1:
            if any(_token_matches(token, expected[0], threshold) for token in actual):
                return True
            continue

        width = len(expected)
        if width > len(actual):
            continue
        for start in range(len(actual) - width + 1):
            window = actual[start:start + width]
            if all(_token_matches(a, e, threshold) for a, e in zip(window, expected)):
                return True
    return False


def language_mix(text: str) -> str:
    """Return ar, en, mixed or unknown from the visible user text."""
    normalized = normalize_flexible(text)
    ar = len(re.findall(r"[\u0600-\u06ff]", normalized))
    en = len(re.findall(r"[a-z]", normalized))
    if ar and en:
        return "mixed"
    if ar:
        return "ar"
    if en:
        return "en"
    return "unknown"
