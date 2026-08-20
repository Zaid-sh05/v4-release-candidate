from __future__ import annotations

import re
import unicodedata

"""Detect and repair a specific, reusable PDF-extraction failure class: an Arabic statutory
PDF whose text is genuinely present but comes out with mirrored/reversed character order per
line (a known behavior of some PDF text extractors against certain Arabic font/glyph
encodings, where visual left-to-right glyph-stream order is read back literally instead of
being reordered to logical reading order -- i.e. no Unicode BiDi reordering was applied).

Found via a real official document (a Jordanian Civil Code PDF on moj.gov.jo): the extracted
text contained "ةداملا" (reversed) everywhere a real "المادة" (forward, "Article") should have
been, so the article-boundary detector found zero matches despite ~883K characters of genuine,
correctly-classified statutory text being present. A valid law must not be silently rejected
just because one extractor mishandled Arabic reading order.

This is NOT simply a pypdf-vs-pdfplumber problem: both extractors read the same broken glyph
order literally (confirmed on a real Penal Code PDF from jiacc.gov.jo -- neither produced a
single forward "المادة" match). The real fix is reconstructing logical order from visual order,
which is what reconstruct_visual_order_arabic() below does.

CRITICAL: naive whole-line character reversal is NOT this reconstruction. It restores Arabic
word order correctly, but also reverses every embedded LTR run (digit sequences, Latin words),
corrupting exactly the tokens a legal citation depends on: 16 -> 61, 1960 -> 0691. This module
reverses each line, then finds every run of non-Arabic-letter, non-whitespace characters that
contains a digit or Latin letter (i.e. real LTR content -- law numbers, years, article numbers,
Latin words, slash-separated dates like 2023/17) and re-reverses just that run's internal
character order to undo the unwanted flip, plus swaps mirrored bracket pairs. Bracket-swap
example: "(2023)" naively reverses to ")3202(" -- both digit order and parenthesis facing are
wrong; the fix restores "(2023)".

Known, honestly-documented residual limitation: Arabic's one mandatory ligature, Lam+Alef
(لا/لأ/لإ/لآ), is visually indistinguishable in the corrupted text from a reversed alef-lam
definite-article prefix (ال, extremely common) -- both appear as the same two-character
substring, but need opposite treatment (kept as-is vs re-reversed). Protecting one breaks the
far more common other case, so this is left unprotected: a small fraction of words containing
an internal (non-word-initial) لا ligature come out with that one letter pair transposed (e.g.
"وتعديلاته" -> "وتعديالته"). This does not affect any numeric, Latin, date, or citation token --
the properties that matter for legal-citation accuracy (article numbers, law numbers, years)
are exact, which is what the regression tests check.
"""

# The exact fragment observed in the wild: reversed("المادة") == "ةداملا". Kept as a literal
# (not computed at import time) so a reader can see the failure signature directly.
_ARTICLE_MARKER_FORWARD = "المادة"
_ARTICLE_MARKER_REVERSED = _ARTICLE_MARKER_FORWARD[::-1]

_MIRROR_PAIRS = {"(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{"}
# Excludes whitespace (so spaces never get swept into a reversed token) AND the mirrored
# bracket characters (handled separately by _MIRROR_PAIRS) -- a run like "(2023)" must not
# have its parens re-reversed by the digit-run fix after the mirror-swap already oriented
# them correctly, e.g. re-including "(" would flip "(2023)" back to ")2023(".
_NON_ARABIC_RUN_RE = re.compile(r"[^؀-ۿ\s()\[\]{}]+")


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


def _has_ltr_content(run: str) -> bool:
    return any(
        ch.isdigit() or (ch.isalpha() and unicodedata.bidirectional(ch) in ("L", "EN", "AN"))
        for ch in run
    )


def _reconstruct_line(line: str) -> str:
    reversed_line = line[::-1]
    reversed_line = "".join(_MIRROR_PAIRS.get(ch, ch) for ch in reversed_line)

    def _fix_run(match: re.Match) -> str:
        run = match.group(0)
        return run[::-1] if _has_ltr_content(run) else run

    return _NON_ARABIC_RUN_RE.sub(_fix_run, reversed_line)


def reconstruct_visual_order_arabic(text: str) -> str:
    """Reconstruct logical-order Arabic from visual-order (mirrored) extracted text, line by
    line, preserving embedded LTR runs (digits, Latin, dates) and mirroring bracket pairs.
    See the module docstring for the algorithm and its one documented residual limitation.

    This is a pure, unconditional transform -- it does not check whether the input actually
    looks corrupted (that is looks_like_reversed_arabic_reading_order()'s job). The release
    invariant "reconstruction only activates on strong corruption evidence, existing clean
    PDFs must not be modified unnecessarily" is enforced by the caller (see
    app.sync_engine.pdf_extraction_report()), which only invokes this after checking that
    detector -- not by this function refusing to run on already-clean text.
    """
    if not text:
        return text
    return "\n".join(_reconstruct_line(line) for line in text.split("\n"))
