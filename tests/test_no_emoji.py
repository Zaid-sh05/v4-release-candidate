import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.chat import smalltalk
from app.text import strip_emoji_style

def main():
    samples=[smalltalk('مرحبا','ar'),smalltalk('كيفك','ar'),smalltalk('hello','en')]
    forbidden=['😀','😄','👋','⚖️','✅','❌','🙂','😂']
    for s in samples:
        assert not any(x in s for x in forbidden),s
    assert strip_emoji_style('نص اختبار 😀 :)') == 'نص اختبار'
    print('no-emoji style tests: OK')
if __name__=='__main__':main()
