import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.router import analyze_query

def check(text,primary=None,intent=None,contains=None):
    r=analyze_query(text)
    if primary: assert r.primary_domain==primary,(text,r)
    if intent: assert r.intent==intent,(text,r)
    if contains:
        for d in contains: assert d in r.domains,(text,r)

def main():
    check('مرحبا',primary='conversation',intent='smalltalk')
    check('مرحبا فصلني صاحب العمل بدون إنذار',primary='labor')
    check('قطعت إشارة حمراء شو العقوبة',primary='traffic',intent='penalty')
    check('فصلني صاحب العمل بدون إنذار شو حقوقي',primary='labor',intent='rights')
    check('شو عقوبة الزنا بالقانون الأردني',primary='criminal',intent='penalty')
    check('الزنا شو أثره على الطلاق',primary='criminal',contains=['personal_status'])
    check('واحد ببتزني على واتساب',primary='cyber',contains=['criminal'])
    check('بدي أستأنف حكم بقضية سرقة',primary='procedure',contains=['criminal'])
    check('كم مدة الاستئناف بالحكم الشرعي الغيابي؟',primary='procedure',intent='deadline',contains=['personal_status'])
    check('كيف أقدم شكوى عند المدعي العام؟',primary='procedure',intent='complaint',contains=['criminal'])
    check('كم رسوم استئناف قضية جزائية؟',primary='procedure',intent='fees',contains=['criminal'])
    check('بدي أستأنف حكم جزائي شو أعمل؟',primary='procedure',contains=['criminal'])
    check('I was fired without notice',primary='labor')
    check('What is the penalty for adultery?',primary='criminal')
    print('router tests: OK')


def test_single_word_lexicon_terms_do_not_match_inside_unrelated_words():
    # "اجر" (wage, labor) is a substring of "مستأجر" (tenant) and "الإيجار" (rent), both civil
    # vocabulary; plain unanchored substring matching misrouted rent disputes to labor.
    check('المستأجر ما دفع الإيجار من ثلاثة أشهر شو حقوقي كمالك', primary='civil')
    # "اجر" is also a substring of "الإجرام" (crime); must not pull labor sources into a
    # criminal-domain question either.
    check('اتهموه بالإجرام المنظم وسرقة السيارات', primary='criminal')


def test_single_word_lexicon_terms_still_match_with_attached_possessive_suffix():
    # Guards against over-correcting the fix above: Arabic attaches possessive suffixes
    # directly to nouns ("راتبي" = "my salary"), which must still match the bare lexicon term.
    check('ما راتبي وأجوري لهذا الشهر لم تصلني', primary='labor')


if __name__=='__main__':main()
