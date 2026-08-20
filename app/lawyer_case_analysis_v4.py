from __future__ import annotations

# Extend the stable lawyer-analysis presenter without duplicating it. These mappings only change
# how already-grounded cognition is explained to the user; they do not create legal conclusions.
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

# The base module imports this dictionary from case_analysis, so updating it here also improves the
# material-facts section for English output.
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


def generate_lawyer_case_analysis_answer(message, route, case, sources):
    return base.generate_lawyer_case_analysis_answer(message, route, case, sources)


__all__ = ["generate_lawyer_case_analysis_answer"]
