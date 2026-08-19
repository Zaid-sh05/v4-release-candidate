import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app.chat import handle_chat
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
