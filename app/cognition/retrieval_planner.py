from __future__ import annotations

from .models import CaseModel


def build_retrieval_queries(case: CaseModel) -> list[str]:
    queries: list[str] = []
    for h in case.hypotheses:
        if h.code == "criminal.intentional_homicide":
            queries.extend([
                "قانون العقوبات الأردني القتل القصد سبق الإصرار المواد والعقوبة",
                "قانون العقوبات الأردني القتل العمد الظروف المشددة",
            ])
        elif h.code == "criminal.unintentional_death":
            queries.extend([
                "قانون العقوبات الأردني التسبب بالوفاة الخطأ الإهمال الرعونة",
                "اجتهادات قضائية أردنية التسبب بالوفاة القصد والخطأ",
            ])
        elif h.code == "criminal.self_defense":
            queries.extend([
                "قانون العقوبات الأردني الدفاع الشرعي شروط الخطر الحال والتناسب",
            ])
        elif h.code == "criminal.theft":
            queries.extend([
                "قانون العقوبات الأردني السرقة أركان الجريمة",
                "قانون العقوبات الأردني السرقة كسر باب منزل ظرف مشدد",
            ])
        elif h.code == "criminal.aggravating_entry":
            queries.append("قانون العقوبات الأردني السرقة دخول منزل كسر قفل ليل مكان مسكون")
        elif h.code == "labor.termination":
            queries.extend([
                "قانون العمل الأردني إنهاء عقد غير محدد المدة الإشعار",
                "قانون العمل الأردني الفصل التعسفي التعويض مدة الخدمة",
            ])
        elif h.code == "procedure.appeal":
            queries.extend([
                "القانون الأردني مدة الاستئناف حسب نوع القضية والمحكمة وصف الحكم",
                "قانون أصول المحاكمات الأردني بدء ميعاد الطعن من الصدور أو التبليغ",
            ])
        elif h.code == "cyber.blackmail_threat":
            queries.extend([
                "قانون الجرائم الإلكترونية الأردني الابتزاز الإلكتروني التهديد بنشر معلومات أو صور",
                "قانون الجرائم الإلكترونية الأردني التهديد عبر الوسائل التقنية طلب منفعة أو مال",
            ])
        elif h.code == "cyber.account_intrusion":
            queries.append(
                "قانون الجرائم الإلكترونية الأردني الدخول غير المصرح به إلى نظام معلومات أو حساب"
            )
        elif h.code == "cyber.private_data_misuse":
            queries.append(
                "قانون الجرائم الإلكترونية الأردني إفشاء أو استخدام بيانات أو معلومات خاصة دون تصريح"
            )

    # Preserve order while removing duplicates.
    unique: list[str] = []
    seen: set[str] = set()
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique
