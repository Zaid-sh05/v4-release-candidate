"""Legal Corpus Normalization: pre-ingestion quality-report regression tests.

Fixtures use the REAL text sample and REAL filename captured from the live jiacc.gov.jo Penal
Code PDF (see the diagnose-source-discovery.yml run against DIAG_URLS pointed at that PDF) --
not synthetic guesses. That real document is exactly the case that motivated this module: the
filename says year 1961, but Jordan's actual Penal Code (No. 16 of 1960) is dated 1960 in its
own body text.
"""
from __future__ import annotations

from app.legal_document_quality import (
    build_quality_report,
    classify_duplicate_articles,
    compare_metadata,
    extract_body_metadata,
    extract_filename_metadata,
)

# Real opening text from Jordan's 1976 Civil Code (No. 43): its own promulgation notice uses
# "لعام" ("for the year") rather than "لسنة" ("for year") -- a legitimate synonym the extractor
# must also recognize, not a malformed document.
_REAL_CIVIL_CODE_BODY_START = (
    "قانون رقم (43) لعام 1976 القانون المدني\n\n"
    "باب تمهيدي \n\nالفصل الاول \n\nاحكام عامة \n\n"
    "المادة 1- يسمى هذا القانون (القانون المدني لسنة 1976) ويعمل به من 1 /1 / 01977"
)

_REAL_PENAL_CODE_FILENAME = "قانون_العقوبات_وتعديلاته__رقم_16_لسنة_1961-1.pdf"
_REAL_PENAL_CODE_BODY_START = (
    "قانون العقوبات وتعديالته رقم 16 لسنة 1960                    \n\n\n"
    "المادة 1                                                   \n"
    "يسمى ىذا القانكف ) قانكف العقكبات لسنة 1960 (             كيعمؿ بو بعد مركر شير عمى نشره "
    "في الجريدة \nالرسمية .                                                   \n\n"
    "تعديالت المادة :                                               \n"
    "- تـ الغاء كممة ) الشاقة (                حيثما كردت"
)


def test_body_metadata_extracts_correct_law_number_and_year():
    meta = extract_body_metadata(_REAL_PENAL_CODE_BODY_START)
    assert meta.law_number == "16"
    assert meta.year == "1960"
    assert meta.source == "body"


def test_filename_metadata_carries_the_wrong_year_from_the_real_filename():
    # The real captured filename says 1961 -- this is the actual defect this module exists to
    # catch, not a hypothetical: naively trusting the filename would misdate the Penal Code.
    meta = extract_filename_metadata(_REAL_PENAL_CODE_FILENAME)
    assert meta.law_number == "16"
    assert meta.year == "1961"
    assert meta.source == "filename"


def test_body_and_filename_year_conflict_is_flagged():
    body = extract_body_metadata(_REAL_PENAL_CODE_BODY_START)
    filename = extract_filename_metadata(_REAL_PENAL_CODE_FILENAME)
    conflicts = compare_metadata(body, filename)
    assert {"field": "year", "body": "1960", "filename": "1961"} in conflicts
    # law_number agrees on both sides -- must NOT be flagged as a conflict.
    assert not any(c["field"] == "law_number" for c in conflicts)


def test_body_metadata_accepts_liaam_as_a_synonym_for_lisana():
    # "لعام 1976" must extract exactly like "لسنة 1976" would -- these are the same word
    # semantically ("for the year"), and Jordan's real 1976 Civil Code promulgation notice
    # uses the "لعام" phrasing, with the number/year leading the law's own name rather than
    # following it ("قانون رقم (43) لعام 1976 القانون المدني").
    meta = extract_body_metadata(_REAL_CIVIL_CODE_BODY_START)
    assert meta.law_number == "43"
    assert meta.year == "1976"


def test_no_conflict_when_filename_has_no_parseable_metadata():
    body = extract_body_metadata(_REAL_PENAL_CODE_BODY_START)
    filename = extract_filename_metadata("scan_2024_final_v2.pdf")
    assert compare_metadata(body, filename) == []


def test_duplicate_classification_separates_inline_citations_from_real_duplicates():
    substantive_body = "نص مادة قانوني تفصيلي يتضمن أحكاماً كاملة حول الموضوع " * 5
    inline_citation_fragment = "كما تنص المادة 17 على ذلك."
    pieces = [
        ("17", substantive_body),
        ("17", inline_citation_fragment),  # much shorter -> inline citation, not a real duplicate
        ("18", substantive_body),  # unique, no finding expected
    ]
    findings = classify_duplicate_articles(pieces)
    assert set(findings) == {"17"}
    assert findings["17"].verdict == "amendment_note_or_inline_citation"
    assert findings["17"].occurrences == 2


def test_duplicate_classification_flags_two_substantive_bodies_for_review():
    body_a = "نص مادة قانوني تفصيلي طويل يتضمن أحكاماً كاملة حول الموضوع الأول " * 5
    body_b = "نص مادة قانوني تفصيلي طويل يتضمن أحكاماً كاملة حول موضوع مختلف تماماً " * 5
    pieces = [("42", body_a), ("42", body_b)]
    findings = classify_duplicate_articles(pieces)
    assert findings["42"].verdict == "genuine_duplicate_needs_review"


def test_quality_report_composes_correctly_on_real_penal_code_fragment():
    substantive = "نص مادة قانوني تفصيلي يتضمن أحكاماً كاملة حول الموضوع ذي الصلة " * 4
    pieces = [(str(n), substantive) for n in range(1, 11)]  # 1..10, no gaps, no duplicates
    report = build_quality_report(
        text=_REAL_PENAL_CODE_BODY_START,
        pieces=pieces,
        filename=_REAL_PENAL_CODE_FILENAME,
        extraction_method="pypdf+bidi",
        readability_score=1.0,
    )
    assert report.law_number == "16"
    assert report.year == "1960"
    assert report.filename_year == "1961"
    assert len(report.metadata_conflicts) == 1
    assert report.article_count == 10
    assert report.distinct_article_numbers == 10
    assert report.missing_article_numbers == []
    assert report.genuine_duplicate_count == 0
    assert report.extraction_method == "pypdf+bidi"
    # Perfect readability/completeness/no-duplicates but one metadata conflict -> high but not 1.0.
    assert 0.8 < report.confidence_score < 1.0


def test_quality_report_flags_missing_article_numbers():
    substantive = "نص مادة قانوني تفصيلي يتضمن أحكاماً كاملة حول الموضوع ذي الصلة " * 4
    pieces = [(str(n), substantive) for n in (1, 2, 3, 5, 6)]  # gap at 4
    report = build_quality_report(
        text="قانون تجريبي رقم 1 لسنة 2000",
        pieces=pieces,
        filename="test.pdf",
        extraction_method="pypdf",
    )
    assert report.missing_article_numbers == [4]
    assert report.distinct_article_numbers == 5
