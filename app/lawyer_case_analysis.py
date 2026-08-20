from __future__ import annotations

from dataclasses import dataclass

from .answer_engine import GroundedAnswer
from .case_analysis import (
    _DOMAIN_AR,
    _DOMAIN_EN,
    _MISSING_EN,
    _evidence_signals,
    _english_output,
    _pick_sources,
    _source_basis_ar,
    _source_basis_en,
)
from .cognition.language_match import normalize_flexible
from .models import RouteResult, SourceItem


_ROLE_AR = {
    "person": "شخص مذكور في الوقائع",
    "worker": "عامل/موظف",
    "employer": "صاحب عمل",
    "victim": "مجني عليه/متضرر محتمل",
    "suspect": "مشتبه به/متهم بحسب السياق",
    "police": "الشرطة",
    "prosecutor": "النيابة/المدعي العام",
    "court": "المحكمة",
    "other": "طرف آخر",
    "unknown": "دور غير محسوم",
}

_ROLE_EN = {
    "person": "person mentioned in the facts",
    "worker": "worker/employee",
    "employer": "employer",
    "victim": "possible victim/affected party",
    "suspect": "suspect/accused depending on posture",
    "police": "police",
    "prosecutor": "prosecutor",
    "court": "court",
    "other": "other party",
    "unknown": "role not yet resolved",
}

_POSTURE_AR = {
    "pre_case": "قبل بدء إجراءات قضائية محددة بحسب المعطيات الحالية",
    "investigation": "مرحلة تحقيق/استدلال",
    "litigation": "قضية منظورة أمام المحكمة",
    "post_judgment": "مرحلة ما بعد صدور حكم أو قرار",
}

_POSTURE_EN = {
    "pre_case": "no specific court proceeding is established from the current facts",
    "investigation": "investigation stage",
    "litigation": "pending court litigation",
    "post_judgment": "post-judgment/review stage",
}

_EVENT_AR = {
    "entry": "دخول إلى منزل أو مكان",
    "breaking": "كسر/خلع أو استعمال وسيلة دخول بالقوة",
    "taking": "أخذ أو استيلاء على مال/منقول",
    "violence": "عنف أو اعتداء",
    "death": "وفاة أو قتل",
    "injury": "إصابة",
    "threat": "تهديد أو ابتزاز",
    "termination": "إنهاء علاقة عمل",
    "judgment": "صدور حكم أو قرار قضائي",
    "payment": "دفع أو تحويل مالي",
    "communication": "اتصال أو رسالة ذات صلة",
    "other": "واقعة أخرى ذات صلة",
}

_EVENT_EN = {
    "entry": "entry into a home or premises",
    "breaking": "breaking/forcing a means of entry",
    "taking": "taking or appropriating money/property",
    "violence": "violence or assault",
    "death": "death or killing",
    "injury": "injury",
    "threat": "threat or blackmail/extortion",
    "termination": "termination of employment",
    "judgment": "court judgment/decision",
    "payment": "payment or money transfer",
    "communication": "relevant communication/message",
    "other": "another relevant event",
}

_ISSUE_EN = {
    "criminal.theft": "possible theft",
    "criminal.aggravating_entry": "entry/breaking circumstances that may materially affect the legal classification",
    "criminal.intentional_homicide": "possible intentional homicide",
    "criminal.unintentional_death": "possible unintentional causing of death",
    "criminal.self_defense": "possible self-defense issue",
    "labor.termination": "termination of employment",
    "procedure.appeal": "appeal/review route",
}

_SUPPORT_EN = {
    "criminal.theft": "the narrative contains a taking/appropriation of money or movable property",
    "criminal.aggravating_entry": "the narrative contains entry and/or breaking/forced-access facts",
    "criminal.intentional_homicide": "a death is described and the actor's intent may be legally material",
    "criminal.unintentional_death": "a death is described but intent/negligence still requires separation",
    "criminal.self_defense": "the narrative includes a claim of responding to an attack or immediate danger",
    "labor.termination": "the narrative describes termination of an employment relationship",
    "procedure.appeal": "the user is asking about review or appeal of a judgment/decision",
}

_RESEARCH_AR = {
    "criminal.theft": "فحص أركان الأخذ/الاستيلاء والملكية والرضا والقصد، ثم مطابقة النص الرسمي على الوقائع المثبتة.",
    "criminal.aggravating_entry": "فحص أثر طريقة الدخول والكسر، وكون المكان منزلاً/مسكوناً، والتوقيت والظروف الأخرى في النص الرسمي.",
    "criminal.intentional_homicide": "فصل القصد وسبق الإصرار وطريقة الفعل والأداة والظروف قبل اختيار النص والعقوبة.",
    "criminal.unintentional_death": "فحص الإهمال أو الرعونة أو مخالفة واجب وسببية الوفاة، مع استبعاد القصد أو إثباته.",
    "criminal.self_defense": "فحص حالّية الخطر، ضرورة الرد، والتناسب وفق النص والاجتهاد الرسمي المتاح.",
    "labor.termination": "فحص نوع العقد ومدة الخدمة والإشعار وسبب الإنهاء والاستحقاقات المرتبطة به.",
    "procedure.appeal": "تحديد المحكمة ونوع القضية ووصف الحكم وتاريخ الصدور/التبليغ قبل حساب طريق وميعاد الطعن.",
}

_RESEARCH_EN = {
    "criminal.theft": "verify taking/appropriation, ownership, consent and intent, then match the proven facts to the official statutory text",
    "criminal.aggravating_entry": "verify the legal effect of entry/breaking, residential character, timing and other circumstances in the official text",
    "criminal.intentional_homicide": "separate intent, premeditation, method, weapon and surrounding circumstances before selecting a provision or penalty",
    "criminal.unintentional_death": "verify negligence/recklessness, duty, causation and whether intent is excluded or established",
    "criminal.self_defense": "verify immediacy of danger, necessity and proportionality against the official law and available judicial guidance",
    "labor.termination": "verify contract type, service period, notice, reason for termination and related entitlements",
    "procedure.appeal": "identify court, case type, judgment type and issuance/service dates before determining the review route or deadline",
}

_CONTRADICTION_EN = {
    "وجود وصف أو إشارة بأن الواقعة غير مقصودة": "the narrative also contains an indication that the result may have been unintended",
    "وجود تخطيط أو قصد ظاهر": "the narrative contains facts pointing toward planning or intent",
}


@dataclass
class _IssueView:
    label: str
    support: list[str]
    missing: list[str]
    contradictions: list[str]


def _clean(value: str | None, limit: int = 220) -> str:
    text = " ".join((value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def _dedupe(values: list[str], limit: int = 8) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _clean(value)
        key = normalize_flexible(clean)
        if not clean or not key or key in seen:
            continue
        seen.add(key)
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def _actor_lines(case, english: bool) -> list[str]:
    out: list[str] = []
    role_map = _ROLE_EN if english else _ROLE_AR
    for actor in getattr(case, "actors", [])[:8]:
        label = _clean(getattr(actor, "label", ""), 80)
        if not label:
            continue
        role = role_map.get(getattr(actor, "role", "unknown"), role_map["unknown"])
        out.append(f"{label} — {role}")
    return _dedupe(out, 8)


def _actor_lookup(case) -> dict[str, str]:
    return {
        getattr(actor, "id", ""): _clean(getattr(actor, "label", ""), 80)
        for actor in getattr(case, "actors", [])
        if getattr(actor, "id", "")
    }


def _chronology(case, english: bool) -> list[str]:
    labels = _EVENT_EN if english else _EVENT_AR
    actors = _actor_lookup(case)
    out: list[str] = []
    for event in sorted(getattr(case, "events", []), key=lambda item: getattr(item, "order", 10**6))[:10]:
        label = labels.get(getattr(event, "event_type", ""), labels["other"])
        details: list[str] = []
        event_actors = [actors.get(actor_id) for actor_id in getattr(event, "actors", [])]
        event_actors = [item for item in event_actors if item]
        if event_actors:
            details.append(("actor: " if english else "الفاعل المذكور: ") + ", ".join(event_actors))
        target = _clean(getattr(event, "target", None), 100)
        if target:
            details.append(("target: " if english else "المحل/الهدف: ") + target)
        when = _clean(getattr(event, "time_expression", None), 80)
        if when:
            details.append(("time: " if english else "الوقت: ") + when)
        location = _clean(getattr(event, "location", None), 100)
        if location:
            details.append(("location: " if english else "المكان: ") + location)
        intent = getattr(event, "intent", "unknown")
        if intent and intent != "unknown":
            intent_labels = {
                "accidental": ("reported as accidental" if english else "وُصف بأنه غير مقصود"),
                "intentional": ("reported as intentional" if english else "وُصف بأنه مقصود"),
                "premeditated": ("reported as premeditated" if english else "وردت إشارة إلى تخطيط/سبق قصد"),
                "self_defense_claim": ("linked to a self-defense claim" if english else "مرتبط بادعاء دفاع عن النفس"),
            }
            if intent in intent_labels:
                details.append(intent_labels[intent])
        suffix = f" ({'; '.join(details)})" if details else ""
        out.append(f"{getattr(event, 'order', len(out)+1)}. {label}{suffix}")
    return _dedupe(out, 10)


def _reported_fact_lines(case, english: bool, disputed: bool) -> list[str]:
    out: list[str] = []
    for fact in getattr(case, "facts", [])[:12]:
        if bool(getattr(fact, "disputed", False)) != disputed:
            continue
        text = _clean(getattr(fact, "text", ""), 240)
        if not text:
            continue
        category = getattr(fact, "category", "context")
        if english:
            category_label = {
                "conduct": "conduct",
                "evidence": "evidence-related statement",
                "mental_state": "mental-state statement",
                "amount": "amount/value",
                "context": "context",
            }.get(category, "context")
            out.append(f"{text} [{category_label}]")
        else:
            category_label = {
                "conduct": "سلوك/فعل",
                "evidence": "واقعة مرتبطة بدليل",
                "mental_state": "قصد/حالة ذهنية",
                "amount": "مبلغ/قيمة",
                "context": "سياق",
            }.get(category, "سياق")
            out.append(f"{text} [{category_label}]")
    return _dedupe(out, 6)


def _issue_views(case, english: bool) -> list[_IssueView]:
    out: list[_IssueView] = []
    for hypothesis in getattr(case, "hypotheses", [])[:5]:
        if getattr(hypothesis, "status", "candidate") == "unlikely" or float(getattr(hypothesis, "confidence", 0.0)) < 0.30:
            continue
        code = getattr(hypothesis, "code", "")
        label = _ISSUE_EN.get(code) if english else _clean(getattr(hypothesis, "label_ar", ""), 180)
        if not label:
            continue

        if english:
            support = [_SUPPORT_EN.get(code, "the issue is raised by the reported fact pattern")]
            missing = [_MISSING_EN.get(item, item) for item in getattr(hypothesis, "missing_elements", [])]
            contradictions = [
                _CONTRADICTION_EN.get(item, "the narrative contains information that may point in a different direction and should be verified")
                for item in getattr(hypothesis, "contradictions", [])
            ]
        else:
            support = list(getattr(hypothesis, "supporting_facts", []) or getattr(hypothesis, "rationale", []) or ["الوقائع المذكورة تثير هذه المسألة للفحص"])
            missing = list(getattr(hypothesis, "missing_elements", []))
            contradictions = list(getattr(hypothesis, "contradictions", []))
        out.append(_IssueView(label, _dedupe(support, 3), _dedupe(missing, 4), _dedupe(contradictions, 2)))
    return out


def _issue_matrix_lines(case, english: bool) -> list[str]:
    lines: list[str] = []
    for issue in _issue_views(case, english):
        if english:
            detail = [f"support: {', '.join(issue.support)}"]
            if issue.missing:
                detail.append(f"still material: {', '.join(issue.missing)}")
            if issue.contradictions:
                detail.append(f"counter-indicators: {', '.join(issue.contradictions)}")
        else:
            detail = [f"ما يثيرها: {', '.join(issue.support)}"]
            if issue.missing:
                detail.append(f"ما يزال جوهرياً: {', '.join(issue.missing)}")
            if issue.contradictions:
                detail.append(f"مؤشرات معاكسة/متعارضة: {', '.join(issue.contradictions)}")
        lines.append(f"{issue.label} — " + " | ".join(detail))
    return lines[:5]


def _material_gaps(case, english: bool) -> list[str]:
    values: list[str] = []
    for hypothesis in getattr(case, "hypotheses", [])[:5]:
        if getattr(hypothesis, "status", "candidate") == "unlikely":
            continue
        for item in getattr(hypothesis, "missing_elements", []):
            values.append(_MISSING_EN.get(item, item) if english else item)
    return _dedupe(values, 7)


def _research_focus(case, english: bool) -> list[str]:
    mapping = _RESEARCH_EN if english else _RESEARCH_AR
    out: list[str] = []
    for hypothesis in getattr(case, "hypotheses", [])[:5]:
        if getattr(hypothesis, "status", "candidate") == "unlikely":
            continue
        item = mapping.get(getattr(hypothesis, "code", ""))
        if item:
            out.append(item)
    return _dedupe(out, 5)


def generate_lawyer_case_analysis_answer(
    message: str,
    route: RouteResult,
    case,
    sources: list[SourceItem],
) -> GroundedAnswer | None:
    """Produce a lawyer-oriented fact/issue/evidence analysis without replacing legal proof.

    Cognition supplies structured understanding of the user's narrative. It may organize
    facts, issues and research questions, but it is never legal authority and never turns
    allegations into proven facts. Legal provisions, penalties, deadlines and final legal
    conclusions remain dependent on the retrieved official sources and the facts ultimately
    established in the matter.
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
    domain = (_DOMAIN_EN if english else _DOMAIN_AR).get(route.primary_domain, route.primary_domain)
    actors = _actor_lines(case, english)
    chronology = _chronology(case, english)
    undisputed_reported = _reported_fact_lines(case, english, disputed=False)
    disputed = _reported_fact_lines(case, english, disputed=True)
    issues = _issue_matrix_lines(case, english)
    evidence = _evidence_signals(message, case)
    gaps = _material_gaps(case, english)
    research = _research_focus(case, english)
    posture = (_POSTURE_EN if english else _POSTURE_AR).get(getattr(case, "procedural_posture", "pre_case"))

    if english:
        parts = [
            f"Preliminary case analysis: the main legal track is **{domain}**. "
            "This is structured issue-spotting from the reported narrative; it is not a finding of guilt, liability, authenticity of evidence, admissibility, or a final legal classification."
        ]
        if posture:
            parts.append(f"Procedural posture: {posture}.")
        if actors:
            parts.append("Parties/actors identified from the narrative:\n" + "\n".join(f"- {item}" for item in actors))
        if chronology:
            parts.append("Legally important facts and chronology:\n" + "\n".join(f"- {item}" for item in chronology))
        elif undisputed_reported:
            parts.append("Legally important facts in the narrative:\n" + "\n".join(f"- {item}" for item in undisputed_reported))
        if issues:
            parts.append("Issues that should be tested:\n" + "\n".join(f"- {item}" for item in issues))
        if disputed:
            parts.append(
                "Expressly disputed/alleged facts:\n"
                + "\n".join(f"- {item}" for item in disputed)
                + "\nThese remain disputed and must not be converted into proven facts by the assistant."
            )
        if evidence:
            parts.append(
                "Evidence/indicators mentioned:\n"
                + "\n".join(f"- {item.en}" for item in evidence)
                + "\nThis identifies evidence mentioned in the narrative only; authenticity, admissibility and evidential weight are not assumed."
            )
        if gaps:
            parts.append("Material facts still to resolve before a final classification or penalty:\n" + "\n".join(f"- {item}" for item in gaps))
        if research:
            parts.append("Next legal research focus:\n" + "\n".join(f"- {item}" for item in research))
        parts.append("Retrieved official legal basis:\n" + "\n".join(f"- {line}" for line in _source_basis_en(picked, case)))
        parts.append(
            "Grounding boundary: I will not assign an article number, offence, penalty, deadline, or final outcome merely from fuzzy language matching or scenario understanding. "
            "Those conclusions must be supported by the official text that fits the established facts and procedural posture."
        )
        return GroundedAnswer("\n\n".join(parts), "partial")

    parts = [
        f"التحليل الأولي للحالة: المسار القانوني الرئيسي هو **{domain}**. "
        "هذا تحليل منظم للوقائع والمسائل المحتملة كما وردت في الرواية، وليس حكماً بالإدانة أو المسؤولية، ولا يفترض صحة الدليل أو قبوله أو وزنه، ولا يشكل تكييفاً نهائياً."
    ]
    if posture:
        parts.append(f"الوضع الإجرائي الظاهر من المعطيات: {posture}.")
    if actors:
        parts.append("الأطراف/الأشخاص المستخرجون من الرواية:\n" + "\n".join(f"- {item}" for item in actors))
    if chronology:
        parts.append("الوقائع المؤثرة قانونياً والتسلسل الزمني:\n" + "\n".join(f"- {item}" for item in chronology))
    elif undisputed_reported:
        parts.append("الوقائع المؤثرة قانونياً في الرواية:\n" + "\n".join(f"- {item}" for item in undisputed_reported))
    if issues:
        parts.append("المسائل القانونية التي يجب فحصها:\n" + "\n".join(f"- {item}" for item in issues))
    if disputed:
        parts.append(
            "وقائع صريحة متنازع عليها/منسوبة ولم تُثبت بعد:\n"
            + "\n".join(f"- {item}" for item in disputed)
            + "\nتبقى هذه الوقائع محل نزاع ولا يحولها النظام إلى حقيقة مثبتة."
        )
    if evidence:
        parts.append(
            "الأدلة/القرائن المذكورة:\n"
            + "\n".join(f"- {item.ar}" for item in evidence)
            + "\nهذا حصر لما ذُكر من أدلة فقط؛ لا يفترض النظام صحتها أو قبولها أو وزنها الإثباتي."
        )
    if gaps:
        parts.append("الوقائع الجوهرية التي ما زال يلزم حسمها قبل التكييف النهائي أو العقوبة:\n" + "\n".join(f"- {item}" for item in gaps))
    if research:
        parts.append("محاور البحث القانوني التالية:\n" + "\n".join(f"- {item}" for item in research))
    parts.append("الأساس القانوني الرسمي المسترجع:\n" + "\n".join(f"- {line}" for line in _source_basis_ar(picked, case)))
    parts.append(
        "حدود الاستناد: لن أحدد رقم مادة أو جريمة نهائية أو عقوبة أو مدة أو نتيجة نهائية اعتماداً على المطابقة المرنة للكلمات أو فهم السيناريو وحده؛ "
        "يجب أن تستند هذه النتائج إلى النص الرسمي المطابق للوقائع التي تثبت فعلاً وللوضع الإجرائي الصحيح."
    )
    return GroundedAnswer("\n\n".join(parts), "partial")


__all__ = ["generate_lawyer_case_analysis_answer"]
