from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
css=(ROOT/'static/styles.css').read_text(encoding='utf-8')
html=(ROOT/'static/index.html').read_text(encoding='utf-8')

def main():
    assert 'class="chat-scroll" id="chatScroll"' in html
    assert '.chat-scroll{flex:1;min-height:0;overflow-y:auto;overflow-x:hidden' in css
    assert '.suggestions{' in css and 'flex-wrap:wrap' in css
    suggestions=css.split('.suggestions{',1)[1].split('}',1)[0]
    assert 'overflow-x:auto' not in suggestions
    assert 'position:fixed' not in css.split('.composer-area{',1)[1].split('}',1)[0]
    print('ui invariant tests: OK')

if __name__=='__main__': main()
