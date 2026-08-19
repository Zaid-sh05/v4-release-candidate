import sys,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.repository import repository

def main():
    assert repository.search('قانون السير',['traffic'])
    assert repository.search('قانون العمل',['labor'])
    assert repository.search('قانون الشركات',['commercial'])
    zina=repository.search('الزنا عقوبة',['criminal'])
    # If the exact offence text is not present in the official corpus, Qanoni must prefer no evidence over unrelated evidence.
    for s in zina:
        hay=s.title+' '+s.excerpt
        assert ('زنا' in hay) or ('قانون العقوبات رقم 16' in s.title),s.title
    # Display titles must not expose URL percent-encoding or UUID filenames.
    for q,d in [('ابتزاز واتساب','cyber'),('عقوبة','criminal')]:
        for s in repository.search(q,[d],8):
            assert '%D8' not in s.title and '%D9' not in s.title,s.title
            assert not re.fullmatch(r'[0-9a-f-]{30,}(?:\.pdf)?',s.title,re.I),s.title
    print('repository tests: OK',repository.stats())
if __name__=='__main__':main()
