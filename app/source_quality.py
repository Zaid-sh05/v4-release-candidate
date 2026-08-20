from __future__ import annotations


def looks_garbled_legal_text(text: str | None) -> bool:
    """Detect visibly broken PDF text layers before they reach a user-facing answer.

    Some official PDFs expose Arabic Presentation Forms (for example ﻧﺤﻦ) instead of
    normal Arabic code points. In long passages that produces unreadable/reversed OCR-like
    output even though the source document itself is authoritative. The source may remain
    registered, but its broken extracted body must not be quoted as legal evidence.
    """
    text = text or ""
    if not text.strip():
        return False

    presentation_forms = 0
    bidi_controls = 0
    replacement_chars = 0
    for ch in text:
        code = ord(ch)
        if 0xFB50 <= code <= 0xFDFF or 0xFE70 <= code <= 0xFEFF:
            presentation_forms += 1
        if code in {0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E}:
            bidi_controls += 1
        if code == 0xFFFD:
            replacement_chars += 1

    # Clean Arabic occasionally contains one compatibility glyph, so use a ratio/volume
    # threshold instead of rejecting a source for a single unusual character.
    if presentation_forms > max(6, len(text) // 20):
        return True
    if bidi_controls > max(2, len(text) // 120):
        return True
    if replacement_chars > 1:
        return True
    return False
