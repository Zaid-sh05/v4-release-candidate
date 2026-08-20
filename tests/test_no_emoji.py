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


def main():
    test_user_facing_answers_have_no_forbidden_emoji()
    test_strip_emoji_style_removes_emoji_and_emoticon()
    test_strip_emoji_style_preserves_english_t_characters_exactly()
    test_strip_emoji_style_collapses_spaces_and_tabs_without_touching_letters()
    print('no-emoji style tests: OK')


if __name__=='__main__':
    main()
