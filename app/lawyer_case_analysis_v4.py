from __future__ import annotations

# Extend the stable lawyer-analysis presenter without duplicating its source-grounded path. These
# mappings only change how already-grounded cognition is explained; they do not create legal rules.
from . import lawyer_case_analysis as base


base._EVENT_AR.update({
    "driving": "قيادة مركبة",
    "collision": "اصطدام/حادث سير",
    "property_damage": "ضرر مادي بالمركبة أو ممتلكات أخرى",
    "statement": "إفادة/أقوال أو شهادة مرتبطة بالواقعة",
    "money_demand": "طلب مبلغ أو منفعة مالية مرتبط بالأقوال/الشهادة",
})

base._EVENT_EN.update({
    "driving": "driving a vehicle",
    "collision": "road collision/traffic accident",
    "property_damage": "property/vehicle damage",
    "statement": "statement/testimony connected to the matter",
    "money_demand": "money/benefit demand linked to a statement or testimony",
})

base._ISSUE_EN.update({
    "traffic.unlicensed_driving": "possible unlicensed driving — dependent on identifying the actual driver",
    "traffic.collision": "road collision requiring responsibility and causation analysis",
    "traffic.collision_injury": "road collision with injury requiring responsibility and causation analysis",
    "civil.accident_damage": "possible civil/compensation consequences of bodily or property damage",
    "procedure.statement_conflict": "conflicting or changed statements/testimony requiring separate analysis",
    "procedure.statement_coercion_claim": "claim that a prior statement/testimony was made under threat or coercion",
    "criminal.statement_linked_money_demand": "money/benefit demand linked to testimony or statements — possible criminal issue requiring verification",
})

base._SUPPORT_EN.update({
    "traffic.unlicensed_driving": "the narrative states that one or more relevant people did not hold a driving licence",
    "traffic.collision": "the narrative contains a road collision",
    "traffic.collision_injury": "the narrative contains a road collision and an injury",
    "civil.accident_damage": "the narrative contains bodily injury and/or property damage that may require proof and valuation",
    "procedure.statement_conflict": "the narrative contains an earlier statement/testimony and a later materially different account",
    "procedure.statement_coercion_claim": "the later account alleges that an earlier statement/testimony was made under threat or coercion",
    "criminal.statement_linked_money_demand": "the narrative links a request for money/benefit to testimony, statements, or a position about them",
})

base._RESEARCH_AR.update({
    "traffic.unlicensed_driving": "تحديد السائق الفعلي أولاً، ثم فحص حالة رخصته وقت القيادة والنص المروري الرسمي المنطبق على تلك الواقعة.",
    "traffic.collision": "مراجعة مخطط/تقرير الحادث والسبب الفني وهوية السائق، ثم مطابقة واجبات السائق والنصوص المرورية الرسمية.",
    "traffic.collision_injury": "ربط هوية السائق وسبب الاصطدام بالتقرير الطبي والسببية، ثم فحص النصوص المرورية وما يتصل بها من آثار أخرى.",
    "civil.accident_damage": "إثبات الإصابة والضرر المادي وقيمتهما والسببية والتأمين والملكية قبل بحث التعويض أو المطالبة المدنية.",
    "procedure.statement_conflict": "مقارنة النص الحرفي لكل إفادة وتاريخها وصفة من أدلى بها والجهة التي تلقتها، ثم البحث في القيمة الإجرائية والأدلة المستقلة المؤيدة لكل رواية.",
    "procedure.statement_coercion_claim": "فحص تفاصيل الإكراه المزعوم وزمانه ومكانه ومن نُسب إليه وأي دليل مستقل عليه، دون افتراض صحة الادعاء أو كذبه.",
    "criminal.statement_linked_money_demand": "تثبيت صياغة طلب المال والشرط المرتبط به ووسيلة الطلب وأي تسجيل/رسالة، ثم مطابقة النص الجزائي الرسمي فقط بعد ثبوت الوقائع.",
})

base._RESEARCH_EN.update({
    "traffic.unlicensed_driving": "identify the actual driver first, then verify that person's licence status at the time and match the official traffic provision",
    "traffic.collision": "review the collision report/diagram, technical cause and driver identity before matching official traffic duties and provisions",
    "traffic.collision_injury": "connect driver identity and collision cause with the medical evidence and causation before researching the applicable official provisions",
    "civil.accident_damage": "prove bodily/property damage, valuation, causation, ownership and insurance position before assessing a civil compensation route",
    "procedure.statement_conflict": "compare the exact wording, date, maker and receiving authority for each statement, then assess procedural significance and independent corroboration",
    "procedure.statement_coercion_claim": "verify who allegedly applied pressure, when/how it occurred and what independent evidence exists without assuming the allegation is true or false",
    "criminal.statement_linked_money_demand": "establish the exact money demand, its condition and any message/recording/witness before matching any criminal provision",
})

base._MISSING_EN.update({
    "هوية من كان يقود المركبة وقت الواقعة": "who was actually driving the vehicle at the relevant time",
    "من كان يقود المركبة فعلياً؟": "who was actually driving the vehicle",
    "حالة رخصة السائق الفعلي وقت القيادة": "the actual driver's licence status at the time",
    "مكان وطبيعة القيادة وقت الواقعة": "where and in what driving context the vehicle was being driven",
    "هوية السائق الفعلي وقت الاصطدام": "the actual driver's identity at the time of collision",
    "كيفية وقوع الاصطدام وسببه الفني": "how the collision occurred and its technical cause",
    "مخطط/تقرير الحادث إن وجد": "the collision diagram/report, if available",
    "التقرير الطبي ودرجة الإصابة": "the medical report and injury severity",
    "علاقة الإصابة بالاصطدام": "causation between the collision and the injury",
    "التقرير الطبي والضرر المثبت للمصاب": "medical evidence and the injury actually established",
    "الرابطة السببية بين الحادث والضرر": "causation between the accident and the claimed damage",
    "تقدير الضرر المادي وملكية الممتلكات المتضررة": "valuation and ownership of the damaged property",
    "التأمين والتقارير الفنية إن وجدت": "insurance position and technical reports, if any",
    "النص الدقيق للأقوال الأولى ومن أدلى بها": "the exact first statement and who made it",
    "النص الدقيق للأقوال اللاحقة وتاريخها": "the exact later statement and its date",
    "صفة كل إفادة: أقوال استدلالية أم شهادة أمام جهة قضائية": "the procedural character of each account: police/investigative statement or testimony before a judicial authority",
    "الأدلة المستقلة التي تؤيد أياً من الروايتين": "independent evidence corroborating either account",
    "من الذي يُدعى أنه هدد أو أكره الشخص؟": "who is alleged to have threatened or coerced the person",
    "متى وأين وكيف وقع التهديد المزعوم؟": "when, where and how the alleged threat/coercion occurred",
    "هل توجد رسائل أو تسجيلات أو شهود أو قرائن مستقلة؟": "whether messages, recordings, witnesses or other independent indicators exist",
    "ما الذي تغير تحديداً بين الإفادة الأولى واللاحقة؟": "exactly what changed between the first and later account",
    "الصياغة الدقيقة لطلب المال والشرط المرتبط به": "the exact wording of the money demand and the condition attached to it",
    "هل توجد رسائل أو تسجيلات أو شهود على الطلب؟": "whether messages, recordings or witnesses support the alleged demand",
    "هل تم دفع أي مبلغ أم بقي الطلب مرفوضاً؟": "whether any amount was actually paid or the demand remained refused",
    "هل كان الطلب مقابل الإدلاء بقول، الاستمرار عليه، تغييره، أو الامتناع عنه؟": "whether the demand was linked to making, maintaining, changing or withholding a statement",
})


def _fact_only_analysis(message, route, case):
    """Render grounded narrative analysis even when retrieval has no matching legal text.

    Facts, chronology, allegations, evidence inventory and research questions come from the user's
    own narrative/cognition graph. No article, offence, penalty, deadline or legal outcome is stated.
    This prevents source scarcity from collapsing a useful lawyer-oriented analysis into a one-line
    refusal while preserving the legal-grounding boundary.
    """
    if case is None or route.intent != "legal_question" or not getattr(case, "hypotheses", None):
        return None
    if getattr(case, "decision", None) and case.decision.action == "clarify" and len(getattr(case, "events", [])) <= 1:
        return None

    english = base._english_output(route, message)
    domain = (base._DOMAIN_EN if english else base._DOMAIN_AR).get(route.primary_domain, route.primary_domain)
    actors = base._actor_lines(case, english)
    chronology = base._chronology(case, english)
    reported = base._reported_fact_lines(case, english, disputed=False)
    disputed = base._reported_fact_lines(case, english, disputed=True)
    issues = base._issue_matrix_lines(case, english)
    evidence = base._evidence_signals(message, case)
    gaps = base._material_gaps(case, english)
    research = base._research_focus(case, english)
    posture = (base._POSTURE_EN if english else base._POSTURE_AR).get(getattr(case, "procedural_posture", "pre_case"))

    if english:
        parts = [
            f"Preliminary case analysis: the main legal track is **{domain}**. "
            "This is structured issue-spotting from the reported narrative; it is not a finding of guilt, liability, evidence authenticity/admissibility, or a final legal classification."
        ]
        if posture:
            parts.append(f"Procedural posture: {posture}.")
        if actors:
            parts.append("Parties/actors identified from the narrative:\n" + "\n".join(f"- {item}" for item in actors))
        if chronology:
            parts.append("Legally important facts and chronology:\n" + "\n".join(f"- {item}" for item in chronology))
        elif reported:
            parts.append("Legally important reported facts:\n" + "\n".join(f"- {item}" for item in reported))
        if issues:
            parts.append("Issues that should be tested:\n" + "\n".join(f"- {item}" for item in issues))
        if disputed:
            parts.append(
                "Expressly disputed/alleged facts:\n"
                + "\n".join(f"- {item}" for item in disputed)
                + "\nThese remain disputed and are not converted into proven facts by the assistant."
            )
        if evidence:
            parts.append(
                "Evidence/indicators mentioned:\n"
                + "\n".join(f"- {item.en}" for item in evidence)
                + "\nThis is an evidence inventory only; authenticity, admissibility and weight are not assumed."
            )
        if gaps:
            parts.append("Material facts still to resolve:\n" + "\n".join(f"- {item}" for item in gaps))
        if research:
            parts.append("Next legal research focus:\n" + "\n".join(f"- {item}" for item in research))
        parts.append(
            "Retrieved official legal basis: no sufficiently specific readable official provision was retrieved for this multi-issue fact pattern, so I will not attach an article number or penalty to it yet."
        )
        parts.append(
            "Grounding boundary: the factual organization and issue list above come from the reported narrative. Any article number, offence, penalty, deadline or final outcome must be supported by official legal text that fits the facts actually established and the correct procedural posture."
        )
        return base.GroundedAnswer("\n\n".join(parts), "partial")

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
    elif reported:
        parts.append("الوقائع المؤثرة قانونياً في الرواية:\n" + "\n".join(f"- {item}" for item in reported))
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
            + "\nهذا حصر لما ذُكر فقط؛ لا يفترض النظام صحة الدليل أو قبوله أو وزنه الإثباتي."
        )
    if gaps:
        parts.append("الوقائع الجوهرية التي ما زال يلزم حسمها:\n" + "\n".join(f"- {item}" for item in gaps))
    if research:
        parts.append("محاور البحث القانوني التالية:\n" + "\n".join(f"- {item}" for item in research))
    parts.append(
        "الأساس القانوني الرسمي المسترجع: لم يُسترجع نص رسمي مقروء ومحدد بما يكفي لتغطية هذه الوقائع المركبة، لذلك لن أربطها الآن برقم مادة أو عقوبة غير مثبتة."
    )
    parts.append(
        "حدود الاستناد: تنظيم الوقائع والمسائل أعلاه مبني على الرواية التي ذكرتها فقط. أما رقم المادة أو الجريمة النهائية أو العقوبة أو المدة أو النتيجة، فيجب أن تستند إلى نص رسمي مطابق للوقائع التي تثبت فعلاً وللوضع الإجرائي الصحيح."
    )
    return base.GroundedAnswer("\n\n".join(parts), "partial")


def generate_lawyer_case_analysis_answer(message, route, case, sources):
    # Preserve the established source-grounded presenter whenever at least one suitable official
    # source exists. Only use fact-only mode when retrieval cannot support a legal-basis section.
    picked = base._pick_sources(sources or [], route, case) if case is not None else []
    if picked:
        return base.generate_lawyer_case_analysis_answer(message, route, case, sources)
    return _fact_only_analysis(message, route, case)


__all__ = ["generate_lawyer_case_analysis_answer"]
