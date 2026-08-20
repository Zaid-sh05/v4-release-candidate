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


def _route() -> RouteResult:
    return RouteResult(
        language='ar',
        intent='legal_question',
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


def test_generate_answer_uses_grounded_draft_case_and_official_evidence(monkeypatch):
    captured={}

    class FakeResponses:
        def create(self,**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text='المبدأ القانوني: تنص المادة 25 على معالجة الفصل التعسفي وفق شروطها. [S1]')

    class FakeClient:
        def __init__(self,api_key):
            assert api_key=='test-key'
            self.responses=FakeResponses()

    monkeypatch.setitem(sys.modules,'openai',SimpleNamespace(OpenAI=FakeClient))
    monkeypatch.setattr(llm.settings,'openai_api_key','test-key')
    monkeypatch.setattr(llm.settings,'openai_model','gpt-5.6')

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
    assert captured['model']=='gpt-5.6'
    assert captured['max_output_tokens']==2400
    assert 'Grounded draft' in captured['input']
    assert 'مسودة آمنة' in captured['input']
    assert 'Structured case understanding' in captured['input']
    assert 'Official evidence' in captured['input']


def test_generate_answer_falls_back_when_model_invents_article(monkeypatch):
    class FakeResponses:
        def create(self,**kwargs):
            return SimpleNamespace(output_text='تنص المادة 999 على عقوبة مقدارها 777 ديناراً. [S1]')

    class FakeClient:
        def __init__(self,api_key):
            self.responses=FakeResponses()

    monkeypatch.setitem(sys.modules,'openai',SimpleNamespace(OpenAI=FakeClient))
    monkeypatch.setattr(llm.settings,'openai_api_key','test-key')
    result=llm.generate_answer('حالات الفصل التعسفي',_route(),[_source()],[],draft_answer='مسودة [S1]')
    assert result is None
