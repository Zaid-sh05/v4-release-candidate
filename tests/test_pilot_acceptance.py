import re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.chat import handle_chat
from app.models import ChatRequest

EMOJI=re.compile('[\U0001F1E6-\U0001FAFF\u2600-\u27BF]+')

def ask(q:str):
    r=handle_chat(ChatRequest(message=q,language='ar'))
    assert not EMOJI.search(r.answer),r.answer
    return r

def main():
    r=ask('شو عقوبة الدائن اللي يطالب بدين وهمي بالإعسار؟')
    assert r.answer.startswith('العقوبة:'),r.answer
    assert '5000' in r.answer and ('ثلاث سنوات' in r.answer or '3 سنوات' in r.answer),r.answer
    assert '114' in r.answer,r.answer

    r=ask('كم مدة الاستئناف بالحكم الشرعي الغيابي؟')
    assert r.answer.startswith('المدة:'),r.answer
    assert ('30' in r.answer or 'ثلاثين' in r.answer or 'ثلاثون' in r.answer),r.answer
    assert 'تبليغ' in r.answer and '112' in r.answer,r.answer
    assert 'المحكمة العليا الشرعية' not in r.answer,r.answer

    r=ask('قطعت إشارة حمراء شو العقوبة؟')
    assert '6 نقاط' in r.answer,r.answer
    assert 'لن أضيف رقماً غير مثبت' in r.answer,r.answer
    assert r.route.primary_domain=='traffic',r.route

    # Regression: the definite article in "الإشارة الحمراء" used to make the
    # generic word "عقوبة" route this question into the criminal engine.
    r=ask('ما عقوبة قطع الإشارة الحمراء في الأردن؟')
    assert r.route.primary_domain=='traffic',r.route
    assert '6 نقاط' in r.answer,r.answer
    assert any('نظام النقاط المرورية' in s.title for s in r.sources),r.sources

    r=ask('شو عقوبة الزنا بالقانون الأردني؟')
    assert r.answer.startswith('العقوبة:'),r.answer
    assert '282' in r.answer and 'سنة إلى ثلاث سنوات' in r.answer,r.answer
    assert 'سنتين' in r.answer and 'بيت الزوجية' in r.answer,r.answer

    r=ask('شو عقوبة السرقة بالقانون الأردني؟')
    assert r.answer.startswith('العقوبة:'),r.answer
    assert '407' in r.answer and 'ستة أشهر إلى سنتين' in r.answer,r.answer
    assert 'ليست عقوبة موحّدة لكل أنواع السرقة' in r.answer,r.answer

    r=ask('ما عقوبة الابتزاز الإلكتروني؟')
    assert r.answer.startswith('العقوبة:'),r.answer
    assert '18' in r.answer and '3000' in r.answer and '6000' in r.answer,r.answer
    assert 'سنة' in r.answer and 'الأشغال المؤقتة' in r.answer,r.answer

    r=ask('كيف أقدم شكوى عند المدعي العام؟')
    assert r.answer.startswith('الإجراء:'),r.answer
    assert 'الادعاء العام' in r.answer and 'حضور' in r.answer and 'الاختصاص' in r.answer,r.answer
    assert r.route.primary_domain=='procedure' and 'criminal' in r.route.domains,r.route

    r=ask('كم رسوم استئناف قضية جزائية؟')
    assert r.answer.startswith('الرسوم:'),r.answer
    assert ('ديناران' in r.answer or re.search(r'\b2\b',r.answer)),r.answer
    assert r.route.intent=='fees' and 'criminal' in r.route.domains,r.route

    r=ask('بدي أستأنف حكم جزائي شو أعمل؟')
    assert r.answer.startswith('الإجراء:'),r.answer
    assert 'لائحة الاستئناف' in r.answer and ('قلم' in r.answer or 'كاتب' in r.answer),r.answer
    assert 'criminal' in r.route.domains,r.route

    r=ask('متى يصبح الحكم قطعياً؟')
    assert ('ما بقدر أجزم' in r.answer or 'لا أستطيع' in r.answer),r.answer

    r=ask('حكم تسوية الوساطة هل هو قطعي؟')
    assert r.answer.startswith('حالة الحكم:'),r.answer
    assert 'لا يخضع لأي طريق من طرق الطعن' in r.answer,r.answer

    r=ask('كم مدة الطعن بقرار الوزير بالمادة 31 من قانون العمل؟')
    assert ('10 أيام' in r.answer or '10 ايام' in r.answer),r.answer
    assert 'هذه مدة خاصة' in r.answer,r.answer

    r=ask('فصلني صاحب العمل بدون إنذار شو حقوقي؟')
    assert 'محدد المدة' in r.answer and 'غير محدد' in r.answer,r.answer
    assert 'بدل الإشعار' in r.answer and 'الفصل التعسفي' in r.answer,r.answer
    assert 'نصف شهر' in r.answer and 'شهرين' in r.answer,r.answer
    assert 'المادة 31' not in r.answer,r.answer
    assert '14 يوماً' not in r.answer and '48 ساعة' not in r.answer,r.answer

    r=ask('ما عقوبة القتل بالاردن؟')
    assert r.answer.startswith('العقوبة:'),r.answer
    assert '326' in r.answer and 'عشرين سنة' in r.answer,r.answer
    assert 'القتل القصد' in r.answer,r.answer

    r=ask('تعرضت لابتزاز على واتساب، شو أعمل؟')
    assert r.answer.startswith('الإجراء المقترح من المصادر الرسمية:'),r.answer
    assert '196' in r.answer and 'ecrimes@psd.gov.jo' in r.answer,r.answer
    assert 'عدم تحويل مبالغ' in r.answer or 'لا تدفع' in r.answer,r.answer
    assert r.route.primary_domain=='cyber',r.route

    r=ask('قانون العمل؟')
    assert r.route.intent=='law_overview',r.route
    assert r.answer.startswith('قانون العمل الأردني:'),r.answer
    assert 'رقم 8 لسنة 1996' in r.answer,r.answer
    assert 'English Search English' not in r.answer and 'يرجى الانتظار' not in r.answer,r.answer

    r=ask('كم مدة استئناف الحكم الجزائي؟')
    assert not r.answer.startswith('المدة:'),r.answer
    assert 'ليست رقماً واحداً' in r.answer and 'المحكمة' in r.answer,r.answer
    assert '1961' not in r.answer,r.answer

    r=ask('كم مدة استئناف الحكم المدني؟')
    assert 'civil' in r.route.domains,r.route
    assert not r.answer.startswith('المدة:'),r.answer
    assert 'صلح حقوق' in r.answer and 'بداية حقوق' in r.answer,r.answer

    print('pilot acceptance tests: OK')

if __name__=='__main__':main()

# V3.4 legal-depth regressions
from app.evaluator import evaluate_answer


def _v34_regressions():
    labor=handle_chat(ChatRequest(message='فصلني صاحب العمل بدون إنذار شو حقوقي؟',language='ar'))
    ans=labor.answer
    for needle in ('بدل الإشعار','الفصل التعسفي','نصف شهر','شهرين','محدد المدة'):
        assert needle in ans,(needle,ans)
    # Generic dismissal must not lead with the special Article 31 path.
    assert 'المادة 31' not in ans,ans
    ev=evaluate_answer('فصلني صاحب العمل بدون إنذار شو حقوقي؟',labor.route,ans,labor.sources)
    assert ev.passed,(ev,ans)

    notice=handle_chat(ChatRequest(message='صاحب العمل قال لا تداوم خلال شهر الإنذار، شو حقي؟',language='ar'))
    assert 'بدل الإشعار' in notice.answer,notice.answer

if __name__=='__main__':
    _v34_regressions()
