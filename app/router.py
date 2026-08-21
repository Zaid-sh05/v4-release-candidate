from __future__ import annotations
from collections import defaultdict
from .models import RouteResult
from .text import normalize_ar, detect_language, extract_numbers

DOMAIN_LABELS = {
    'general': {'ar':'بحث قانوني عام','en':'General legal research'},
    'civil': {'ar':'القانون المدني','en':'Civil law'},
    'criminal': {'ar':'القانون الجزائي','en':'Criminal law'},
    'personal_status': {'ar':'الأحوال الشخصية والشرعي','en':'Personal status and Sharia'},
    'labor': {'ar':'قانون العمل','en':'Labor law'},
    'commercial': {'ar':'الشركات والقانون التجاري','en':'Companies and commercial law'},
    'procedure': {'ar':'أصول المحاكمات والإجراءات','en':'Court procedure'},
    'cyber': {'ar':'الجرائم الإلكترونية وحماية البيانات','en':'Cybercrime and data protection'},
    'traffic': {'ar':'قانون السير والمرور','en':'Traffic law'},
    'administrative': {'ar':'القانون الإداري','en':'Administrative law'},
    'real_estate': {'ar':'العقارات والملكية','en':'Real estate law'},
    'constitutional': {'ar':'القانون الدستوري','en':'Constitutional law'},
    'tax_finance': {'ar':'الضرائب والمال والتأمين','en':'Tax, finance and insurance'},
}

LEXICON = {
 'traffic': {
  'ar': ['قانون السير','مخالفة سير','اشارة حمراء','إشارة حمراء','رادار','سرعة زائدة','رخصة قيادة','رخصة سوق','سحب الرخصة','نقاط مرورية','حادث سير','دهس','تصادم','مركبة','سيارة','سائق','ترخيص مركبة'],
  'en': ['traffic law','traffic violation','red light','speeding','speed camera','driving licence','driving license','traffic points','road accident','vehicle','driver'],
 },
 'labor': {
  'ar': ['قانون العمل','صاحب العمل','عقد عمل','فصل من العمل','فصلني','طردني','استقالة','راتب','أجر','اجور','أجور','دوام','عمل اضافي','عمل إضافي','إجازة','عامل','موظف','إنهاء عقد العمل','انهاء عقد العمل','تعويض فصل','فصل تعسفي','إشعار إنهاء','اشعار انهاء'],
  'en': ['labor law','labour law','employer','employee','employment contract','fired','dismissed','termination','salary','wage','overtime','leave','resignation','wrongful dismissal'],
 },
 'personal_status': {
  'ar': ['الأحوال الشخصية','شرعي','شرعية','محكمة شرعية','استئناف شرعي','المحكمة العليا الشرعية','زواج','طلاق','خلع','نفقة','حضانة','مهر','ميراث','ارث','إرث','وصية','نسب','عدة','شقاق ونزاع'],
  'en': ['personal status','sharia court','sharia appeal','marriage','divorce','khula','maintenance','alimony','custody','dowry','inheritance','will','paternity'],
 },
 'criminal': {
  'ar': ['قانون العقوبات','جزائي','جزائية','جنائي','جنائية','محكمة جزائية','قضية جزائية','قضية جنائية','جريمة','جناية','جنحة','عقوبة','حبس','سجن','قتل','شروع بالقتل','سرقة','احتيال','تزوير','اعتداء','يعتدي علي','اعتداء جسدي','ضرب','تهديد','اغتصاب','هتك عرض','تحرش','زنا','الزنا','مخدرات','رشوة','اختلاس','خطف','اتجار بالبشر','سلاح','شكوى جزائية','مدعي عام','المدعي العام','نيابة عامة','النيابة العامة','ادعاء عام','الادعاء العام','عنف أسري','العنف الأسري','أمر حماية'],
  'en': ['penal code','criminal law','crime','felony','misdemeanor','penalty','prison','murder','attempted murder','theft','fraud','forgery','assault','rape','harassment','adultery','drugs','bribery','prosecution','public prosecutor','domestic violence','protection order'],
 },
 'cyber': {
  'ar': ['الجرائم الإلكترونية','جرائم الكترونية','ابتزاز إلكتروني','ابتزاز الكتروني','ابتزاز','ابتزني','ببتزني','يبتزني','تهكير','اختراق','حساب وهمي','واتساب','انستغرام','فيسبوك','تشهير إلكتروني','حماية البيانات','بيانات شخصية','خصوصية','المعاملات الإلكترونية','التوقيع الإلكتروني','عقد إلكتروني'],
  'en': ['cybercrime','electronic crimes','online blackmail','online extortion','hacking','social media','whatsapp','instagram','facebook','data protection','personal data','privacy','electronic transactions','electronic signature','e-contract'],
 },
 'commercial': {
  'ar': ['قانون الشركات','شركة','شركات','سجل تجاري','مسؤولية محدودة','شركة مساهمة','مساهم','اعسار','إعسار','دائن','مدين','دين وهمي','ديون وهمية','إعادة التنظيم','استثمار','تاجر','شيك','شيك بدون رصيد','كمبيالة','اندماج شركة','اتفاق احتكاري','تحديد الأسعار','منع المنافسة','هيئة المنافسة','ممارسات احتكارية','قانون المنافسة'],
  'en': ['companies law','company','companies','commercial register','limited liability','llc','shareholder','insolvency','creditor','debtor','investment','merchant','cheque','check','antitrust','price fixing','competition law','monopoly practices'],
 },
 'civil': {
  'ar': ['القانون المدني','قانون مدني','حكم مدني','الحكم المدني','قضية مدنية','دعوى مدنية','قضية حقوقية','دعوى حقوقية','عقد','تعويض','دين','قرض','إيجار','ايجار','مستأجر','مستاجر','مالك','بيع','شراء','وكالة','كفالة','التزام','ضرر','مطالبة مالية','حقوق المؤلف','الملكية الفكرية','حقوق النشر','نسخ التصميم','سرقة أدبية','عيب مصنعي','استبدال المنتج','ضمان المنتج','حماية المستهلك'],
  'en': ['civil code','civil law','contract','compensation','debt','loan','lease','rent','tenant','landlord','sale','agency','guarantee','damages','copyright','intellectual property','plagiarism','manufacturing defect','consumer protection'],
 },
 'procedure': {
  'ar': ['أصول المحاكمات','اصول المحاكمات','استئناف','استأنف','استانف','استاناف','تمييز','طعن','نقض','فسخ الحكم','إعادة المحاكمة','اعادة المحاكمة','دعوى','تبليغ','تبليغ الحكم','تنفيذ حكم','تنفيذ الحكم','إجراءات التنفيذ','دائرة التنفيذ','حجز','بينة','إثبات','سند خطي','إثبات الدين','قانون البينات','اختصاص المحكمة','مهلة الطعن','ميعاد الطعن','مدة الاستئناف','ميعاد الاستئناف','الحكم القطعي','حكم قطعي','حكم وجاهي','حكم غيابي','وجاهي اعتباري','لائحة الاستئناف','رسوم الاستئناف','وساطة','تسوية قضائية','اتفاقية تسوية','بند التحكيم','هيئة تحكيم','إجراءات التحكيم','مركز التحكيم','التحكيم التجاري'],
  'en': ['civil procedure','criminal procedure','appeal','cassation','review','lawsuit','service of process','judgment service','enforcement','attachment','evidence','jurisdiction','appeal deadline','final judgment','default judgment','arbitration clause','arbitration tribunal','arbitration proceedings','commercial arbitration','execution proceedings','evidence law'],
 },
 'administrative': {
  'ar': ['القضاء الإداري','قرار إداري','موظف حكومي','وظيفة عامة','بلدية','أمانة عمان','رخصة مهن','عطاء حكومي','إدارة قضايا الدولة','تأسيس جمعية','جمعية خيرية','تسجيل جمعية','سجل الجمعيات','مجلس إدارة الجمعية','جمعية غير ربحية'],
  'en': ['administrative law','administrative court','administrative decision','government employee','public service','municipality','public tender','establish an association','nonprofit association','register an association'],
 },
 'real_estate': {
  'ar': ['الملكية العقارية','عقار','أرض','ارض','طابو','دائرة الأراضي','سند تسجيل','إفراز','رهن عقاري','شقة'],
  'en': ['real estate','property law','land','title deed','land department','parcel','mortgage','apartment'],
 },
 'constitutional': {
  'ar': ['الدستور الأردني','الدستور','المحكمة الدستورية','حق دستوري','مجلس النواب','مجلس الأعيان'],
  'en': ['jordanian constitution','constitution','constitutional court','constitutional right','parliament','senate'],
 },
 'tax_finance': {
  'ar': ['ضريبة الدخل','ضريبة المبيعات','جمارك','الرسوم الجمركية','رسوم جمركية','تخليص جمركي','دائرة الجمارك','استيراد سيارة','ضمان اجتماعي','تأمين','بوليصة تأمين','شركة تأمين','مطالبة تأمين','تعويض تأميني','بنك','قرض بنكي','البنك المركزي','فتح حساب بنكي','حساب جاري','الأوراق المالية','بورصة عمان','البورصة الأردنية','البورصة','طرح أسهم','اكتتاب عام','هيئة الأوراق المالية','غسل الأموال','تمويل الإرهاب','عملية مالية مشبوهة','شركة صرافة','شرائح ضريبة الدخل','أصول افتراضية'],
  'en': ['income tax','sales tax','customs','customs duty','customs clearance','social security','insurance','insurance policy','insurance claim','banking','bank loan','central bank','bank account','securities law','stock exchange','ipo','money laundering','suspicious transaction','income tax bracket','virtual assets'],
 },
}

SMALLTALK_AR = ['مرحبا','مرحباً','اهلا','أهلا','هلا','السلام عليكم','صباح الخير','مساء الخير','كيفك','شو اخبارك','مين انت','عرفني عن حالك','شو بتقدر تعمل','ساعدني','شكرا','شكراً','يسلمو','تمام','اوكي','أوكي']
SMALLTALK_EN = ['hi','hello','hey','good morning','good evening','how are you','who are you','what can you do','help me','thanks','thank you','okay','ok']

# Order matters only on ties. Specific intents have intentionally richer vocabularies.
INTENTS = {
 'penalty': ['شو العقوبة','ما العقوبة','عقوبة','عقوبه','غرامة','غرامه','حبس','سجن','كم الغرامة','penalty','fine','punishment','sentence'],
 'deadline': ['كم مدة','قديش المدة','كم يوم','خلال كم','مدة الاستئناف','مهلة الاستئناف','ميعاد الاستئناف','مدة الطعن','مهلة الطعن','ميعاد الطعن','متى ينتهي','deadline','time limit','how many days','how long to appeal'],
 'appeal': ['استئناف','استأنف','استانف','استاناف','تمييز','طعن','نقض','فسخ الحكم','اعادة المحاكمة','إعادة المحاكمة','appeal','cassation','challenge judgment'],
 'judgment': ['الحكم القطعي','حكم قطعي','متى يصبح الحكم','هل الحكم قطعي','هل هو قطعي','حكم قطعي','حكم وجاهي','حكم غيابي','وجاهي اعتباري','صدر الحكم','تبليغ الحكم','final judgment','default judgment','judgment final'],
 'complaint': ['كيف اشتكي','كيف أشتكي','تقديم شكوى','شكوى جزائية','مدعي عام','المدعي العام','نيابة عامة','النيابة العامة','ادعاء عام','الادعاء العام','file a complaint','public prosecutor'],
 'enforcement': ['تنفيذ الحكم','كيف انفذ الحكم','كيف أنفذ الحكم','دائرة التنفيذ','حجز اموال','حجز أموال','منع سفر','enforce judgment','execution department'],
 'fees': ['كم الرسوم','شو الرسوم','رسوم الاستئناف','رسوم الدعوى','كم بدفع','fees','filing fee','court fees'],
 'procedure': ['كيف اقدم','كيف أقدم','إجراءات','اجراءات','شو اعمل','شو أعمل','دعوى','تبليغ','procedure','how do i','file'],
 'rights': ['حقوقي','حقي','شو الي','شو إلي','استحق','تعويض','راتبي','اجازتي','إجازتي','my rights','entitled','compensation'],
 'law_overview': ['قانون العمل','قانون السير','قانون العقوبات','القانون المدني','قانون الشركات','قانون الاحوال الشخصية','قانون الأحوال الشخصية','قانون الجرائم الالكترونية','قانون الجرائم الإلكترونية','labor law','traffic law','penal code','civil code','companies law','cybercrime law'],
 'law_lookup': ['المادة','مادة','قانون رقم','نص القانون','article','law number','legal text'],
 'contract_review': ['راجع العقد','مراجعة عقد','بند العقد','هذا العقد','review contract','contract clause'],
}


def _phrase_weight(phrase: str) -> float:
    words=phrase.split()
    return 1.0 + min(2.6,(len(words)-1)*0.55 + len(phrase)/70)


def _strip_ar_clitic(token: str) -> str:
    """Normalize common Arabic clitics for routing-only phrase matching.

    This intentionally does not alter the stored query. It only makes phrases such as
    "إشارة حمراء" match user wording such as "الإشارة الحمراء" or
    "وبالإشارة الحمراء".
    """
    t=(token or '').strip('؟?!.,،؛:()[]{}\"\'')
    if len(t) <= 2:
        return t
    # Combined prefixes first. Keep the stem conservative to avoid over-stripping.
    for prefix in ('وال','فال','بال','كال'):
        if t.startswith(prefix) and len(t) > len(prefix)+2:
            t=t[len(prefix):]
            break
    else:
        if t.startswith('و') and len(t)>4:
            t=t[1:]
        elif t.startswith('ف') and len(t)>4:
            t=t[1:]
    if t.startswith('ال') and len(t)>4:
        t=t[2:]
    return t


_AR_POSSESSIVE_SUFFIXES = ('ي', 'ه', 'ها', 'هم', 'هن', 'كم', 'كن', 'نا', 'ك')


def _token_matches_single_word_phrase(token: str, phrase: str) -> bool:
    """Match a single-word lexicon phrase against a token, tolerating an attached possessive
    suffix ("راتبي" for "راتب") without falling back to unanchored substring containment
    (which would also match unrelated words like "مستأجر" for "اجر")."""
    if token == phrase:
        return True
    return any(token == phrase + suffix for suffix in _AR_POSSESSIVE_SUFFIXES)


def _phrase_in_text(normalized_text: str, phrase: str, lang: str) -> bool:
    p=normalize_ar(phrase) if lang=='ar' else phrase.lower()
    if not p:
        return False
    if lang!='ar':
        return p in normalized_text
    # Only take the raw-substring shortcut for multi-word phrases (already anchored by the
    # surrounding spaces). A single short Arabic root (e.g. "اجر" wage) is otherwise a substring
    # of many unrelated longer words (e.g. "مستأجر" tenant, "الدين" religion vs "دين" debt), so
    # single-word phrases must go through the whole-token comparison below instead.
    if ' ' in p and p in normalized_text:
        return True
    text_tokens=[_strip_ar_clitic(x) for x in normalized_text.split()]
    phrase_tokens=[_strip_ar_clitic(x) for x in p.split()]
    if not phrase_tokens or len(phrase_tokens)>len(text_tokens):
        return False
    width=len(phrase_tokens)
    if width==1:
        return any(_token_matches_single_word_phrase(t, phrase_tokens[0]) for t in text_tokens)
    return any(text_tokens[i:i+width]==phrase_tokens for i in range(len(text_tokens)-width+1))


# Terms such as "عقوبة" describe the requested answer type, not the legal domain.
# They get a small routing weight so a specific subject (traffic, labor, cyber, etc.) wins.
GENERIC_DOMAIN_TERMS = {
    'criminal': {
        normalize_ar('عقوبة'), normalize_ar('حبس'), normalize_ar('سجن'),
        'penalty', 'prison',
    },
}


def _intent_score(n: str, term: str, lang: str) -> float:
    p=normalize_ar(term) if lang=='ar' else term.lower()
    if p not in n: return 0.0
    return _phrase_weight(p) + (1.0 if len(p.split())>1 else 0)


def _contains_any(normalized: str, phrases: list[str], lang: str) -> bool:
    return any(_phrase_in_text(normalized, phrase, lang) for phrase in phrases)


def analyze_query(text: str, requested_language: str='auto', force_domain: str|None=None) -> RouteResult:
    lang=detect_language(text) if requested_language=='auto' else requested_language
    normalized=normalize_ar(text) if lang=='ar' else ' '.join((text or '').lower().split())
    articles,laws,years=extract_numbers(text)

    scores=defaultdict(float); matched:dict[str,list[str]]=defaultdict(list)
    for domain,languages in LEXICON.items():
        seen=set()
        for phrase in languages[lang]:
            p=normalize_ar(phrase) if lang=='ar' else phrase.lower()
            if not p or p in seen: continue
            seen.add(p)
            if _phrase_in_text(normalized, phrase, lang):
                weight=_phrase_weight(p)
                if p in GENERIC_DOMAIN_TERMS.get(domain,set()):
                    weight*=0.22
                scores[domain]+=weight; matched[domain].append(phrase)

    legal_score=sum(scores.values())
    smalltalk_terms=SMALLTALK_AR if lang=='ar' else SMALLTALK_EN
    smalltalk_hit=any((normalize_ar(x) if lang=='ar' else x.lower()) in normalized for x in smalltalk_terms)
    if not force_domain and smalltalk_hit and legal_score<0.9:
        return RouteResult(language=lang,intent='smalltalk',primary_domain='conversation',domains=['conversation'],confidence=1.0,matched_terms=[],article_numbers=articles,law_numbers=laws,years=years,normalized_text=normalized)

    if force_domain and force_domain in DOMAIN_LABELS:
        primary=force_domain; domains=[force_domain]; confidence=1.0
    elif scores:
        ranked=sorted(scores.items(),key=lambda x:x[1],reverse=True)
        primary,best=ranked[0]; domains=[primary]
        for d,s in ranked[1:]:
            if s>=max(1.15,best*0.52): domains.append(d)
        confidence=min(0.98,0.48+(best/(best+3.0))*0.5)
    else:
        primary='general'; domains=['general']; confidence=0.32

    n=normalized
    def add(d:str):
        if d not in domains: domains.append(d)

    # High-signal subject overrides. Generic words such as "penalty" must never
    # pull a clearly traffic/cyber/labor question into the criminal MCP.
    red_light_hit=_contains_any(n,['اشارة حمراء','إشارة حمراء','الاشارة الحمراء','الإشارة الحمراء','تجاوز الاشارة الضوئية الحمراء','قطع الاشارة الحمراء','red light'],lang)
    traffic_signal=red_light_hit or _contains_any(n,['مخالفة سير','رادار','سرعة زائدة','نقاط مرورية','رخصة قيادة','رخصة سوق','سحب الرخصة','traffic violation','speeding','traffic points'],lang)
    if traffic_signal:
        primary='traffic'; domains=['traffic']; confidence=max(confidence,0.92)
    elif _contains_any(n,['ابتزاز إلكتروني','ابتزاز الكتروني','جرائم الكترونية','الجرائم الإلكترونية','تهكير','اختراق','cybercrime','online blackmail','online extortion'],lang):
        primary='cyber'; domains=['cyber']; confidence=max(confidence,0.9)
    elif _contains_any(n,['فصلني','طردني','فصل تعسفي','صاحب العمل','عقد عمل','employment contract','wrongful dismissal','employer'],lang):
        primary='labor'; domains=['labor']; confidence=max(confidence,0.9)

    appeal_hit=_contains_any(n,['استئناف','استأنف','استانف','استاناف','تمييز','طعن','نقض','appeal','cassation'],lang)
    if appeal_hit:
        substantive=[(d,s) for d,s in scores.items() if d!='procedure' and s>0]
        previous=primary if primary!='procedure' else None
        primary='procedure'; domains=['procedure']
        if previous: add(previous)
        if substantive: add(max(substantive,key=lambda x:x[1])[0])
        if _contains_any(n,['سرقة','سرقه','قتل','احتيال','تزوير','اعتداء','ضرب','اغتصاب','زنا','جريمة','جريمه','جناية','جنايه','جنحة','جنحه','theft','murder','fraud','forgery','assault','rape','adultery','crime'],lang): add('criminal')
        if _contains_any(n,['شرعي','شرعية','احوال شخصية','أحوال شخصية','طلاق','نفقه','نفقة','حضانة','sharia','divorce','custody'],lang): add('personal_status')

    if _contains_any(n,['زنا','adultery'],lang) and _contains_any(n,['طلاق','زواج','زوج','divorce','marriage'],lang): add('personal_status')
    if _contains_any(n,['ابتزاز','ابتزني','ببتزني','يبتزني','blackmail','extortion'],lang) and primary=='cyber': add('criminal')
    if primary=='traffic' and _contains_any(n,['تعويض','اصابة','إصابة','وفاة','وفاه','compensation','injury','death'],lang): add('civil')
    if primary in {'criminal','civil','personal_status','labor'} and appeal_hit: add('procedure')

    # Deadline questions are procedural even if the underlying subject was the only lexical hit.
    time_question=_contains_any(n,['كم يوم','قديش','كم مدة','كم مده','خلال كم','مهلة','مهله','ميعاد','deadline','time limit','how many days','how long'],lang)
    if time_question and _contains_any(n,['استئناف','طعن','تمييز','تبليغ','حكم','appeal','judgment','cassation'],lang):
        if primary!='procedure':
            previous=primary; primary='procedure'; domains=['procedure',previous]
        else: add('procedure')

    intent='legal_question'; best_name=None; best_score=0.0
    for name,terms in INTENTS.items():
        score=sum(_intent_score(n,t,lang) for t in terms)
        if score>best_score:
            best_name=name; best_score=score
    if best_name: intent=best_name

    # A short request naming a law is an overview request, not a request to dump the
    # raw scraped law-list page. Detailed questions still use their more specific intent.
    short_tokens=[x for x in n.split() if x]
    law_names=['قانون العمل','قانون السير','قانون العقوبات','القانون المدني','قانون الشركات','قانون الاحوال الشخصية','قانون الأحوال الشخصية','قانون الجرائم الالكترونية','قانون الجرائم الإلكترونية',
               'labor law','traffic law','penal code','civil code','companies law','cybercrime law']
    if len(short_tokens) <= 6 and _contains_any(n,law_names,lang) and not any(_contains_any(n,INTENTS[k],lang) for k in ('penalty','deadline','fees','complaint','rights','judgment')):
        intent='law_overview'

    # Time questions override a generic appeal hit.
    if time_question and appeal_hit: intent='deadline'
    # Penalty question should remain penalty even if it mentions a court sentence.
    if _contains_any(n,['شو العقوبة','ما العقوبة','كم الغرامة','penalty','fine'],lang) and _contains_any(n,['عقوبة','غرامة','penalty','fine'],lang): intent='penalty'

    # High-signal procedural intents override broader lexical hits.
    fee_hit=_contains_any(n,['رسوم','كم بدفع','شو الرسوم','كم الرسوم','fee','fees','filing fee','court fees'],lang)
    complaint_hit=_contains_any(n,['كيف اشتكي','كيف أشتكي','تقديم شكوى','شكوى','مدعي عام','المدعي العام','نيابة عامة','النيابة العامة','ادعاء عام','الادعاء العام','complaint','public prosecutor','prosecutor'],lang)
    criminal_case_hit=_contains_any(n,['جزائي','جزائية','جنائي','جنائية','قضية جزائية','قضية جنائية','criminal case'],lang)
    if fee_hit:
        intent='fees'
    if complaint_hit:
        intent='complaint'
        previous=primary if primary!='procedure' else None
        primary='procedure'; domains=['procedure']
        if previous and previous!='general': add(previous)
        add('criminal')
    elif criminal_case_hit and (appeal_hit or fee_hit or intent in {'procedure','appeal','deadline','fees'}):
        previous=primary if primary not in {'procedure','general'} else None
        primary='procedure'; domains=['procedure']
        if previous: add(previous)
        add('criminal')

    terms=[]
    for d in domains: terms.extend(matched.get(d,[]))
    return RouteResult(language=lang,intent=intent,primary_domain=primary,domains=domains[:4],confidence=round(confidence,2),matched_terms=list(dict.fromkeys(terms))[:12],article_numbers=articles,law_numbers=laws,years=years,normalized_text=normalized)
