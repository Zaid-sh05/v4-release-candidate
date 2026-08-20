from __future__ import annotations
import re
import unicodedata
from urllib.parse import unquote, urlparse

AR_DIACRITICS = re.compile(r'[\u0617-\u061A\u064B-\u0652\u0670\u06D6-\u06ED]')
UUID_FILE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:\.(?:pdf|docx))?$', re.I)


def normalize_ar(text: str) -> str:
    text = unicodedata.normalize('NFKC', text or '').lower().strip()
    text = AR_DIACRITICS.sub('', text)
    text = text.translate(str.maketrans({'أ':'ا','إ':'ا','آ':'ا','ى':'ي','ؤ':'و','ئ':'ي','ة':'ه'}))
    text = re.sub(r'[ـ]+', '', text)
    text = re.sub(r'[^\w\s\u0600-\u06ff]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def detect_language(text: str) -> str:
    ar = len(re.findall(r'[\u0600-\u06FF]', text or ''))
    en = len(re.findall(r'[A-Za-z]', text or ''))
    return 'ar' if ar >= en else 'en'


def looks_garbled_text(text: str | None) -> bool:
    """Reject broken PDF/OCR layers before they can become legal evidence shown to a user.

    Official Jordanian PDFs occasionally expose visually Arabic text as presentation-form glyphs,
    or leak unrelated Unicode letters/symbols such as ᗷ / ᣢ / ᡧ into the extracted layer. A source
    may still be official, but that extraction is not safe to quote, summarize, or feed to an LLM.
    """
    value = text or ''
    if len(value.strip()) < 20:
        return False
    if '\ufffd' in value:
        return True

    presentation_forms = 0
    foreign_letterlike = 0
    meaningful = 0
    for ch in value:
        if ch.isspace():
            continue
        cp = ord(ch)
        category = unicodedata.category(ch)
        if 0xFB50 <= cp <= 0xFDFF or 0xFE70 <= cp <= 0xFEFF:
            presentation_forms += 1
            meaningful += 1
            continue
        if (
            0x0600 <= cp <= 0x06FF
            or 0x0750 <= cp <= 0x077F
            or 0x08A0 <= cp <= 0x08FF
            or 0x0041 <= cp <= 0x005A
            or 0x0061 <= cp <= 0x007A
            or ch.isdigit()
        ):
            meaningful += 1
            continue
        # Normal punctuation/currency characters are harmless. Unrelated letters, marks and
        # alphabetic-looking symbols in an Arabic legal paragraph are strong extraction damage.
        if category[0] in {'L', 'M'}:
            foreign_letterlike += 1
            meaningful += 1

    base = max(meaningful, 1)
    if presentation_forms >= max(5, int(base * 0.025)):
        return True
    if foreign_letterlike >= max(4, int(base * 0.018)):
        return True

    # Repeated isolated junk glyphs are another common PDF extraction signature.
    suspicious_tokens = re.findall(r'(?<![\w\u0600-\u06ff])[က-᥿Ⰰ-⿿ꀀ-\ua4ff](?![\w\u0600-\u06ff])', value)
    return len(suspicious_tokens) >= 3


def pretty_title(title: str, body: str = '', authority: str = '') -> str:
    raw = unquote((title or '').strip())
    if '/' in raw:
        raw = urlparse(raw).path.rsplit('/', 1)[-1]
    stem = re.sub(r'\.(pdf|docx|doc|html?)$', '', raw, flags=re.I)
    stem = stem.replace('_', ' ').replace('-', ' ')
    stem = re.sub(r'\s+', ' ', stem).strip(' .-_')

    generic = (
        UUID_FILE.match(raw)
        or not stem
        or bool(re.fullmatch(r'[0-9a-f-]{20,}', stem, re.I))
        or bool(re.search(r'\b(?:merged|scan|document|file|copy)\b', stem, re.I))
    )
    if generic:
        inferred = infer_legal_title(body)
        return inferred or (f'وثيقة قانونية رسمية — {authority}' if authority else 'وثيقة قانونية رسمية')

    m = re.search(r'(?:عدد|issue)\s*([0-9٠-٩]{3,6})', stem, re.I)
    if m and not any(x in stem for x in ('قانون','نظام','تعليمات','دستور','قرار')):
        return f'الجريدة الرسمية — العدد {m.group(1)}'

    if not re.search(r'[\u0600-\u06ff]', stem) or (len(stem) < 18 and re.search(r'\d', stem)):
        inferred = infer_legal_title(body)
        if inferred:
            return inferred

    if len(stem) > 180:
        inferred = infer_legal_title(body)
        if inferred:
            return inferred
    return stem[:180]


def infer_legal_title(body: str) -> str | None:
    text = re.sub(r'\s+', ' ', body or '')[:4000]
    for pattern in [
        r'((?:قانون|نظام|تعليمات)\s+.{3,120}?\s+رقم\s*\(?\s*[0-9٠-٩]+\s*\)?\s+لسنة\s*[0-9٠-٩]{4})',
        r'((?:قانون|نظام|تعليمات)\s+.{3,140}?\s+لسنة\s*[0-9٠-٩]{4})',
    ]:
        m = re.search(pattern, text)
        if m:
            value = re.sub(r'\s+', ' ', m.group(1)).strip(' :-')
            if 8 <= len(value) <= 180:
                return value
    return None


def extract_numbers(text: str) -> tuple[list[str], list[str], list[str]]:
    trans = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
    t = (text or '').translate(trans)
    articles = re.findall(r'(?:المادة|مادة|article)\s*\(?\s*(\d{1,4})', t, flags=re.I)
    laws = re.findall(r'(?:قانون|law)\s*(?:رقم|no\.?|number)?\s*\(?\s*(\d{1,4})', t, flags=re.I)
    years = re.findall(r'\b((?:19|20)\d{2})\b', t)
    return list(dict.fromkeys(articles)), list(dict.fromkeys(laws)), list(dict.fromkeys(years))


_EMOJI_RE = re.compile(
    '['
    '\U0001F1E6-\U0001F1FF'
    '\U0001F300-\U0001FAFF'
    '\U00002600-\U000026FF'
    '\U00002700-\U000027BF'
    ']+',
    flags=re.UNICODE,
)
_EMOTICON_RE = re.compile(r"(?:(?<=\s)|^)(?:[:;=8][\-^']?[)(/DPpOo]|<3)(?=\s|$)")


def strip_emoji_style(text: str) -> str:
    value = _EMOJI_RE.sub('', text or '')
    value = _EMOTICON_RE.sub('', value)
    value = re.sub(r'[ \t]{2,}', ' ', value)
    value = re.sub(r' *\n', '\n', value)
    return value.strip()
