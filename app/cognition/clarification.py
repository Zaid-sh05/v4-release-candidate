from __future__ import annotations

from .models import CaseModel, ClarifyingQuestion


QUESTION_BANK = {
    "criminal.intentional_homicide": [
        ClarifyingQuestion("homicide_intent", "هل كان الفاعل يقصد قتل الشخص، أم كان يقصد فعلاً آخر وحدثت الوفاة؟", "القصد يغيّر التكييف القانوني جذرياً.", ["criminal.intentional_homicide", "criminal.unintentional_death"], 100),
        ClarifyingQuestion("homicide_premeditation", "هل كان هناك تخطيط مسبق أو انتظار أو تحضير قبل الواقعة؟", "سبق الإصرار أو التحضير قد يغيّر الوصف والعقوبة.", ["criminal.intentional_homicide"], 90),
        ClarifyingQuestion("homicide_mechanism", "كيف حدثت الوفاة تحديداً، وما الأداة أو الفعل الذي أدى إليها؟", "طريقة الفعل مهمة لربط النتيجة بالفعل وتقييم القصد.", ["criminal.intentional_homicide", "criminal.unintentional_death"], 85),
    ],
    "criminal.unintentional_death": [
        ClarifyingQuestion("death_negligence", "هل حصل إهمال أو سرعة أو رعونة أو مخالفة تعليمات قبل الوفاة؟", "التسبب غير المقصود يحتاج فهم السلوك الذي سبق النتيجة.", ["criminal.unintentional_death"], 95),
    ],
    "criminal.self_defense": [
        ClarifyingQuestion("defense_immediacy", "وقت استعمال القوة، هل كان الاعتداء أو الخطر ما زال قائماً فعلاً؟", "استمرار الخطر من الوقائع الجوهرية في تقييم الدفاع الشرعي.", ["criminal.self_defense"], 100),
        ClarifyingQuestion("defense_proportionality", "شو كان نوع الاعتداء، وشو القوة اللي استُعملت للرد عليه؟", "لازم نعرف طبيعة الاعتداء والرد قبل تقييم التناسب.", ["criminal.self_defense"], 90),
    ],
    "criminal.theft": [
        ClarifyingQuestion("theft_consent", "هل أخذ الشيء بدون إذن صاحبه وبقصد الاحتفاظ فيه أو التصرف فيه؟", "الرضا والقصد من الوقائع الأساسية في توصيف الاستيلاء.", ["criminal.theft"], 95),
        ClarifyingQuestion("theft_place_time", "وين ومتى صار الأخذ؟ وهل كان المكان بيتاً مسكوناً أو محلاً مغلقاً؟", "المكان والوقت وطريقة الدخول قد تؤثر في الوصف القانوني.", ["criminal.theft", "criminal.aggravating_entry"], 80),
    ],
    "criminal.aggravating_entry": [
        ClarifyingQuestion("entry_permission", "هل دخل الشخص بدون إذن، وهل كسر باب أو قفل أو استعمل طريقة غير عادية للدخول؟", "طريقة الدخول قد تكون ظرفاً مؤثراً.", ["criminal.aggravating_entry", "criminal.theft"], 90),
    ],
    "labor.termination": [
        ClarifyingQuestion("labor_contract", "عقدك محدد المدة ولا غير محدد المدة؟", "نوع العقد يغير حقوق الإنهاء.", ["labor.termination"], 100),
        ClarifyingQuestion("labor_service", "كم مدة خدمتك عند صاحب العمل؟", "مدة الخدمة تدخل في بعض الاستحقاقات والحسابات.", ["labor.termination"], 90),
        ClarifyingQuestion("labor_reason", "شو السبب اللي ذكره صاحب العمل للفصل؟", "سبب الإنهاء لازم يُفحص قبل وصف الفصل.", ["labor.termination"], 95),
        ClarifyingQuestion("labor_notice", "هل استلمت إشعار إنهاء خطي؟ وإذا نعم، متى؟", "الإشعار وتاريخه يؤثران في بدل الإشعار والمدة.", ["labor.termination"], 88),
    ],
    "procedure.appeal": [
        ClarifyingQuestion("appeal_case_type", "القضية حقوقية/مدنية، جزائية، شرعية، إدارية، ولا تنفيذ؟", "مدة وطريق الطعن تختلف حسب نوع القضية.", ["procedure.appeal"], 100),
        ClarifyingQuestion("appeal_court", "أي محكمة أصدرت الحكم أو القرار؟", "المحكمة التي أصدرت القرار تحدد جهة الطعن غالباً.", ["procedure.appeal"], 95),
        ClarifyingQuestion("appeal_presence", "الحكم كان وجاهي، غيابي، ولا بمثابة الوجاهي؟", "بداية حساب المدة قد تختلف بحسب وصف الحكم.", ["procedure.appeal"], 92),
        ClarifyingQuestion("appeal_date", "متى صدر الحكم، ومتى تم تبليغك فيه إن حصل تبليغ؟", "لا يمكن حساب آخر يوم للطعن بدون التاريخ الصحيح.", ["procedure.appeal"], 98),
    ],
}


def choose_questions(case: CaseModel, limit: int = 3) -> list[ClarifyingQuestion]:
    seen: set[str] = set()
    out: list[ClarifyingQuestion] = []
    for hypothesis in case.hypotheses:
        for question in QUESTION_BANK.get(hypothesis.code, []):
            if question.id in seen:
                continue
            seen.add(question.id)
            out.append(question)
    out.sort(key=lambda q: q.priority, reverse=True)
    return out[:limit]
