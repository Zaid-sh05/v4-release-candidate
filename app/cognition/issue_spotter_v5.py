from __future__ import annotations

from .issue_spotter_v4 import spot_issues as base_spot_issues
from .language_match import contains_fuzzy, normalize_flexible, tokens
from .models import CaseModel, LegalHypothesis


_MEDIUM_PREPOSITION_TOKENS = [tokens(p) for p in ("عبر", "من خلال", "بواسطة", "خلال", "via", "through")]
_MEDIUM_NOUN_TOKENS = {
    "تطبيق", "تطبيقات", "منصه", "منصات", "موقع", "مواقع", "برنامج", "برامج",
    "حساب", "حسابات", "رسائل", "رساله", "شات", "النت", "الانترنت",
    "app", "apps", "platform", "account", "website", "chat", "messages", "online",
}


def _digital_medium_context(text: str) -> bool:
    """Recognize an unnamed digital channel by its grammatical construction.

    A fixed list of platform names cannot generalize to a product Qanoni has never seen
    named. Detecting the "<preposition> <medium-noun>" construction itself (e.g. "عبر
    تطبيق", "من خلال حساب") lets the narrative be understood without knowing the product.
    """
    words = tokens(text)
    for prep_tokens in _MEDIUM_PREPOSITION_TOKENS:
        width = len(prep_tokens)
        if not width or width > len(words):
            continue
        for i in range(len(words) - width + 1):
            if words[i:i + width] != prep_tokens:
                continue
            if any(w in _MEDIUM_NOUN_TOKENS for w in words[i + width:i + width + 4]):
                return True
    return False


def _add(items: list[LegalHypothesis], hypothesis: LegalHypothesis) -> None:
    if any(item.code == hypothesis.code for item in items):
        return
    items.append(hypothesis)


def _has(text: str, *terms: str) -> bool:
    return contains_fuzzy(text, *terms)


def _norm(text: str) -> str:
    return normalize_flexible(text or "")


def spot_issues(case: CaseModel) -> list[LegalHypothesis]:
    """Expand neutral lawyer issue-spotting across the main Jordanian-law practice areas.

    This layer does not determine legal liability, entitlement, validity, guilt, deadlines, or
    remedies. It only identifies material legal questions raised by the reported narrative and the
    facts/evidence that must be verified before official legal text can be applied.
    """
    items = list(base_spot_issues(case))
    text = case.raw_message or ""
    n = _norm(text)

    # ------------------------------------------------------------------
    # Labor / employment
    # ------------------------------------------------------------------
    employment_context = _has(
        text,
        "عامل", "موظف", "صاحب العمل", "شركة بشتغل", "عقد عمل", "راتب", "أجر",
        "employee", "employer", "employment", "salary", "wage",
    )
    unpaid_wage = employment_context and _has(
        text,
        "ما دفع راتبي", "لم يدفع راتبي", "راتب متأخر", "رواتب متأخرة", "حجز راتبي",
        "ما قبضت", "لم أقبض", "أجر غير مدفوع", "unpaid salary", "unpaid wage", "withheld salary",
    )
    overtime = employment_context and _has(
        text,
        "عمل إضافي", "عمل اضافي", "ساعات إضافية", "ساعات اضافية", "اوفر تايم", "أوفر تايم",
        "overtime", "extra hours",
    )
    leave = employment_context and _has(
        text,
        "إجازة", "اجازة", "إجازاتي", "اجازاتي", "إجازة سنوية", "إجازة مرضية",
        "annual leave", "sick leave", "leave balance",
    )

    if unpaid_wage:
        _add(items, LegalHypothesis(
            code="labor.unpaid_wages",
            label_ar="مطالبة محتملة بأجر/راتب غير مدفوع",
            domain="labor",
            rationale=["الرواية تتضمن أجراً أو راتباً يدعي العامل أنه لم يُدفع"],
            missing_elements=[
                "الفترة التي لم يُدفع عنها الأجر",
                "مقدار الأجر المتفق عليه وطريقة إثباته",
                "كشوف الرواتب/التحويلات البنكية أو أي إيصالات",
                "هل انتهت علاقة العمل أم ما زالت قائمة؟",
            ],
            confidence=0.90,
            status="needs_clarification",
        ))

    if overtime:
        _add(items, LegalHypothesis(
            code="labor.overtime",
            label_ar="مطالبة محتملة ببدل عمل إضافي",
            domain="labor",
            rationale=["الرواية تتضمن ساعات عمل إضافية أو مطالبة ببدلها"],
            missing_elements=[
                "ساعات العمل الأصلية والمتفق عليها",
                "عدد وتواريخ ساعات العمل الإضافية",
                "سجلات الحضور/المغادرة أو الرسائل أو التكليفات",
                "هل دُفع أي بدل عن تلك الساعات؟",
            ],
            confidence=0.84,
            status="needs_clarification",
        ))

    if leave:
        _add(items, LegalHypothesis(
            code="labor.leave_entitlement",
            label_ar="نزاع محتمل حول إجازة أو رصيد إجازات",
            domain="labor",
            rationale=["الرواية تثير مسألة إجازة أو رصيد إجازات ضمن علاقة العمل"],
            missing_elements=[
                "نوع الإجازة محل النزاع",
                "مدة الخدمة والسنة/الفترة ذات الصلة",
                "سجل الإجازات الموافق عليها والمستخدمة",
                "هل النزاع عن منح الإجازة أم بدلها عند انتهاء العمل؟",
            ],
            confidence=0.76,
            status="needs_clarification",
        ))

    # ------------------------------------------------------------------
    # Civil: contracts, debt, non-traffic damage
    # ------------------------------------------------------------------
    contract_context = _has(
        text,
        "عقد", "اتفاق", "بيع", "شراء", "إيجار", "ايجار", "مقاول", "توريد",
        "contract", "agreement", "sale", "lease", "rent", "supply",
    )
    breach_context = _has(
        text,
        "ما التزم", "لم يلتزم", "ما نفذ", "لم ينفذ", "أخل", "اخل", "فسخ", "تأخر بالتسليم",
        "تأخر عن التسليم", "تأخر", "لم يسلم", "breach", "did not perform", "failed to deliver",
        "termination of contract", "delayed",
    )
    debt_context = _has(
        text,
        "دين", "قرض", "سلفته", "أقرضته", "اقرضته", "مطالبة مالية", "مبلغ بذمته",
        "debt", "loan", "owes me", "money owed",
    )
    payment_denial = _has(
        text,
        "ينكر الدين", "أنكر الدين", "انكر الدين", "بيقول دفع", "يدعي أنه دفع", "يدعي انه دفع",
        "denies the debt", "says he paid", "claims he paid",
    )
    # "كسر" alone is ambiguous: "كسر القفل" (broke the lock) is a burglary entry method already
    # captured by criminal.aggravating_entry / property_crime routing, not a standalone civil
    # damages claim. Bare "كسر"/"تلف" was previously enough to fire this civil hypothesis even
    # for a pure break-in-and-theft narrative with no independent property-damage claim, letting
    # it outrank the correct criminal classification on confidence alone. Require an explicit
    # damage/compensation-flavored term instead of the bare, overloaded verb.
    damage_context = _has(
        text,
        "سبب لي ضرر", "سبب ضرر", "أضرار", "أتلف", "اتلف", "تلف", "خسارة", "تعويض",
        "damaged", "loss", "compensation", "damages",
    )

    if contract_context and breach_context:
        _add(items, LegalHypothesis(
            code="civil.contract_performance",
            label_ar="نزاع عقدي حول التنفيذ/الإخلال والآثار المترتبة",
            domain="civil",
            rationale=["الرواية تتضمن عقداً أو اتفاقاً مع ادعاء بعدم التنفيذ أو الإخلال"],
            missing_elements=[
                "نسخة العقد وشروط الالتزام محل النزاع",
                "ما الذي نفذه كل طرف وما الذي بقي دون تنفيذ؟",
                "مواعيد الاستحقاق/التسليم وأي إنذارات أو مراسلات",
                "الضرر أو المبلغ المطالب به وكيف تم احتسابه",
            ],
            confidence=0.88,
            status="needs_clarification",
        ))

    if debt_context:
        _add(items, LegalHypothesis(
            code="civil.debt_claim",
            label_ar="مطالبة مالية/دين يحتاج إثبات أصل الدين والوفاء",
            domain="civil",
            rationale=["الرواية تتضمن مبلغاً مدعى بأنه دين أو قرض أو التزام مالي"],
            missing_elements=[
                "مصدر الدين وتاريخ نشوئه",
                "قيمة الدين وما تم دفعه إن وجد",
                "المستندات/التحويلات/الإقرارات أو الشهود المؤيدون",
                "تاريخ الاستحقاق وأي مطالبة أو إنذار سابق",
            ],
            contradictions=["وجود ادعاء بالوفاء أو إنكار أصل الدين"] if payment_denial else [],
            confidence=0.86,
            status="needs_clarification",
        ))

    traffic_words = _has(text, "سيارة", "مركبة", "حادث سير", "دهس", "تصادم", "traffic", "vehicle", "car accident")
    if damage_context and not traffic_words:
        _add(items, LegalHypothesis(
            code="civil.compensation_damage",
            label_ar="مطالبة تعويض محتملة عن ضرر غير مروري",
            domain="civil",
            rationale=["الرواية تتضمن ضرراً أو خسارة يُطلب التعويض عنها"],
            missing_elements=[
                "الفعل أو الواقعة التي يُنسب إليها الضرر",
                "طبيعة الضرر وقيمته وكيفية إثباته",
                "الرابطة السببية بين الفعل والضرر",
                "الفواتير أو التقارير أو الخبرة أو الأدلة المؤيدة",
            ],
            confidence=0.74,
            status="needs_clarification",
        ))

    # ------------------------------------------------------------------
    # Personal status
    # ------------------------------------------------------------------
    divorce = _has(text, "طلاق", "طلقني", "تطليق", "خلع", "شقاق ونزاع", "divorce", "khula")
    maintenance = _has(text, "نفقة", "ما بصرف", "لا ينفق", "مصروف الأولاد", "مصروف الاطفال", "alimony", "maintenance", "child support")
    custody = _has(text, "حضانة", "الحاضن", "اخذ الاولاد", "أخذ الأولاد", "منعني من رؤية", "مشاهدة الأطفال", "custody", "visitation", "child access")

    if divorce:
        _add(items, LegalHypothesis(
            code="personal_status.divorce_path",
            label_ar="مسار إنهاء علاقة زوجية/طلاق يحتاج تحديد نوع الطلب والوقائع",
            domain="personal_status",
            rationale=["الرواية تتضمن طلباً أو واقعة مرتبطة بالطلاق/التفريق/الخلع"],
            missing_elements=[
                "حالة الزواج والوثائق المتاحة",
                "نوع الطلب المقصود وسبب اللجوء إليه",
                "هل توجد دعاوى أو أحكام سابقة بين الطرفين؟",
                "هل توجد مسائل مرتبطة بالمهر أو النفقة أو الأولاد؟",
            ],
            confidence=0.90,
            status="needs_clarification",
        ))

    if maintenance:
        _add(items, LegalHypothesis(
            code="personal_status.maintenance",
            label_ar="مطالبة نفقة/إنفاق محتملة تحتاج تحديد المستفيد والفترة",
            domain="personal_status",
            rationale=["الرواية تتضمن مطالبة بالنفقة أو عدم الإنفاق"],
            missing_elements=[
                "من هو طالب النفقة ومن هو الملزم المدعى عليه؟",
                "الفترة المطلوب عنها النفقة",
                "وجود حكم نفقة سابق من عدمه",
                "الدخل والاحتياجات والمصاريف التي يمكن إثباتها",
            ],
            confidence=0.88,
            status="needs_clarification",
        ))

    if custody:
        _add(items, LegalHypothesis(
            code="personal_status.custody_access",
            label_ar="نزاع محتمل حول الحضانة/المشاهدة أو الوصول للأطفال",
            domain="personal_status",
            rationale=["الرواية تثير مسألة حضانة أو مشاهدة أو تسليم أطفال"],
            missing_elements=[
                "أعمار الأطفال ووضعهم الحالي",
                "هل يوجد حكم حضانة/مشاهدة/استزارة سابق؟",
                "مكان إقامة الأطفال ومن يقوم برعايتهم فعلياً",
                "الواقعة المحددة محل النزاع وأي محاضر أو رسائل مرتبطة بها",
            ],
            confidence=0.86,
            status="needs_clarification",
        ))

    # ------------------------------------------------------------------
    # Commercial / companies
    # ------------------------------------------------------------------
    company_context = _has(text, "شركة", "شريك", "مدير شركة", "مساهم", "حصص", "سجل تجاري", "company", "partner", "shareholder", "manager")
    authority_context = company_context and _has(
        text,
        "وقع باسم الشركة", "وقّع باسم الشركة", "بدون تفويض", "دون تفويض", "غير مفوض", "غير مخول",
        "صلاحية المدير", "صلاحية التوقيع", "signed for the company", "without authority", "not authorized",
    )
    partner_money = company_context and _has(
        text,
        "سحب من حساب الشركة", "أخذ من حساب الشركة", "حول لنفسه", "حوّل لنفسه", "أموال الشركة",
        "company account", "transferred company money", "withdrew company money",
    )
    share_dispute = company_context and _has(
        text,
        "حصتي", "حصص الشركة", "أسهمي", "اسهمي", "نقل الحصص", "تنازل عن الحصص", "شريك جديد",
        "my shares", "company shares", "transfer of shares", "ownership stake",
    )

    if authority_context:
        _add(items, LegalHypothesis(
            code="commercial.company_authority",
            label_ar="مسألة صلاحية تمثيل/توقيع عن الشركة تحتاج فحصاً",
            domain="commercial",
            rationale=["الرواية تتضمن تصرفاً أو توقيعاً باسم شركة مع نزاع حول الصلاحية"],
            missing_elements=[
                "نوع الشركة وسجلها الحالي",
                "صفة الشخص الذي وقع أو تصرف باسمها",
                "المفوضون بالتوقيع وحدود التفويض وقت التصرف",
                "العقد/القرار/محضر الهيئة أو السجل الذي يثبت الصلاحية",
            ],
            confidence=0.88,
            status="needs_clarification",
        ))

    if partner_money:
        _add(items, LegalHypothesis(
            code="commercial.company_funds",
            label_ar="نزاع حول استعمال/سحب أموال الشركة يحتاج فصل ذمة الشركة عن الشركاء",
            domain="commercial",
            rationale=["الرواية تتضمن سحباً أو تحويلاً من أموال الشركة لمصلحة شخص مرتبط بها"],
            missing_elements=[
                "مصدر الأموال وحساب الشركة المعني",
                "صفة من أجرى السحب أو التحويل وصلاحياته",
                "سبب العملية والمستند المحاسبي أو القرار المؤيد لها",
                "القيود البنكية/المحاسبية وأي اعتراضات داخل الشركة",
            ],
            confidence=0.82,
            status="needs_clarification",
        ))

    if share_dispute:
        _add(items, LegalHypothesis(
            code="commercial.shareholding_dispute",
            label_ar="نزاع حصص/أسهم أو ملكية في شركة يحتاج فحص السجل والتصرفات",
            domain="commercial",
            rationale=["الرواية تتضمن نزاعاً حول حصة أو سهم أو نقل ملكية في شركة"],
            missing_elements=[
                "نوع الشركة ورأس المال المسجل",
                "نسبة/عدد الحصص أو الأسهم محل النزاع",
                "سجل الشركاء/المساهمين والتعديلات المسجلة",
                "العقد أو التنازل أو القرار الذي يُدعى أنه غيّر الملكية",
            ],
            confidence=0.80,
            status="needs_clarification",
        ))

    # ------------------------------------------------------------------
    # Cyber / data / online coercion
    # ------------------------------------------------------------------
    online_context = _has(
        text, "واتساب", "فيسبوك", "انستغرام", "إنستغرام", "حساب", "اونلاين", "أونلاين",
        "whatsapp", "facebook", "instagram", "online", "account",
    ) or _digital_medium_context(text)
    # Decomposed into independent components (threat + disclosure-or-benefit-demand)
    # rather than a fixed collocation like "هدد بنشر", so word order and phrasing that
    # were never seen in a fixture still resolve to the same legal issue.
    threat_language = _has(text, "هدد", "تهديد", "مهدد", "threat", "threatened", "ابتزاز", "ابتزني", "ببتزني", "blackmail", "extortion")
    disclosure_language = _has(text, "ينشر", "نشر", "يفضح", "فضح", "تسريب", "يسرب", "publish", "leak", "expose", "disclose")
    benefit_demand_language = _has(
        text, "دفع", "دفعت", "مبلغ", "فلوس", "مصاري", "مقابل", "إذا ما", "اذا ما",
        "حولتله", "حولت", "pay", "payment", "in exchange", "unless",
    )
    blackmail = online_context and threat_language and (disclosure_language or benefit_demand_language)
    intrusion = online_context and _has(
        text,
        "اخترق", "اختراق", "تهكير", "دخل حسابي", "سرق كلمة السر", "غير كلمة السر",
        "hacked", "account hacked", "unauthorized access", "stole my password",
    )
    private_data = online_context and _has(
        text,
        "صوري الخاصة", "بياناتي", "بيانات شخصية", "رقم هويتي", "محادثاتي", "خصوصيتي",
        "private photos", "personal data", "private messages", "privacy",
    )

    if blackmail:
        _add(items, LegalHypothesis(
            code="cyber.blackmail_threat",
            label_ar="ابتزاز/تهديد إلكتروني محتمل يحتاج حفظ الدليل الرقمي وتحديد الحساب",
            domain="cyber",
            rationale=["الرواية تربط تهديداً أو نشر محتوى بطلب مال/منفعة عبر وسيلة إلكترونية"],
            missing_elements=[
                "النص الدقيق للتهديد أو طلب المنفعة",
                "الحساب/الرقم/المنصة المستخدمة وهوية صاحبها إن كانت معروفة",
                "الرسائل الأصلية وبياناتها الزمنية وأي نسخ احتياطية",
                "هل تم دفع مبلغ أو إرسال محتوى أو تنفيذ أي جزء من الطلب؟",
            ],
            confidence=0.94,
            status="needs_clarification",
        ))

    if intrusion:
        _add(items, LegalHypothesis(
            code="cyber.account_intrusion",
            label_ar="دخول/اختراق غير مصرح به لحساب أو نظام محتمل",
            domain="cyber",
            rationale=["الرواية تتضمن ادعاء دخول أو سيطرة غير مصرح بها على حساب/نظام"],
            missing_elements=[
                "الحساب/النظام الذي تم الدخول إليه",
                "كيفية اكتشاف الدخول غير المصرح به",
                "سجلات الدخول والتنبيهات ورسائل تغيير كلمة المرور",
                "الأفعال التي حصلت داخل الحساب بعد الدخول",
            ],
            confidence=0.90,
            status="needs_clarification",
        ))

    if private_data:
        _add(items, LegalHypothesis(
            code="cyber.private_data_misuse",
            label_ar="استعمال/كشف محتوى أو بيانات خاصة يحتاج تحديد المصدر والاستخدام",
            domain="cyber",
            rationale=["الرواية تتضمن محتوى خاصاً أو بيانات شخصية ضمن سياق إلكتروني"],
            missing_elements=[
                "نوع البيانات/المحتوى ومصدره",
                "كيف حصل الطرف الآخر عليه؟",
                "هل تم نشره أو إرساله أم اقتصر الأمر على التهديد؟",
                "المنصات/الأشخاص الذين وصل إليهم المحتوى وأدلة ذلك",
            ],
            confidence=0.78,
            status="needs_clarification",
        ))

    # ------------------------------------------------------------------
    # Procedure: appeal deadline and service status
    # ------------------------------------------------------------------
    service = _has(
        text,
        "بلغوني الحكم", "تبليغ الحكم", "وصلني التبليغ", "ما تبلغت", "لم أتبلغ", "تبليغ باطل",
        "served with the judgment", "service of judgment", "not served", "invalid service",
    )
    deadline = _has(
        text,
        "مدة الاستئناف", "مهلة الاستئناف", "ميعاد الاستئناف", "مدة الطعن", "مهلة الطعن", "فاتت المدة",
        "appeal deadline", "time to appeal", "deadline passed", "late appeal",
    )

    if service:
        _add(items, LegalHypothesis(
            code="procedure.service_status",
            label_ar="حالة/صحة التبليغ مسألة إجرائية مؤثرة تحتاج التحقق",
            domain="procedure",
            rationale=["الرواية تثير حصول التبليغ أو إنكاره أو الاعتراض على صحته"],
            missing_elements=[
                "نوع الحكم/القرار والجهة التي أصدرته",
                "تاريخ وطريقة ومكان التبليغ المدعى به",
                "من استلم التبليغ وما الصفة المثبتة في ورقة التبليغ",
                "نسخة ورقة التبليغ أو بياناتها الرسمية",
            ],
            confidence=0.88,
            status="needs_clarification",
        ))

    if deadline:
        _add(items, LegalHypothesis(
            code="procedure.appeal_deadline_material",
            label_ar="ميعاد الطعن/الاستئناف مسألة حاسمة تتوقف على نوع الحكم وبداية المدة",
            domain="procedure",
            rationale=["الرواية تسأل عن مدة طعن أو تشير إلى احتمال فواتها"],
            missing_elements=[
                "نوع القضية والمحكمة ودرجة الحكم",
                "وصف الحكم: وجاهي/غيابي/بمثابة الوجاهي أو الوصف الإجرائي المقابل",
                "تاريخ الصدور وتاريخ التبليغ إن وجد",
                "النص الرسمي النافذ الذي يحدد المدة وبداية احتسابها",
            ],
            confidence=0.92,
            status="needs_clarification",
        ))

    return sorted(items, key=lambda hypothesis: hypothesis.confidence, reverse=True)


__all__ = ["spot_issues"]
