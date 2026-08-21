import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app.chat_v4 import handle_chat
from app.models import ChatRequest


def test_labor_followup_keeps_case_context():
    first=handle_chat(ChatRequest(message='فصلني صاحب العمل بدون إنذار، شو حقوقي؟',language='ar'))
    second=handle_chat(ChatRequest(
        message='عقدي غير محدد المدة، صارلي 4 سنوات، وما أعطوني أي إنذار',
        language='ar',conversation_id=first.conversation_id,
    ))
    assert second.route.primary_domain=='labor'
    assert second.route.intent=='rights'
    assert '4 سنوات' in second.answer
    assert '2 شهر' in second.answer
    assert 'الفصل التعسفي' in second.answer
    assert 'المادة الرسمية المسترجعة غير كافية' not in second.answer


def test_third_detail_can_use_accumulated_context():
    first=handle_chat(ChatRequest(message='فصلني صاحب العمل بدون إنذار، شو حقوقي؟',language='ar'))
    second=handle_chat(ChatRequest(message='عقدي غير محدد المدة، صارلي 4 سنوات، وما أعطوني أي إنذار',language='ar',conversation_id=first.conversation_id))
    third=handle_chat(ChatRequest(message='راتبي 500 دينار',language='ar',conversation_id=first.conversation_id))
    assert third.route.primary_domain=='labor'
    assert '1000 دينار' in third.answer
    assert '4 سنوات' in third.answer


def test_new_topic_does_not_inherit_labor_context():
    first=handle_chat(ChatRequest(message='فصلني صاحب العمل بدون إنذار، شو حقوقي؟',language='ar'))
    _=handle_chat(ChatRequest(message='عقدي غير محدد المدة، صارلي 4 سنوات، وما أعطوني أي إنذار',language='ar',conversation_id=first.conversation_id))
    new=handle_chat(ChatRequest(message='ما عقوبة القتل في الاردن؟',language='ar',conversation_id=first.conversation_id))
    assert new.route.primary_domain=='criminal'
    assert new.route.intent=='penalty'
    assert 'المادة 326' in new.answer


# P0 regression: a short confirming followup ("سرق سيارة") right after a full theft narrative
# was silently treated as a brand-new, standalone case -- losing the actors, the night/breaking
# facts, and (before the retrieval-layer fix in app.repository) surfacing an unrelated adultery
# article purely because it shares the Penal Code's title with the real theft article. Both the
# continuity heuristic and the retrieval scoring bug are covered here so this exact production
# regression can never silently return.
_THEFT_NARRATIVE = 'احمد دخل منزل خالد ليلا وكسر نافذة السيارة وسرقها'
_THEFT_FOLLOWUP_VARIANTS = (
    'سرق سيارة',
    'سرق مركبة',
    'اخذ سيارة بدون إذن',
    'كسر قزاز السيارة وسرقها',
    'سرق سيارة بالليل',
    'دخل الكراج وسرق المركبة',
    'stole the car after breaking the window',
)


def test_short_theft_followup_inherits_the_same_case():
    first=handle_chat(ChatRequest(message=_THEFT_NARRATIVE,language='ar'))
    assert first.route.primary_domain=='criminal'
    followup=handle_chat(ChatRequest(message='سرق سيارة',language='ar',conversation_id=first.conversation_id))
    assert followup.route.primary_domain=='criminal'
    # The actor from the original narrative must survive into the followup's answer -- proof
    # the case context (not just the domain) was actually carried forward, not just guessed
    # again independently from two words.
    assert 'خالد' in followup.answer


def test_short_theft_followup_never_cites_an_unrelated_offense_article():
    first=handle_chat(ChatRequest(message=_THEFT_NARRATIVE,language='ar'))
    for variant in _THEFT_FOLLOWUP_VARIANTS:
        resp=handle_chat(ChatRequest(message=variant,language='ar',conversation_id=first.conversation_id))
        for source in resp.sources:
            if source.domain!='criminal' or not source.article:
                continue
            hay=(source.title or '')+' '+(source.excerpt or '')
            assert 'الزاني' not in hay and 'الزانية' not in hay,(variant,source.title,source.article)
        assert 'المادة 282' not in resp.answer,(variant,resp.answer)
