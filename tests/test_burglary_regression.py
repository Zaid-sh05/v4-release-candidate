from types import SimpleNamespace

from app.chat_v4 import _filter_source_items, _filter_source_rows, _v4_retrieval_fallback
from app.models import SourceItem
from app.routing_guard import apply_case_route, route_query
from app.source_quality import looks_garbled_legal_text


BURGLARY = (
    "قام أحمد بالدخول إلى منزل جاره خالد أثناء غيابه، بعد أن كسر قفل الباب الخارجي. "
    "أخذ جهاز حاسوب محمول ومبلغا نقديا مقداره 500 دينار، ثم غادر المكان. لاحقا عثرت "
    "الشرطة على الحاسوب في منزل أحمد، وأظهرت كاميرا مراقبة قريبة وجوده أمام منزل خالد "
    "في وقت وقوع الحادث."
)


def _source(*, sid: str, domain: str, title: str, excerpt: str, article: str | None = None):
    return SourceItem(
        id=sid,
        title=title,
        authority="جهة رسمية",
        domain=domain,
        source_url="https://example.gov.jo/law",
        article=article,
        excerpt=excerpt,
        source_kind="official_guidance",
        score=0.9,
    )


def test_incident_word_does_not_turn_burglary_into_traffic_case():
    route = route_query(BURGLARY, "ar")

    assert route.primary_domain == "criminal"
    assert "criminal" in route.domains
    assert "traffic" not in route.domains


def test_cognition_fusion_cannot_reintroduce_traffic_for_burglary():
    route = route_query(BURGLARY, "ar")
    case = SimpleNamespace(
        domains=["traffic", "criminal"],
        hypotheses=[
            SimpleNamespace(confidence=0.91, domain="traffic"),
            SimpleNamespace(confidence=0.80, domain="criminal"),
        ],
        cognition_provider="groq",
        user_goal="information",
    )

    fused = apply_case_route(route, case)

    assert fused.primary_domain == "criminal"
    assert "traffic" not in fused.domains


def test_real_road_accident_still_routes_to_traffic():
    route = route_query("كنت بسوق السيارة وصدمت شخص بحادث سير وتوفى", "ar")

    assert route.primary_domain == "traffic"
    assert route.domains[:2] == ["traffic", "criminal"]


def test_arabic_presentation_form_pdf_text_is_rejected():
    broken = (
        "ﻧﺤﻦ ﻋﺒﺪ ﷲ اﻟﺜﺎﻧﻲ اﺑﻦ اﻟﺤﺴﯿﻦ ﻣﻠﻚ اﻟﻤﻤﻠﻜﺔ اﻷردﻧﯿﺔ اﻟﮭﺎﺷﻤﯿﺔ "
        "ﺑﻤﻘﺘﻀﻰ اﻟﻤﺎدة ﻣﻦ اﻟﺪﺳﺘﻮر وﺑﻨﺎء ﻋﻠﻰ ﻣﺎ ﻗﺮره ﻣﺠﻠﺴﺎ اﻷﻋﯿﺎن واﻟﻨﻮاب"
    )
    clean = "المادة 407: يعاقب من يرتكب السرقة وفق الشروط والأحكام الواردة في قانون العقوبات."

    assert looks_garbled_legal_text(broken) is True
    assert looks_garbled_legal_text(clean) is False


def test_source_guards_drop_garbled_text_even_inside_correct_domain():
    broken = _source(
        sid="broken",
        domain="criminal",
        title="قانون العقوبات",
        excerpt="ﻧﺤﻦ ﻋﺒﺪ ﷲ اﻟﺜﺎﻧﻲ اﺑﻦ اﻟﺤﺴﯿﻦ ﻣﻠﻚ اﻟﻤﻤﻠﻜﺔ اﻷردﻧﯿﺔ " * 5,
    )
    clean = _source(
        sid="clean",
        domain="criminal",
        title="قانون العقوبات رقم 16 لسنة 1960 وتعديلاته — المادة 407",
        excerpt="المادة 407: نص رسمي نظيف متعلق بالسرقة.",
        article="407",
    )

    items = _filter_source_items([broken, clean], ["criminal"])
    rows = _filter_source_rows(
        [broken.model_dump(), clean.model_dump()],
        ["criminal"],
    )

    assert [x.id for x in items] == ["clean"]
    assert [x["id"] for x in rows] == ["clean"]


def test_generic_burglary_fallback_is_case_oriented_not_raw_pdf_dump():
    route = route_query(BURGLARY, "ar")
    route.intent = "legal_question"
    source = _source(
        sid="penal-407",
        domain="criminal",
        title="قانون العقوبات رقم 16 لسنة 1960 وتعديلاته — المادة 407",
        excerpt="المادة 407: يعاقب من يرتكب السرقة الواقعة على صورة الأخذ وفق النص.",
        article="407",
    )

    answer = _v4_retrieval_fallback(BURGLARY, route, [source])

    assert "المسار الأساسي هنا جزائي وليس مرورياً" in answer
    assert "قانون العقوبات" in answer
    assert "قانون السير" not in answer
    assert "لن أطبّق عقوبة السرقة العامة تلقائياً" in answer
