from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_ARABIC_DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_TOKEN_RE = re.compile(r"[a-z0-9\u0600-\u06ff]+", re.IGNORECASE)
_REPEAT_RE = re.compile(r"(.)\1{2,}", re.IGNORECASE)


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


def _token_variants(token: str) -> set[str]:
    variants = {token}
    if not token:
        return variants

    # Conservative Arabic clitics: expose matching alternatives rather than mutating
    # the original token. Do not strip a bare leading waw from short words.
    for prefix in ("وال", "فال", "بال", "كال", "لل", "ال"):
        if token.startswith(prefix) and len(token) >= len(prefix) + 3:
            variants.add(token[len(prefix):])
    if token.startswith("و") and len(token) >= 5:
        variants.add(token[1:])
    if token.startswith("ف") and len(token) >= 5:
        variants.add(token[1:])
    return {v for v in variants if v}


def _similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0
    # Very short legal cues are too collision-prone for fuzzy matching.
    if min(len(left), len(right)) <= 3:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _token_matches(actual: str, expected: str, threshold: float) -> bool:
    for a in _token_variants(actual):
        for e in _token_variants(expected):
            if a == e:
                return True
            # Length-sensitive floor. A one-letter typo in a 4-6 letter word should
            # usually pass, while loose similarities in short Arabic words should not.
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
