from __future__ import annotations

"""Detect a specific, reusable PDF-extraction failure class: an Arabic statutory PDF whose
text is genuinely present but comes out with mirrored/reversed character order per line (a
known behavior of some PDF text extractors against certain Arabic font/glyph encodings, where
visual left-to-right glyph-stream order is read back literally instead of being reordered to
logical reading order).

Found via a real official document (a Jordanian Civil Code PDF on moj.gov.jo): the extracted
text contained "ةداملا" (reversed) everywhere a real "المادة" (forward, "Article") should have
been, so the article-boundary detector found zero matches despite ~883K characters of genuine,
correctly-classified statutory text being present. A valid law must not be silently rejected
just because one extractor mishandled Arabic reading order -- this module lets a caller detect
that specific failure mode and try an alternate extractor instead of giving up.
"""

# The exact fragment observed in the wild: reversed("المادة") == "ةداملا". Kept as a literal
# (not computed at import time) so a reader can see the failure signature directly.
_ARTICLE_MARKER_FORWARD = "المادة"
_ARTICLE_MARKER_REVERSED = _ARTICLE_MARKER_FORWARD[::-1]


def looks_like_reversed_arabic_reading_order(text: str, *, min_occurrences: int = 3) -> bool:
    """True when the text contains the character-reversed article marker significantly more
    than the correctly-ordered one -- a strong, specific signal of mirrored reading order,
    not just "this document happens to have no articles" (e.g. a cover page or an FAQ).
    """
    if not text:
        return False
    forward = text.count(_ARTICLE_MARKER_FORWARD)
    reversed_count = text.count(_ARTICLE_MARKER_REVERSED)
    return reversed_count >= min_occurrences and reversed_count > forward
