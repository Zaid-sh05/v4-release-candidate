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
if __name__=='__main__':main()
