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


def pretty_title(title: str, body: str = '', authority: str = '') -> str:
    raw = unquote((title or '').strip())
    if '/' in raw:
        raw = urlparse(raw).path.rsplit('/', 1)[-1]
    stem = re.sub(r'\.(pdf|docx|doc|html?)$', '', raw, flags=re.I)
    stem = stem.replace('_', ' ').replace('-', ' ')
    stem = re.sub(r'\s+', ' ', stem).strip(' .-_')

    # UUIDs, scanner/export names and meaningless generated filenames are never shown to users.
    generic = (
        UUID_FILE.match(raw)
        or not stem
        or bool(re.fullmatch(r'[0-9a-f-]{20,}', stem, re.I))
        or bool(re.search(r'\b(?:merged|scan|document|file|copy)\b', stem, re.I))
    )
    if generic:
        inferred = infer_legal_title(body)
        return inferred or (f'وثيقة قانونية رسمية — {authority}' if authority else 'وثيقة قانونية رسمية')

    # Gazette issue filenames are made readable rather than exposing export syntax.
    m = re.search(r'(?:عدد|issue)\s*([0-9٠-٩]{3,6})', stem, re.I)
    if m and not any(x in stem for x in ('قانون','نظام','تعليمات','دستور','قرار')):
        return f'الجريدة الرسمية — العدد {m.group(1)}'

    # If a file name is mostly a code and the body exposes a proper legal title, prefer the legal title.
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


# User-facing Qanoni answers intentionally use no emoji/emoticons. The model prompt
# asks for that style; this post-processing rule makes it deterministic.
_EMOJI_RE = re.compile(
    '['
    '\U0001F1E6-\U0001F1FF'  # flags
    '\U0001F300-\U0001FAFF'  # symbols, pictographs, transport, supplemental emoji
    '\U00002600-\U000026FF'  # miscellaneous symbols
    '\U00002700-\U000027BF'  # dingbats
    ']+',
    flags=re.UNICODE,
)
_EMOTICON_RE = re.compile(r"(?:(?<=\s)|^)(?:[:;=8][\-^']?[)(/DPpOo]|<3)(?=\s|$)")


def strip_emoji_style(text: str) -> str:
    value = _EMOJI_RE.sub('', text or '')
    value = _EMOTICON_RE.sub('', value)
    value = re.sub(r'[ \\t]{2,}', ' ', value)
    value = re.sub(r' *\\n', '\\n', value)
    return value.strip()
