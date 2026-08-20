from __future__ import annotations

from dataclasses import dataclass

from .answer_engine import GroundedAnswer
from .cognition.language_match import contains_fuzzy, language_mix, normalize_flexible
from .models import RouteResult, SourceItem
from .source_quality import looks_garbled_legal_text
from .text import normalize_ar


_DOMAIN_AR = {
    "criminal": "القانون الجزائي",
    "labor": "قانون العمل",
    "traffic": "قانون السير",
    "civil": "القانون المدني",
    "personal_status": "الأحوال الشخصية",
    "procedure": "الإجراءات وأصول المحاكمات",
    "cyber": "الجرائم الإلكترونية وحماية البيانات",
    "commercial": "القانون التجاري والشركات",
    "administrative": "القانون الإداري",
    "real_estate": "العقارات والملكية",
    "constitutional": "القانون الدستوري",
    "tax_finance": "الضرائب والمال",
}

_DOMAIN_EN = {
    "criminal": "criminal law",
    "labor": "labor law",
    "traffic": "traffic law",
    "civil": "civil law",
    "personal_status": "personal-status law",
    "procedure": "court procedure",
    "cyber": "cybercrime and data-protection law",
    "commercial": "commercial and companies law",
    "administrative": "administrative law",
    "real_estate": "real-estate law",
    "constitutional": "constitutional law",
    "tax_finance": "tax and finance law",
}

_HYPOTHESIS_EN = {
    "criminal.theft": "possible theft",
    "criminal.aggravating_entry": "entry or breaking that may materially affect the legal classification",
    "criminal.intentional_homicide": "possible intentional homicide",
    "criminal.unintentional_death": "possible unintentional causing of death",
    "criminal.self_defense": "a possible self-defense issue",
    "labor.termination": "termination of employment",
    "procedure.appeal": "an appeal or review route",
}

_EVENT_AR = {
    "entry": "دخول إلى منزل أو مكان",
    "breaking": "كسر أو خلع وسيلة دخول",
    "taking": "أخذ أو استيلاء على مال/منقول",
    "violence": "استعمال عنف أو اعتداء",
    "death": "وجود وفاة أو قتل ضمن الوقائع",
    "injury": "وجود إصابة",
    "threat": "وجود تهديد أو ابتزاز",
    "termination": "إنهاء علاقة عمل",
    "judgment": "وجود حكم قضائي",
    "payment": "وجود دفع أو تحويل مالي",
}

_EVENT_EN = {
    "entry": "entry into a home or premises",
    "breaking": "breaking or forcing a means of entry",
    "taking": "taking or appropriating money/property",
    "violence": "use of violence or assault",
    "death": "a death or killing in the facts",
    "injury": "an injury",
    "threat": "a threat or blackmail/extortion",
    "termination": "termination of employment",
    "judgment": "a court judgment",
    "payment": "a payment or money transfer",
}

_MISSING_EN = {
    "ملكية المال": "who owned the property",
    "رضا المالك من عدمه": "whether the owner consented",
    "قصد التملك": "the intent behind taking the property",
    "هل كان الدخول دون إذن؟": "whether the entry was without permission",
    "هل وقع ليلاً؟": "whether the conduct occurred at night",
    "هل كان المكان مسكوناً؟": "whether the premises were occupied/residential",
    "طبيعة القصد وقت الفعل": "the actor's intent at the time",
    "كيفية وقوع الفعل والأداة والظروف": "how the act occurred, including the means and surrounding circumstances",
    "هل أراد الفاعل إحداث الوفاة أو الأذى؟": "whether the actor intended death or injury",
    "هل وقع إهمال أو رعونة أو مخالفة واجب؟": "whether negligence, recklessness, or breach of duty was involved",
    "هل كان الخطر حالاً؟": "whether the danger was immediate",
    "هل كان الرد لازماً ومتناسباً؟": "whether the response was necessary and proportionate",
    "نوع العقد": "the type of employment contract",
    "مدة الخدمة": "length of service",
    "سبب الإنهاء": "the stated reason for termination",
    "وجود إشعار خطي": "whether written notice was given",
    "نوع المحكمة": "which court issued the decision",
    "نوع القضية": "the type of case",
    "وصف الحكم: وجاهي/غيابي/بمثابة الوجاهي": "the judgment type (in-person/default/equivalent)",
    "تاريخ الصدور أو التبليغ": "the judgment/service date",
}

_SOURCE_KIND_WEIGHT = {
    "canonical_verified": 8,
    "verified_crosscheck": 8,
    "judicial_principle": 7,
    "official_guidance": 6,
    "official_service": 6,
    "canonical": 5,
    "official_sync": 3,
    "reference": -5,
}


@dataclass
class _EvidenceSignal:
    ar: str
    en: str


def _dedupe(values: list[str], limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = " ".join((value or "").split()).strip()
        key = normalize_flexible(clean)
        if not clean or not key or key in seen:
            continue
        seen.add(key)
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def _english_output(route: RouteResult, message: str) -> bool:
    if route.language == "en":
        return True
    mix = language_mix(message)
    # Keep Arabic as the default for mixed Jordanian messages unless the router already
    # classified the requested language as English.
    return mix == "en"


def _evidence_signals(message: str, case) -> list[_EvidenceSignal]:
    out: list[_EvidenceSignal] = []
    kinds = {getattr(item, "kind", "") for item in getattr(case, "evidence", [])}

    if "camera" in kinds or contains_fuzzy(message, "كاميرا", "كاميرات", "كاميرا مراقبة", "cctv", "security camera", "surveillance camera", "camra"):
        out.append(_EvidenceSignal("وجود كاميرا/تسجيل مراقبة مذكور ضمن الوقائع", "a camera/CCTV or surveillance recording is mentioned"))
    if "physical" in kinds or contains_fuzzy(message, "عثر الشرطة", "عثرت الشرطة", "ضبط", "وجدت الشرطة", "police found", "police recovered", "recovered the laptop", "seized"):
        out.append(_EvidenceSignal("وجود ضبط أو عثور مادي من الشرطة على شيء مرتبط بالواقعة", "police recovery/seizure of physical property is mentioned"))
    if "witness" in kinds or contains_fuzzy(message, "شاهد", "شهود", "witness", "witnesses"):
        out.append(_EvidenceSignal("وجود شاهد أو شهود مذكورين", "a witness or witnesses are mentioned"))
    if "digital" in kinds or contains_fuzzy(message, "واتساب", "رسالة", "رسائل", "محادثة", "لقطة شاشة", "whatsapp", "message", "messages", "screenshot"):
        out.append(_EvidenceSignal("وجود دليل أو أثر رقمي مذكور", "digital evidence or communications are mentioned"))
    if "document" in kinds or contains_fuzzy(message, "عقد", "إيصال", "فاتورة", "مستند", "contract", "receipt", "invoice", "document"):
        out.append(_EvidenceSignal("وجود مستند أو وثيقة مرتبطة بالموضوع", "a document or written record is mentioned"))
    return out[:4]


def _important_events(case, english: bool) -> list[str]:
    labels = _EVENT_EN if english else _EVENT_AR
    items: list[str] = []
    for event in getattr(case, "events", []):
        label = labels.get(getattr(event, "event_type", ""))
        if label:
            items.append(label)
    return _dedupe(items, 6)


def _hypothesis_labels(case, english: bool) -> list[str]:
    labels: list[str] = []
    for hypothesis in getattr(case, "hypotheses", [])[:4]:
        if hypothesis.confidence < 0.35 or hypothesis.status == "unlikely":
            continue
        if english:
            label = _HYPOTHESIS_EN.get(hypothesis.code)
            if label:
                labels.append(label)
        else:
            labels.append(hypothesis.label_ar)
    return _dedupe(labels, 3)


def _missing_elements(case, english: bool) -> list[str]:
    missing: list[str] = []
    for hypothesis in getattr(case, "hypotheses", [])[:4]:
        if hypothesis.confidence < 0.35 or hypothesis.status == "unlikely":
            continue
        for item in hypothesis.missing_elements:
            missing.append(_MISSING_EN.get(item, item) if english else item)
    return _dedupe(missing, 5)


def _source_relevance(source: SourceItem, route: RouteResult, case) -> float:
    if source.source_kind == "reference" or not source.excerpt or looks_garbled_legal_text(source.excerpt):
        return -100.0
    if source.domain not in route.domains:
        return -100.0

    score = float(source.score or 0) + _SOURCE_KIND_WEIGHT.get(source.source_kind, 0)
    title = normalize_ar(source.title or "")
    excerpt = normalize_ar(source.excerpt or "")

    if source.domain == route.primary_domain:
        score += 5

    codes = {h.code for h in getattr(case, "hypotheses", [])}
    if "criminal.theft" in codes:
        if "قانون العقوبات" in title:
            score += 8
        if "سرق" in title or "سرق" in excerpt:
            score += 5
    if "criminal.aggravating_entry" in codes:
        if any(x in excerpt for x in ("كسر", "خلع", "منزل", "مسكون", "دخول")):
            score += 6
    if any(code.startswith("criminal.") for code in codes) and "قانون العقوبات" in title:
        score += 5
    if "labor.termination" in codes and ("قانون العمل" in title or "فصل" in excerpt or "انهاء" in excerpt):
        score += 7
    if "procedure.appeal" in codes and ("اصول المحاكمات" in title or "استيناف" in title or "استئناف" in source.title):
        score += 7
    return score


def _pick_sources(sources: list[SourceItem], route: RouteResult, case, limit: int = 3) -> list[tuple[int, SourceItem]]:
    ranked: list[tuple[float, int, SourceItem]] = []
    for index, source in enumerate(sources or [], 1):
        score = _source_relevance(source, route, case)
        if score > -50:
            ranked.append((score, index, source))
    ranked.sort(key=lambda item: item[0], reverse=True)

    picked: list[tuple[int, SourceItem]] = []
    seen_titles: set[str] = set()
    for _, index, source in ranked:
        key = normalize_flexible(source.title)
        if key in seen_titles:
            continue
        seen_titles.add(key)
        picked.append((index, source))
        if len(picked) >= limit:
            break
    return picked


def _source_basis_ar(picked: list[tuple[int, SourceItem]], case) -> list[str]:
    lines: list[str] = []
    codes = {h.code for h in getattr(case, "hypotheses", [])}
    has_entry = "criminal.aggravating_entry" in codes
    for index, source in picked:
        article = f"، المادة {source.article}" if source.article else ""
        line = f"{source.title}{article}. [S{index}]"
        if has_entry and str(source.article or "") == "407":
            line += " هذا المصدر يفيد في موضوع السرقة، لكنه لا يكفي وحده لتحديد حكم واقعة تتضمن كسراً أو دخول منزل."
        lines.append(line)
    return lines


def _source_basis_en(picked: list[tuple[int, SourceItem]], case) -> list[str]:
    lines: list[str] = []
    codes = {h.code for h in getattr(case, "hypotheses", [])}
    has_entry = "criminal.aggravating_entry" in codes
    for index, source in picked:
        article = f", Article {source.article}" if source.article else ""
        line = f"{source.title}{article}. [S{index}]"
        if has_entry and str(source.article or "") == "407":
            line += " This source is relevant to theft, but it is not enough by itself to determine the rule for a fact pattern involving forced entry into a home."
        lines.append(line)
    return lines


def generate_case_analysis_answer(
    message: str,
    route: RouteResult,
    case,
    sources: list[SourceItem],
) -> GroundedAnswer | None:
    """Build a structured preliminary case analysis grounded in retrieved official sources.

    The cognition object may identify issues and missing facts, but it is never treated as
    legal authority. Legal-source citations are required before this layer returns an answer.
    """
    if case is None or route.intent != "legal_question":
        return None
    if not getattr(case, "hypotheses", None):
        return None
    if getattr(case, "decision", None) and case.decision.action == "clarify" and len(getattr(case, "events", [])) <= 1:
        return None

    picked = _pick_sources(sources, route, case)
    if not picked:
        return None

    english = _english_output(route, message)
    hypotheses = _hypothesis_labels(case, english)
    events = _important_events(case, english)
    evidence = _evidence_signals(message, case)
    missing = _missing_elements(case, english)
    domain = (_DOMAIN_EN if english else _DOMAIN_AR).get(route.primary_domain, route.primary_domain)

    if english:
        parts = [
            f"Preliminary case analysis: the main legal track is **{domain}**. "
            "This is issue-spotting from the facts you described, not a finding of guilt, liability, or a final legal classification."
        ]
        if hypotheses:
            parts.append("Issues that should be tested:\n" + "\n".join(f"- {item}" for item in hypotheses))
        if events:
            parts.append("Legally important facts in the narrative:\n" + "\n".join(f"- {item}" for item in events))
        if evidence:
            parts.append("Evidence/indicators mentioned:\n" + "\n".join(f"- {item.en}" for item in evidence))
        if missing:
            parts.append("Before a final classification or penalty, the material points that may still need confirmation include:\n" + "\n".join(f"- {item}" for item in missing))
        parts.append("Retrieved official legal basis:\n" + "\n".join(f"- {line}" for line in _source_basis_en(picked, case)))
        parts.append(
            "I will not assign an article number or penalty merely from fuzzy language matching. "
            "Those must come from the official text that matches the exact facts and circumstances."
        )
        return GroundedAnswer("\n\n".join(parts), "partial")

    parts = [
        f"التحليل الأولي للحالة: المسار القانوني الرئيسي هو **{domain}**. "
        "هذا تكييف أولي للوقائع التي ذكرتها، وليس حكماً بالإدانة أو المسؤولية ولا تكييفاً نهائياً."
    ]
    if hypotheses:
        parts.append("المسائل القانونية التي يجب فحصها:\n" + "\n".join(f"- {item}" for item in hypotheses))
    if events:
        parts.append("الوقائع المؤثرة قانونياً في الرواية:\n" + "\n".join(f"- {item}" for item in events))
    if evidence:
        parts.append("الأدلة/القرائن المذكورة:\n" + "\n".join(f"- {item.ar}" for item in evidence))
    if missing:
        parts.append("قبل التكييف النهائي أو تحديد العقوبة، قد يلزم حسم النقاط التالية:\n" + "\n".join(f"- {item}" for item in missing))
    parts.append("الأساس القانوني الرسمي المسترجع:\n" + "\n".join(f"- {line}" for line in _source_basis_ar(picked, case)))
    parts.append(
        "لن أحدد رقم مادة أو عقوبة اعتماداً على المطابقة المرنة للكلمات أو على فهم لغوي فقط؛ "
        "رقم المادة والعقوبة يجب أن يأتيا من النص الرسمي المطابق للوقائع والظروف نفسها."
    )
    return GroundedAnswer("\n\n".join(parts), "partial")
