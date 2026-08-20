from __future__ import annotations

import sys
from types import SimpleNamespace

from app import llm
from app.models import RouteResult, SourceItem


def _source() -> SourceItem:
    return SourceItem(
        id='labor-25',
        title='قانون العمل الأردني رقم 8 لسنة 1996 وتعديلاته — المادة 25',
        authority='وزارة العمل',
        domain='labor',
        source_url='https://example.gov.jo/labor/25',
        law_number='8',
        year='1996',
        article='25',
        excerpt='المادة 25: إذا تبين للمحكمة أن فصل العامل كان تعسفياً فلها أن تصدر أمراً بإعادة العامل أو دفع تعويض وفق الشروط الواردة في النص.',
        source_kind='canonical_verified',
        score=1.0,
    )


def _route(intent: str='legal_question') -> RouteResult:
    return RouteResult(
        language='ar',
        intent=intent,
        primary_domain='labor',
        domains=['labor'],
        confidence=0.95,
        normalized_text='حالات الفصل التعسفي',
    )


def test_validator_accepts_supported_article_and_citation():
    ok,reasons=llm.validate_generated_answer(
        'المبدأ القانوني: تنص المادة 25 على معالجة الفصل التعسفي وفق شروطها. [S1]',
        [_source()],
        'ar',
    )
    assert ok, reasons


def test_validator_accepts_numbered_list_enumerator_but_still_checks_claim_numbers():
    ok,reasons=llm.validate_generated_answer(
        '1. إذا ثبت الفصل التعسفي فقد يترتب التعويض وفق المادة 25. [S1]',
        [_source()],
        'ar',
    )
    assert ok, reasons
    assert llm._claim_numbers('1. إذا ثبت الفصل التعسفي فقد يترتب التعويض وفق المادة 25. [S1]')==['25']


def test_validator_rejects_numbered_list_with_unsupported_article():
    ok,reasons=llm.validate_generated_answer(
        '2. تنص المادة 999 على تعويض غير مثبت. [S1]',
        [_source()],
        'ar',
    )
    assert not ok
    assert 'unsupported_legal_number:999' in reasons
    assert 'unsupported_legal_number:2' not in reasons


def test_validator_rejects_nonexistent_source_number():
    ok,reasons=llm.validate_generated_answer('تنص المادة 25 على ذلك. [S2]',[_source()],'ar')
    assert not ok
    assert 'invalid_citation_index' in reasons


def test_validator_rejects_unsupported_legal_number():
    ok,reasons=llm.validate_generated_answer(
        'تنص المادة 999 على تعويض مقداره 777 ديناراً. [S1]',
        [_source()],
        'ar',
    )
    assert not ok
    assert any(x.startswith('unsupported_legal_number:') for x in reasons)


def test_validator_rejects_hard_legal_rule_without_sources():
    ok,reasons=llm.validate_generated_answer('يعاقب الفاعل بالحبس سنة واحدة.',[],'ar')
    assert not ok
    assert 'hard_legal_claim_without_sources' in reasons


def test_generate_answer_uses_grounded_draft_case_and_latency_controls(monkeypatch):
    captured={}
    client_kwargs={}

    class FakeResponses:
        def create(self,**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text='المبدأ القانوني: تنص المادة 25 على معالجة الفصل التعسفي وفق شروطها. [S1]')

    class FakeClient:
        def __init__(self,**kwargs):
            client_kwargs.update(kwargs)
            assert kwargs['api_key']=='test-key'
            self.responses=FakeResponses()

    monkeypatch.setitem(sys.modules,'openai',SimpleNamespace(OpenAI=FakeClient))
    monkeypatch.setattr(llm.settings,'openai_api_key','test-key')
    monkeypatch.setattr(llm.settings,'openai_model','gpt-5.6')
    monkeypatch.setattr(llm.settings,'openai_reasoning_effort','low')
    monkeypatch.setattr(llm.settings,'openai_timeout_seconds',18.0)

    case=SimpleNamespace(to_dict=lambda:{
        'user_goal':'legal_analysis',
        'actors':[],
        'facts':[{'text':'تم فصل العامل','category':'employment'}],
        'events':[],
        'evidence':[],
        'amounts':[],
        'dates':[],
        'procedural_posture':'pre_case',
        'domains':['labor'],
        'hypotheses':[],
        'clarifying_questions':[],
        'warnings':[],
    })
    answer=llm.generate_answer(
        'حالات الفصل التعسفي',
        _route(),
        [_source()],
        [{'role':'user','content':'عندي سؤال عن العمل'}],
        draft_answer='مسودة آمنة من الطبقة الحتمية. [S1]',
        case=case,
    )
    assert answer and '[S1]' in answer
    assert client_kwargs['timeout']==18.0
    assert client_kwargs['max_retries']==0
    assert captured['model']=='gpt-5.6'
    assert captured['max_output_tokens']==1600
    assert captured['reasoning']=={'effort':'low'}
    assert captured['text']=={'verbosity':'medium'}
    assert 'Grounded draft' in captured['input']
    assert 'مسودة آمنة' in captured['input']
    assert 'Structured case understanding' in captured['input']
    assert 'Official evidence' in captured['input']


def test_generate_answer_falls_back_when_model_invents_article(monkeypatch):
    class FakeResponses:
        def create(self,**kwargs):
            return SimpleNamespace(output_text='تنص المادة 999 على عقوبة مقدارها 777 ديناراً. [S1]')

    class FakeClient:
        def __init__(self,**kwargs):
            self.responses=FakeResponses()

    monkeypatch.setitem(sys.modules,'openai',SimpleNamespace(OpenAI=FakeClient))
    monkeypatch.setattr(llm.settings,'openai_api_key','test-key')
    result=llm.generate_answer('حالات الفصل التعسفي',_route(),[_source()],[],draft_answer='مسودة [S1]')
    assert result is None


def test_v4_writer_policy_skips_short_direct_questions_and_keeps_high_value_synthesis():
    from app import chat_v4

    direct=_route('procedure')
    assert chat_v4._should_use_openai_writer('ما هي اجراءات الطلاق؟',direct,None) is False

    overview=_route('legal_question')
    assert chat_v4._should_use_openai_writer('حالات الفصل التعسفي في القانون الأردني',overview,None) is True

    long_case=(
        'قام صاحب العمل بإنهاء خدمة العامل بعد خلاف طويل، وذكر سبباً مختلفاً في كتاب الفصل '
        'عن السبب الذي أرسله في الرسائل، ويوجد شهود ورسائل ويريد العامل معرفة وضعه القانوني.'
    )
    assert chat_v4._should_use_openai_writer(long_case,overview,SimpleNamespace()) is True


def test_v4_short_query_skips_embedding_round_trip(monkeypatch):
    from app import chat_v4

    called=[]
    monkeypatch.setattr(chat_v4,'_ORIGINAL_EMBED_QUERY',lambda text: called.append(text) or [0.1])
    assert chat_v4._v4_embed_query('قطعت إشارة حمراء شو العقوبة؟') is None
    assert called==[]

    long_text=' '.join(['تفاصيل']*40)
    assert chat_v4._v4_embed_query(long_text)==[0.1]
    assert called==[long_text]


def test_research_composer_policy_covers_professional_legal_sections_without_forcing_them():
    ar=llm.SYSTEM_AR
    en=llm.SYSTEM_EN
    for phrase in ('الحالات أو الصور الرئيسية','الحقوق والآثار','مهلة أو موعد إجرائي','الأدلة المهمة','مثال افتراضي','النص النافذ بتاريخ الواقعة'):
        assert phrase in ar
    for phrase in ('main situations','rights, remedies','urgent procedural deadline','important evidence','hypothetical example','applicable version'):
        assert phrase in en
    assert 'لا تفرض أقساماً غير مفيدة' in ar
    assert 'do not mechanically include irrelevant sections' in en.lower()
