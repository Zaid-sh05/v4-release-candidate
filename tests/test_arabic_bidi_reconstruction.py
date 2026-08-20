"""Regression tests for Unicode BiDi reconstruction of visual-order Arabic PDF text.

Real evidence (see PR history): pypdf AND pdfplumber both read certain official Arabic PDFs'
glyph stream in mirrored (visual) order rather than logical order -- this is not a
pypdf-vs-pdfplumber problem, it is a missing BiDi reordering step. Naive whole-line character
reversal is explicitly forbidden because it also reverses embedded LTR runs (law numbers,
years, article numbers, dates, Latin words), corrupting exactly the tokens legal citations
depend on. These tests assert the release invariants: Arabic restored to readable order, while
every numeric/Latin/date/punctuation token is preserved EXACTLY.
"""
from __future__ import annotations

from unittest.mock import patch

from app.arabic_text_quality import looks_like_reversed_arabic_reading_order, reconstruct_visual_order_arabic
from app.sync_engine import pdf_extraction_report

# Real fragments captured from the moj.gov.jo Civil Code PDF and the jiacc.gov.jo Penal Code
# PDF's pypdf extraction output -- not synthetic guesses.
_REAL_CORRUPTED_ARTICLE_MARKER = "                                                   1 ةداملا"
_REAL_CORRUPTED_PENAL_CODE_HEADER = "                    1960 ةنسل 16 مقر هتلايدعتو تابوقعلا نوناق"


def test_reconstructs_real_captured_article_marker_exactly():
    assert reconstruct_visual_order_arabic(_REAL_CORRUPTED_ARTICLE_MARKER).strip() == "المادة 1"


def test_reconstructs_real_captured_penal_code_header_preserving_numbers():
    result = reconstruct_visual_order_arabic(_REAL_CORRUPTED_PENAL_CODE_HEADER).strip()
    # Law number and year must survive exactly -- this is the whole point (naive reversal
    # turns 16 -> 61 and 1960 -> 0691; a correct reconstruction must not).
    assert "16" in result
    assert "1960" in result
    assert "61" not in result.replace("1960", "").replace("16", "")
    assert result.startswith("قانون العقوبات")


def test_empty_text_is_a_no_op():
    assert reconstruct_visual_order_arabic("") == ""


# Property-style invariant checks: reconstruct(reconstruct(x)) == x for a corrupted-looking
# input built by applying the same transform once (self-consistency / round-trip check),
# covering every category the release invariants require.
_INVARIANT_CASES = [
    "المادة 16",
    "قانون رقم 16 لسنة 1960",
    "المادة 1449",
    "500 دينار",
    "2023/17",
    "Article 18",
    "القانون المدني (Civil Code) لسنة 1976",
    "المادة (3)",
    "المادة 5-أ",
    "المواد 1، 2، 3",
    "صدر بتاريخ 2023/06/15",
    "المادة 100 والمادة 200",
]


def test_numeric_and_latin_tokens_survive_a_full_corrupt_and_reconstruct_round_trip():
    for original in _INVARIANT_CASES:
        corrupted = reconstruct_visual_order_arabic(original)  # simulate a plausible corruption
        restored = reconstruct_visual_order_arabic(corrupted)  # reconstruct should undo it
        assert restored == original, f"round-trip failed for {original!r}: got {restored!r}"


def test_article_numbers_are_never_altered_by_reconstruction():
    # Property B/C/D from the release invariants: numeric sequences, years, and article
    # numbers must be preserved exactly, never partially reversed or digit-shuffled.
    for original in ["المادة 16", "المادة 1449", "المادة 100"]:
        corrupted = reconstruct_visual_order_arabic(original)
        for token in ("16", "1449", "100"):
            if token in original:
                assert token in corrupted, f"{token} lost in corrupted form of {original!r}"


def test_latin_words_survive_untouched():
    original = "Article 18"
    corrupted = reconstruct_visual_order_arabic(original)
    assert "Article" in corrupted
    assert "18" in corrupted


def test_mixed_arabic_english_remains_usable():
    original = "القانون المدني (Civil Code) لسنة 1976"
    corrupted = reconstruct_visual_order_arabic(original)
    restored = reconstruct_visual_order_arabic(corrupted)
    assert "Civil Code" in restored
    assert "1976" in restored


def test_parentheses_are_mirrored_correctly_not_just_reversed():
    original = "المادة (3)"
    corrupted = reconstruct_visual_order_arabic(original)
    # A naive reversal would produce ")3(" (wrong-facing parens); a correct mirror-swap
    # must keep the parens the right way around wherever they land.
    assert corrupted.count("(") == corrupted.count(")") == 1
    open_idx = corrupted.index("(")
    close_idx = corrupted.index(")")
    assert open_idx < close_idx


def test_hyphenated_and_comma_separated_lists_round_trip():
    for original in ["المادة 5-أ", "المواد 1، 2، 3"]:
        corrupted = reconstruct_visual_order_arabic(original)
        restored = reconstruct_visual_order_arabic(corrupted)
        assert restored == original


def test_reconstruction_only_activates_on_strong_corruption_signal():
    # Release invariant H: must not fire on ordinary clean text just because it contains
    # digits or Latin words near Arabic text.
    clean = "المادة 1 يسمى هذا القانون لسنة 1976 (Civil Code)."
    assert looks_like_reversed_arabic_reading_order(clean) is False


# -- pdf_extraction_report() orchestration: BiDi is tried before switching extractors, and a
#    candidate is only ever selected if it strictly improves on the article count so far. --

def _corrupted_multi_article_text(n: int = 4) -> str:
    # Realistic body content between markers (not bare marker lines glued together), matching
    # how real statutory PDFs are structured. reconstruct_visual_order_arabic() applied once
    # to clean text is a faithful stand-in for what a real visual-order extraction produces
    # (proven self-consistent by the round-trip tests above).
    clean = "\n".join(
        f"المادة {i}\nنص المادة رقم {i} يتضمن أحكاماً تفصيلية حول الموضوع ذي الصلة."
        for i in range(1, n + 1)
    )
    return reconstruct_visual_order_arabic(clean)


def test_pdf_extraction_report_prefers_bidi_reconstruction_over_extractor_switch():
    corrupted_text = _corrupted_multi_article_text()
    # pdfplumber would read the same broken glyph order pypdf did (real observed behavior on
    # the jiacc.gov.jo Penal Code PDF) -- it should NOT be preferred over BiDi reconstruction,
    # which does find real article structure here.
    with patch("app.sync_engine.pdf_text", return_value=corrupted_text), \
         patch("app.sync_engine.pdfplumber_text", return_value=corrupted_text):
        result = pdf_extraction_report(b"%PDF-fake")
    assert result["selected_extractor"] == "pypdf+bidi"
    assert result["bidi_article_count"] >= 3
    assert "المادة" in result["selected_text"]


def test_pdf_extraction_report_keeps_primary_when_it_already_has_articles():
    clean_text = "\n".join(f"المادة {n}\nنص المادة رقم {n}." for n in range(1, 5))
    with patch("app.sync_engine.pdf_text", return_value=clean_text):
        result = pdf_extraction_report(b"%PDF-fake")
    assert result["selected_extractor"] == "pypdf"
    assert result["bidi_attempted"] is False
    assert result["fallback_attempted"] is False


def test_pdf_extraction_report_falls_back_to_pdfplumber_when_bidi_does_not_help():
    # Trips the corruption detector (3+ reversed markers) but has no digits anywhere near
    # them (e.g. a corrupted table-of-contents/index page referencing "المادة" in prose) --
    # BiDi reconstruction restores the word order but split_articles() still finds no article
    # NUMBER to anchor on, so it genuinely does not help here, unlike the realistic full-body
    # case in the previous test.
    corrupted_text = "\n".join(f"ةداملا ةروكذملا مقر {i}" for i in ("أ", "ب", "ج"))
    clean_fallback = "\n".join(
        f"المادة {n}\nنص المادة رقم {n} يتضمن أحكاماً تفصيلية حول الموضوع ذي الصلة."
        for n in range(1, 5)
    )
    with patch("app.sync_engine.pdf_text", return_value=corrupted_text), \
         patch("app.sync_engine.pdfplumber_text", return_value=clean_fallback):
        result = pdf_extraction_report(b"%PDF-fake")
    assert result["selected_extractor"] == "pdfplumber"
    assert result["selected_text"] == clean_fallback


def test_pdf_extraction_report_never_downgrades_when_nothing_helps():
    corrupted_text = _REAL_CORRUPTED_PENAL_CODE_HEADER
    with patch("app.sync_engine.pdf_text", return_value=corrupted_text), \
         patch("app.sync_engine.pdfplumber_text", return_value=corrupted_text):
        result = pdf_extraction_report(b"%PDF-fake")
    assert result["selected_extractor"] == "pypdf"
    assert result["selected_text"] == corrupted_text
