from __future__ import annotations

from dataclasses import dataclass

from .text import infer_legal_title

"""Legal Corpus Normalization: pre-ingestion quality reporting for a single extracted document.

Read-only / analysis-only. Nothing here writes to Supabase or the local repository -- it takes
already-extracted text (e.g. from app.sync_engine.pdf_extraction_report()'s selected_text) plus
the raw source filename, and produces a structured report a human or a promotion gate can review
before a document is ever ingested.

Two problems this module exists to catch before promotion:

1. Filenames are not authoritative legal metadata. A real captured example: the official
   jiacc.gov.jo Penal Code PDF is named ".../قانون_العقوبات_وتعديلاته__رقم_16_لسنة_1961-1.pdf"
   (year 1961), but the law's own body text reads "قانون العقوبات وتعديلاته رقم 16 لسنة 1960"
   (year 1960 -- Jordan's actual Penal Code, No. 16 of 1960). app.text.pretty_title() prefers a
   filename-derived title whenever the filename "looks like" a real Arabic legal title (has
   Arabic characters, isn't absurdly long), which means this specific wrong year would silently
   become the stored title. The body text is ground truth; the filename is a weak, sometimes
   wrong, hint that must be cross-checked, not trusted.

2. split_articles()'s heading regex matches "المادة N" wherever it appears preceded by
   whitespace/newline -- including an inline citation inside another article's body (e.g. "...
   كما تنص المادة 17 على ..."), not only real article headings. That produces a second, usually
   much shorter, chunk under an already-used article number. A real duplicate full article and a
   short inline-citation fragment need different handling: the former is a genuine data-quality
   problem worth investigating before ingestion, the latter is expected regex noise. This module
   classifies each case by relative body length rather than silently merging or dropping either.
"""

_AR_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')


def _to_ascii_digits(s: str) -> str:
    return s.translate(_AR_DIGITS)


def _extract_number_year(title: str | None) -> tuple[str | None, str | None]:
    """Pull (law_number, year) out of a title string shaped like '... رقم 16 لسنة 1960'
    ('لعام' is an accepted synonym for 'لسنة' -- e.g. the Civil Code's own promulgation
    notice reads 'رقم (43) لعام 1976')."""
    if not title:
        return None, None
    import re

    m = re.search(r'رقم\s*\(?\s*([0-9٠-٩]{1,4})\s*\)?\s+(?:لسنة|لعام)\s*([0-9٠-٩]{4})', title)
    if not m:
        return None, None
    return _to_ascii_digits(m.group(1)), _to_ascii_digits(m.group(2))


@dataclass(frozen=True)
class DocumentMetadata:
    title: str | None
    law_number: str | None
    year: str | None
    source: str  # 'body' | 'filename'


def extract_body_metadata(text: str) -> DocumentMetadata:
    """Ground-truth metadata: parsed from the statutory body text itself, never the filename."""
    title = infer_legal_title(text)
    law_number, year = _extract_number_year(title)
    return DocumentMetadata(title=title, law_number=law_number, year=year, source='body')


def extract_filename_metadata(filename: str) -> DocumentMetadata:
    """Weak-hint metadata: parsed from the filename/URL stem only. Never treated as authoritative."""
    import re
    from urllib.parse import unquote, urlparse

    raw = unquote((filename or '').strip())
    if '/' in raw:
        raw = urlparse(raw).path.rsplit('/', 1)[-1]
    stem = re.sub(r'\.(pdf|docx|doc|html?)$', '', raw, flags=re.I)
    stem = re.sub(r'\s+', ' ', stem.replace('_', ' ').replace('-', ' ')).strip()
    law_number, year = _extract_number_year(stem)
    title = stem if (law_number or year) else None
    return DocumentMetadata(title=title, law_number=law_number, year=year, source='filename')


def compare_metadata(body: DocumentMetadata, filename: DocumentMetadata) -> list[dict]:
    """Flag conflicts between body-derived (authoritative) and filename-derived (hint) metadata.

    Only flags fields present on both sides -- a filename that simply lacks a year is not a
    conflict, it is missing information. A conflict means the two sources actively disagree.
    """
    conflicts = []
    for field_name in ('law_number', 'year'):
        body_value = getattr(body, field_name)
        filename_value = getattr(filename, field_name)
        if body_value and filename_value and body_value != filename_value:
            conflicts.append({'field': field_name, 'body': body_value, 'filename': filename_value})
    return conflicts


@dataclass(frozen=True)
class DuplicateArticleFinding:
    occurrences: int
    body_lengths: list[int]
    verdict: str  # 'amendment_note_or_inline_citation' | 'genuine_duplicate_needs_review'


def classify_duplicate_articles(pieces: list[tuple[str | None, str]], *, short_ratio: float = 0.35) -> dict[str, DuplicateArticleFinding]:
    """For each article number appearing more than once, decide whether the extra occurrence(s)
    look like real duplicate article bodies or short inline citations / amendment-note noise.

    Heuristic: within one article number's occurrences, any body shorter than `short_ratio` of
    the longest body for that same number is almost certainly an inline citation caught by
    split_articles()'s heading regex, not a second real article. If two or more occurrences are
    each at least `short_ratio` of the longest, that is flagged for manual review rather than
    silently resolved -- this module reports, it does not decide ingestion policy.
    """
    by_number: dict[str, list[str]] = {}
    for number, body in pieces:
        if number is None:
            continue
        by_number.setdefault(number, []).append(body or '')

    findings: dict[str, DuplicateArticleFinding] = {}
    for number, bodies in by_number.items():
        if len(bodies) < 2:
            continue
        lengths = [len(b) for b in bodies]
        longest = max(lengths)
        substantive_count = sum(1 for length in lengths if longest and length >= longest * short_ratio)
        verdict = 'genuine_duplicate_needs_review' if substantive_count >= 2 else 'amendment_note_or_inline_citation'
        findings[number] = DuplicateArticleFinding(occurrences=len(bodies), body_lengths=lengths, verdict=verdict)
    return findings


@dataclass(frozen=True)
class LegalDocumentQualityReport:
    law_title: str | None
    law_number: str | None
    year: str | None
    filename_title: str | None
    filename_law_number: str | None
    filename_year: str | None
    metadata_conflicts: list[dict]
    article_count: int
    distinct_article_numbers: int
    missing_article_numbers: list[int]
    duplicate_articles: dict[str, DuplicateArticleFinding]
    genuine_duplicate_count: int
    extraction_method: str
    readability_score: float | None
    confidence_score: float


def _missing_numbers(distinct: set[int]) -> list[int]:
    if not distinct:
        return []
    lo, hi = min(distinct), max(distinct)
    return [n for n in range(lo, hi + 1) if n not in distinct]


def build_quality_report(
    *,
    text: str,
    pieces: list[tuple[str | None, str]],
    filename: str,
    extraction_method: str,
    readability_score: float | None = None,
) -> LegalDocumentQualityReport:
    """Compose the full pre-ingestion quality report for one already-extracted document.

    Pure/read-only: takes already-produced extraction output (text, split_articles() pieces,
    which extractor path was selected) and never fetches, writes, or promotes anything itself.
    """
    body_meta = extract_body_metadata(text)
    filename_meta = extract_filename_metadata(filename)
    conflicts = compare_metadata(body_meta, filename_meta)

    numbers: list[int] = []
    for number, _ in pieces:
        if number is None:
            continue
        try:
            numbers.append(int(number))
        except ValueError:
            continue
    distinct = set(numbers)
    missing = _missing_numbers(distinct)
    duplicates = classify_duplicate_articles(pieces)
    genuine_duplicates = sum(1 for f in duplicates.values() if f.verdict == 'genuine_duplicate_needs_review')

    # Confidence score: a simple, inspectable composite -- not a learned metric. Each component
    # is 0..1 and independently meaningful; a reviewer can see exactly why a score is low.
    components = []
    if readability_score is not None:
        components.append(readability_score)
    if distinct:
        components.append(1.0 - min(len(missing) / max(len(distinct), 1), 1.0))
    if duplicates:
        components.append(1.0 - min(genuine_duplicates / max(len(distinct), 1), 1.0))
    else:
        components.append(1.0)
    components.append(0.5 if conflicts else 1.0)
    confidence = sum(components) / len(components) if components else 0.0

    return LegalDocumentQualityReport(
        law_title=body_meta.title,
        law_number=body_meta.law_number,
        year=body_meta.year,
        filename_title=filename_meta.title,
        filename_law_number=filename_meta.law_number,
        filename_year=filename_meta.year,
        metadata_conflicts=conflicts,
        article_count=len(pieces),
        distinct_article_numbers=len(distinct),
        missing_article_numbers=missing,
        duplicate_articles=duplicates,
        genuine_duplicate_count=genuine_duplicates,
        extraction_method=extraction_method,
        readability_score=readability_score,
        confidence_score=round(confidence, 3),
    )
