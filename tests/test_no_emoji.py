import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app.chat import smalltalk
from app.text import strip_emoji_style


def test_user_facing_answers_have_no_forbidden_emoji():
    samples=[smalltalk('مرحبا','ar'),smalltalk('كيفك','ar'),smalltalk('hello','en')]
    forbidden=['😀','😄','👋','⚖️','✅','❌','🙂','😂']
    for sample in samples:
        assert not any(item in sample for item in forbidden), sample


def test_strip_emoji_style_removes_emoji_and_emoticon():
    assert strip_emoji_style('نص اختبار 😀 :)') == 'نص اختبار'


def test_strip_emoji_style_preserves_english_t_characters_exactly():
    text = 'The theft and taking facts are important to the next legal test.'
    assert strip_emoji_style(text) == text


def test_strip_emoji_style_collapses_spaces_and_tabs_without_touching_letters():
    text = 'The  theft\t\tand  taking facts'
    assert strip_emoji_style(text) == 'The theft and taking facts'


# Permanent regression for the historical "letter t disappears" defect (fixed in
# commit 62093d6): a raw-string typo (`[ \\t]` instead of `[ \t]`) made the cleanup
# regex treat the literal letter "t" as whitespace, silently eating it whenever it
# touched a space or another "t" (double letters, word-initial/final boundaries).
_T_WORDS = (
    'the', 'it', 'not', 'to', 'test', 'text', 'statutory', 'taking', 'theft',
    'important', 'termination', 'statement', 'testimony', 'structured',
    'spotting', 'intent', 'context', 'that',
)


def test_strip_emoji_style_preserves_every_boundary_and_doubled_t_word():
    for word in _T_WORDS:
        sentence = f'The next legal point is that {word} matters to this case.'
        result = strip_emoji_style(sentence)
        assert word in result.split(), f'{word!r} corrupted: {result!r}'
        assert result.count('t') == sentence.count('t'), f'{word!r} lost a t: {result!r}'


def test_strip_emoji_style_preserves_mixed_arabic_english_and_unicode():
    text = 'حلل الحالة: the taking and theft claims رقم [S1] تحتاج testimony.'
    assert strip_emoji_style(text) == text


def main():
    test_user_facing_answers_have_no_forbidden_emoji()
    test_strip_emoji_style_removes_emoji_and_emoticon()
    test_strip_emoji_style_preserves_english_t_characters_exactly()
    test_strip_emoji_style_collapses_spaces_and_tabs_without_touching_letters()
    test_strip_emoji_style_preserves_every_boundary_and_doubled_t_word()
    test_strip_emoji_style_preserves_mixed_arabic_english_and_unicode()
    print('no-emoji style tests: OK')


if __name__=='__main__':
    main()
