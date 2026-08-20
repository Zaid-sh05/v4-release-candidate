"""Regression tests for the reversed-Arabic-reading-order PDF extraction fallback.

Found via a real official document: a Jordanian Civil Code PDF on moj.gov.jo extracts as
~883K characters of genuine, correctly-classified statutory text via pypdf, but every
"المادة" (Article) marker comes out character-reversed as "ةداملا", so the article-boundary
detector finds zero matches and a valid, complete law gets rejected. The fixtures below use
that real captured failure signature, not a synthetic guess.
"""
from __future__ import annotations

from app.arabic_text_quality import looks_like_reversed_arabic_reading_order
from app.sync_engine import choose_pdf_extraction

# Real fragments captured from the moj.gov.jo Civil Code PDF's pypdf extraction output.
_REAL_CORRUPTED_FRAGMENT = """
                                                                                               1976     : ةنسلا
                                                                                     1449         : داوملا ددع
                                                                           01-01-1977 : نايرسلا خيرات
                     .ركذ ام عم ضراعتي   نا ىاع هقفلاو ءاضقلا  رقا امب هاك كلذ يف دشرتسيو4.
                                                                                                    )3 ( ةداملا
                                                                                                    )4 ( ةداملا
                                                                                                    )5 ( ةداملا
"""

_CORRECT_ARABIC_LEGAL_TEXT = """
القانون المدني رقم 43 لسنة 1976

المادة 1
يسمى هذا القانون (القانون المدني لسنة 1976) ويعمل به من تاريخ نشره.

المادة 2
تسري النصوص التشريعية على جميع المسائل التي تتناولها هذه النصوص في لفظها أو في فحواها.

المادة 3
تسري القوانين الجزائية على كل من ارتكب جريمة في المملكة.
"""

_ORDINARY_NON_STATUTORY_TEXT = "مرحباً بكم في موقع وزارة العدل. لمزيد من المعلومات يرجى التواصل معنا."


def test_detects_real_captured_reversed_reading_order():
    assert looks_like_reversed_arabic_reading_order(_REAL_CORRUPTED_FRAGMENT) is True


def test_correct_forward_order_is_not_flagged():
    assert looks_like_reversed_arabic_reading_order(_CORRECT_ARABIC_LEGAL_TEXT) is False


def test_ordinary_text_with_no_article_markers_is_not_flagged():
    assert looks_like_reversed_arabic_reading_order(_ORDINARY_NON_STATUTORY_TEXT) is False


def test_empty_text_is_not_flagged():
    assert looks_like_reversed_arabic_reading_order("") is False


def test_choose_extraction_keeps_primary_when_it_already_has_articles():
    result = choose_pdf_extraction(_CORRECT_ARABIC_LEGAL_TEXT, _REAL_CORRUPTED_FRAGMENT)
    assert result == _CORRECT_ARABIC_LEGAL_TEXT


def test_choose_extraction_keeps_primary_when_not_corrupted_and_no_articles():
    # A genuinely article-free page (not a reading-order failure) must not trigger a fallback.
    result = choose_pdf_extraction(_ORDINARY_NON_STATUTORY_TEXT, _CORRECT_ARABIC_LEGAL_TEXT)
    assert result == _ORDINARY_NON_STATUTORY_TEXT


def test_choose_extraction_switches_to_fallback_when_primary_is_corrupted_and_fallback_works():
    result = choose_pdf_extraction(_REAL_CORRUPTED_FRAGMENT, _CORRECT_ARABIC_LEGAL_TEXT)
    assert result == _CORRECT_ARABIC_LEGAL_TEXT


def test_choose_extraction_keeps_primary_when_fallback_does_not_help_either():
    result = choose_pdf_extraction(_REAL_CORRUPTED_FRAGMENT, _REAL_CORRUPTED_FRAGMENT)
    assert result == _REAL_CORRUPTED_FRAGMENT


def test_choose_extraction_keeps_primary_when_no_fallback_was_attempted():
    result = choose_pdf_extraction(_REAL_CORRUPTED_FRAGMENT, None)
    assert result == _REAL_CORRUPTED_FRAGMENT
