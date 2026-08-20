from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
css=(ROOT/'static/styles.css').read_text(encoding='utf-8')
polish=(ROOT/'static/pilot-polish.css').read_text(encoding='utf-8')
html=(ROOT/'static/index.html').read_text(encoding='utf-8')
js=(ROOT/'static/app.js').read_text(encoding='utf-8')


def test_chat_layout_keeps_scroll_and_nonfixed_composer():
    assert 'class="chat-scroll" id="chatScroll"' in html
    assert '.chat-scroll{flex:1;min-height:0;overflow-y:auto;overflow-x:hidden' in css
    assert '.suggestions{' in css and 'flex-wrap:wrap' in css
    suggestions=css.split('.suggestions{',1)[1].split('}',1)[0]
    assert 'overflow-x:auto' not in suggestions
    assert 'position:fixed' not in css.split('.composer-area{',1)[1].split('}',1)[0]


def test_mobile_ui_respects_safe_area_and_reduces_suggestion_clutter():
    assert 'env(safe-area-inset-bottom)' in polish
    assert '.suggestion:nth-child(n+5){display:none}' in polish
    assert '.composer textarea{font-size:16px' in polish
    assert 'calc(100% - 38px)' in polish


def test_bilingual_ui_has_language_aware_brand_avatars_and_coverage_titles():
    assert "if(state.lang==='en')return role==='assistant'?'Q':'U'" in js
    assert 'function renderBrand()' in js
    assert 'COVERAGE_TITLE_EN' in js
    assert "$('#sendBtn').setAttribute('aria-label',t('send'))" in js
    assert "settingsDesc:'Live Qanoni service status." in js
    assert 'server-side environment secrets' in js


def test_settings_render_real_v4_ai_and_cloud_state():
    assert 'h.ai?.answer_generation' in js
    assert 'h.ai?.cognition' in js
    assert "answer.provider==='extractive'?t('answerExtractive')" in js
    assert "h.corpus?.store==='supabase'" in js
    assert 'local_fallback' in js


def test_static_assets_are_cache_busted_for_v4_polish():
    assert '/static/app.js?v=40' in html
    assert '/static/pilot-polish.css?v=1' in html
    assert '/static/feedback-review.js?v=2' in html


def main():
    test_chat_layout_keeps_scroll_and_nonfixed_composer()
    test_mobile_ui_respects_safe_area_and_reduces_suggestion_clutter()
    test_bilingual_ui_has_language_aware_brand_avatars_and_coverage_titles()
    test_settings_render_real_v4_ai_and_cloud_state()
    test_static_assets_are_cache_busted_for_v4_polish()
    print('ui invariant tests: OK')


if __name__=='__main__':
    main()
